"""原生 PostgreSQL 验证增量状态与展示投影、到期收尾及旧执行者隔离。"""

import json
import os
from uuid import uuid4

import pytest
import test_deepagents_runtime
from test_deepagents_runtime import draft_state, prepared_runtime, report

from tender.api.analysis import routes as analysis_api

env = test_deepagents_runtime.env
pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库集成验证"
)


def test_merged_batch_read_uses_bounded_postgres_windows(env):
    import asyncio

    from tender.adapters.pg.analysis.checkpoints import run_async
    from tender.application.shared.research import ResearchSession

    row = report(env)
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


def progress_state():
    state = draft_state("project_basic_info_parsing")
    state["agent_progress"] = {"protocol": state["agent_workspace"]["protocol"], "draft_count": 2}
    state["business_gaps"] = [{"key": "execution:incomplete", "detail": "截止时间已到",
                               "topic": "身份", "scope": {"kind": "unknown", "lot_refs": []},
                               "code": "search_exhausted"}]
    return state


@pytest.mark.parametrize("failure", ["cancel", "lease", "owner", "lock"])
@pytest.mark.parametrize("status", ["partial", "failed"])
def test_expired_settlement_cannot_bypass_execution_restrictions(env, failure, status):
    runtime = prepared_runtime(env)
    assert runtime.claim()
    state = progress_state()
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
    runtime = prepared_runtime(env)
    assert runtime.claim()
    state = progress_state()
    runtime.save(state)
    service = analysis_api.analysis_service(env.request)
    assert "progress" in service.get_report(runtime.report["id"])["modules"][0]
    env.db.execute("UPDATE knowledge_collection SET deleted_at=now() WHERE id=:id",
                   {"id": runtime.sources[0]["collection_id"]})
    assert "progress" not in service.get_report(runtime.report["id"])["modules"][0]
    with pytest.raises(PermissionError):
        runtime.finish("partial", state=state)
    runtime.release()


@pytest.mark.parametrize("max_calls", [4, 5, 6, 40])
def test_single_agent_can_search_after_review_and_budget_never_publishes_draft(
    env, monkeypatch, max_calls,
):
    from langchain_core.messages import AIMessage, message_to_dict

    from tender.adapters.pg.analysis.checkpoints import run_async
    from tender.application.analysis.drafts import DraftWorkspace
    from tender.ports.llm.chat import Completion

    runtime = prepared_runtime(env)
    env.db.execute("""UPDATE agent_module_run SET limits=jsonb_set(limits,'{max_model_calls}',
                   CAST(:calls AS JSONB)) WHERE id=:id""",
                   {"calls": str(max_calls), "id": runtime.run["id"]})
    observed = []

    class Router(test_deepagents_runtime.NativeRouter):
        async def chat(self, messages, tools):
            if self.calls < 2:
                return await super().chat(messages, tools)
            await self.reserve()
            self.calls += 1
            names = {t["function"]["name"] for t in tools}
            assert {"submit_analysis", "record_review", "search_document"} <= names
            assert "complete_research" not in names
            result = next(json.loads(m["data"]["content"]) for m in messages
                if m["type"] == "tool" and m["data"].get("name") == "search_document")
            bid = result["blocks"][0]["id"]
            if self.calls == 3:
                name, args = "submit_analysis", {"records": [{
                    "kind": "requirement", "group": "项目基本信息",
                    "content": {"字段": "质保期限", "内容": "质保三年"},
                    "scope": {"kind": "common"}, "block_ids": [bid],
                }]}
            else:
                receipt = next(json.loads(m["data"]["content"])["accepted"][0]
                    for m in messages if m["type"] == "tool"
                    and m["data"].get("name") == "submit_analysis")
                if self.calls == 4:
                    name, args = "record_review", {"records": [{
                        "record_id": receipt["id"], "version": 1, "status": "passed",
                        "reason": "原文质保三年，核对期限与范围", "block_ids": [bid],
                    }]}
                elif self.calls == 5:
                    observed.append(env.db.rows(
                        "SELECT business_data FROM analysis_module WHERE id=:id",
                        {"id": runtime.run["module_id"]},
                    )[0]["business_data"].get("records", []))
                    name, args = "search_document", {"query": "采购数量"}
                else:
                    name, args = "submit_analysis", {"final": True,
                        "record_ids": [receipt["id"]], "summary": "核对质保及相关要求"}
            return self.respond(Completion(content="", model="fixture",
                agent_message=message_to_dict(AIMessage(content="", tool_calls=[{
                    "name": name, "args": args, "id": f"single-{self.calls}",
                }]))))

        async def complete(self, prompt):
            raise AssertionError("不得调用独立审查模型")

    monkeypatch.setattr(env.executor, "model_factory",
                        lambda feature, purpose, **kwargs: Router(purpose=purpose, **kwargs))
    run = env.db.rows("SELECT a.*,m.module_key FROM agent_module_run a JOIN analysis_module m "
                      "ON m.id=a.module_id WHERE a.id=:id", {"id": runtime.run["id"]})[0]
    run_async(env.executor.execute_module(runtime.report, run, runtime.sources))
    stored = env.db.rows("SELECT * FROM agent_module_run WHERE id=:id", {"id": run["id"]})[0]
    module = env.db.rows("SELECT * FROM analysis_module WHERE id=:id",
                         {"id": run["module_id"]})[0]
    assert stored["model_calls"] == min(max_calls, 6)
    assert len(stored["state"]["staged_items"]) == 1
    if max_calls < 6:
        assert module["status"] == "partial"
        assert not module["business_data"].get("records")
        assert not stored["state"]["agent_workspace"]["finalized"]
        return
    assert module["status"] == "completed" and observed == [[]]
    assert len(module["business_data"]["records"]) == 1
    state = stored["state"]
    book = DraftWorkspace(state, state["research"]["seen"], run["module_key"])
    rid = state["staged_items"][0]["id"]
    assert book.review_current(rid)
    book.seen[next(iter(book.seen))]["content"] += "补遗修改质保期限"
    assert not book.review_current(rid)
