"""原生 PostgreSQL 验证增量状态与展示投影、到期收尾及旧执行者隔离。"""

import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_deepagents_runtime
from analysis_review_fixture import check_results
from test_deepagents_runtime import prepared_runtime, publishable_state, report

from tender.application.analysis.protocol import PROTOCOL_VERSION
from tender.application.analysis.service import AnalysisService
from tender.application.analysis.topic_flow import FLOW_KEY, TopicFlow, TopicUpdate

env = test_deepagents_runtime.env
pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库集成验证"
)


def test_merged_batch_read_uses_bounded_postgres_windows(env):
    import asyncio

    from tender.adapters.pg.analysis.checkpoints import run_async
    from tender.application.analysis.research import ResearchSession

    row = report(env, topic_flow=True)
    # 多个独立元素确保原文派生至少16块，真实仓储仍执行每次最多12块的契约。
    env.db.execute("""INSERT INTO element
        (version_id,run_id,page_no,order_no,anchor,type,text,bbox_x0,bbox_y0,bbox_x1,bbox_y1)
        SELECT e.version_id,e.run_id,1,g.n,'p1b' || g.n,'title','独立条款' || g.n,0,0,1,1
        FROM (SELECT version_id,run_id FROM element LIMIT 1) e
        CROSS JOIN generate_series(2,20) AS g(n)""")
    row, sources = test_deepagents_runtime.worker.prepare_report(env.db, row)
    source = next(s for s in sources if s["project_id"] == row["project_id"])
    anchors = [env.db.read_chunk_window(source, offset, 1).rows[0] for offset in (2, 7)]
    reads = []

    async def read(selected, offset, limit):
        reads.append((offset, limit))
        return await asyncio.to_thread(env.db.read_chunk_window, selected, offset, limit)

    async def authorize():
        pass

    async def forbidden(*args):
        raise AssertionError("已知锚点补读无需重新检索")

    research = ResearchSession(sources, row["project_id"], forbidden, read, authorize)
    research.seen = {r["block_id"]: r for r in anchors}
    result = run_async(research.read_evidence([r["block_id"] for r in anchors], 2, 8))
    assert reads == [(0, 12), (12, 4)]
    assert [r["offset"] for r in result["blocks"]] == list(range(16))
    assert research.tool_calls == 1 and len(research.seen) == 16
    assert research.events[-1]["action"] == "read_result"


def progress_state(runtime):
    state = publishable_state("project_basic_info_parsing")
    state["staged_items_verified"] = False
    state["topic_flow"] = {"entries": {}, "evidence_topics": {},
                           "audit": {"round": 0, "results": {}}}
    state["business_gaps"] = [{"key": "execution:incomplete", "detail": "截止时间已到",
                               "topic": "身份", "scope": {"kind": "unknown", "lot_refs": []},
                               "code": "search_exhausted"}]
    return state


def test_new_report_freezes_topic_flow_and_old_report_remains_legacy(env):
    current = report(env, topic_flow=True)
    old = report(env)
    # 新建报告始终使用当前协议；历史读取用真实旧快照验证，不能靠失效的创建参数模拟。
    old["skill_snapshot"].pop(FLOW_KEY)
    env.db.execute("UPDATE analysis_report SET skill_snapshot=CAST(:snapshot AS JSONB) "
                   "WHERE id=:id",
                   {"snapshot": json.dumps(old["skill_snapshot"]), "id": old["id"]})
    old = test_deepagents_runtime.analysis_api.report_row(env.request, old["id"])
    assert current["skill_snapshot"][FLOW_KEY] == PROTOCOL_VERSION
    assert FLOW_KEY not in old["skill_snapshot"]
    assert current["runtime_version"] == old["runtime_version"]


