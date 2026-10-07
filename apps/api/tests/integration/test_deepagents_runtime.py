"""独立 PostgreSQL schema 验证多连接硬配额、恢复和真实 DeepAgents 调度。"""

import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, message_to_dict
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import make_conninfo
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from test_knowledge_flow import add_source

from tender.api import knowledge, projects
from tender.application import agent_runtime
from tender.application.agent_checkpoints import run_async
from tender.application.knowledge_store import KnowledgeStore
from tender.application.provider_cooldown import ProviderCooldown
from tender.core import settings
from tender.ports.llm import Completion
from tender.worker import deep_analysis as worker

pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库集成验证"
)


@pytest.fixture
def env(monkeypatch):
    schema = "test_agents_" + uuid4().hex
    base = create_engine(settings.database_url())
    tables = (
        "project",
        "document",
        "document_version",
        "parse_run",
        "page",
        "element",
        "project_file",
        "lot",
        "job",
        "knowledge_collection",
        "knowledge_source",
        "project_knowledge_collection",
        "knowledge_index",
        "knowledge_chunk",
        "analysis_report",
        "analysis_module",
        "knowledge_relation",
        "knowledge_answer",
        "llm_feature_model",
        "llm_model",
        "llm_provider",
        "config_release",
        "agent_module_run",
        "agent_run_event",
        "llm_call_log",
    )
    with base.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        for table in tables:
            conn.execute(
                text(
                    f'CREATE TABLE "{schema}".{table} '
                    f"(LIKE public.{table} INCLUDING DEFAULTS "
                    "INCLUDING CONSTRAINTS INCLUDING INDEXES)"
                )
            )
            columns = (
                conn.execute(
                    text("""SELECT column_name FROM information_schema.columns
                WHERE table_schema=:schema AND table_name=:table
                  AND column_default LIKE 'nextval%'"""),
                    {"schema": schema, "table": table},
                )
                .scalars()
                .all()
            )
            for column in columns:
                seq = f"{schema}.{table}_{column}_seq"
                conn.execute(text(f"CREATE SEQUENCE {seq}"))
                conn.execute(
                    text(
                        f'ALTER TABLE "{schema}".{table} ALTER COLUMN {column} '
                        f"SET DEFAULT nextval('{seq}')"
                    )
                )
    url = make_url(settings.database_url()).update_query_dict(
        {"options": f"-csearch_path={schema},public"}
    )
    engine = create_engine(url, pool_size=10, max_overflow=10)
    db = KnowledgeStore(engine, 1)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(components=SimpleNamespace(engine=engine))),
        headers={},
    )
    dsn = make_conninfo(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
        options=f"-csearch_path={schema}",
    )
    # 测试锁空间独立于实际 worker，真实报告不会消耗测试配额。
    monkeypatch.setattr(agent_runtime, "QUOTA_NAMESPACE", 20000000 + int(uuid4().hex[:5], 16))
    monkeypatch.setattr(worker, "checkpoint_dsn", lambda: dsn)
    monkeypatch.setattr(settings, "company_id", lambda: 1)

    async def setup():
        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            await saver.setup()

    run_async(setup())
    try:
        yield SimpleNamespace(db=db, request=request, engine=engine, dsn=dsn)
    finally:
        engine.dispose()
        with base.begin() as conn:
            # schema 名只由 UUID 生成，且本 fixture 创建；不涉及用户数据表。
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def report(env):
    project = projects.create_project(projects.ProjectCreate(name="DeepAgents专项"), env.request)
    with env.engine.begin() as conn:
        add_source(conn, project["id"], "采购交换机10台，质保三年。")
    knowledge.save_settings(
        project["id"], knowledge.AnalysisSettings(category="goods"), env.request
    )
    created = knowledge.start_analysis(project["id"], knowledge.AnalysisInput(), env.request)
    return knowledge.report_row(env.request, created["id"])


def prepared_runtime(env):
    row = report(env)
    row, sources = worker.prepare_report(env.db, row)
    run = env.db.rows(
        """SELECT a.* FROM agent_module_run a JOIN analysis_module m ON m.id=a.module_id
        WHERE m.report_id=:id ORDER BY a.id LIMIT 1""",
        {"id": row["id"]},
    )[0]
    return agent_runtime.AgentRuntime(env.db, row, run, sources)


