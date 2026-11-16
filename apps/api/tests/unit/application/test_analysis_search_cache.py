"""分页缓存必须保持查询语义，并在并发、取消与权限变化时守住调用边界。"""

import asyncio

import pytest
from test_analysis_research import block, session

from tender.application.analysis.research import AgentLimits


@pytest.mark.parametrize("queries", [("投标 保证金", "投标保证金"), ("A&amp;B", "A&B")])
def test_different_queries_do_not_reuse_each_others_candidates(queries):
    async def run():
        research = session([])
        research.compact_results = True
        calls = []

        async def retrieve(_sources, query):
            calls.append(query)
            return [block() | {"block_id": query, "content": query, "element_id": len(calls)}], {}

        research.retrieve = retrieve
        for query in queries:
            result = await research.search(query, "project")
            assert result["blocks"] == [{"id": query, "text": query,
                                        "source_id": 1, "chapter": "质保"}]
        assert calls == list(queries)

    asyncio.run(run())


def test_concurrent_pages_share_one_retrieval_but_each_consume_tool_budget():
    async def run():
        research = session([], limits=AgentLimits(max_search_results=2))
        research.compact_results = True
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def retrieve(_sources, _query):
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            return [block() | {"block_id": f"b{i}", "element_id": i} for i in range(4)], {}

        research.retrieve = retrieve
        first = asyncio.create_task(research.search("质保", "project"))
        await entered.wait()
        second = asyncio.create_task(research.search("质保", "project", offset=2))
        await asyncio.sleep(0)
        release.set()
        pages = await asyncio.gather(first, second)
        assert calls == 1
        assert [[r["id"] for r in p["blocks"]] for p in pages] == [["b0", "b1"], ["b2", "b3"]]
        assert research.tool_calls == 2
        assert len([e for e in research.events if e["action"] == "search_result"]) == 2

    asyncio.run(run())


def test_canceling_waiting_page_does_not_cancel_other_retrieval():
    async def run():
        research = session([])
        research.compact_results = True
        entered, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def retrieve(_sources, _query):
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            return [block()], {}

        research.retrieve = retrieve
        first = asyncio.create_task(research.search("质保", "project"))
        await entered.wait()
        second = asyncio.create_task(research.search("质保", "project"))
        await asyncio.sleep(0)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        release.set()
        assert (await first)["blocks"]
        assert calls == 1

    asyncio.run(run())


@pytest.mark.parametrize("failure", [RuntimeError, asyncio.CancelledError])
def test_unsuccessful_retrieval_can_be_retried(failure):
    async def run():
        research = session([])
        research.compact_results = True
        calls = 0

        async def retrieve(_sources, _query):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise failure()
            return [block()], {}

        research.retrieve = retrieve
        with pytest.raises(failure):
            await research.search("质保", "project")
        assert (await research.search("质保", "project"))["blocks"]
        assert calls == 2

    asyncio.run(run())


def test_cached_page_is_still_authorized_before_delivery():
    async def run():
        research = session([block()])
        research.compact_results = True
        await research.search("质保", "project")
        checks = 0

        async def revoked():
            nonlocal checks
            checks += 1
            if checks == 2:
                raise PermissionError("资料已解除关联")

        research.authorize = revoked
        with pytest.raises(PermissionError, match="解除关联"):
            await research.search("质保", "project")
        assert len([e for e in research.events if e["action"] == "search_result"]) == 1

    asyncio.run(run())
