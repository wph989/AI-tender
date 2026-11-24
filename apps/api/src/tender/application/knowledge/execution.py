"""知识索引与问答执行用例；Worker 只处理队列入口与执行锁。"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable
from typing import Any

from tender.application.knowledge.content import fingerprint, source_state
from tender.application.knowledge.qa_agent import answer_with_agent
from tender.application.knowledge.retrieval import retrieve_chunks
from tender.application.llm.routing import RoutingModel
from tender.core.logging import get_logger
from tender.domain.knowledge.text import CHUNK_VERSION
from tender.domain.shared.errors import TenderError
from tender.ports.llm.embedding import EmbeddingModel
from tender.ports.llm.rerank import RerankModel
from tender.ports.repository.knowledge.dispatch import KnowledgeDispatchRepository
from tender.ports.repository.knowledge.execution import KnowledgeExecutionRepository

logger = get_logger(__name__)

# 知识任务的领取顺序：索引先于依赖它的报告与问答。
DISPATCH_KINDS = ("index", "report", "answer")


def dispatch_ready(db: KnowledgeDispatchRepository) -> list[tuple[str, int]]:
    """登记到期索引并领取可派发任务；投递哪条消息由调度侧按 kind 决定。"""
    for source in db.sources(db.collections_pending_index()):
        if source_state(source) in {"ready", "partial"} and (
            not source["index_id"] or (source.get("index_status") == "completed"
                                      and source.get("chunk_version") != CHUNK_VERSION)
        ):
            db.create_index(source)
    return [
        (kind, record_id)
        for kind in DISPATCH_KINDS
        for record_id in db.claim_dispatchable(kind, 2)
    ]


def graph_expand(
    db: KnowledgeExecutionRepository, project_id: int, hits: list[dict], sources: list[dict]
) -> tuple[list[dict], list[dict]]:
    snapshot = db.relation_snapshot(project_id)
    if snapshot is None:
        return hits, []
    data = snapshot["data"]
    records = {row["id"]: row for bucket in ("facts", "requirements", "format_nodes")
               for row in data[bucket]}
    identity = ("source_id", "collection_id", "version_id", "parse_run_id")
    source_runs = {tuple(s[k] for k in identity) for s in sources}
    allowed = set(db.collections_for_project(project_id))
    relations = []
    for row in data["relations"]:
        endpoints = [records.get(row[key]) for key in ("subject_id", "object_id")]
        if (
            row["verification"] != "supported" or row["scope"]["kind"] == "unknown"
            or any(r is None or r["verification"] != "supported" for r in endpoints)
            or not row["citations"]
            or any(tuple(ref[k] for k in identity) not in source_runs
                   or ref["collection_id"] not in allowed for ref in row["citations"])
        ):
            continue
        relations.append(row)
    selected = []
    names = set()
    hit_ids = {r["block_id"] for r in hits}
    # 权限和原文版本会变化；遍历前整条复核，避免失效边把第二跳关系带入上下文。
    checked: dict[str, bool] = {}
    for _depth in range(2):
        next_names = set()
        for rel in relations:
            if rel in selected:
                continue
            # 原文名称和列举顺序仅供展示，遍历按已解析标段集合匹配同一范围。
            scope_key = (rel["scope"]["kind"], frozenset(rel["scope"]["lot_ids"]))
            if (
                hit_ids.intersection(ref["block_id"] for ref in rel["citations"])
                or (rel["subject_id"], scope_key) in names
                or (rel["object_id"], scope_key) in names
            ):
                for ref in rel["citations"]:
                    key = fingerprint(ref)
                    if key not in checked:
                        try:
                            db.resolve(ref)
                            checked[key] = True
                        except LookupError:
                            checked[key] = False
                if not all(checked[fingerprint(ref)] for ref in rel["citations"]):
                    continue
                selected.append(rel)
                next_names.update((rel[key], scope_key)
                                  for key in ("subject_id", "object_id"))
                if len(selected) >= 24:
                    break
        if len(selected) >= 24:
            break
        hit_ids = set()
        names = next_names
    if not selected:
        # 问答每次检索都会尝试扩展；无关联时无需反复读取全部资料。
        return hits, []
    seen = {r["block_id"] for r in hits}
    # 同一长元素可拆成多个块，只补读关系实际引用且尚未命中的块。
    wanted: dict[int, set[str]] = {}
    for rel in selected:
        for ref in rel["citations"]:
            if ref["block_id"] not in seen:
                wanted.setdefault(ref["source_id"], set()).add(ref["block_id"])
    for source in sources:
        # 按块序号保持原文顺序，不能把 c12 排在 c2 前面。
        positions = sorted((int(key.rsplit("c", 1)[1]), key)
                           for key in wanted.get(source["source_id"], set()))
        for offset, block_id in positions:
            # 已核验的稳定块ID包含序号；复用有界读取，索引缺失时也只读到目标块。
            for block in db.read_chunk_window(source, offset, 1).rows:
                if block["block_id"] == block_id and block_id not in seen:
                    hits.append(block)
                    seen.add(block_id)
    # 问答展示关系摘要，节点关联仍由稳定记录ID决定，不能靠归纳文字猜同一身份。
    predicates = {"supersedes": "替代", "conflicts": "冲突", "requires": "依赖", "contains": "包含"}
    return hits, [{
        "subject": records[rel["subject_id"]]["title"],
        "predicate": predicates[rel["predicate"]],
        "object": records[rel["object_id"]]["title"],
        "scope": ("公共要求" if rel["scope"]["kind"] == "common"
                  else "、".join(rel["scope"]["lot_refs"])),
        "condition": rel["text"], "citations": rel["citations"],
    } for rel in selected]


def _log_failure(event: str, exc: Exception, **fields: Any) -> None:
    # 业务失败被收敛到数据库后 Celery 会正常返回，必须在这里保留未知错误的堆栈。
    # 业务异常已在适配器脱敏，不回放原始异常链；未知故障仍保留完整链。
    logger.error(
        event,
        **fields,
        exception="".join(traceback.format_exception(exc, chain=not isinstance(exc, TenderError))),
    )


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
                # 入库前已组成完整条款；相同文字复用向量，来源与定位仍分别保存。
                passages = list(dict.fromkeys(r["content"] for r in chunks))
                embedded = []
                for start in range(0, len(passages), 16):
                    db.renew_lease("index", index_id)
                    embedded.extend(
                        await client.embed(passages[start : start + 16])
                    )
                if len(embedded) != len(passages):
                    raise ValueError("向量模型返回数量与检索单元数量不一致")
                by_content = dict(zip(passages, embedded, strict=True))
                vectors = [by_content[r["content"]] for r in chunks]
                if vectors and any(len(v) != len(vectors[0]) for v in vectors):
                    raise ValueError("向量模型在索引期间改变了维度")
            db.complete_index(index_id, chunks=chunks, vectors=vectors, config=config)
        except Exception as exc:
            _log_failure("index.fail", exc, index_id=index_id)
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

            async def read_source(source: dict, offset: int, limit: int):
                return await asyncio.to_thread(db.read_chunk_window, source, offset, limit)

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
            _log_failure("answer.fail", exc, answer_id=answer_id)
            db.finish_task("answer", answer_id, "failed", str(exc)[:1000])