def test_hard_quota_across_reports_and_no_lease_theft(env):
    first, second, third = [prepared_runtime(env) for _ in range(3)]
    try:
        assert first.claim()
        assert second.claim()
        assert not third.claim()
        # 过期租约不能抢走仍持有会话锁的模块，否则慢请求会使实际并发突破配额。
        env.db.execute(
            "UPDATE agent_module_run SET lease_until=now()-interval '1 minute' WHERE id=:id",
            {"id": first.run["id"]},
        )
        assert not third.claim()
        first.release()
        assert third.claim()
    finally:
        for runtime in (first, second, third):
            runtime.release()


def test_resume_preserves_budget_evidence_and_deadline(env):
    first = prepared_runtime(env)
    assert first.claim()
    first.reserve("model")
    first.save({"research": {"seen": {"original": {"content": "独立证据"}}}})
    deadline = first.run["deadline_at"]
    first.release()
    # 恢复等待配额的旧线程应显示排队，但不能重置已经消耗的预算和时限。
    worker.prepare_report(env.db, knowledge.report_row(env.request, first.report["id"]))
    run = env.db.rows("SELECT * FROM agent_module_run WHERE id=:id", {"id": first.run["id"]})[0]
    assert run["status"] == "pending"
    resumed = agent_runtime.AgentRuntime(env.db, first.report, run, first.sources)
    try:
        assert resumed.claim()
        assert resumed.run["deadline_at"] == deadline
        assert resumed.run["model_calls"] == 1
        assert resumed.run["state"]["research"]["seen"]["original"]["content"] == "独立证据"
        resumed.run["limits"]["max_model_calls"] = 1
        with pytest.raises(ValueError, match="预算"):
            resumed.reserve("model")
        env.db.execute(
            "UPDATE analysis_report SET status='canceled' WHERE id=:id", {"id": first.report["id"]}
        )
        with pytest.raises(InterruptedError):
            resumed.reserve("tool")
    finally:
        resumed.release()


class NativeRouter:
    def __init__(self, *, before_request, **kwargs):
        self.reserve = before_request
        self.calls = 0

    async def chat(self, messages, tools):
        await self.reserve()
        await asyncio.sleep(0.01)
        self.calls += 1
        if self.calls == 1:
            name, args = "search_document", {"query": "质保"}
        else:
            name, args = (
                "submit_analysis",
                {
                    "items": [],
                    "relations": [],
                    "outline_nodes": [],
                    "research_summary": "已检索质保，当前专题无新增事项",
                },
            )
        return Completion(
            content="",
            model="fixture",
            agent_message=message_to_dict(
                AIMessage(
                    content="", tool_calls=[{"name": name, "args": args, "id": f"call{self.calls}"}]
                )
            ),
        )

    async def aclose(self):
        pass


def test_controller_runs_13_independent_graphs_with_postgres_checkpoints(env, monkeypatch):
    row = report(env)
    routers = []

    def model(*args, **kwargs):
        router = NativeRouter(**kwargs)

        async def broken_close():
            raise RuntimeError("模拟SDK清理失败")

        router.aclose = broken_close
        routers.append(router)
        return router

    async def retrieve(db, sources, query, *args, **kwargs):
        return db.readable_chunks(sources[0]), {"mode": "keyword"}

    monkeypatch.setattr(worker, "_routing_model", model)
    monkeypatch.setattr(worker, "retrieve_chunks", retrieve)
    run_async(worker.analyze_report(env.db, row))
    result = knowledge.get_report(row["id"], env.request)
    assert result["status"] == "completed", (result["error_message"], result["modules"])
    assert len(routers) == len(result["modules"]) == 13
    runs = env.db.rows("SELECT * FROM agent_module_run")
    assert len({r["thread_id"] for r in runs}) == 13
    assert all(r["status"] == "completed" and r["model_calls"] == 2 for r in runs)
    assert all(r["state"]["research"]["seen"] for r in runs)
    assert result["coverage"]["mode"] == "agent_research"
    assert "scanned_blocks" not in result["coverage"]
    assert len(env.db.rows("SELECT id FROM agent_run_event WHERE kind='client_close_failed'")) == 13
    assert not env.db.rows(
        "SELECT objid FROM pg_locks WHERE locktype='advisory' AND classid=:ns"
        " AND objsubid=2 AND granted",
        {"ns": agent_runtime.QUOTA_NAMESPACE},
    )
    # 已完成报告的重复派发不能再调用任何模型。
    from tender.worker import knowledge as entry

    monkeypatch.setattr(entry, "_store", lambda: env.db)
    run_async(entry._analyze_project(row["id"]))
    assert len(routers) == 13