def test_audit_target_and_checked_version_survive_database_reload(env):
    from tender.adapters.pg.analysis.checkpoints import run_async
    from tender.application.analysis.research import AgentLimits
    from tender.application.analysis.topic_flow import TopicIncomplete

    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    try:
        state = publishable_state("project_basic_info_parsing")
        state["staged_items"] = state["staged_items"][:1]
        state["business_topics"] = [{"key": "a", "title": "质保", "checks": ["期限"]}]
        research = SimpleNamespace(seen={"s1r1c0": {"content": "质保三年"}},
                                   sources=[], limits=AgentLimits())
        flow = TopicFlow(state, research)
        flow.apply([TopicUpdate.model_validate({
            "topic": "a", "scope": {"kind": "common", "lot_refs": []},
            "checked": ["期限"], "evidence_ids": ["s1r1c0"], "record_keys": ["warranty"],
        })], {"warranty"})
        calls = []

        async def save(value):
            runtime.save(value)

        async def first(payload):
            return {"issues": [{"topic": "a", "detail": "核对附件例外",
                                "target": "合同附件九第七条", "evidence_ids": [],
                                "record_keys": []}]}

        assert not run_async(flow.audit(first, save))
        stored = env.db.rows("SELECT state FROM agent_module_run WHERE id=:id",
                             {"id": runtime.run["id"]})[0]["state"]
        restored = TopicFlow(stored, research)
        assert "合同附件九第七条" in restored.prompt()
        assert stored["topic_flow"]["audit"]["topic_signatures"]

        async def repaired(payload):
            calls.append(payload)
            return {"issues": []}

        assert run_async(restored.audit(repaired, save))
        current = env.db.rows("SELECT state FROM agent_module_run WHERE id=:id",
                              {"id": runtime.run["id"]})[0]["state"]
        restored = TopicFlow(current, research)
        assert run_async(restored.audit(repaired, save)) and len(calls) == 1
        research.seen["s1r1c0"]["content"] += "但易损件一年"
        with pytest.raises(TopicIncomplete, match="发生变化"):
            run_async(restored.audit(repaired, save))
    finally:
        runtime.release()


def test_expired_incremental_run_preserves_verified_projection_and_state_atomically(env):
    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    state = progress_state(runtime)
    runtime.save(state)
    env.db.execute("UPDATE agent_module_run SET deadline_at=now()-interval '1 second' WHERE id=:id",
                   {"id": runtime.run["id"]})
    with pytest.raises(TimeoutError):
        runtime.reserve("model")
    runtime.finish("partial", "截止时间已到", state=state)
    row = env.db.rows("SELECT state,status,model_calls FROM agent_module_run WHERE id=:id",
                      {"id": runtime.run["id"]})[0]
    module = env.db.rows("SELECT items,business_data,status FROM analysis_module WHERE id=:id",
                         {"id": runtime.run["module_id"]})[0]
    assert row["state"]["business_gaps"] == state["business_gaps"]
    assert row["status"] == module["status"] == "partial"
    assert row["model_calls"] == 0
    assert [r["id"] for r in module["business_data"]["records"]] == ["keep"]
    assert "progress" in module["business_data"]
    runtime.release()


def test_expired_run_with_only_pending_review_does_not_leave_old_result_effective(env):
    from tender.application.analysis.data import assemble_dataset

    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    state = progress_state(runtime)
    runtime.save(state)
    state["staged_items"][0]["review_status"] = "needs_review"
    env.db.execute("UPDATE agent_module_run SET deadline_at=now()-interval '1 second' WHERE id=:id",
                   {"id": runtime.run["id"]})
    runtime.finish("failed", "只有待复核事项，无有效成果", state=state)
    module = env.db.rows("SELECT module_key,title,status,business_data "
                         "FROM analysis_module WHERE id=:id",
                         {"id": runtime.run["module_id"]})[0]
    assert module["business_data"]["records"][0]["review_status"] == "needs_review"
    data = assemble_dataset([module], [])
    assert not data["requirements"] and not data["facts"]
    assert any(g["code"] == "record_needs_review" for g in data["gaps"])
    runtime.release()


@pytest.mark.parametrize("failure", ["cancel", "lease", "owner", "lock"])
@pytest.mark.parametrize("status", ["partial", "failed"])
def test_expired_settlement_cannot_bypass_execution_restrictions(env, failure, status):
    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    state = progress_state(runtime)
    runtime.save(state)
    if failure == "cancel":
        env.db.execute("UPDATE analysis_report SET status='canceled' WHERE id=:id",
                       {"id": runtime.report["id"]})
    elif failure == "lease":
        env.db.execute("""UPDATE agent_module_run SET lease_until=now()-interval '1 second'
                       WHERE id=:id""",
                       {"id": runtime.run["id"]})
    elif failure == "owner":
        env.db.execute("UPDATE agent_module_run SET owner=CAST(:owner AS UUID) WHERE id=:id",
                       {"id": runtime.run["id"], "owner": str(uuid4())})
    else:
        runtime.store.lock_connection.invalidate()
    with pytest.raises(InterruptedError):
        runtime.finish(status, state=state)
    assert env.db.rows("SELECT status FROM agent_module_run WHERE id=:id",
                       {"id": runtime.run["id"]})[0]["status"] == "running"
    runtime.release()


