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

from tender.api import config, llm, parsing, project_files, projects
from tender.api.errors import ApiProblem
from tender.application.model_profiles import FEATURE_FIELDS, MODEL_FIELDS
from tender.config.registry import ConfigRegistry
from tender.domain.errors import ParseUnavailable
from tender.ports.parser import ParseJobStatus, ParseProgress
from tender.worker import tasks

pytestmark = pytest.mark.skipif(os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库")


@pytest.fixture
def runtime(env, monkeypatch):
    request, connection = env
    request.headers = {}
    components = request.app.state.components
    components.configs = ConfigRegistry(components.engine)
    components.blobs = SimpleNamespace(put=lambda *args, **kwargs: None)
    monkeypatch.setattr(tasks, "_engine", components.engine)
    monkeypatch.setattr(tasks, "_advisory_lock", lambda *args, **kwargs: nullcontext(True))
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
    delays, calls = [], []

    async def poll(*args):
        calls.append(True)
        return ParseJobStatus("fixture", "running", ParseProgress(10, 1, 0), False), None

    monkeypatch.setattr(tasks, "_poll", poll)
    monkeypatch.setattr(tasks.poll_parse, "apply_async",
                        lambda **kwargs: delays.append(kwargs["countdown"]))
    tasks.poll_parse.run("poll-fixture")
    first = tasks._execution_start("poll-fixture", "parse")
    tasks.poll_parse.run("poll-fixture")
    tasks.poll_parse.run("poll-fixture")
    result = connection.execute(text("SELECT * FROM job WHERE id='poll-fixture'" )).mappings().one()
    assert len(calls) == 2 and delays == [2.5, 2.5]
    assert result["status"] == "failed" and result["error_code"] == "parse_timeout"
    assert result["progress"]["poll_attempts"] == 2
    assert tasks._execution_start("poll-fixture", "parse") == first


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
    delays = []

    async def unavailable(*args):
        raise ParseUnavailable("测试网络故障")

    def retry(**kwargs):
        delays.append(kwargs["countdown"])
        return RuntimeError("测试消息重试")

    monkeypatch.setattr(tasks, "_poll", unavailable)
    monkeypatch.setattr(tasks.poll_parse, "retry", retry)
    with pytest.raises(RuntimeError, match="测试消息重试"):
        tasks.poll_parse.run("poll-fixture")
    tasks.poll_parse.run("poll-fixture")
    assert delays == [0.15]
    row = connection.execute(text(
        "SELECT status,progress FROM job WHERE id='poll-fixture'"
    )).mappings().one()
    assert row["status"] == "failed" and row["progress"]["poll_attempts"] == 1


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
    first = tasks._execution_start("convert-fixture", "convert")
    asyncio.run(tasks._process_office_file(row, None))
    assert all(0 < seconds <= 120 and retries == 0 for seconds, retries in received)
    assert tasks._execution_start("convert-fixture", "convert") == first
