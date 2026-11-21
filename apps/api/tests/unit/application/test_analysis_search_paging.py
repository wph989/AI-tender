"""同一查询用 offset 翻页，避免靠改写同义词反复检索。"""

import asyncio

from test_analysis_research import block, session

from tender.application.shared.research import AgentLimits


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