def test_progress_is_hidden_after_source_access_is_revoked(env):
    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    state = progress_state(runtime)
    runtime.save(state)
    service = AnalysisService(env.db, 1, None, None, None)
    key = "project_basic_info_parsing"
    assert "progress" in service.get_module_records(runtime.report["id"], key)
    env.db.execute("UPDATE knowledge_collection SET deleted_at=now() WHERE id=:id",
                   {"id": runtime.sources[0]["collection_id"]})
    assert "progress" not in service.get_module_records(runtime.report["id"], key)
    with pytest.raises(PermissionError):
        runtime.finish("partial", state=state)
    runtime.release()


def test_verified_unknown_scope_is_saved_and_reloaded_without_becoming_complete(env):
    from tender.application.knowledge.content import citation

    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    try:
        state = publishable_state("project_basic_info_parsing")
        state["staged_items"] = state["staged_items"][:1]
        item = state["staged_items"][0]
        item["business"]["scope"] = {"kind": "unknown", "lot_refs": []}
        original = env.db.readable_chunks(runtime.sources[0])[0]
        ref = citation(original, "质保三年")
        item["values"][0]["citations"] = [ref]
        item["business"]["citations"] = [ref]
        state["business_topics"] = [{"key": "warranty", "title": "质保", "checks": ["范围"]}]
        research = SimpleNamespace(seen={original["block_id"]: original})
        flow = TopicFlow(state, research)
        flow.data["evidence_topics"][original["block_id"]] = ["warranty"]
        updates = flow.prepare_updates([item], [TopicUpdate(topic="warranty")])
        flow.validate_records([item], updates)
        flow.apply(updates, {"warranty"})
        runtime.save(state)
        service = AnalysisService(env.db, 1, None, None, None)
        payload = service.get_module_records(runtime.report["id"], "project_basic_info_parsing")
        assert len(payload["records"]) == 1
        assert payload["records"][0]["scope"]["kind"] == "unknown"
        assert payload["progress"]["topics"][0]["status"] != "ready"
        stored = env.db.rows("SELECT state FROM agent_module_run WHERE id=:id",
                             {"id": runtime.run["id"]})[0]["state"]
        restored = TopicFlow(stored, research)
        assert restored.pending()
        assert restored.entries[0]["record_keys"] == ["warranty"]
        runtime.finish("partial", "适用范围待确认，保留核实正文", state=stored)
    finally:
        runtime.release()


def test_scope_revision_persists_current_progress_and_review_state_across_reload(env):
    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    try:
        common = {"kind": "common", "lot_refs": []}
        narrowed = {"kind": "lots", "lot_refs": ["A标段"]}
        state = publishable_state("project_basic_info_parsing")
        state["staged_items"] = state["staged_items"][:1]
        state["business_topics"] = [{"key": "warranty", "title": "质保", "checks": ["范围"]}]
        research = SimpleNamespace(seen={"s1r1c0": {"content": "质保三年"}})
        flow = TopicFlow(state, research)
        initial = {"topic": "warranty", "scope": common, "status": "ready", "checked": ["范围"],
                   "evidence_ids": ["s1r1c0"], "record_keys": ["warranty"], "detail": "范围已核对"}
        flow.apply([TopicUpdate.model_validate(initial)], {"warranty"})
        runtime.save(state)
        state["staged_items"][0]["business"]["scope"] = narrowed
        revision = TopicUpdate.model_validate(initial | {
            "scope": narrowed, "replaces_scopes": [common],
        })
        flow.apply([revision], {"warranty"})
        runtime.save(state)
        stored = env.db.rows("SELECT state,model_calls,tool_calls FROM agent_module_run "
                             "WHERE id=:id",
                             {"id": runtime.run["id"]})[0]
        restored = TopicFlow(stored["state"], research)
        restored.apply([revision], {"warranty"})
        assert len(restored.entries) == 1 and restored.entries[0]["scope"] == narrowed
        module = env.db.rows("SELECT business_data FROM analysis_module WHERE id=:id",
                             {"id": runtime.run["module_id"]})[0]["business_data"]
        assert module["progress"]["topics"][0]["scope"] == narrowed
        assert module["records"][0]["review_status"] == "needs_review"
        assert stored["model_calls"] == stored["tool_calls"] == 0
        restored.state["staged_items"][0]["review_status"] = "current"
        restored.sync()
        assert not restored.pending()
        runtime.save(restored.state)
        published = env.db.rows("SELECT business_data FROM analysis_module WHERE id=:id",
                                {"id": runtime.run["module_id"]})[0]["business_data"]
        assert published["records"][0]["id"] == "keep"
        assert published["records"][0]["scope"] == narrowed
        assert published["progress"]["topics"][0]["status"] == "ready"
    finally:
        runtime.release()


