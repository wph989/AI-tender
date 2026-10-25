"""知识索引与问答执行用例；Worker 只处理队列入口与执行锁。"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable

from tender.application.knowledge.qa_agent import answer_with_agent
from tender.application.knowledge.retrieval import retrieve_chunks
from tender.application.llm.routing import RoutingModel
from tender.core.logging import get_logger
from tender.domain.shared.errors import TenderError
from tender.ports.llm.embedding import EmbeddingModel
from tender.ports.llm.rerank import RerankModel
from tender.ports.repository.knowledge.execution import KnowledgeExecutionRepository

logger = get_logger(__name__)


def graph_expand(
    db: KnowledgeExecutionRepository, project_id: int, hits: list[dict], sources: list[dict]
) -> tuple[list[dict], list[dict]]:
    source_runs = {(s["source_id"], s["parse_run_id"]) for s in sources}
    relations = db.verified_relations(project_id)
    relations = [
        r
        for r in relations
        if r["citations"]
        and all((ref["source_id"], ref["parse_run_id"]) in source_runs for ref in r["citations"])
    ]
    selected = []
    names = set()
    text_hits = "\n".join(r["content"] for r in hits)
    for _depth in range(2):
        next_names = set()
        for rel in relations:
            if rel in selected:
                continue
            if (
                rel["subject"] in text_hits
                or rel["object"] in text_hits
                or (
                    (rel["subject"], rel["scope"]) in names
                    or (rel["object"], rel["scope"]) in names
                )
            ):
                selected.append(rel)
                next_names.update(((rel["subject"], rel["scope"]), (rel["object"], rel["scope"])))
                if len(selected) >= 24:
                    break
        if len(selected) >= 24:
            break
        text_hits = ""
        names = next_names
    if not selected:
        # 问答每次检索都会尝试扩展；无关联时无需反复读取全部资料。
        return hits, []
    seen = {r["block_id"] for r in hits}
    wanted = {ref["element_id"] for rel in selected for ref in rel["citations"]}
    for source in sources:
        for block in db.readable_chunks(source):
            if block["element_id"] in wanted and block["block_id"] not in seen:
                hits.append(block)
                seen.add(block["block_id"])
    return hits, selected


class KnowledgeExecutor:
    def __init__(
        self,
        db: KnowledgeExecutionRepository,
        *,
        model_factory: Callable[..., RoutingModel],
        embedding_gateway: Callable[[dict], EmbeddingModel],
        rerank_gateway: Callable[[dict], RerankModel],
    ) -> None:
        # 通过构造参数注入能力，独立验收无需导入 Celery 或创建真实供应商客户端。
        self.db, self.model_factory = db, model_factory
        self.embedding_gateway, self.rerank_gateway = embedding_gateway, rerank_gateway

    async def build_index(self, index_id: int) -> None:
        db = self.db
        index = db.index_for_build(index_id)
        if index is None or index["status"] not in {"pending", "running"}:
            return
        client = None
        try:
            db.collection(index["collection_id"])
            source = next(
                (
                    s
                    for s in db.sources([index["collection_id"]])
                    if s["source_id"] == index["source_id"] and s["parse_run_id"] == index["run_id"]
                ),
                None,
            )
            if source is None:
                raise ValueError("资料已更新或删除，请使用最新解析结果重建索引")
            db.mark_index_running(index_id)
            chunks = db.readable_chunks(source)
            if not chunks:
                raise ValueError("解析结果没有可索引的文字，请检查原文或使用 OCR 重新解析")
            config = db.embedding_config()
            vectors = None
            if config:
                client = self.embedding_gateway(config)
                vectors = []
                for start in range(0, len(chunks), 16):
                    db.renew_lease("index", index_id)
                    vectors.extend(
                        await client.embed([r["content"] for r in chunks[start : start + 16]])
                    )
                if vectors and any(len(v) != len(vectors[0]) for v in vectors):
                    raise ValueError("向量模型在索引期间改变了维度")
            db.complete_index(index_id, chunks=chunks, vectors=vectors, config=config)
        except Exception as exc:
            # 业务失败被收敛到数据库后 Celery 会正常返回，必须在这里保留未知错误的堆栈。
            # 业务异常已在适配器脱敏，不回放原始异常链；未知故障仍保留完整链。
            logger.error(
                "index.fail",
                index_id=index_id,
                exception="".join(
                    traceback.format_exception(exc, chain=not isinstance(exc, TenderError)),
                ),
            )
            db.finish_task("index", index_id, "failed", str(exc)[:1000])
        finally:
            if client:
                await client.aclose()

    async def answer_question(self, answer_id: int) -> None:
        db = self.db
        answer = db.answer(answer_id)
        if answer is None or answer["status"] not in {"pending", "running"}:
            return
        try:
            ids = answer["collection_ids"]
            if answer["project_id"] and set(ids) - set(
                db.collections_for_project(answer["project_id"])
            ):
                raise ValueError("知识库关联已变更，请重新提问")
            for cid in ids:
                db.collection(cid)
            sources = answer["snapshot"]["sources"]
            db.mark_answer_running(answer_id)

            async def authorize() -> None:
                await asyncio.to_thread(db.renew_lease, "answer", answer_id)

            async def retrieve_selected(selected: list[dict], query: str):
                return await retrieve_chunks(
                    db,
                    selected,
                    query,
                    lambda: db.renew_lease("answer", answer_id),
                    self.embedding_gateway,
                    self.rerank_gateway,
                )

            async def read_source(source: dict) -> list[dict]:
                return await asyncio.to_thread(db.readable_chunks, source)

            async def expand_selected(selected: list[dict], hits: list[dict]):
                return await asyncio.to_thread(
                    graph_expand, db, answer["project_id"], hits, selected
                )

            # 问答由独立 Agent 检索、核对并作答；项目范围取其自身，集合问答回落到资料来源的项目。
            project_id = answer["project_id"]
            if project_id is None and sources:
                project_id = sources[0]["project_id"]
            draft, research = await answer_with_agent(
                model_factory=lambda **limits: self.model_factory(
                    "knowledge_ask", "knowledge_ask", **limits
                ),
                sources=sources,
                project_id=project_id,
                question=answer["question"],
                retrieve=retrieve_selected,
                read=read_source,
                authorize=authorize,
                expand=expand_selected if answer["project_id"] else None,
            )
            items = draft["fields"]
            searches = [event for event in research.events if event["action"] == "search_result"]
            # 只展示 Agent 实际检索并读到的图谱依据，不能把图外预检结果冒充作答上下文。
            graph_relations = []
            for event in searches:
                for link in event["relations"]:
                    if link not in graph_relations:
                        graph_relations.append(link)
            relations = graph_relations + [
                r for r in draft["relations"] if r not in graph_relations
            ]
            snapshot = {
                **answer["snapshot"],
                "mode": "hybrid" if any(e.get("mode") == "hybrid" for e in searches) else "keyword",
                "reranked": any(e.get("reranked") for e in searches),
                "embedding_configured": any(e.get("embedding_configured") for e in searches),
                "semantic_source_ids": sorted(
                    {sid for e in searches for sid in e.get("semantic_source_ids", [])}
                ),
                "warning": "；".join(
                    dict.fromkeys(e["warning"] for e in searches if e.get("warning"))
                ),
                "retrieved_blocks": len(research.seen),
                "graph_used": bool(graph_relations),
                "graph_relation_count": len(graph_relations),
                "no_evidence": not bool(items),
            }
            db.save_answer(answer_id, items=items, relations=relations, snapshot=snapshot)
            db.finish_task("answer", answer_id, "completed")
        except Exception as exc:
            # 路由可能串联带供应商凭证的 SDK 错误，只记录已脱敏的业务异常堆栈。
            logger.error(
                "answer.fail",
                answer_id=answer_id,
                exception="".join(
                    traceback.format_exception(exc, chain=not isinstance(exc, TenderError)),
                ),
            )
            db.finish_task("answer", answer_id, "failed", str(exc)[:1000])