def test_provider_cooldown_survives_new_instances_and_never_shortens(env):
    # 显式提交，第二个独立连接才能验证共享冷却，而非读取同一事务的临时状态。
    with env.db.engine.begin() as conn:
        provider_id = conn.execute(
            text(
                "INSERT INTO llm_provider(name,base_url) "
                "VALUES('共享限流测试','http://fixture') RETURNING id"
            )
        ).scalar_one()
    candidate = SimpleNamespace(provider_id=provider_id)
    first = ProviderCooldown(env.db.engine)
    first.defer(candidate, 60)
    second_engine = create_engine(env.db.engine.url)
    try:
        second = ProviderCooldown(second_engine)
        assert 50 < second.remaining(candidate) <= 60
        second.defer(candidate, 1)
        assert first.remaining(candidate) > 50
        with env.db.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE llm_provider SET rate_limited_until=now()-interval '1 second' "
                    "WHERE id=:id"
                ),
                {"id": provider_id},
            )
        assert second.remaining(candidate) == 0
    finally:
        second_engine.dispose()


@pytest.mark.parametrize("staged", [False, True])
def test_retry_creates_one_new_attempt_and_preserves_completed_modules(env, staged):
    runtime = prepared_runtime(env)
    assert runtime.claim()
    runtime.reserve("model")
    saved_state = {"draft": {"items": [], "relations": [], "research_summary": "已经检索"}}
    if staged:
        saved_state = {
            "staged_items": [
                {
                    "id": "part1",
                    "kind": "fact",
                    "title": "质保",
                    "text": "质保三年",
                    "citations": [
                        {
                            "source_id": runtime.sources[0]["source_id"],
                            "project_id": runtime.report["project_id"],
                            "quote": "质保三年",
                        }
                    ],
                }
            ],
            "invalid_submissions": 3,
        }
    runtime.save(saved_state)
    runtime.finish("failed", "故障注入")
    runtime.release()
    env.db.execute(
        "UPDATE analysis_report SET status='partial' WHERE id=:id", {"id": runtime.report["id"]}
    )
    key = env.db.rows(
        "SELECT module_key FROM analysis_module WHERE id=:id", {"id": runtime.run["module_id"]}
    )[0]["module_key"]
    result = knowledge.retry_report(
        runtime.report["id"],
        knowledge.RetryInput(module_keys=[key], max_output_tokens=8192),
        env.request,
    )
    assert result["status"] == "pending"
    rows = env.db.rows(
        "SELECT * FROM agent_module_run WHERE module_id=:id ORDER BY attempt",
        {"id": runtime.run["module_id"]},
    )
    assert [r["model_calls"] for r in rows] == [1, 0]
    assert [r["attempt"] for r in rows] == [1, 2]
    assert rows[0]["limits"]["max_output_tokens"] == 4096
    assert rows[1]["limits"]["max_output_tokens"] == 8192
    assert rows[0]["thread_id"] != rows[1]["thread_id"]
    carried_key = "staged_items" if staged else "draft"
    assert rows[1]["state"][carried_key] == rows[0]["state"][carried_key]
    assert "invalid_submissions" not in rows[1]["state"]
    with pytest.raises(knowledge.ApiProblem):
        knowledge.retry_report(
            runtime.report["id"], knowledge.RetryInput(module_keys=[key]), env.request
        )


def test_dynamic_reference_revocation_stops_tool_and_hides_existing_result(env):
    runtime = prepared_runtime(env)
    reference = projects.create_project(projects.ProjectCreate(name="参考专项"), env.request)
    with env.engine.begin() as conn:
        add_source(conn, reference["id"], "历史质保五年。")
        cid = conn.execute(
            text(
                "UPDATE knowledge_collection SET is_project=false,purpose='reference'"
                " WHERE upload_project_id=:id RETURNING id"
            ),
            {"id": reference["id"]},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO project_knowledge_collection VALUES (:pid,:cid)"),
            {"pid": runtime.report["project_id"], "cid": cid},
        )
    runtime.sources += env.db.sources([cid])
    try:
        assert runtime.claim()
        runtime.reserve("tool")
        env.db.execute(
            "DELETE FROM project_knowledge_collection WHERE project_id=:id",
            {"id": runtime.report["project_id"]},
        )
        with pytest.raises(PermissionError, match="撤销"):
            runtime.guard()
        # 服务端展示规则也使用实时关联，不能借旧报告继续读取参考引文。
        item = {
            "id": "test",
            "kind": "suggestion",
            "title": "历史参考",
            "text": "五年",
            "citations": [{"collection_id": cid}],
        }
        shown = knowledge.visible_items(
            env.db, [item], env.db.collections_for_project(runtime.report["project_id"])
        )
        assert shown[0]["verification"] == "unavailable"
    finally:
        runtime.release()
