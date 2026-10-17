"""专题检索必须同时满足阈值和数量限制，不能靠重排或工具扩展绕过。"""

import asyncio
import math
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from test_analysis_research import block, session, source

from tender.application.agent_runtime import limits_snapshot
from tender.application.analysis_research import AgentLimits
from tender.application.knowledge import rank_chunks
from tender.application.knowledge_retrieval import retrieve_chunks
from tender.config.schema import resolve_values


def rows(count: int) -> list[dict]:
    return [block() | {
        "block_id": f"b{i}", "element_id": i + 1, "offset": i, "ordinal": i,
        "content": f"投标保证金 第{i}项",
    } for i in range(count)]


class Store:
    def __init__(self, blocks, *, vectors=None, rerank=False):
        self.blocks, self.vectors, self.rerank = blocks, vectors, rerank

    def embedding_config(self):
        return {"signature": "test"} if self.vectors is not None else None

    def readable_chunks(self, _source):
        return [dict(row) for row in self.blocks]

    def index_vectors(self, _index_id):
        return [{"ordinal": i, "embedding": value} for i, value in enumerate(self.vectors)]

    def rerank_config(self):
        return {"id": 1} if self.rerank else None


class Embedding:
    async def embed(self, _texts):
        return [[1.0, 0.0]]

    async def aclose(self):
        pass


SOURCE = source() | {
    "is_parseable": True, "parse_status": "completed", "index_id": 1,
    "embedding_signature": "test",
}


def test_config_defaults_and_overrides_are_frozen_in_module_limits():
    defaults = limits_snapshot(SimpleNamespace(resolved_config=lambda: resolve_values({})))
    assert defaults["similarity_threshold"] == 0.6 and defaults["max_search_results"] == 6
    configured = limits_snapshot(SimpleNamespace(resolved_config=lambda: resolve_values({
        "analysis.similarity_threshold": 0.75, "analysis.max_search_results": 20,
    })))
    assert asdict(AgentLimits(**configured))["similarity_threshold"] == 0.75
    assert AgentLimits(**configured).max_search_results == 20


def test_vector_threshold_is_inclusive_and_low_vector_cannot_bypass_via_keyword():
    blocks = [
        {"content": "无关键词但语义达标", "embedding": [0.6, 0.8]},
        {"content": "投标保证金", "embedding": [0.59, math.sqrt(1 - 0.59 ** 2)]},
        {"content": "投标保证金", "embedding": [-1.0, 0.0]},
    ]
    result = rank_chunks(blocks, "投标保证金", [1.0, 0.0], min_similarity=0.6)
    assert [row["content"] for row in result] == ["无关键词但语义达标"]
    # RRF分数本来就小于0.6，不能拿它过滤，否则正确的语义结果也会消失。
    assert result[0]["score"] < 0.6


def test_keyword_fallback_uses_hit_ratio_and_filters_before_limit():
    result = rank_chunks([
        {"content": "alpha"}, {"content": "alpha beta"},
        {"content": "alpha beta gamma"}, {"content": "其他条款"},
    ], "alpha beta gamma", limit=1, min_similarity=0.6)
    assert len(result) == 1 and result[0]["content"] == "alpha beta gamma"
    assert rank_chunks([{"content": "alpha"}], "alpha beta gamma", min_similarity=0.6) == []


@pytest.mark.parametrize(("count", "maximum", "expected"), [(100, 6, 6), (2, 6, 2), (40, 20, 20)])
def test_many_matches_obey_configurable_limit_without_old_sixteen_block_cap(
    count, maximum, expected,
):
    async def run():
        hits, info = await retrieve_chunks(
            Store(rows(count)), [SOURCE], "投标保证金", lambda: None, lambda _: Embedding(),
            min_similarity=0.6, max_results=maximum,
        )
        assert len(hits) == expected and info["max_results"] == maximum
        assert info["similarity_threshold"] == 0.6

    asyncio.run(run())


def test_rerank_orders_only_qualified_candidates_before_final_limit():
    async def run():
        blocks = rows(4)
        order_seen = []

        class Rerank:
            async def rerank(self, _query, documents, _top_n):
                order_seen.extend(documents)
                # 重排分数的尺度由供应商定义，不能套用向量阈值。
                return [(i, 0.01) for i in reversed(range(len(documents)))]

            async def aclose(self):
                pass

        hits, info = await retrieve_chunks(
            Store(blocks, vectors=[[1, 0], [0.6, 0.8], [0.1, 0.99], [-1, 0]], rerank=True),
            [SOURCE], "投标保证金", lambda: None, lambda _: Embedding(), lambda _: Rerank(),
            min_similarity=0.6, max_results=1,
        )
        assert len(order_seen) == 2 and len(hits) == 1 and info["reranked"]
        assert hits[0]["content"] == order_seen[-1]

    asyncio.run(run())


def test_failed_embedding_or_rerank_does_not_drop_threshold_or_backfill():
    async def run():
        class FailedEmbedding(Embedding):
            async def embed(self, _texts):
                raise RuntimeError("测试向量服务不可用")

        class FailedRerank:
            async def rerank(self, *_args):
                raise RuntimeError("测试重排服务不可用")

            async def aclose(self):
                pass

        hits, info = await retrieve_chunks(
            Store([block() | {"content": "alpha"}], vectors=[], rerank=True),
            [SOURCE], "alpha beta gamma", lambda: None, lambda _: FailedEmbedding(),
            lambda _: FailedRerank(), min_similarity=0.6, max_results=6,
        )
        assert hits == [] and info["mode"] == "keyword" and info["warning"]
        hits, info = await retrieve_chunks(
            Store(rows(20), rerank=True), [SOURCE], "投标保证金", lambda: None,
            lambda _: Embedding(), lambda _: FailedRerank(), min_similarity=0.6, max_results=6,
        )
        assert len(hits) == 6 and "重排服务不可用" in info["warning"]

    asyncio.run(run())


def test_compact_tool_only_delivers_qualified_id_and_text_under_limit():
    async def run():
        research = session(rows(20), limits=AgentLimits(max_search_results=3))
        research.compact_results = True

        async def retrieve(selected, query):
            return await retrieve_chunks(
                Store(rows(20)), [SOURCE], query, lambda: None, lambda _: Embedding(),
                min_similarity=research.limits.similarity_threshold,
                max_results=research.limits.max_search_results,
            )

        research.retrieve = retrieve
        result = await research.search("投标保证金", "project")
        assert len(result["blocks"]) == len(research.seen) == 3
        assert all(set(row) == {"id", "text"} for row in result["blocks"])
        assert "retrieval" not in result
        assert (await research.search("alpha beta gamma", "project"))["blocks"] == []

    asyncio.run(run())


def test_compact_expansion_cannot_exceed_limit_or_bypass_scope_check():
    async def run():
        research = session(rows(2), limits=AgentLimits(max_search_results=2))
        research.compact_results = True

        async def expand(_sources, blocks):
            return blocks + rows(8)[2:], []

        research.expand = expand
        assert len((await research.search("投标保证金", "project"))["blocks"]) == 2
        assert len(research.seen) == 2

        async def forbidden(_sources, blocks):
            return blocks + [block(99, 99)], []

        research.expand = forbidden
        with pytest.raises(PermissionError):
            await research.search("投标保证金", "project")

    asyncio.run(run())
