"""同一查询用 offset 翻页，避免靠改写同义词反复检索。"""

import asyncio
import json

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from synthesis_fixtures import noop, research_calls, submission, summary_record
from test_analysis_research import block, session
from test_analysis_synthesis import execute
from test_deep_analysis import call

from tender.application.analysis.agent import ResearchMiddleware
from tender.application.analysis.research import AgentLimits


def rows(count):
    return [
        block() | {
            "block_id": f"s1r1c{index}",
            "element_id": index,
            "offset": index,
            "content": f"第{index}条质保三年",
        }
        for index in range(count)
    ]


def paged(data, *, limits=None):
    research = session(data, limits=limits)
    research.compact_results = True
    calls = []

    async def retrieve(selected, query):
        calls.append(query)
        return list(data), {"mode": "hybrid", "search_limited": False}

    research.retrieve = retrieve
    return research, calls


def tool_request(name, args, *, call_id):
    call_data = {"name": name, "args": args, "id": call_id, "type": "tool_call"}
    return ToolCallRequest(
        tool_call=call_data,
        tool=None,
        state={"messages": [AIMessage(content="", id=call_id, tool_calls=[call_data])]},
        runtime=None,
    )


def test_search_document_accepts_offset_and_returns_next_offset():
    _, _, router = asyncio.run(
        execute([
            call("search_document", {"query": "质保补充", "offset": 6}, "page"),
            *research_calls(),
            call("submit_analysis", submission([summary_record()]), "final"),
        ])
    )
    params = {
        tool["function"]["name"]: tool["function"]["parameters"]
        for tool in router.requests[0][1]
    }
    assert params["search_document"]["properties"]["offset"]["minimum"] == 0
    assert params["search_knowledge"]["properties"]["offset"]["minimum"] == 0

    async def run():
        research, _ = paged(rows(8))
        first = await research.search("质保", "project")
        assert first["page"] == {
            "offset": 0, "limit": 6, "next_offset": 6, "has_more": True,
        }

    asyncio.run(run())


def test_same_query_pages_without_rephrasing():
    async def run():
        research, calls = paged(rows(14))
        first = await research.search("质保", "project")
        second = await research.search("质保", "project", offset=6)
        # 同一查询翻页复用候选缓存，只做了一次检索。
        assert calls == ["质保"]
        assert first["page"]["next_offset"] == 6 and "offset=next_offset" in first["search_hint"]
        assert second["page"] == {
            "offset": 6, "limit": 6, "next_offset": 12, "has_more": True,
        }
        assert [block_item["id"] for block_item in second["blocks"]] == [
            f"s1r1c{index}" for index in range(6, 12)
        ]
        # 未读候选不会因为缓存而提前进入证据账。
        assert len(research.seen) == 12

    asyncio.run(run())


def test_identical_query_and_offset_still_hits_repeat_limit():
    async def run():
        research, _ = paged(rows(14))
        state = {}
        wraps = ResearchMiddleware(research, state, noop, noop)

        async def handler(req):
            args = req.tool_call["args"]
            result = await research.search(
                args["query"], "project", offset=args.get("offset", 0)
            )
            return ToolMessage(
                content=json.dumps(result, ensure_ascii=False),
                tool_call_id=req.tool_call["id"],
                name="search_document",
            )

        for ordinal in range(3):
            await wraps.awrap_tool_call(
                tool_request("search_document", {"query": "质保", "offset": 3},
                             call_id=f"c{ordinal}"),
                handler,
            )
        # 翻页游标同样进入工具指纹：相同 query+offset 仍受重复调用上限约束。
        with pytest.raises(RuntimeError, match="重复调用已达上限"):
            await wraps.awrap_tool_call(
                tool_request("search_document", {"query": "质保", "offset": 3},
                             call_id="c3"),
                handler,
            )
        await wraps.awrap_tool_call(
            tool_request("search_document", {"query": "质保", "offset": 9},
                         call_id="c4"),
            handler,
        )

    asyncio.run(run())


def test_page_with_only_seen_blocks_still_advances_cursor():
    async def run():
        research, _ = paged(rows(14))
        await research.search("质保", "project", offset=6)
        repeated = await research.search("质保", "project", offset=6)
        assert repeated["blocks"] == [] and repeated["already_read"]
        # 本页全部是已读块也按原始页大小推进，不让游标卡死。
        assert repeated["page"]["next_offset"] == 12
        assert repeated["page"]["has_more"] is True

    asyncio.run(run())


def test_page_beyond_total_returns_exhausted_without_budget_use():
    async def run():
        research, _ = paged(rows(10))
        await research.search("质保", "project")
        beyond = await research.search("质保", "project", offset=12)
        assert beyond["blocks"] == [] and beyond["already_read"] == []
        assert beyond["page"]["next_offset"] is None
        assert beyond["page"]["has_more"] is False
        assert "已无更多候选" in beyond["search_hint"]
        # 没有原文进入证据账，预算不会被空页消耗。
        assert len(research.seen) == 6

    asyncio.run(run())


def test_paging_respects_evidence_budget():
    async def run():
        research, _ = paged(rows(14), limits=AgentLimits(max_evidence_blocks=8))
        await research.search("质保", "project")
        second = await research.search("质保", "project", offset=6)
        assert len(research.seen) == 8
        assert second["budget_exhausted"] is True
        assert second["omitted_blocks"] == 4
        assert len(second["blocks"]) == 2

    asyncio.run(run())


def test_non_topic_session_keeps_original_search_shape():
    async def run():
        research = session(rows(20))

        async def retrieve(selected, query):
            return list(rows(20)), {"mode": "hybrid", "search_limited": False}

        research.retrieve = retrieve
        result = await research.search("质保", "project", offset=5)
        assert "page" not in result and "retrieval" in result
        # 问答沿用原协议：仍然只返回前 12 块且忽略 offset。
        assert len(result["blocks"]) == 12
        assert research.events[-1]["search_limited"] is True
        assert "offset" not in research.events[-1]

    asyncio.run(run())
