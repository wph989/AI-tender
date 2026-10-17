"""检索与问答共用同一混合召回，嵌入客户端由装配点注入。"""

import asyncio
from collections.abc import Callable

from tender.application.knowledge import rank_chunks, source_state
from tender.ports.embedding import EmbeddingModel
from tender.ports.repository.knowledge import KnowledgeStore
from tender.ports.rerank import RerankModel


async def retrieve_chunks(
    db: KnowledgeStore,
    sources: list[dict],
    question: str,
    heartbeat: Callable[[], None],
    gateway: Callable[[dict], EmbeddingModel],
    rerank_gateway: Callable[[dict], RerankModel] | None = None,
    *,
    embedding_timeout: float | None = None,
    min_similarity: float | None = None,
    max_results: int | None = None,
) -> tuple[list[dict], dict]:
    rows = []
    # 同步数据库访问移到线程池，避免大表查询阻塞进程内事件循环（模型页轮询等）。
    config = await asyncio.to_thread(db.embedding_config)
    vector = None
    semantic_sources = set()
    warning = None
    if config:
        client = None
        try:
            client = gateway(config)
            # 页面搜索不能等到代理断开才回退；后台问答仍采用模型自身的等待预算。
            vector = (await asyncio.wait_for(
                client.embed([question]), timeout=embedding_timeout,
            ))[0]
        except TimeoutError:
            warning = "语义检索等待超时，本次已使用全文检索，可稍后重试语义检索。"
        except Exception as exc:
            warning = f"语义检索暂不可用，使用全文检索：{str(exc)[:200]}"
        finally:
            if client:
                await client.aclose()
    for source in sources:
        heartbeat()
        if source_state(source) not in {"ready", "partial"}:
            continue
        blocks = await asyncio.to_thread(db.readable_chunks, source)
        if (
            vector is not None
            and source.get("index_id")
            and source.get("embedding_signature") == config["signature"]
        ):
            vectors = await asyncio.to_thread(db.index_vectors, source["index_id"])
            by_ordinal = {r["ordinal"]: r["embedding"] for r in vectors}
            for block in blocks:
                candidate = by_ordinal.get(block["ordinal"])
                if candidate is not None and len(candidate) == len(vector):
                    block["embedding"] = candidate
                    semantic_sources.add(source["source_id"])
        rows.extend(blocks)
    # 专题先过滤后保留足够候选供重排；不能被旧的16块截断限制可配置的返回数量。
    ranked = rank_chunks(
        rows, question, vector,
        limit=max(30, max_results) if max_results is not None else 16,
        min_similarity=min_similarity,
    )
    reranked = False
    rerank_config = await asyncio.to_thread(db.rerank_config) if rerank_gateway else None
    if ranked and rerank_config and rerank_gateway:
        client = None
        try:
            client = rerank_gateway(rerank_config)
            candidates = ranked[:30]
            order = await client.rerank(
                question, [r["content"] for r in candidates], len(candidates)
            )
            ranked = [candidates[index] for index, _ in order] + ranked[30:]
            reranked = True
        except Exception:
            warning = (warning + "；" if warning else "") + "重排服务不可用，保留混合检索顺序"
        finally:
            if client:
                await client.aclose()
    if max_results is not None:
        ranked = ranked[:max_results]
    return ranked, {
        "reranked": reranked,
        "mode": "hybrid" if semantic_sources else "keyword",
        "semantic_source_ids": sorted(semantic_sources),
        "warning": warning,
        "embedding_configured": config is not None,
        **({"similarity_threshold": min_similarity, "max_results": max_results}
           if min_similarity is not None or max_results is not None else {}),
    }
