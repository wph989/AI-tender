"""专题检索必须同时满足阈值和数量限制，不能靠重排或工具扩展绕过。"""

import asyncio
import math
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from test_analysis_research import block, session, source

from tender.adapters.llm.rerank_http import HttpRerankModel
from tender.application.analysis import execution
from tender.application.analysis.research import AgentLimits
from tender.application.analysis.runtime import limits_snapshot
from tender.application.knowledge.content import rank_chunks
from tender.application.knowledge.retrieval import retrieve_chunks
from tender.config.schema import resolve_values
from tender.ports.repository.knowledge.retrieval import SearchCandidates


def rows(count: int) -> list[dict]:
    return [
        block()
        | {
            "block_id": f"b{i}",
            "element_id": i + 1,
            "offset": i,
            "ordinal": i,
            "content": f"投标保证金 第{i}项",
        }
        for i in range(count)
    ]


class Store:
    def __init__(self, blocks, *, vectors=None, rerank=False):
        self.blocks, self.vectors, self.rerank = blocks, vectors, rerank

    def embedding_config(self):
        return {"signature": "test"} if self.vectors is not None else None

    def readable_chunks(self, _source):
        return [dict(row) for row in self.blocks]

    def index_vectors(self, _index_id):
        return [{"ordinal": i, "embedding": value} for i, value in enumerate(self.vectors)]

    def search_candidates(self, sources, query, vector, signature, *, limit, min_similarity):
        blocks = [dict(row) for row in self.blocks]
        semantic = []
        if vector is not None and self.vectors is not None and signature == "test":
            for row, embedding in zip(blocks, self.vectors, strict=True):
                row["embedding"] = embedding
            semantic = [source["source_id"] for source in sources]
        return SearchCandidates(
            rank_chunks(blocks, query, vector, limit=limit, min_similarity=min_similarity),
            semantic,
        )

    def rerank_config(self):
        return {"id": 1} if self.rerank else None


class Embedding:
    async def embed(self, _texts):
        return [[1.0, 0.0]]

    async def aclose(self):
        pass


SOURCE = source() | {
    "is_parseable": True,
    "parse_status": "completed",
    "index_id": 1,
    "embedding_signature": "test",
}


def test_config_defaults_and_overrides_are_frozen_in_module_limits():
    defaults = limits_snapshot(SimpleNamespace(resolved_config=lambda: resolve_values({})))
    assert defaults["similarity_threshold"] == 0.6 and defaults["max_search_results"] == 6
    configured = limits_snapshot(
        SimpleNamespace(
            resolved_config=lambda: resolve_values(
                {
                    "analysis.similarity_threshold": 0.75,
                    "analysis.max_search_results": 20,
                }
            )
        )
    )
    assert asdict(AgentLimits(**configured))["similarity_threshold"] == 0.75
    assert AgentLimits(**configured).max_search_results == 20


def test_keyword_and_vector_qualify_independently_before_fusion():
    blocks = [
        {"content": "无关键词但语义达标", "embedding": [0.6, 0.8]},
        {"content": "投标保证金", "embedding": [0.59, math.sqrt(1 - 0.59**2)]},
        {"content": "投标保证金", "embedding": [-1.0, 0.0]},
    ]
    result = rank_chunks(blocks, "投标保证金", [1.0, 0.0], min_similarity=0.6)
    assert len(result) == 3
    assert any(row["content"] == "无关键词但语义达标" for row in result)
    # RRF分数本来就小于0.6，不能拿它过滤，否则正确的语义结果也会消失。
    assert result[0]["score"] < 0.6


def test_keyword_fallback_uses_hit_ratio_and_filters_before_limit():
    result = rank_chunks(
        [
            {"content": "alpha"},
            {"content": "alpha beta"},
            {"content": "alpha beta gamma"},
            {"content": "其他条款"},
        ],
        "alpha beta gamma",
        limit=1,
        min_similarity=0.6,
    )
    assert len(result) == 1 and result[0]["content"] == "alpha beta gamma"
    assert rank_chunks([{"content": "alpha"}], "alpha beta gamma", min_similarity=0.6) == []


@pytest.mark.parametrize(
    ("count", "maximum", "expected"),
    [
        (100, 6, 6),
        (2, 6, 2),
        (40, 20, 20),
        (6, 6, 6),
        (31, 30, 30),
        (30, 30, 30),
    ],
)
def test_many_matches_obey_configurable_limit_without_old_sixteen_block_cap(
    count,
    maximum,
    expected,
):
    async def run():
        hits, info = await retrieve_chunks(
            Store(rows(count)),
            [SOURCE],
            "投标保证金",
            lambda: None,
            lambda _: Embedding(),
            min_similarity=0.6,
            max_results=maximum,
        )
        assert len(hits) == expected and info["max_results"] == maximum
        assert info["similarity_threshold"] == 0.6
        assert info["search_limited"] is (count > maximum)

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
            [SOURCE],
            "投标保证金",
            lambda: None,
            lambda _: Embedding(),
            lambda _: Rerank(),
            min_similarity=0.6,
            max_results=1,
        )
        assert len(order_seen) == 4 and len(hits) == 1 and info["reranked"]
        assert hits[0]["content"] == order_seen[-1]

    asyncio.run(run())


