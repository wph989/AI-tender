"""真实失败轨迹回归：关闭工作不扣纠错账，读懂原文即可统一综合。"""

import asyncio
import copy
import json

from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import noop
from test_analysis_argument_failures import request
from test_analysis_compact_protocol import ledger
from test_analysis_research import block, session
from test_analysis_topic_flow import snapshot
from test_deep_analysis import KEY, ScriptedRouter, call

from tender.application.analysis.agent import (
    ResearchMiddleware,
    RoutedAgentModel,
    build_module_agent,
)
from tender.application.analysis.protocol import PROTOCOL_VERSION, ResearchDelta, ResearchLedger
from tender.application.analysis.search_control import TopicSearch
from tender.application.analysis.topic_flow import TopicFlow


def test_known_finished_work_does_not_consume_argument_budget():
    book, flow, state, research = ledger()
    flow.entries[0]["checks"].append("其他未完成核对项")

    async def run():
        book.update([ResearchDelta(work_ids=["w1"], detail="已确认", evidence_ids=["s1r1c0"],
                                   scope={"kind": "common", "lot_refs": []})])
        # 保持研究阶段，模拟其他工作尚在处理，而模型仍持有本项旧索引。
        flow.data["phase"] = "research"
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)
        before = copy.deepcopy(state)
        result = await middleware.awrap_tool_call(
            request("search_document", {"query": "质保", "work": "w1"}), noop,
        )
        assert result.status == "success" and json.loads(result.content)["work_closed"]
        assert not state.get("argument_failures")
        assert state["topic_flow"]["entries"] == before["topic_flow"]["entries"]

    asyncio.run(run())


def test_broad_topic_keys_do_not_require_work_to_belong_to_every_topic():
    book, flow, _, _ = ledger()
    flow.state["business_topics"].append({"key": "b", "title": "数量", "checks": ["数量"]})
    flow.data["entries"]["extra"] = flow._entry(flow.state["business_topics"][-1],
                                                {"kind": "unknown", "lot_refs": []})
    book.works()
    selected = TopicSearch(flow).begin("search_document", {
        "query": "质保和数量", "work": "w1", "topic_keys": ["a", "b"],
    })
    assert [w["id"] for w in selected] == ["w1"]


def test_long_clause_can_be_understood_without_forced_per_batch_registration():
    book, flow, _, research = ledger()
    control = TopicSearch(flow)
    for index in range(8):
        args = {"block_id": "s1r1c0", "work": "w1"}
        selected = control.begin("read_document", args)
        before = set(research.seen)
        row = block() | {"block_id": f"s1r1c{index + 1}", "content": f"清单续段{index}"}
        research.seen[row["block_id"]] = row
        payload = {"blocks": [{"id": row["block_id"]}]}
        flow.evidence(before, ["a"], payload)
        control.end(selected, payload, before)
        assert "analysis_required" not in payload
        assert "complete_research" in payload["next_action"]
    # 读完真实长条款后直接综合；不必通过examined笔记反复解除采集门禁。
    restored = TopicFlow(json.loads(json.dumps(flow.state)), research)
    ResearchLedger(restored).finish("已读完整清单和例外，依据充分")
    assert not restored.researching and not restored.entries[0].get("findings")
    assert not any(w.get("exhausted") for w in restored.data["search_work"].values())


def test_misplaced_research_status_is_rejected_with_tool_specific_feedback():
    async def run():
        state = {}
        research = session([block()])
        graph, _ = build_module_agent(
            key=KEY, model=RoutedAgentModel(router=ScriptedRouter([])), research=research,
            state=state,
            snapshot=snapshot(("a",)) | {"__analysis_flow_version__": PROTOCOL_VERSION},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop,
        )
        node = graph.nodes["tools"].bound
        tool = node.tools_by_name["update_research"]
        result = await tool.ainvoke(call("update_research", {
            "updates": [{"work_ids": ["w1"], "detail": "只看到标题", "examined_ids": ["s1r1c0"]}],
            "status": "examined",
        }, "bad"))
        assert isinstance(result, ToolMessage) and "status" in result.content
        assert "updates" in result.content and "submit_analysis" not in result.content
        assert not state["topic_flow"].get("entries", {}).get("findings")

    asyncio.run(run())


def test_analysis_and_continuation_in_one_response_reuse_serial_tool_execution():
    book, flow, state, research = ledger()
    middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)
    results = []

    async def run():
        async def update_handler(req):
            book.update([ResearchDelta(work_ids=["w1"], status="examined",
                                       detail="已分析，补查例外", examined_ids=["s1r1c0"])])
            return ToolMessage(content='{"updated":true}', tool_call_id=req.tool_call["id"])

        async def read_handler(req):
            results.append("真实补读")
            return ToolMessage(content='{"blocks":[]}', tool_call_id=req.tool_call["id"])

        await middleware.awrap_tool_call(request("update_research", {
            "updates": [],
        }, call_id="analysis", round_id="shared-round"), update_handler)
        await middleware.awrap_tool_call(request("read_document", {
            "block_id": "s1r1c0", "after": 1, "work": "w1",
        }, call_id="read", round_id="shared-round"), read_handler)
        assert results == ["真实补读"]
        assert not state.get("argument_failures") and flow.researching

    asyncio.run(run())
