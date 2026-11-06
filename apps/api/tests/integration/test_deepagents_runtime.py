"""独立 PostgreSQL schema 验证多连接硬配额、恢复和真实 DeepAgents 调度。"""

import asyncio
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from data_schema import install_data_schema
from langchain_core.messages import AIMessage, message_to_dict
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import make_conninfo
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from store import SqlStore
from test_knowledge_flow import add_source

from tender.adapters.pg.analysis.checkpoints import run_async
from tender.adapters.pg.repositories.analysis import runtime as run_store
from tender.adapters.pg.repositories.llm.provider_cooldown import ProviderCooldown
from tender.api.analysis import routes as analysis_api
from tender.api.projects import routes as projects
from tender.api.shared.errors import ApiProblem
from tender.application.analysis import execution as worker
from tender.application.analysis import runtime as agent_runtime
from tender.application.analysis.agent import VerificationUnavailable
from tender.application.analysis.skills import MODULES, skill_snapshot
from tender.config.registry import ConfigRegistry
from tender.core import settings
from tender.core.di import create_analysis_executor
from tender.ports.llm.chat import Completion

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
    with engine.begin() as connection:
        install_data_schema(connection)
    db = SqlStore(engine, 1)
    request = SimpleNamespace(
        # 配置与仓储指向同一个隔离 schema，保持生产装配契约。
        app=SimpleNamespace(state=SimpleNamespace(components=SimpleNamespace(
            engine=engine, configs=ConfigRegistry(engine),
        ))),
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
    monkeypatch.setattr(run_store, "QUOTA_NAMESPACE", 20000000 + int(uuid4().hex[:5], 16))
    executor = create_analysis_executor(db)
    executor.checkpoints = lambda: AsyncPostgresSaver.from_conn_string(dsn)
    monkeypatch.setattr(settings, "company_id", lambda: 1)

    async def setup():
        async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
            await saver.setup()

    run_async(setup())
    try:
        yield SimpleNamespace(db=db, request=request, engine=engine, dsn=dsn, executor=executor)
    finally:
        engine.dispose()
        with base.begin() as conn:
            # schema 名只由 UUID 生成，且本 fixture 创建；不涉及用户数据表。
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def report(env, *, topic_flow=False):
    project = projects.create_project(projects.ProjectCreate(name="DeepAgents专项"), env.request)
    with env.engine.begin() as conn:
        add_source(conn, project["id"], "采购交换机10台，质保三年。")
    analysis_api.save_settings(
        project["id"], analysis_api.AnalysisSettings(category="goods"), env.request
    )
    created = analysis_api.start_analysis(project["id"], analysis_api.AnalysisInput(), env.request)
    if not topic_flow:
        # 既有脚本专门回归历史协议；新报告冻结与增量协议由 topic_flow 集成用例覆盖。
        env.db.execute("""UPDATE analysis_report SET skill_snapshot=
            skill_snapshot - '__analysis_flow_version__' WHERE id=:id""", {"id": created["id"]})
    return analysis_api.report_row(env.request, created["id"])


def prepared_runtime(env, *, topic_flow=False):
    row = report(env, topic_flow=topic_flow)
    row, sources = worker.prepare_report(env.db, row)
    run = env.db.rows(
        """SELECT a.* FROM agent_module_run a JOIN analysis_module m ON m.id=a.module_id
        WHERE m.report_id=:id ORDER BY a.id LIMIT 1""",
        {"id": row["id"]},
    )[0]
    return agent_runtime.AgentRuntime(env.db, row, run, sources)


def prepared_runtimes(env, count: int = 1):
    """同一报告里按模块顺序取前若干个运行账，用于验证同报告内部的抢槽与收殓。"""
    row = report(env)
    row, sources = worker.prepare_report(env.db, row)
    runs = env.db.rows(
        """SELECT a.* FROM agent_module_run a JOIN analysis_module m ON m.id=a.module_id
        WHERE m.report_id=:id ORDER BY a.id""",
        {"id": row["id"]},
    )
    return [agent_runtime.AgentRuntime(env.db, row, run, sources) for run in runs[:count]]


def publishable_state(module_key: str) -> dict:
    """构造一条已核实、一条未核实的暂存成果，验证 partial 只发布前者。"""
    ref = {
        "block_id": "s1r1c0", "quote": "质保三年", "source_id": 1, "project_id": 1,
        "page_no": 1, "file_name": "fixture.pdf", "bbox": [0, 0, 1, 1],
    }

    def entry(record_id, key, title, text, verification):
        business = {
            "id": record_id, "key": key, "kind": "requirement",
            "scope": {"kind": "common", "lot_refs": []}, "module_key": module_key,
            "title": title, "text": text, "structuring": "complete",
            "citations": [dict(ref)],
        }
        return {
            "id": record_id, "field": title, "group": "", "sort_order": 0,
            "values": [{"value": text, "citations": [dict(ref)]}], "note": "",
            "business": business, "verification": verification,
        }

    return {
        "staged_items": [
            entry("keep", "warranty", "质保期限", "质保三年", "supported"),
            entry("drop", "delivery", "交货期", "交货期30日", "pending"),
        ],
        "staged_items_verified": True,
    }


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


def test_claim_backoff_does_not_starve_later_modules(env, monkeypatch):
    """配额占满时等待模块退避轮询，仍能依次领取，权限复核不随轮询次数增长。"""

    class Model:
        async def aclose(self):
            pass

    class CountingRuntime(agent_runtime.AgentRuntime):
        claims = 0
        checks = 0

        def claim(self):
            type(self).claims += 1
            return super().claim()

        def check_access(self):
            type(self).checks += 1
            return super().check_access()

    prepared = prepared_runtimes(env, 3)
    # 执行器按运行账里的 module_key 建模型；JOIN 回读模块键，与恢复流程测试一致。
    runs = env.db.rows(
        """SELECT a.*,m.module_key FROM agent_module_run a
        JOIN analysis_module m ON m.id=a.module_id
        WHERE m.report_id=:id ORDER BY a.id LIMIT 3""",
        {"id": prepared[0].report["id"]},
    )
    runtimes = [
        agent_runtime.AgentRuntime(env.db, prepared[0].report, run, prepared[0].sources)
        for run in runs
    ]
    resolved = env.db.resolved_config
    monkeypatch.setattr(
        env.db, "resolved_config", lambda: resolved() | {"analysis.max_inflight": 1}
    )
    monkeypatch.setattr(worker, "AgentRuntime", CountingRuntime)
    monkeypatch.setattr(env.executor, "model_factory", lambda *a, **kw: Model())
    monkeypatch.setattr(worker, "build_module_agent", lambda **kwargs: (kwargs["key"], {}))

    async def invoke(graph, files, *, state=None, **kwargs):
        # 每个模块占用配额片刻，后两个必然经历等待与退避轮询。
        await asyncio.sleep(0.2)
        state["draft"] = {"fields": [], "relations": [], "business_data": {}}

    monkeypatch.setattr(worker, "invoke_module", invoke)

    async def execute_all():
        await asyncio.gather(*[
            env.executor.execute_module(runtime.report, runtime.run, runtime.sources)
            for runtime in runtimes
        ])

    run_async(execute_all())
    ids = {runtime.run["id"] for runtime in runtimes}
    rows = [
        row
        for row in env.db.rows(
            """SELECT r.id,r.status AS run_status,m.status AS module_status
            FROM agent_module_run r JOIN analysis_module m ON m.id=r.module_id
            WHERE m.report_id=:report""",
            {"report": runtimes[0].report["id"]},
        )
        if row["id"] in ids
    ]
    assert len(rows) == 3
    assert all(row["run_status"] == "completed" for row in rows)
    assert all(row["module_status"] == "completed" for row in rows)
    # 后两个模块至少各有一次未领取成功的轮询，说明确实等待过而不是一次就抢到。
    assert CountingRuntime.claims > 3
    # 等待短于 30 秒时只有领取前的一次权限复核，没有逐轮查询。
    assert CountingRuntime.checks == 3


def test_resume_preserves_budget_evidence_and_deadline(env):
    first = prepared_runtime(env)
    assert first.claim()
    first.reserve("model")
    first.save({"research": {"seen": {"original": {"content": "独立证据"}}}})
    deadline = first.run["deadline_at"]
    first.release()
    # 恢复等待配额的旧线程应显示排队，但不能重置已经消耗的预算和时限。
    worker.prepare_report(env.db, analysis_api.report_row(env.request, first.report["id"]))
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
    def __init__(self, *, purpose="", **kwargs):
        self.reserve = kwargs["before_request"]
        self.key = next((key for key in MODULES if key in purpose), "project_basic_info_parsing")
        self.topics = json.loads(skill_snapshot()[self.key + "/references/coverage.json"])
        self.calls = 0

    async def chat(self, messages, tools):
        await self.reserve()
        await asyncio.sleep(0.01)
        self.calls += 1
        if self.calls == 1:
            name, args = "list_documents", {}
        elif self.calls == 2:
            name, args = "search_document", {"query": "质保"}
        elif self.calls == 3:
            name, args = "complete_research", {
                "topics": [{"topic": topic["key"], "status": "searched_not_found",
                            "queries": ["质保"], "evidence_ids": [], "detail": "本次未识别新增事项"}
                           for topic in self.topics],
                "references": [], "research_summary": "已检查项目资料和各专题检索范围",
            }
        else:
            name, args = (
                "submit_analysis",
                {
                    "records": [], "coverage": [
                        {"topic": topic["key"], "status": "searched_not_found",
                         "scope": {"kind": "common", "lot_refs": []},
                         "record_keys": [], "detail": "本次未识别新增事项"}
                        for topic in self.topics
                    ], "gaps": [],
                    "research_summary": "已检索质保，当前专题无新增事项",
                    "final": True,
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


def test_selected_evidence_resolves_only_retained_id_after_review(env, monkeypatch):
    """真实图、检查点和元素表串联，证明模型看不到位置且只解析最终选中的证据。"""
    row = report(env)
    with env.engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO element
            (version_id,run_id,page_no,order_no,anchor,type,text,bbox_x0,bbox_y0,bbox_x1,bbox_y1)
            SELECT version_id,run_id,1,2,'p1b2','text',text,0.2,0.3,0.9,0.4
            FROM element LIMIT 1""")
        )
    row, sources = worker.prepare_report(env.db, row)
    run = env.db.rows("""SELECT a.*,m.module_key FROM agent_module_run a
        JOIN analysis_module m ON m.id=a.module_id ORDER BY a.id LIMIT 1""")[0]
    selected, resolved_ids = [], []
    original_resolve = env.db.resolve

    def resolve(ref, **kwargs):
        resolved_ids.append(ref["block_id"])
        return original_resolve(ref, **kwargs)

    class EvidenceRouter(NativeRouter):
        async def chat(self, messages, tools):
            if self.calls < 3:
                return await super().chat(messages, tools)
            await self.reserve()
            self.calls += 1
            result = next(
                json.loads(m["data"]["content"])
                for m in messages
                if m["type"] == "tool" and m["data"].get("name") == "search_document"
            )
            assert "retrieval" not in result
            assert all(set(b) == {"id", "text"} for b in result["blocks"])
            args = {
                "records": [{
                    "key": "warranty", "kind": "requirement", "title": "质保",
                    "group": "项目基本信息",
                    "content": {"字段": "质保期限", "内容": "质保期限为三年"},
                    "scope": {"kind": "common", "lot_refs": []},
                    "citations": [
                        {"block_id": b["id"], "quote": "质保三年"} for b in result["blocks"]
                    ],
                }],
                "coverage": [
                    {"topic": topic["key"], "status": "searched_not_found",
                     "scope": {"kind": "common", "lot_refs": []},
                     "record_keys": [], "detail": "仅核实质保条款"}
                    for topic in self.topics
                ], "gaps": [],
                "research_summary": "已核对质保",
                "final": True,
            }
            return Completion(
                content="",
                model="fixture",
                agent_message=message_to_dict(
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "submit_analysis", "args": args, "id": "submit"}],
                    )
                ),
            )

        async def complete(self, prompt):
            await self.reserve()
            items = json.loads(prompt.rsplit("\n", 1)[-1])
            refs = items[0]["evidence_sets"][items[0]["values"][0]["evidence_set"]]["citations"]
            assert len(refs) == 2 and all(set(r) == {"id", "text"} for r in refs)
            # 校验请求包含业务属性，不能只核对展示文字后把标段范围直接落库。
            assert items[0]["business"]["scope"] == {"kind": "common", "lot_refs": []}
            selected.append(refs[-1]["id"])
            return Completion(
                content=json.dumps(
                    {
                        "reviews": [
                            {
                                "supported": True,
                                "unsupported_claims": [],
                                "unresolved_references": [],
                                "evidence_ids": [[selected[-1]] for _ in items[0]["values"]],
                            }
                        ]
                    }
                ),
                model="fixture",
            )

    async def retrieve(db, selected_sources, query, *args, **kwargs):
        return db.readable_chunks(selected_sources[0]), {"mode": "keyword"}

    monkeypatch.setattr(
        env.executor, "model_factory",
        lambda feature, purpose, **kw: EvidenceRouter(purpose=purpose, **kw),
    )
    monkeypatch.setattr(worker, "retrieve_chunks", retrieve)
    monkeypatch.setattr(env.db, "resolve", resolve)
    run_async(env.executor.execute_module(row, run, sources))
    module = env.db.rows("SELECT * FROM analysis_module WHERE id=:id", {"id": run["module_id"]})[0]
    assert module["status"] == "completed", module["error_message"]
    assert resolved_ids == selected and len(selected) == 1
    refs = module["items"][0]["values"][0]["citations"]
    assert len(refs) == 1 and refs[0]["block_id"] == selected[0]
    assert refs[0]["bbox"] == [0.2, 0.3, 0.9, 0.4]
    business = module["business_data"]["records"][0]
    assert business["id"] == module["items"][0]["record_id"]
    assert business["verification"] == "supported"
    assert "citations" not in business
    assert [module["business_data"]["evidence"][key] for key in business["evidence_ids"]] == refs


def test_guard_migration_seeds_isolated_config_catalog(env):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "alembic/versions/0010_analysis_guards.py"
    spec = importlib.util.spec_from_file_location("guard_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with env.engine.begin() as conn:
        # search_path首先命中测试schema；不给业务配置定义或活动发布写入任何内容。
        conn.execute(text("CREATE TABLE config_item (LIKE public.config_item INCLUDING ALL)"))
        for statement in migration._STATEMENTS:
            conn.execute(text(statement))
        rows = conn.execute(text("SELECT key,default_value FROM config_item")).all()
    assert len(rows) == 5
    assert dict(rows)["analysis.max_subagent_retries"] == 2


def test_controller_runs_13_independent_graphs_with_postgres_checkpoints(env, monkeypatch):
    row = report(env)
    routers = []

    def model(feature_key, purpose, **kwargs):
        # 各模块使用自己的冻结覆盖清单，检索门禁也在真实检查点中持久化。
        router = NativeRouter(purpose=purpose, **kwargs)

        async def broken_close():
            raise RuntimeError("模拟SDK清理失败")

        router.aclose = broken_close
        routers.append(router)
        return router

    async def retrieve(db, sources, query, *args, **kwargs):
        return db.readable_chunks(sources[0]), {"mode": "keyword"}

    monkeypatch.setattr(env.executor, "model_factory", model)
    monkeypatch.setattr(worker, "retrieve_chunks", retrieve)
    run_async(env.executor.analyze_report(row))
    result = analysis_api.get_report(row["id"], env.request)
    bad = [
        (m["module_key"], m["status"], m.get("error_message"))
        for m in result["modules"]
        if m["status"] != "completed"
    ]
    assert result["status"] == "completed", (result["error_message"], bad)
    assert len(routers) == len(result["modules"]) == 13
    runs = env.db.rows("SELECT * FROM agent_module_run")
    assert len({r["thread_id"] for r in runs}) == 13
    assert all(r["status"] == "completed" and r["model_calls"] == 4 for r in runs)
    assert all(r["state"]["research"]["seen"] for r in runs)
    assert all(r["state"]["loaded_skill"]["sha256"] for r in runs)
    assert len(env.db.rows("SELECT id FROM agent_run_event WHERE kind='skill_loaded'")) == 13
    assert result["coverage"]["mode"] == "agent_research"
    assert "scanned_blocks" not in result["coverage"]
    assert len(env.db.rows("SELECT id FROM agent_run_event WHERE kind='client_close_failed'")) == 13
    snapshots = env.db.rows("SELECT * FROM analysis_data_snapshot WHERE report_id=:id",
                            {"id": row["id"]})
    assert len(snapshots) == 1 and snapshots[0]["schema_version"] == "1"
    # 模型只提交空结果时，13 个模块执行完成也不能伪装成业务覆盖完整。
    assert snapshots[0]["data"]["readiness"] == "unavailable"
    assert snapshots[0]["data"]["coverage"]
    assert not env.db.rows(
        "SELECT objid FROM pg_locks WHERE locktype='advisory' AND classid=:ns"
        " AND objsubid=2 AND granted",
        {"ns": run_store.QUOTA_NAMESPACE},
    )
    # 已完成报告的重复派发不能再调用任何模型。
    from tender.worker.knowledge import tasks as entry

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
    runtime.reserve("tool")
    carried_field = {
        "id": "part1",
        "field": "质保",
        "group": "",
        "sort_order": 0,
        "values": [
            {
                "value": "质保三年",
                "citations": [
                    {
                        "source_id": runtime.sources[0]["source_id"],
                        "project_id": runtime.report["project_id"],
                        "quote": "质保三年",
                    }
                ],
            }
        ],
        "note": "",
        "verification": "supported",
    }
    saved_state = {
        "draft": {
            "fields": [carried_field],
            "relations": [],
            "research_summary": "已经检索",
        },
        "invalid_submissions": 3,
        "consecutive_invalid_submissions": 3,
        "consecutive_unsubmitted_responses": 2,
        "last_unsubmitted_message_id": "old-response",
    }
    if staged:
        saved_state = {
            "staged_items": [carried_field],
            "pending_final": {"research_summary": "旧的最终提交尚未完成校验"},
            "invalid_submissions": 3,
            "consecutive_invalid_submissions": 3,
            "staged_items_verified": True,
            "consecutive_unsubmitted_responses": 2,
            "last_unsubmitted_message_id": "old-response",
        }
    saved_state["research"] = {
        "seen": {}, "events": [{"action": "search_result", "scope": "project"}],
        "tool_calls": 1,
    }
    runtime.save(saved_state)
    if staged:
        # 逐字段落库：已核实成果写进模块结果，模块失败后前端仍能展示。
        items = env.db.rows(
            "SELECT items FROM analysis_module WHERE id=:id", {"id": runtime.run["module_id"]}
        )[0]["items"]
        assert [item["id"] for item in items] == ["part1"]
    runtime.finish("failed", "故障注入")
    runtime.release()
    env.db.execute(
        "UPDATE analysis_report SET status='partial' WHERE id=:id", {"id": runtime.report["id"]}
    )
    key = env.db.rows(
        "SELECT module_key FROM analysis_module WHERE id=:id", {"id": runtime.run["module_id"]}
    )[0]["module_key"]
    result = analysis_api.retry_report(
        runtime.report["id"],
        analysis_api.RetryInput(module_keys=[key], max_output_tokens=262144, timeout_seconds=1200),
        env.request,
    )
    assert result["status"] == "pending"
    rows = env.db.rows(
        "SELECT * FROM agent_module_run WHERE module_id=:id ORDER BY attempt",
        {"id": runtime.run["module_id"]},
    )
    assert [r["model_calls"] for r in rows] == [1, 0]
    assert [r["tool_calls"] for r in rows] == [1, 0]
    assert rows[0]["state"]["research"]["tool_calls"] == 1
    assert rows[1]["state"]["research"]["tool_calls"] == 0
    assert rows[1]["state"]["research"]["events"] == rows[0]["state"]["research"]["events"]
    assert [r["attempt"] for r in rows] == [1, 2]
    assert rows[0]["limits"]["max_output_tokens"] == 8192
    assert rows[1]["limits"]["max_output_tokens"] == 262144
    assert rows[0]["limits"]["timeout_seconds"] == 1800
    assert rows[1]["limits"]["timeout_seconds"] == 1200
    assert rows[0]["thread_id"] != rows[1]["thread_id"]
    if staged:
        # 已核实字段连同验证标记恢复，补跑不需要再调用校验模型。
        assert rows[1]["state"]["staged_items"] == rows[0]["state"]["staged_items"]
        assert rows[1]["state"]["staged_items_verified"] is True
    else:
        # draft 会让新图直接结束，补跑必须转成暂存后继续补齐未完成内容。
        assert "draft" not in rows[1]["state"]
        assert rows[1]["state"]["staged_items"] == rows[0]["state"]["draft"]["fields"]
        assert rows[1]["state"]["staged_items_verified"] is True
    assert "invalid_submissions" not in rows[1]["state"]
    assert "consecutive_invalid_submissions" not in rows[1]["state"]
    assert "field_failures" not in rows[1]["state"]
    assert "unavailable_submissions" not in rows[1]["state"]
    assert "pending_final" not in rows[1]["state"]
    assert "consecutive_unsubmitted_responses" not in rows[1]["state"]
    assert "last_unsubmitted_message_id" not in rows[1]["state"]
    with pytest.raises(ApiProblem):
        analysis_api.retry_report(
            runtime.report["id"], analysis_api.RetryInput(module_keys=[key]), env.request
        )


def test_canceled_report_retries_failed_and_canceled_modules(env):
    """取消不是终态：重新发起只重跑失败与已取消模块，完成的模块保持原结果。"""
    runtime = prepared_runtime(env)
    assert runtime.claim()
    runtime.finish("failed", "故障注入")
    runtime.release()
    report_id = runtime.report["id"]
    with env.engine.begin() as conn:
        # 模拟用户取消：未完成的模块停在取消态，报告本身也进入 canceled。
        conn.execute(
            text("""UPDATE analysis_module SET status='canceled'
            WHERE report_id=:id AND id<>:module"""),
            {"id": report_id, "module": runtime.run["module_id"]},
        )
        conn.execute(
            text("UPDATE analysis_report SET status='canceled' WHERE id=:id"),
            {"id": report_id},
        )
    result = analysis_api.retry_report(report_id, analysis_api.RetryInput(), env.request)
    assert result["status"] == "pending"
    runs = env.db.rows(
        """SELECT m.module_key,m.status,a.attempt FROM analysis_module m
        JOIN agent_module_run a ON a.module_id=m.id
        AND a.attempt=(SELECT max(attempt) FROM agent_module_run WHERE module_id=m.id)
        WHERE m.report_id=:id ORDER BY m.id""",
        {"id": report_id},
    )
    assert runs and all(row["status"] == "pending" and row["attempt"] == 2 for row in runs)
    assert analysis_api.get_report(report_id, env.request)["status"] == "pending"


def test_partial_finish_publishes_only_supported_items(env):
    """校验不可用时模块以 partial 收尾，未核实条目绝不随已核实成果一起发布。"""
    runtime = prepared_runtime(env)
    assert runtime.claim()
    module_key = next(iter(MODULES))
    runtime.finish("partial", "校验服务不可用", state=publishable_state(module_key))
    runtime.release()
    module = env.db.rows(
        "SELECT * FROM analysis_module WHERE id=:id", {"id": runtime.run["module_id"]}
    )[0]
    assert module["status"] == "partial"
    assert module["error_message"] == "校验服务不可用"
    run = env.db.rows(
        "SELECT status FROM agent_module_run WHERE id=:id", {"id": runtime.run["id"]}
    )[0]
    assert run["status"] == "partial"
    assert [item["record_id"] for item in module["items"]] == ["keep"]
    records = module["business_data"]["records"]
    assert [record["id"] for record in records] == ["keep"]
    assert all(record["verification"] == "supported" for record in records)


def test_partial_report_retry_selects_partial_modules(env):
    """空 module_keys 补跑只选部分完成/失败模块；partial 已发布成果保留。"""
    runtime = prepared_runtime(env)
    assert runtime.claim()
    module_key = next(iter(MODULES))
    runtime.finish("partial", "校验服务不可用", state=publishable_state(module_key))
    runtime.release()
    report_id = runtime.report["id"]
    env.db.execute(
        "UPDATE analysis_report SET status='partial' WHERE id=:id", {"id": report_id}
    )
    result = analysis_api.retry_report(report_id, analysis_api.RetryInput(), env.request)
    assert result["status"] == "pending"
    rows = env.db.rows(
        """SELECT m.id,a.attempt FROM analysis_module m JOIN agent_module_run a
        ON a.module_id=m.id AND a.attempt=(
            SELECT max(attempt) FROM agent_module_run WHERE module_id=m.id)
        WHERE m.report_id=:id ORDER BY m.id""",
        {"id": report_id},
    )
    assert [row["id"] for row in rows if row["attempt"] == 2] == [runtime.run["module_id"]]


def test_report_with_all_partial_modules_is_partial(env, monkeypatch):
    """全部模块只有已核实成果时报告是 partial，快照为未完成模块登记缺口。"""

    class Model:
        async def aclose(self):
            pass

    monkeypatch.setattr(env.executor, "model_factory", lambda *a, **kw: Model())
    monkeypatch.setattr(
        worker, "build_module_agent", lambda **kwargs: (kwargs["key"], {}),
    )

    async def invoke(graph, files, *, state=None, **kwargs):
        state.update(publishable_state(graph))
        raise VerificationUnavailable("校验服务不可用")

    monkeypatch.setattr(worker, "invoke_module", invoke)
    row = report(env)
    run_async(env.executor.analyze_report(row))

    result = analysis_api.get_report(row["id"], env.request)
    assert result["status"] == "partial"
    assert len(result["modules"]) == 13
    assert all(module["status"] == "partial" for module in result["modules"])
    assert all(
        [item["record_id"] for item in module["items"]] == ["keep"]
        for module in result["modules"]
    )
    snapshot = env.db.rows(
        "SELECT data FROM analysis_data_snapshot WHERE report_id=:id", {"id": row["id"]}
    )[0]["data"]
    incomplete = [gap for gap in snapshot["gaps"] if gap["code"] == "module_incomplete"]
    assert {gap["module_key"] for gap in incomplete} == {
        module["module_key"] for module in result["modules"]
    }
    # 未核实条目既不能进入模块结果，也不能混进业务数据集。
    assert "drop" not in json.dumps(snapshot, ensure_ascii=False)


def test_cancel_without_worker_closes_queued_and_orphaned_modules(env):
    runtime = prepared_runtime(env)
    report_id = runtime.report["id"]
    env.db.execute("UPDATE agent_module_run SET status='running' WHERE id=:id",
                   {"id": runtime.run["id"]})
    env.db.execute("UPDATE analysis_module SET status='running' WHERE id=:id",
                   {"id": runtime.run["module_id"]})
    result = analysis_api.cancel_report(report_id, env.request)
    assert result == {"status": "canceled", "canceling": False}
    assert analysis_api.cancel_report(report_id, env.request) == result
    current = analysis_api.get_report(report_id, env.request)
    assert all(m["status"] == "canceled" for m in current["modules"])
    assert all(r["status"] == "canceled" for m in current["modules"] for r in m["runs"])
    selected = current["modules"][3]
    analysis_api.retry_report(report_id, analysis_api.RetryInput(
        module_keys=[selected["module_key"]]), env.request)
    after = analysis_api.get_report(report_id, env.request)
    assert [(m["id"], m["runs"][-1]["attempt"]) for m in after["modules"]
            if m["status"] == "pending"] == [(selected["id"], 2)]


def test_cancel_before_modules_created_can_retry(env):
    row = report(env)
    analysis_api.cancel_report(row["id"], env.request)
    assert analysis_api.retry_report(row["id"], analysis_api.RetryInput(), env.request)[
        "status"] == "waiting"


def test_retry_before_modules_created_persists_new_limits(env):
    """模块尚未创建时没有运行账可承载预算;必须更新报告快照供 prepare_report 使用。"""
    row = report(env)
    analysis_api.cancel_report(row["id"], env.request)
    analysis_api.retry_report(
        row["id"],
        analysis_api.RetryInput(max_output_tokens=12345, timeout_seconds=4321),
        env.request,
    )
    persisted = analysis_api.report_row(env.request, row["id"])["runtime_settings"]
    assert persisted["max_output_tokens"] == 12345
    assert persisted["timeout_seconds"] == 4321
    prepared, _ = worker.prepare_report(env.db, analysis_api.report_row(env.request, row["id"]))
    run = env.db.rows(
        """SELECT a.limits FROM agent_module_run a JOIN analysis_module m ON m.id=a.module_id
        WHERE m.report_id=:id ORDER BY a.id LIMIT 1""",
        {"id": prepared["id"]},
    )[0]
    assert run["limits"]["max_output_tokens"] == 12345
    assert run["limits"]["timeout_seconds"] == 4321


def test_retry_waits_for_canceled_controller_to_exit(env):
    from tender.api.shared.errors import ApiProblem

    runtime = prepared_runtime(env)
    report_id = runtime.report["id"]
    with env.engine.connect() as controller:
        controller.execute(text("SELECT pg_advisory_lock(hashtextextended(:key,0))"),
                           {"key": f"analysis_report:{report_id}"})
        try:
            assert analysis_api.cancel_report(report_id, env.request)["canceling"]
            assert analysis_api.get_report(report_id, env.request)["canceling"]
            with pytest.raises(ApiProblem) as caught:
                analysis_api.retry_report(report_id, analysis_api.RetryInput(), env.request)
            assert caught.value.code == "cancellation_pending"
        finally:
            controller.execute(text("SELECT pg_advisory_unlock(hashtextextended(:key,0))"),
                               {"key": f"analysis_report:{report_id}"})
    assert not analysis_api.get_report(report_id, env.request)["canceling"]
    assert analysis_api.retry_report(report_id, analysis_api.RetryInput(), env.request)[
        "status"] == "pending"


def test_cancel_interrupts_active_module_and_releases_quota(env, monkeypatch):
    runtime = prepared_runtime(env)
    started, stopped = asyncio.Event(), asyncio.Event()

    class Model:
        async def aclose(self):
            pass

    async def blocked_request(*args, **kwargs):
        started.set()
        try:
            await asyncio.sleep(60)
        finally:
            stopped.set()

    monkeypatch.setattr(env.executor, "model_factory", lambda *a, **kw: Model())
    monkeypatch.setattr(worker, "build_module_agent", lambda **kw: (None, {}))
    monkeypatch.setattr(worker, "invoke_module", blocked_request)

    async def scenario():
        task = asyncio.create_task(env.executor.execute_module(
            runtime.report, runtime.run | {
                "module_key": next(iter(MODULES)),
            }, runtime.sources))
        try:
            await asyncio.wait_for(started.wait(), 10)
            canceled = await asyncio.to_thread(
                analysis_api.cancel_report, runtime.report["id"], env.request)
            assert canceled["canceling"]
            # 心跳每 15 秒一次，取消最晚在下一次心跳被发现；留出收尾余量。
            await asyncio.wait_for(task, 20)
            assert stopped.is_set()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    run_async(scenario())
    current = analysis_api.get_report(runtime.report["id"], env.request)
    assert not current["canceling"]
    assert all(m["status"] == "canceled" for m in current["modules"])
    assert all(r["status"] == "canceled" for m in current["modules"] for r in m["runs"])


def test_explicit_retry_reparses_completed_module_from_scratch(env):
    """显式指定模块时，已完成的专题也能重新解析：新 attempt 不继承旧草稿。"""
    runtime = prepared_runtime(env)
    assert runtime.claim()
    runtime.reserve("model")
    field = {
        "id": "done1",
        "field": "质保",
        "group": "",
        "sort_order": 0,
        "values": [
            {
                "value": "质保三年",
                "citations": [
                    {
                        "source_id": runtime.sources[0]["source_id"],
                        "project_id": runtime.report["project_id"],
                        "quote": "质保三年",
                    }
                ],
            }
        ],
        "note": "",
        "verification": "supported",
    }
    draft = {"fields": [field], "relations": [], "research_summary": "已经检索"}
    runtime.save({"staged_items": [field], "staged_items_verified": True, "draft": draft})
    runtime.finish("completed", draft=draft)
    runtime.release()
    report_id = runtime.report["id"]
    module_id = runtime.run["module_id"]
    key = env.db.rows("SELECT module_key FROM analysis_module WHERE id=:id", {"id": module_id})[0][
        "module_key"
    ]
    env.db.execute("UPDATE analysis_report SET status='completed' WHERE id=:id", {"id": report_id})
    assert (
        analysis_api.retry_report(
            report_id, analysis_api.RetryInput(module_keys=[key]), env.request
        )[
            "status"
        ]
        == "pending"
    )
    rows = env.db.rows(
        "SELECT attempt,state FROM agent_module_run WHERE module_id=:id ORDER BY attempt",
        {"id": module_id},
    )
    assert [row["attempt"] for row in rows] == [1, 2]
    # 重新解析不能继承旧草稿，否则新图会直接以旧成果收尾，等于没有重跑。
    assert rows[1]["state"] == {}
    assert (
        env.db.rows("SELECT status FROM analysis_module WHERE id=:id", {"id": module_id})[0][
            "status"
        ]
        == "pending"
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
            "field": "历史参考",
            "group": "",
            "sort_order": 0,
            "values": [{"value": "五年", "citations": [{"collection_id": cid}]}],
            "note": "",
        }
        shown = analysis_api.visible_items(
            env.db, [item], env.db.collections_for_project(runtime.report["project_id"])
        )
        assert shown[0]["verification"] == "unavailable"
    finally:
        runtime.release()


def test_retry_uses_live_config_and_keeps_report_snapshot_untouched(env):
    """用户改大预算后补跑必须按配置中心当前值执行，不能被创建时的旧快照锁死。"""
    runtime = prepared_runtime(env)
    old = env.db.rows(
        "SELECT limits FROM agent_module_run WHERE id=:id", {"id": runtime.run["id"]}
    )[0]["limits"]
    assert old["max_model_calls"] == 40 and old["context_tokens"] == 24000
    assert old["max_finish_corrections"] == 2
    assert runtime.claim()
    runtime.finish("failed", "故障注入")
    runtime.release()
    env.db.execute(
        "UPDATE analysis_report SET status='partial' WHERE id=:id", {"id": runtime.report["id"]}
    )
    # 模拟用户在配置中心调大预算（values 只含覆盖项，读取时会与默认值合并）。
    env.db.execute(
        """INSERT INTO config_release (company_id, version_no, values, status, created_by)
        VALUES (1, 1, CAST(:values AS JSONB), 'active', '测试')""",
        {"values": json.dumps({"analysis.max_model_calls": 80, "analysis.context_tokens": 200000,
                               "analysis.max_finish_corrections": 5})},
    )
    analysis_api.retry_report(runtime.report["id"], analysis_api.RetryInput(), env.request)
    runs = env.db.rows(
        "SELECT * FROM agent_module_run WHERE module_id=:id ORDER BY attempt",
        {"id": runtime.run["module_id"]},
    )
    assert runs[-1]["attempt"] == 2
    assert runs[-1]["limits"]["max_model_calls"] == 80
    assert runs[-1]["limits"]["context_tokens"] == 200000
    assert runs[0]["limits"]["max_finish_corrections"] == 2
    assert runs[-1]["limits"]["max_finish_corrections"] == 5
    # 未在配置中心显式调整的键回落默认值，同样不沿用旧快照。
    assert runs[-1]["limits"]["max_tool_calls"] == 48
    # 报告创建时的快照保持原值，只作为历史记录，不被补跑改写。
    assert (
        analysis_api.report_row(env.request, runtime.report["id"])["runtime_settings"][
            "max_model_calls"
        ]
        == 40
    )


def test_stale_run_without_holder_returns_to_queue(env):
    """执行者消失（锁已释放、租约过期、状态仍是 running）的运行必须让位。

    现场故障形态：模块异常收尾失败后留下这种僵尸运行，它没有配额锁却被算作
    「本报告最靠前的待执行运行」，使同报告后面的模块每次抢槽都被拒绝，整份报告
    永远停在「分析中」。收殓后再争抢，报告才能继续推进。
    """
    first, second = prepared_runtimes(env, 2)
    try:
        assert first.claim()
        # 会话锁随进程消失（release 等价于 PostgreSQL 侧自动释放），但状态与租约照现场保留。
        first.release()
        env.db.execute(
            "UPDATE agent_module_run SET lease_until=now()-interval '1 minute' WHERE id=:id",
            {"id": first.run["id"]},
        )
        # 其他模块抢槽时先收殓僵尸：没有执行者也不再有租约的运行回到排队态。
        assert not second.claim()
        assert (
            env.db.rows(
                "SELECT status, lease_until FROM agent_module_run WHERE id=:id",
                {"id": first.run["id"]},
            )[0]["status"]
            == "pending"
        )
        # 收殓后该模块自身可重新领取，报告不会永久卡在等待配额。
        assert first.claim()
    finally:
        first.release()
        second.release()


def test_publish_failure_still_records_terminal_run_state(env, monkeypatch):
    """成果发布失败不能带走运行终态。

    业务库缺 business_data 等列时 UPDATE analysis_module 必然报错；若它与运行终态
    同一事务回滚，留下的就是 lease 已过期的 status='running' 僵尸运行。
    """

    def broken_publish(self, conn, publish):
        raise RuntimeError('column "business_data" of relation "analysis_module" does not exist')

    runtime = prepared_runtime(env)
    try:
        assert runtime.claim()
        # 成果发布在运行账实现的 savepoint 内，故障点必须注在真正执行发布的仓储上。
        monkeypatch.setattr(run_store.AgentRunStore, "_publish", broken_publish)
        runtime.finish("completed", draft={"fields": [], "business_data": {}, "relations": []})
        run = env.db.rows(
            """SELECT status, error_message, lease_until, finished_at
            FROM agent_module_run WHERE id=:id""",
            {"id": runtime.run["id"]},
        )[0]
        assert run["status"] == "failed"
        assert "模块成果发布失败" in run["error_message"]
        assert run["lease_until"] is None and run["finished_at"] is not None
        module = env.db.rows(
            "SELECT status FROM analysis_module WHERE id=:id", {"id": runtime.run["module_id"]}
        )[0]
        # 成果没发布，模块不能对外显示为完成。
        assert module["status"] == "failed"
    finally:
        runtime.release()