def test_exhausted_search_work_is_persisted_and_settles_without_audit_requests(env):
    from tender.application.analysis.research import AgentLimits, ToolArgumentError
    from tender.application.analysis.search_control import TopicSearch

    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    try:
        common = {"kind": "common", "lot_refs": []}
        state = publishable_state("project_basic_info_parsing")
        state["staged_items"] = state["staged_items"][:1]
        state["business_topics"] = [{"key": "warranty", "title": "质保", "checks": ["期限"]}]
        research = SimpleNamespace(seen={"s1r1c0": {"content": "质保三年"}}, limits=AgentLimits())
        flow = TopicFlow(state, research)
        task = {"detail": "核对起算点", "record_keys": ["warranty"]}
        progress = {"topic": "warranty", "scope": common, "status": "researching",
                    "checked": ["期限"], "evidence_ids": ["s1r1c0"], "tasks": [task],
                    "record_keys": ["warranty"], "detail": "起算点待核对"}
        flow.apply([TopicUpdate.model_validate(progress)], {"warranty"})
        control = TopicSearch(flow)
        for index in range(3):
            target = control.begin("search_document", {"topic_keys": ["warranty"],
                                                       "query": f"起算点换词{index}",
                                                       "work": task["detail"]})
            control.end(target, {"blocks": [], "already_read": ["s1r1c0"]}, {"s1r1c0"})
            runtime.save(state)
        stored = env.db.rows("SELECT state FROM agent_module_run WHERE id=:id",
                             {"id": runtime.run["id"]})[0]["state"]
        restored = TopicFlow(stored, research)
        restored.apply([TopicUpdate.model_validate(progress)], {"warranty"})
        with pytest.raises(ToolArgumentError, match="耗尽"):
            TopicSearch(restored).begin("search_document", {"topic_keys": ["warranty"],
                                                           "work": task["detail"]})
        assert TopicSearch.summary(stored)["research_calls"] == 3
        assert stored["topic_flow"]["audit"]["results"] == {}
        runtime.finish("partial", "起算点检索无进展", state=stored)
        module = env.db.rows("SELECT status,business_data FROM analysis_module WHERE id=:id",
                             {"id": runtime.run["module_id"]})[0]
        assert module["status"] == "partial" and len(module["business_data"]["records"]) == 1
    finally:
        runtime.release()


