"""无进展判定只认新增证据与新增核实成果，换检索词不能续命。"""

import asyncio

from langchain_core.messages import AIMessage
from synthesis_fixtures import accept, noop
from test_analysis_research import block, session
from test_deep_analysis import submitted_field

from tender.application.analysis.agent import ResearchMiddleware
from tender.application.analysis.policy import progress_signature
from tender.application.analysis.research import AgentLimits
from tender.application.knowledge.content import validate_items


def search_event(query):
    return {
        "action": "search_result",
        "scope": "project",
        "query": query,
        "source_ids": [],
    }


def test_new_query_without_new_evidence_is_not_progress():
    seen = {"s1r1c0": block()}
    baseline = progress_signature(seen, {}, research_events=[search_event("质保")])
    rephrased = progress_signature(
        seen,
        {},
        research_events=[search_event("质保期"), search_event("保修期限")],
    )
    # 改写同义词只是换检索词，没有带回新证据块。
    assert rephrased == baseline


def test_validation_issue_fix_alone_is_not_progress():
    assert progress_signature(
        {}, {"research_validation_issues": ["topic:warranty"]}
    ) == progress_signature({}, {})


def test_new_evidence_resets_no_progress_counter():
    async def run():
        research = session([block()], limits=AgentLimits(max_finish_corrections=1))
        await research.search("质保", "project")
        state = {}
        middleware = ResearchMiddleware(research, state, noop, noop, review_support=accept)
        for number in range(4):
            await middleware.abefore_model(
                {"messages": [AIMessage(content="", id=str(number))]}, None
            )
        assert state["no_progress_rounds"] == 3 and state["finish_only"]

        research.seen["s1r1c1"] = block() | {"block_id": "s1r1c1"}
        await middleware.abefore_model({"messages": [AIMessage(content="", id="evidence")]}, None)
        assert state["no_progress_rounds"] == 0 and state["finish_only"]

    asyncio.run(run())


def test_new_supported_item_resets_no_progress_counter():
    async def run():
        research = session([block()], limits=AgentLimits(max_finish_corrections=1))
        await research.search("质保", "project")
        state = {}
        middleware = ResearchMiddleware(research, state, noop, noop, review_support=accept)
        for number in range(4):
            await middleware.abefore_model(
                {"messages": [AIMessage(content="", id=str(number))]}, None
            )
        assert state["no_progress_rounds"] == 3

        fields = validate_items([submitted_field("质保期限", "质保三年")], research.seen)
        fields[0]["verification"] = "supported"
        state["staged_items"] = fields
        await middleware.abefore_model({"messages": [AIMessage(content="", id="fact")]}, None)
        assert state["no_progress_rounds"] == 0

    asyncio.run(run())


def test_legacy_progress_signature_resets_once_and_does_not_finish():
    async def run():
        research = session([block()], limits=AgentLimits(max_finish_corrections=1))
        await research.search("质保", "project")
        # 旧检查点的签名必然与新签名不同：首次恢复只把计数归零，不立刻进入收尾。
        state = {"progress_signature": "legacy", "no_progress_rounds": 2}
        middleware = ResearchMiddleware(research, state, noop, noop, review_support=accept)
        await middleware.abefore_model({"messages": [AIMessage(content="", id="first")]}, None)
        assert state["no_progress_rounds"] == 0 and not state.get("finish_only")
        await middleware.abefore_model({"messages": [AIMessage(content="", id="second")]}, None)
        assert state["no_progress_rounds"] == 1

    asyncio.run(run())
