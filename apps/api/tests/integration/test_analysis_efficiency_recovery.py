"""真实PostgreSQL保存合包回执后中断，恢复只能投影，不能再次请求模型。"""

import asyncio
import json
import os

import pytest
import test_deepagents_runtime
from analysis_review_fixture import check_results
from test_deepagents_runtime import prepared_runtime, publishable_state

from tender.application.analysis.research import ResearchSession
from tender.application.analysis.review import audit_combined, review_call_count, review_scope
from tender.application.analysis.topic_flow import TopicFlow, identity
from tender.application.knowledge.content import citation

env = test_deepagents_runtime.env
pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要隔离数据库集成验证",
)


@pytest.mark.parametrize("legacy", [False, True])
def test_frozen_shared_review_survives_saved_response_without_resetting_attempt_or_budget(
    env, legacy,
):
    runtime = prepared_runtime(env)
    assert runtime.claim()
    original_deadline, original_attempt = runtime.run["deadline_at"], runtime.run["attempt"]
    try:
        source = runtime.sources[0]
        rows = env.db.read_chunk_window(source, 0, 12).rows

        async def allow():
            runtime.check_access()

        async def retrieve(_sources, _query):
            return rows, {}

        async def read(selected, offset, limit):
            return env.db.read_chunk_window(selected, offset, limit)

        research = ResearchSession(runtime.sources, runtime.report["project_id"],
                                   retrieve, read, allow)
        research.seen = {r["block_id"]: r for r in rows}
        state = publishable_state("project_basic_info_parsing")
        state["business_topics"] = [{"key": t, "checks": ["质保条件"]} for t in ("a", "b")]
        for item in state["staged_items"]:
            ref = citation(rows[0], "质保三年")
            item["business"].update(text="质保三年", citations=[ref])
            item["values"][0].update(value="质保三年", citations=[ref])
        flow = TopicFlow(state, research)
        for entry, item in zip(flow.entries, state["staged_items"], strict=True):
            entry.update(scope={"kind": "common", "lot_refs": []},
                         record_keys=[item["business"]["key"]], evidence_ids=list(research.seen))
        flow.data["entries"] = {identity(e["topic"], e["scope"]): e for e in flow.entries}
        flow.data["audit"]["version"] = "combined-v3"
        assert review_call_count(flow, *review_scope(flow)) == 1
        if legacy:
            flow.data["audit"]["packet_plan"].pop("call_groups")
            # 真实旧计划没有后续新增的核对回执及逐事项候选字段，不能用半新半旧形状模拟恢复。
            for packets in flow.data["audit"]["packet_plan"]["topics"].values():
                for packet in packets:
                    packet.pop("check_items", None)
                    packet.pop("record_evidence_ids", None)
        calls = []

        async def review(payload):
            runtime.reserve("model")
            calls.append(payload)
            return {"reviews": {r["record_id"]: {"supported": True, "issues": [],
                    "block_ids": r["block_ids"]} for r in payload["records"]}, "issues": [],
                    "check_results": check_results(payload)}

        async def interrupt(value):
            value["research"] = research.checkpoint()
            runtime.save(value)
            if value["topic_flow"]["audit"]["results"]:
                raise ConnectionError("完整合包回执保存后中断")

        with pytest.raises(ConnectionError):
            asyncio.run(audit_combined(flow, review, interrupt))
        persisted = env.db.rows("SELECT * FROM agent_module_run WHERE id=:id",
                                {"id": runtime.run["id"]})[0]
        restored = TopicFlow(json.loads(json.dumps(persisted["state"])), research)

        async def save(value):
            runtime.save(value)

        assert asyncio.run(audit_combined(restored, review, save))
        assert len(calls) == 1
        row = env.db.rows("SELECT * FROM agent_module_run WHERE id=:id",
                          {"id": runtime.run["id"]})[0]
        assert row["deadline_at"] == original_deadline and row["attempt"] == original_attempt
        assert row["model_calls"] == 1
        assert len(row["state"]["topic_flow"]["audit"]["completed_topics"]) == 2
    finally:
        runtime.release()