@pytest.mark.parametrize("count,limit", [(8, 6), (41, 40), (8, 10)])
def test_partial_rerank_keeps_unselected_candidates_and_truncation(count, limit):
    async def run():
        store = Store(rows(count), rerank=True)
        original = store.search_candidates([SOURCE], "投标保证金", None, None,
                                           limit=100, min_similarity=None).rows
        async with httpx.AsyncClient(
            base_url="https://fixture.invalid/",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.8},
                ],
            })),
        ) as client:
            hits, info = await retrieve_chunks(
                store, [SOURCE], "投标保证金", lambda: None,
                lambda _: Embedding(),
                lambda _: HttpRerankModel(
                    "https://fixture.invalid", "fixture", top_n_limit=2, client=client,
                ),
                max_results=limit,
            )
        expected = [original[1], original[0], *original[2:]][:limit]
        assert [row["element_id"] for row in hits] == [row["element_id"] for row in expected]
        assert info["reranked"] and info["warning"] is None
        assert info["search_limited"] is (count > limit)

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
            [SOURCE],
            "alpha beta gamma",
            lambda: None,
            lambda _: FailedEmbedding(),
            lambda _: FailedRerank(),
            min_similarity=0.6,
            max_results=6,
        )
        assert hits == [] and info["mode"] == "keyword" and info["warning"]
        hits, info = await retrieve_chunks(
            Store(rows(20), rerank=True),
            [SOURCE],
            "投标保证金",
            lambda: None,
            lambda _: Embedding(),
            lambda _: FailedRerank(),
            min_similarity=0.6,
            max_results=6,
        )
        assert len(hits) == 6 and "重排服务不可用" in info["warning"]

    asyncio.run(run())


@pytest.mark.parametrize("embedding_fails", [False, True])
def test_client_close_failure_preserves_retrieval_result_and_fallback(embedding_fails):
    async def run():
        closed = []

        class ClosingEmbedding(Embedding):
            async def embed(self, texts):
                if embedding_fails:
                    raise RuntimeError("向量服务不可用")
                return await super().embed(texts)

            async def aclose(self):
                closed.append("embedding")
                raise RuntimeError("向量连接关闭失败")

        class ClosingRerank:
            async def rerank(self, _query, _documents, _top_n):
                return [(1, 0.9), (0, 0.8)]

            async def aclose(self):
                closed.append("rerank")
                raise RuntimeError("重排连接关闭失败")

        store = Store(rows(2), vectors=[[1, 0], [1, 0]], rerank=True)
        original = store.search_candidates(
            [SOURCE], "投标保证金", None, None, limit=30, min_similarity=0.6,
        ).rows
        hits, info = await retrieve_chunks(
            store,
            [SOURCE], "投标保证金", lambda: None,
            lambda _: ClosingEmbedding(), lambda _: ClosingRerank(),
            min_similarity=0.6, max_results=2,
        )
        assert closed == ["embedding", "rerank"]
        assert [row["block_id"] for row in hits] == [r["block_id"] for r in reversed(original)]
        assert info["mode"] == ("keyword" if embedding_fails else "hybrid")
        assert info["reranked"]
        if embedding_fails:
            assert "语义检索暂不可用" in info["warning"]

    asyncio.run(run())


def test_cancellation_during_client_cleanup_is_propagated():
    class CanceledEmbedding(Embedding):
        async def aclose(self):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(retrieve_chunks(
            Store(rows(2), vectors=[[1, 0], [1, 0]]), [SOURCE], "投标保证金", lambda: None,
            lambda _: CanceledEmbedding(), max_results=2,
        ))


def test_compact_tool_only_delivers_qualified_id_and_text_under_limit():
    async def run():
        research = session(rows(20), limits=AgentLimits(max_search_results=3))
        research.compact_results = True

        async def retrieve(selected, query):
            return await retrieve_chunks(
                Store(rows(20)),
                [SOURCE],
                query,
                lambda: None,
                lambda _: Embedding(),
                min_similarity=research.limits.similarity_threshold,
                max_results=research.limits.max_search_results,
            )

        research.retrieve = retrieve
        result = await research.search("投标保证金", "project")
        assert len(result["blocks"]) == len(research.seen) == 3
        assert all(set(row) == {"id", "text"} for row in result["blocks"])
        assert "retrieval" not in result
        assert result["search_limited"] is True
        assert "限定 source_id" in result["search_hint"]
        assert research.events[-1]["search_limited"] is True
        empty = await research.search("alpha beta gamma", "project")
        assert empty["blocks"] == [] and "search_limited" not in empty

    asyncio.run(run())