def test_check_exhaustion_preserves_other_work_and_stable_task_ids_across_reload(env):
    from tender.application.analysis.research import AgentLimits, ToolArgumentError
    from tender.application.analysis.search_control import TopicSearch

    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    try:
        state = publishable_state("project_basic_info_parsing")
        state["staged_items"] = state["staged_items"][:1]
        state["business_topics"] = [{"key": "a", "title": "质保", "checks": ["期限", "起算点"]}]
        research = SimpleNamespace(seen={"s1r1c0": {"content": "质保三年"}}, limits=AgentLimits())
        flow = TopicFlow(state, research)
        progress = {"topic": "a", "scope": {"kind": "common", "lot_refs": []},
                    "status": "researching", "checked": [], "record_keys": ["warranty"],
                    "evidence_ids": ["s1r1c0"], "detail": "继续核对",
                    "tasks": [{"detail": "找附件"}]}
        flow.apply([TopicUpdate.model_validate(progress)], {"warranty"})
        task_id = next(iter(flow.entries[0]["tasks"]))
        control = TopicSearch(flow)
        for index in range(3):
            work = control.begin("search_document", {"topic_keys": ["a"], "work": "期限",
                                                     "query": str(index)})
            control.end(work, {"blocks": []}, set(research.seen))
        with pytest.raises(ToolArgumentError):
            control.begin("search_document", {"topic_keys": ["a"], "work": "期限", "query": "再找"})
        runtime.save(state)
        stored = env.db.rows("SELECT state FROM agent_module_run WHERE id=:id",
                             {"id": runtime.run["id"]})[0]["state"]
        restored = TopicFlow(stored, research)
        assert restored.entries[0]["blocked_checks"] == ["期限"]
        assert restored.entries[0]["status"] in {"researching", "needs_review"}
        assert TopicSearch(restored).begin("search_document", {
            "topic_keys": ["a"], "work": "起算点",
        })
        renamed = progress | {"tasks": [{"task_id": task_id, "detail": "核对附件原文"}]}
        restored.apply([TopicUpdate.model_validate(renamed)], {"warranty"})
        runtime.save(stored)
        projected = env.db.rows("SELECT business_data FROM analysis_module WHERE id=:id",
                                {"id": runtime.run["module_id"]})[0]["business_data"]
        topic = projected["progress"]["topics"][0]
        assert topic["tasks"][0]["task_id"] == task_id
        assert topic["tasks"][0]["detail"] == "核对附件原文"
        assert topic["blocked_checks"] == ["期限"]
    finally:
        runtime.release()


