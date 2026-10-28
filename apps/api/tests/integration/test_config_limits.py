"""隔离schema验证范围唯一来源、迁移、任务默认值与持久轮询预算；不调用外部服务。"""

import asyncio
import os
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from test_knowledge_flow import add_source
from test_llm_management import env as env
from test_llm_management import model, provider

from tender.api.analysis import routes as analysis_api
from tender.api.configuration import routes as config
from tender.api.documents import parsing
from tender.api.knowledge import routes as knowledge
from tender.api.llm import routes as llm
from tender.api.projects import files as project_files
from tender.api.projects import routes as projects
from tender.api.shared.errors import ApiProblem
from tender.application.analysis.research import AgentLimits, ResearchSession
from tender.application.knowledge.retrieval import retrieve_chunks
from tender.application.llm.profiles import FEATURE_FIELDS, MODEL_FIELDS
from tender.config.registry import ConfigRegistry
from tender.core.di import create_document_pipeline_repository
from tender.domain.shared.errors import ParseUnavailable
from tender.ports.documents.parser import ParseJobStatus, ParseProgress
from tender.worker.documents import tasks

pytestmark = pytest.mark.skipif(os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库")


@pytest.fixture
def runtime(env, monkeypatch):
    request, connection = env
    request.headers = {}
    components = request.app.state.components
    components.configs = ConfigRegistry(components.engine)
    components.blobs = SimpleNamespace(put=lambda *args, **kwargs: None)
    monkeypatch.setattr(
        tasks, "_repository", create_document_pipeline_repository(components.engine)
    )
    monkeypatch.setattr(tasks._locks, "lock", lambda *args, **kwargs: nullcontext(True))
    monkeypatch.setattr(tasks, "_store", lambda: SimpleNamespace(close=lambda: None))
    project = projects.create_project(projects.ProjectCreate(name="配置生效验证"), request)
    return request, connection, project["id"]


def release(request, values):
    return config.create_release(config.ReleaseCreate(values=values), request)


def test_numeric_rules_drive_api_metadata_and_database_limits(runtime):
    request, connection, _ = runtime
    release(request, {"analysis.context_tokens": 1, "analysis.max_model_calls": 1000000})
    entries = {entry["key"]: entry for entry in config.list_items(request)["items"]}
    assert entries["analysis.max_model_calls"]["minimum"] == 1
    assert "maximum" not in entries["analysis.max_model_calls"]
    assert entries["preprocess.denoise"]["writable"] is False
    with pytest.raises(ApiProblem):
        release(request, {"preprocess.denoise": False})
    with pytest.raises(ApiProblem):
        release(request, {"job.poll.max_interval_ms": 1})
    p = provider(request)
    m = model(request, p["id"], extra_retries=99, max_tokens=262144, timeout_seconds=1200.5)
    assert m["extra_retries"] == 99
    feature = llm.update_feature("analysis", llm.FeaturePatch(
        revision=1, failover_limit=10, max_total_requests=1000, deadline_seconds=172800,
    ), request)
    assert feature["max_total_requests"] == 1000
    assert feature["deadline_seconds"] == 172800
    settings = llm.llm_settings()
    assert settings["model_fields"] == MODEL_FIELDS
    assert settings["feature_fields"] == FEATURE_FIELDS
    assert connection.execute(text(
        "SELECT default_value FROM config_item WHERE key='analysis.max_evidence_blocks'"
    )).scalar_one() == 160


def test_retrieval_config_metadata_bounds_and_migration_seed(runtime):
    request, connection, _ = runtime
    entries = {entry["key"]: entry for entry in config.list_items(request)["items"]}
    threshold = entries["analysis.similarity_threshold"]
    maximum = entries["analysis.max_search_results"]
    assert threshold["value"] == threshold["default"] == 0.6
    assert threshold["minimum"] == 0 and threshold["maximum"] == 1 and threshold["writable"]
    assert maximum["value"] == maximum["default"] == 6 and maximum["minimum"] == 1
    seeded = dict(connection.execute(text("""SELECT key, default_value FROM config_item
        WHERE key IN ('analysis.similarity_threshold','analysis.max_search_results')""")).all())
    assert seeded == {
        "analysis.similarity_threshold": 0.6, "analysis.max_search_results": 6,
    }
    for patch in ({"analysis.similarity_threshold": 1.01},
                  {"analysis.similarity_threshold": -0.1}, {"analysis.max_search_results": 0}):
        with pytest.raises(ApiProblem):
            release(request, patch)


def test_finish_correction_config_is_editable_seeded_and_frozen_for_new_reports(runtime):
    request, connection, pid = runtime
    entry = next(item for item in config.list_items(request)["items"]
                 if item["key"] == "analysis.max_finish_corrections")
    assert entry["value"] == entry["default"] == 2 and entry["minimum"] == 1
    assert entry["writable"] and "maximum" not in entry
    assert connection.execute(text("""SELECT default_value FROM config_item
        WHERE key='analysis.max_finish_corrections'""")).scalar_one() == 2
    with pytest.raises(ApiProblem):
        release(request, {"analysis.max_finish_corrections": 0})
    release(request, {"analysis.max_finish_corrections": 5})
    add_source(connection, pid, "质保三年")
    analysis_api.save_settings(pid, analysis_api.AnalysisSettings(category="goods"), request)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    frozen = connection.execute(text("SELECT runtime_settings FROM analysis_report WHERE id=:id"),
                                {"id": report["id"]}).scalar_one()
    assert frozen["max_finish_corrections"] == 5
    release(request, {"analysis.max_finish_corrections": 8})
    assert connection.execute(text("SELECT runtime_settings FROM analysis_report WHERE id=:id"),
                              {"id": report["id"]}).scalar_one()["max_finish_corrections"] == 5


def test_saved_retrieval_config_freezes_report_and_filters_real_document_chunks(runtime):
    request, connection, pid = runtime
    for content in ["alpha beta gamma"] * 8 + ["alpha", "无关内容"]:
        add_source(connection, pid, content)
    release(request, {"analysis.similarity_threshold": 0.8, "analysis.max_search_results": 3})
    analysis_api.save_settings(pid, analysis_api.AnalysisSettings(category="goods"), request)
    report = analysis_api.start_analysis(pid, analysis_api.AnalysisInput(), request)
    frozen = connection.execute(text("SELECT runtime_settings FROM analysis_report WHERE id=:id"),
                                {"id": report["id"]}).scalar_one()
    assert frozen["similarity_threshold"] == 0.8 and frozen["max_search_results"] == 3
    # 发布后改配置不能改变已有报告的检索口径；真实仓储仍按该报告冻结参数检索。
    release(request, {"analysis.similarity_threshold": 0.2, "analysis.max_search_results": 20})
    db = knowledge.store(request)
    sources = db.sources(db.collections_for_project(pid))
    limits = AgentLimits(**frozen)

    async def run():
        async def retrieve(selected, query):
            return await retrieve_chunks(
                db, selected, query, lambda: None,
                lambda _: pytest.fail("本用例未绑定向量模型，不得调用真实服务"),
                min_similarity=limits.similarity_threshold, max_results=limits.max_search_results,
            )

        async def read(source, offset, limit):
            return db.read_chunk_window(source, offset, limit)

        async def authorize():
            pass

        research = ResearchSession(sources, pid, retrieve, read, authorize, limits,
                                   compact_results=True)
        result = await research.search("alpha beta gamma", "project")
        assert len(result["blocks"]) == len(research.seen) == 3
        assert all(set(row) == {"id", "text"} and row["text"] == "alpha beta gamma"
                   for row in result["blocks"])
        # 高阈值不允许拿一次关键词命中冒充相似资料，也不能以空结果推断全文没有要求。
        assert (await research.search("alpha delta epsilon", "project"))["blocks"] == []

    asyncio.run(run())


def test_upload_and_reparse_freeze_configured_defaults_with_explicit_override(runtime):
    request, connection, pid = runtime
    draft = release(request, {"mineru.tier": "advanced", "mineru.ocr_mode": "ocr"})
    impacts = config.get_release(draft["id"], request)["impact"]
    config.acknowledge_release(draft["id"], config.AcknowledgeRequest(
        items=[config.ImpactRef(kind=item["kind"], ref=item["ref"]) for item in impacts],
    ), request)
    config.activate_release(draft["id"], config.ActivateRequest(), request)
    upload = asyncio.run(project_files._add_project_file(
        request, project_id=pid, item=project_files.FileInput("样本.pdf", b"%PDF-fixture"),
        role="main", auto_parse=True, tier=None, ocr_mode=None, replaces_id=None,
    ))
    snapshot = connection.execute(text("SELECT config_snapshot FROM job WHERE id=:id"),
                                  {"id": upload["job_id"]}).scalar_one()
    assert snapshot["tier"] == "advanced" and snapshot["ocr_mode"] == "ocr"
    version, _ = add_source(connection, pid, "解析样本")
    created = parsing._create_parse_job(version, parsing.ParseRequest(tier="basic"), request,
                                        force=True)
    snapshot = connection.execute(text("SELECT config_snapshot FROM job WHERE id=:id"),
                                  {"id": created["job_id"]}).scalar_one()
    assert snapshot["tier"] == "basic" and snapshot["ocr_mode"] == "ocr"


def parsing_job(runtime):
    request, connection, pid = runtime
    version, run = add_source(connection, pid, "轮询样本", status="running")
    connection.execute(text("""INSERT INTO job
        (id, company_id, project_id, project_file_id, version_id, run_id, status, stage)
        SELECT 'poll-fixture',1,:pid,id,:version,:run,'running','parsing'
        FROM project_file WHERE version_id=:version"""),
                       {"pid": pid, "version": version, "run": run})
    return request, connection


def test_poll_interval_and_attempts_survive_new_task_invocations(runtime, monkeypatch):
    request, connection = parsing_job(runtime)
    release(request, {"job.poll.initial_interval_ms": 1500, "job.poll.max_interval_ms": 2500,
                      "job.poll.max_attempts": 2})
    calls = []

    async def poll(*args):
        calls.append(True)
        return ParseJobStatus("fixture", "running", ParseProgress(10, 1, 0), False), None

    monkeypatch.setattr(tasks, "_poll", poll)
    tasks.poll_parse.run("poll-fixture")
    first = tasks._repository.execution_start("poll-fixture", "parse")
    due = connection.execute(text(
        "SELECT next_attempt_at - now() FROM job WHERE id='poll-fixture'"
    )).scalar_one()
    assert due == timedelta(seconds=2.5)
    tasks.poll_parse.run("poll-fixture")
    assert len(calls) == 1  # 提前重复消息不能消耗轮询预算。
    for _ in range(2):
        connection.execute(text("UPDATE job SET next_attempt_at=now() - interval '1 second' "
                                "WHERE id='poll-fixture'"))
        tasks.poll_parse.run("poll-fixture")
    result = connection.execute(text("SELECT * FROM job WHERE id='poll-fixture'" )).mappings().one()
    assert len(calls) == 2
    assert result["status"] == "draining" and result["error_code"] == "parse_timeout"
    assert result["finished_at"] is None
    assert result["progress"]["poll_attempts"] == 2
    assert tasks._repository.execution_start("poll-fixture", "parse") == first


def test_expired_parse_deadline_stops_before_external_poll(runtime, monkeypatch):
    request, connection = parsing_job(runtime)
    release(request, {"job.timeout.parse_minutes": 1})
    expired = datetime.now(UTC) - timedelta(minutes=2)
    connection.execute(text("""UPDATE job SET progress=jsonb_build_object(
        'parse_started_at',CAST(:started AS text)) WHERE id='poll-fixture'"""),
                       {"started": expired.isoformat()})
    monkeypatch.setattr(tasks, "_poll", lambda *args: pytest.fail("超时任务不应请求外部解析服务"))
    tasks.poll_parse.run("poll-fixture")
    assert connection.execute(text(
        "SELECT error_code FROM job WHERE id='poll-fixture'"
    )).scalar_one() == "parse_timeout"


def test_poll_network_retry_uses_configured_delay_and_consumes_attempt(runtime, monkeypatch):
    request, connection = parsing_job(runtime)
    release(request, {"job.poll.initial_interval_ms": 100, "job.poll.max_interval_ms": 150,
                      "job.poll.max_attempts": 1})
    calls = []

    async def unavailable(*args):
        calls.append(True)
        raise ParseUnavailable("测试网络故障")

    monkeypatch.setattr(tasks, "_poll", unavailable)
    tasks.poll_parse.run("poll-fixture")
    due = connection.execute(text(
        "SELECT next_attempt_at - now() FROM job WHERE id='poll-fixture'"
    )).scalar_one()
    assert due == timedelta(seconds=0.15)
    connection.execute(text("UPDATE job SET next_attempt_at=now() - interval '1 second' "
                            "WHERE id='poll-fixture'"))
    tasks.poll_parse.run("poll-fixture")
    assert calls == [True]
    row = connection.execute(text(
        "SELECT status,progress,finished_at FROM job WHERE id='poll-fixture'"
    )).mappings().one()
    assert row["status"] == "draining" and row["progress"]["poll_attempts"] == 1
    assert row["finished_at"] is None


def test_conversion_uses_configured_budget_and_preserves_first_start(runtime, monkeypatch):
    request, _, _ = runtime
    release(request, {"job.timeout.convert_minutes": 2, "job.retry.convert_500": 0})
    row = {"id": "convert-fixture", "company_id": 1}
    # 复用真实job表记录首启时间，转换适配器只记录实际收到的总预算与重试次数。
    _, connection = parsing_job(runtime)
    connection.execute(text("UPDATE job SET id='convert-fixture' WHERE id='poll-fixture'"))
    received = []

    async def convert(row, store, remaining, extra_retries):
        received.append((remaining, extra_retries))
        return 1, 1, False

    monkeypatch.setattr(tasks, "_convert_office_file", convert)
    asyncio.run(tasks._process_office_file(row, None))
    first = tasks._repository.execution_start("convert-fixture", "convert")
    asyncio.run(tasks._process_office_file(row, None))
    assert all(0 < seconds <= 120 and retries == 0 for seconds, retries in received)
    assert tasks._repository.execution_start("convert-fixture", "convert") == first


def test_new_job_budget_stays_fixed_after_config_change(runtime):
    request, connection, pid = runtime
    release(request, {"job.timeout.parse_minutes": 4, "job.poll.max_attempts": 9})
    version, _ = add_source(connection, pid, "新任务预算")
    created = parsing._create_parse_job(
        version, parsing.ParseRequest(), request, force=True,
    )
    before = tasks._repository.runtime_values(created["job_id"])
    release(request, {"job.timeout.parse_minutes": 44, "job.poll.max_attempts": 99})
    assert tasks._repository.runtime_values(created["job_id"]) == before
    assert before["job.timeout.parse_minutes"] == 4
    assert before["job.poll.max_attempts"] == 9
    snapshot = connection.execute(text("SELECT config_snapshot FROM job WHERE id=:id"),
                                  {"id": created["job_id"]}).scalar_one()
    assert snapshot["execution_origin"] == "created"


def test_legacy_job_freezes_first_execution_and_records_origin(runtime):
    request, connection = parsing_job(runtime)
    release(request, {"job.timeout.parse_minutes": 3})
    before = tasks._repository.runtime_values("poll-fixture")
    release(request, {"job.timeout.parse_minutes": 33})
    assert tasks._repository.runtime_values("poll-fixture") == before
    assert before["job.timeout.parse_minutes"] == 3
    snapshot = connection.execute(text(
        "SELECT config_snapshot FROM job WHERE id='poll-fixture'"
    )).scalar_one()
    assert snapshot["execution_origin"] == "legacy_first_execution"
    assert snapshot["execution_frozen_at"]


def test_legacy_job_uses_historical_snapshot_instead_of_live_values(runtime):
    request, connection, pid = runtime
    release(request, {"job.timeout.parse_minutes": 6})
    version, _ = add_source(connection, pid, "历史快照")
    created = parsing._create_parse_job(
        version, parsing.ParseRequest(), request, force=True,
    )
    # 模拟升级前的任务：只有 config_snapshot_id，没有内嵌 execution 数据。
    connection.execute(text("""UPDATE job SET config_snapshot = config_snapshot
        - 'execution' - 'execution_origin' WHERE id=:id"""), {"id": created["job_id"]})
    release(request, {"job.timeout.parse_minutes": 66})
    restored = tasks._repository.runtime_values(created["job_id"])
    assert restored["job.timeout.parse_minutes"] == 6
    snapshot = connection.execute(text("SELECT config_snapshot FROM job WHERE id=:id"),
                                  {"id": created["job_id"]}).scalar_one()
    assert snapshot["execution_origin"] == "job_config_snapshot"


def test_submit_retry_backoff_survives_new_task_messages(runtime, monkeypatch):
    _, connection = parsing_job(runtime)
    connection.execute(text("UPDATE job SET status='pending', stage='submitting', run_id=NULL "
                            "WHERE id='poll-fixture'"))

    async def unavailable(*args):
        raise ParseUnavailable("模拟提交前网络不可用")

    monkeypatch.setattr(tasks, "_submit", unavailable)
    starts = []
    for expected_delay in (2, 2, 4):
        tasks.submit_parse.run("poll-fixture")
        row = connection.execute(text("SELECT status, progress, next_attempt_at - now() AS delay "
                                      "FROM job WHERE id='poll-fixture'")).mappings().one()
        assert row["status"] == "pending" and row["delay"] == timedelta(seconds=expected_delay)
        starts.append(row["progress"]["parse_started_at"])
        connection.execute(text("UPDATE job SET next_attempt_at=now() - interval '1 second' "
                                "WHERE id='poll-fixture'"))
    assert row["progress"]["retry_attempts"] == 3
    assert len(set(starts)) == 1