def test_limited_candidate_window_guides_cached_pages_before_new_queries():
    async def run():
        research = session(rows(6), limits=AgentLimits(max_search_results=2, max_search_pages=3))
        research.compact_results = True
        original = research.retrieve

        async def retrieve(sources, query):
            hits, info = await original(sources, query)
            return hits, info | {"search_limited": True}

        research.retrieve = retrieve
        for offset in (0, 2):
            result = await research.search("投标保证金", "project", offset=offset)
            assert result["page"]["has_more"] and result["search_limited"]
            assert "offset=next_offset" in result["search_hint"]
            assert "末尾" not in result["search_hint"]
        last = await research.search("投标保证金", "project", offset=4)
        assert not last["page"]["has_more"]
        assert "具体未决条件" in last["search_hint"]

    asyncio.run(run())


@pytest.mark.parametrize("page_size", [2, 6, 20])
def test_executor_retrieves_full_configured_window_once(monkeypatch, page_size):
    async def run():
        limits = AgentLimits(max_search_results=page_size)
        runtime = Mock()
        runtime.claim.return_value = True
        runtime.run = {
            "state": {}, "limits": asdict(limits), "thread_id": "pages",
            "deadline_at": datetime.now(UTC) + timedelta(seconds=60),
            "model_calls": 0, "tool_calls": 0,
        }
        monkeypatch.setattr(execution, "AgentRuntime", lambda *_: runtime)
        research = None

        def build(**kwargs):
            nonlocal research
            research = kwargs["research"]
            research.compact_results = True
            return object(), {}

        async def invoke(*_args, state, **_kwargs):
            collected = []
            offset = 0
            for _ in range(limits.max_search_pages):
                result = await research.search("投标保证金", "project", offset=offset)
                collected.extend(b["id"] for b in result["blocks"])
                offset = result["page"]["next_offset"]
            assert len(set(collected)) == page_size * limits.max_search_pages
            assert offset is None
            state["draft"] = {"fields": [], "relations": [], "research_summary": "分页验收"}

        @asynccontextmanager
        async def saver():
            yield None

        monkeypatch.setattr(execution, "build_module_agent", build)
        monkeypatch.setattr(execution, "invoke_module", invoke)
        store = Store(rows(101))
        store.search_candidates = Mock(wraps=store.search_candidates)
        executor = execution.AnalysisExecutor(
            store, model_factory=Mock(return_value=AsyncMock()),
            embedding_gateway=Mock(), rerank_gateway=Mock(), checkpoints=saver,
        )
        await executor.execute_module(
            {"id": 1, "project_id": 10,
             "skill_snapshot": {"__analysis_flow_version__": "research-v3"}, "category": "goods",
             "topics": [], "lot_settings": []},
            {"id": 2, "module_key": "deposit_requirement_parsing", "attempt": 1}, [SOURCE],
        )
        runtime.abandon.assert_not_called()
        runtime.finish.assert_called_once()
        assert runtime.finish.call_args.args[0] == "completed"
        store.search_candidates.assert_called_once()

    asyncio.run(run())


def test_compact_expansion_cannot_exceed_limit_or_bypass_scope_check():
    async def run():
        research = session(rows(2), limits=AgentLimits(max_search_results=2))
        research.compact_results = True

        async def expand(_sources, blocks):
            return blocks + rows(8)[2:], []

        research.expand = expand
        result = await research.search("投标保证金", "project")
        assert len(result["blocks"]) == 2 and result["search_limited"] is True
        assert len(research.seen) == 2

        async def forbidden(_sources, blocks):
            return blocks + [block(99, 99)], []

        research.expand = forbidden
        with pytest.raises(PermissionError):
            await research.search("投标保证金", "project")

    asyncio.run(run())


def test_keyword_empty_search_guides_narrower_query_without_weakening_threshold():
    async def run():
        blocks = [block() | {"content": "监理报酬清单：详见附件4报价表。"}]
        research = session(blocks)
        research.compact_results = True

        async def retrieve(_sources, query):
            return await retrieve_chunks(
                Store(blocks),
                [SOURCE],
                query,
                lambda: None,
                lambda _: Embedding(),
                min_similarity=0.6,
                max_results=6,
            )

        research.retrieve = retrieve
        # 真实标书验收中，堆叠多个主题会把只包含目标名称的转引块过滤掉。
        empty = await research.search("报价表 增值税税金 一次性报价", "project")
        assert empty["blocks"] == [] and research.seen == {}
        assert "关键词" in empty["search_hint"] and "单一" in empty["search_hint"]
        assert research.events[-1]["similarity_threshold"] == 0.6
        found = await research.search("报价表", "project")
        assert len(found["blocks"]) == 1 and "search_hint" not in found
        repeated = await research.search("报价表", "project")
        assert repeated["already_read"] and "search_hint" not in repeated

        async def semantic_empty(_sources, _query):
            return [], {"mode": "hybrid"}

        research.retrieve = semantic_empty
        semantic = await research.search("报价表", "project")
        assert "search_hint" not in semantic

    asyncio.run(run())