@pytest.mark.parametrize("max_calls", [4, 5, 6, 40])
def test_new_report_researches_before_synthesis_and_independent_audit(env, monkeypatch, max_calls):
    import json

    from langchain_core.messages import AIMessage, message_to_dict

    from tender.adapters.pg.analysis.checkpoints import run_async
    from tender.ports.llm.chat import Completion

    runtime = prepared_runtime(env, topic_flow=True)
    env.db.execute("""UPDATE agent_module_run SET limits=jsonb_set(limits,'{max_model_calls}',
                   CAST(:calls AS JSONB)) WHERE id=:id""",
                   {"calls": str(max_calls), "id": runtime.run["id"]})
    key = "project_basic_info_parsing"
    topics = [{"key": "warranty", "title": "质保", "checks": ["期限"]},
              {"key": "quantity", "title": "采购数量", "checks": ["数量"]}]
    snapshot = runtime.report["skill_snapshot"]
    snapshot[key + "/references/coverage.json"] = json.dumps(topics, ensure_ascii=False)
    env.db.execute("UPDATE analysis_report SET skill_snapshot=CAST(:rules AS JSONB) WHERE id=:id",
                   {"rules": json.dumps(snapshot), "id": runtime.report["id"]})
    observed, completed = [], []

    class Router(test_deepagents_runtime.NativeRouter):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

        async def chat(self, messages, tools):
            await self.reserve()
            self.calls += 1
            if self.calls == 1:
                name, args = "list_documents", {}
            elif self.calls == 2:
                name, args = "search_document", {"query": "质保", "work_ids": ["w1", "w2"]}
            elif self.calls == 3:
                evidence = next(json.loads(m["data"]["content"])["blocks"][0]["id"]
                                for m in messages if m["type"] == "tool"
                                and m["data"].get("name") == "search_document")
                name, args = "update_research", {"updates": [{
                    "work_ids": ["w1", "w2"], "scope": {"kind": "common", "lot_refs": []},
                    "detail": "已核对完整条款", "evidence_ids": [evidence],
                }]}
            else:
                index = 0 if self.calls == 4 else 1
                if index == 1:
                    saved = env.db.rows("SELECT business_data FROM analysis_module WHERE id=:id",
                                        {"id": runtime.run["module_id"]})[0]
                    observed.append(saved["business_data"])
                topic = topics[index]
                result = next(json.loads(m["data"]["content"]) for m in reversed(messages)
                              if m["type"] == "tool" and m["data"].get("name") == "search_document")
                block_id = (result["blocks"][0]["id"] if result["blocks"]
                            else result["already_read"][0])
                quote = "质保三年" if index == 0 else "采购交换机10台"
                scope = {"kind": "common", "lot_refs": []}
                name, args = "submit_analysis", {"records": [{
                    "kind": "requirement", "title": topic["title"],
                    "group": "项目基本信息", "content": {"字段": topic["title"], "内容": quote},
                    "scope": scope, "block_ids": [block_id],
                    "work_ids": [f"w{index + 1}"],
                }], "final": index == 1}
            return self.respond(Completion(
                content="", model="offline", agent_message=message_to_dict(
                    AIMessage(content="", tool_calls=[{"name": name, "args": args,
                                                       "id": f"incremental-{self.calls}"}]))))

        async def complete(self, prompt):
            await self.reserve()
            payload = json.loads(prompt.rsplit("\n", 1)[-1])
            completed.append(payload)
            reviews = {row["record_id"]: {"supported": True, "issues": [],
                       "block_ids": row["block_ids"]}
                       for row in payload["records"]}
            checks = check_results(payload)
            return Completion(content=json.dumps({"reviews": reviews, "issues": [],
                                                   "check_results": checks}),
                              model="offline")

        async def aclose(self):
            pass

    monkeypatch.setattr(env.executor, "model_factory",
                        lambda feature, purpose, **kwargs: Router(purpose=purpose, **kwargs))
    run = env.db.rows("SELECT a.*,m.module_key FROM agent_module_run a JOIN analysis_module m "
                      "ON m.id=a.module_id WHERE a.id=:id", {"id": runtime.run["id"]})[0]
    run_async(env.executor.execute_module(runtime.report, run, runtime.sources))
    module = env.db.rows("SELECT status,business_data FROM analysis_module WHERE id=:id",
                         {"id": run["module_id"]})[0]
    if max_calls in {4, 5}:
        assert module["status"] == "failed"
        assert len(module["business_data"]["records"]) == 0
        stored = env.db.rows("SELECT state,model_calls FROM agent_module_run WHERE id=:id",
                             {"id": run["id"]})[0]
        assert stored["model_calls"] == max_calls and len(completed) == 0
        assert stored["state"]["research"]["seen"]
        assert stored["state"]["staged_items"]
        assert any(g["key"] == "execution:incomplete"
                   for g in stored["state"]["business_gaps"])
        return
    assert module["status"] == "completed"
    assert len(observed) == 1 and len(observed[0]["records"]) == 0
    assert len(module["business_data"]["records"]) == 2
    # 两主题合包后六次预算已足够；原文只传一份，核对清单仍包含全部主题。
    assert len(completed) == 1
    assert set(completed[0]["topics"]) == {"quantity", "warranty"}
    assert {row["topic"] for row in completed[0]["checks"]} == {"quantity", "warranty"}
    assert len(completed[0]["records"]) == 2
    # 同一原文可置于共享上下文，核对完整发送内容，避免把位置优化误判成丢失证据。
    spans = completed[0]["evidence"] + completed[0]["context_evidence"]
    assert len(spans) == 1 and spans[0]["id"] == "s1r1g2c0"
    stored = env.db.rows("SELECT state,model_calls FROM agent_module_run WHERE id=:id",
                         {"id": run["id"]})[0]
    assert stored["state"]["topic_flow"]["audit"]["done"]
    assert set(stored["state"]["topic_flow"]["audit"]["completed_topics"]) == {
        "0:quantity", "0:warranty",
    }
    assert stored["model_calls"] == 6
    # JSON审查账从真实数据库恢复后复用已完成请求，资料版本变化则拒绝旧完成状态。
    from tender.application.analysis.research import AgentLimits
    from tender.application.analysis.review import audit_combined
    from tender.application.analysis.topic_flow import TopicIncomplete

    research = SimpleNamespace(seen=stored["state"]["research"]["seen"],
                               events=stored["state"]["research"]["events"],
                               sources=runtime.sources, limits=AgentLimits())
    restored = TopicFlow(stored["state"], research)

    async def forbidden(_):
        raise AssertionError("恢复不应新增模型请求")

    async def save(_):
        pass

    assert run_async(audit_combined(restored, forbidden, save))
    research.seen["s1r1g2c0"]["content"] += "但补遗变更质保期限"
    with pytest.raises(TopicIncomplete, match="数据变化"):
        run_async(audit_combined(restored, forbidden, save))
