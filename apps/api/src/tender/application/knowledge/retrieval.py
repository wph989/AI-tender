"""检索与问答共用同一混合召回，嵌入客户端由装配点注入。"""

import asyncio
from collections.abc import Callable

from tender.application.knowledge.content import source_state
from tender.core.logging import get_logger
from tender.ports.llm.embedding import EmbeddingModel
from tender.ports.llm.rerank import RerankModel
from tender.ports.repository.knowledge.retrieval import RetrievalRepository

logger = get_logger(__name__)


async def retrieve_chunks(
    db: RetrievalRepository,
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
    # 同步数据库访问移到线程池，避免大表查询阻塞进程内事件循环（模型页轮询等）。
    config = await asyncio.to_thread(db.embedding_config)
    vector = None
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
            # 回退不向上抛异常，需在此记录堆栈；不采集问题和检索正文。
            logger.warning("embedding.fail", exc_info=True)
            warning = f"语义检索暂不可用，使用全文检索：{str(exc)[:200]}"
        finally:
            if client:
                await client.aclose()
    usable = [source for source in sources if source_state(source) in {"ready", "partial"}]
    await asyncio.to_thread(heartbeat)
    # 召回与排名在仓储内完成，事件循环只接收有界候选；多取一项判断是否截断。
    candidates = await asyncio.to_thread(
        db.search_candidates, usable, question, vector,
        config["signature"] if config is not None else None,
        limit=max(30, max_results + 1) if max_results is not None else 16,
        min_similarity=min_similarity,
    )
    ranked = candidates.rows
    semantic_sources = candidates.semantic_source_ids
    reranked = False
    rerank_config = await asyncio.to_thread(db.rerank_config) if rerank_gateway else None
    if ranked and rerank_config and rerank_gateway:
        rerank_client = None
        try:
            rerank_client = rerank_gateway(rerank_config)
            rerank_candidates = ranked[:30]
            order = await rerank_client.rerank(
                question, [row["content"] for row in rerank_candidates], len(rerank_candidates)
            )
            # 供应商可只返回 top_n；其余合格候选保留原顺序，不能跳过它们直接拼接尾部。
            selected = {index for index, _ in order}
            ranked = (
                [rerank_candidates[index] for index, _ in order]
                + [row for index, row in enumerate(rerank_candidates) if index not in selected]
                + ranked[30:]
            )
            reranked = True
        except Exception:
            logger.warning("rerank.fail", exc_info=True)
            warning = (warning + "；" if warning else "") + "重排服务不可用，保留混合检索顺序"
        finally:
            if rerank_client:
                await rerank_client.aclose()
    search_limited = max_results is not None and len(ranked) > max_results
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
        **({"search_limited": search_limited} if max_results is not None else {}),
    }
