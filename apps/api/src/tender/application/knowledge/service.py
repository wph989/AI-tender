"""知识库、资料处理、检索与问答用例。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from tender.application.documents.parsing import ParseService
from tender.application.knowledge.content import align_citation, dedupe_citations, source_state
from tender.application.knowledge.retrieval import retrieve_chunks
from tender.application.projects.files import role_is_parseable
from tender.application.shared.errors import Conflict, Forbidden, InvalidArgument, NotFound
from tender.config.schema import document_execution_snapshot
from tender.ports.configuration.registry import ConfigReader
from tender.ports.llm.embedding import EmbeddingModel
from tender.ports.repository.knowledge.store import KnowledgeStore


def visible_items(
    store: KnowledgeStore,
    items: list[dict],
    allowed_collections: list[int] | None = None,
) -> list[dict]:
    result = []
    for item in items:
        accessible = True
        values: list[dict] = []
        # 同一元素会被多个值引用，按元素复用解析结果，避免反复查库与重复解析正文。
        resolved_elements: dict[tuple, dict] = {}
        for value in item.get("values", []):
            refs: list[dict] = []
            for ref in value.get("citations", []):
                try:
                    if (
                        allowed_collections is not None
                        and ref["collection_id"] not in allowed_collections
                    ):
                        raise LookupError("已解除知识库关联")
                    element_key = (
                        ref.get("version_id"),
                        ref.get("parse_run_id"),
                        ref.get("element_id"),
                        ref.get("anchor"),
                    )
                    resolved = resolved_elements.get(element_key)
                    if resolved is None:
                        # 只判可见性时不需要正文，避免为被丢弃的文本渲染全文。
                        resolved = store.resolve(ref, with_content=not item.get("output"))
                        resolved_elements[element_key] = resolved
                except LookupError:
                    accessible = False
                    break
                # 历史报告可能把同块其它事实当摘录；展示前按值回查元素原文收敛定位，
                # 只在原文里确定性找到该值时改写，找不到就保留原引用，不伪造位置。
                refs.append(
                    dict(ref)
                    if item.get("output")
                    else align_citation(
                        {str(ref.get("block_id")): resolved},
                        ref,
                        str(value.get("value") or ""),
                    )
                )
            if not accessible:
                break
            values.append({**value, "citations": dedupe_citations(refs)})
        if accessible and values:
            item = {**item, "values": values}
        result.append(
            item
            if accessible
            else {
                "id": item["id"],
                **({"record_id": item["record_id"]} if item.get("record_id") else {}),
                "field": item.get("field", "来源已不可用"),
                "group": item.get("group", ""),
                "sort_order": item.get("sort_order", 0),
                "values": [],
                "note": "资料已删除或解除关联，请更新分析。",
                "verification": "unavailable",
            }
        )
    return result


class KnowledgeService:
    def __init__(
        self,
        repository: KnowledgeStore,
        company_id: int,
        configs: ConfigReader,
        embedding_gateway: Callable[[dict], EmbeddingModel],
        parsing: ParseService,
    ) -> None:
        self.company_id = company_id
        self.configs = configs
        self.embedding_gateway = embedding_gateway
        self.store = repository
        self.parsing = parsing

    def collection(self, collection_id: int) -> dict[str, Any]:
        try:
            return self.store.collection(collection_id)
        except LookupError as exc:
            raise NotFound(str(exc)) from exc

    def project_collection(self, project_id: int) -> int:
        if not self.store.project_exists(project_id):
            raise NotFound("项目不存在")
        own = self.store.collection_for_project(project_id)
        if own is None:
            raise NotFound("项目资料库尚未创建")
        return own

    def public_sources(self, collection_ids: list[int]) -> list[dict]:
        return [{**row, "state": source_state(row)} for row in self.store.sources(collection_ids)]

    def list_collections(self) -> dict[str, Any]:
        return {"items": self.store.collection_overview()}

    def create_collection(self, *, name: str, purpose: str) -> dict[str, Any]:
        normalized = name.strip()
        if not normalized:
            raise InvalidArgument("知识库名称不能为空")
        return self.store.create_collection(name=normalized, purpose=purpose)

    def get_collection(self, collection_id: int) -> dict[str, Any]:
        collection = self.collection(collection_id)
        embedding = self.store.embedding_config()
        sources = self.public_sources([collection_id])
        for source in sources:
            source["semantic_ready"] = bool(
                embedding
                and source["index_status"] == "completed"
                and source["embedding_signature"] == embedding["signature"]
                and source["dimension"]
            )
            source["needs_reindex"] = bool(
                embedding and source["index_status"] == "completed" and not source["semantic_ready"]
            )
        return {
            **collection,
            "sources": sources,
            "embedding_configured": embedding is not None,
            "embedding_model": embedding["model_id"] if embedding else None,
        }

    def update_collection(
        self,
        collection_id: int,
        *,
        name: str,
        purpose: str,
    ) -> dict[str, Any]:
        collection = self.collection(collection_id)
        if collection["is_project"]:
            raise Conflict("项目资料库的名称与用途由项目维护", code="project_collection")
        normalized = name.strip()
        if not normalized:
            raise InvalidArgument("知识库名称不能为空")
        # 用途变更会改变已有答案的证据含义，只允许空库修改。
        if purpose != collection["purpose"] and self.store.sources([collection_id]):
            raise Conflict(
                "已有资料的知识库不能修改用途，请新建知识库",
                code="collection_not_empty",
            )
        self.store.update_collection(collection_id, name=normalized, purpose=purpose)
        return self.get_collection(collection_id)

    def delete_collection(self, collection_id: int) -> dict[str, bool]:
        collection = self.collection(collection_id)
        if collection["is_project"]:
            raise Conflict("请从项目入口管理项目资料", code="project_collection")
        self.store.soft_delete_collection(collection_id)
        return {"deleted": True}

    def reindex_collection(self, collection_id: int) -> dict[str, int]:
        self.collection(collection_id)
        count = 0
        with self.store.transaction() as tx:
            tx.lock_collection(collection_id)
            for source in self.store.sources([collection_id]):
                if source_state(source) not in {"ready", "partial"}:
                    continue
                if tx.pending_index(source["source_id"], source["parse_run_id"]):
                    continue
                tx.insert_index(
                    source_id=source["source_id"],
                    version_id=source["version_id"],
                    run_id=source["parse_run_id"],
                )
                count += 1
        return {"queued_count": count}

    async def search_collection(self, collection_id: int, query: str) -> dict[str, Any]:
        self.collection(collection_id)
        hits, info = await retrieve_chunks(
            self.store,
            await asyncio.to_thread(self.store.sources, [collection_id]),
            query,
            lambda: None,
            self.embedding_gateway,
            embedding_timeout=15,
        )
        for hit in hits:
            hit.pop("embedding", None)
        return {"items": hits, **info}

    def resolve_citation(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.store.resolve(payload)
        except LookupError as exc:
            raise NotFound(str(exc), code="citation_unavailable") from exc

    async def test_embedding(self) -> dict[str, Any]:
        config = self.store.embedding_config()
        if config is None:
            raise Conflict(
                "请先在模型管理中绑定语义检索向量模型",
                code="embedding_not_configured",
            )
        client = self.embedding_gateway(config)
        try:
            vectors = await client.embed(["招标资格条件与证明材料"])
            return {
                "status": "ok",
                "model": config["model_id"],
                "dimension": len(vectors[0]),
            }
        finally:
            await client.aclose()

    def process_source(self, source_id: int) -> dict[str, Any]:
        source = self.store.source_for_processing(source_id)
        if source is None:
            raise NotFound("资料不存在")
        suffix = PurePosixPath(source["display_name"]).suffix.lower()
        if not role_is_parseable(source["role"], suffix):
            raise Conflict(
                "此格式暂不支持解析，请提供 PDF、Office 或文本版本",
                code="unsupported_format",
            )
        self.store.mark_source_parseable(source["id"])
        if source["version_id"] is not None:
            return self.parsing.create_job(
                source["version_id"],
                tier=None,
                ocr_mode=None,
                force=self.store.has_parse_run(source["version_id"]),
                reason="资料重新处理",
                actor="local-user",
            )
        active = self.configs.active(self.company_id)
        job_id = f"job_{uuid4().hex}"
        with self.store.transaction() as tx:
            tx.lock_source(source["id"])
            if tx.inflight_source_job(source["id"]):
                raise Conflict("该资料已有处理任务", code="process_in_flight")
            tx.insert_job(
                {
                    "id": job_id,
                    "company_id": self.company_id,
                    "project_id": source["project_id"],
                    "project_file_id": source["id"],
                    "status": "pending",
                    "stage": "probing" if suffix == ".pdf" else "converting",
                    "config_snapshot": {
                        "tier": "standard",
                        "ocr_mode": "auto",
                        "auto_parse": True,
                        "execution": document_execution_snapshot(
                            active.resolved if active is not None else None
                        ),
                        "execution_origin": "created",
                    },
                    "config_snapshot_id": tx.snapshot_for_job(active),
                }
            )
        return {"job_id": job_id, "status": "pending"}

    def project_knowledge(self, project_id: int) -> dict[str, Any]:
        own_id = self.project_collection(project_id)
        ids = self.store.collections_for_project(project_id)
        return {
            "collection_id": own_id,
            "linked_collection_ids": [item for item in ids if item != own_id],
            "sources": self.public_sources([own_id]),
        }

    def link_collections(self, project_id: int, collection_ids: list[int]) -> dict[str, Any]:
        own_id = self.project_collection(project_id)
        ids = sorted(set(collection_ids) - {own_id})
        for collection_id in ids:
            collection = self.collection(collection_id)
            if collection["is_project"]:
                raise InvalidArgument(
                    "请关联独立知识库；项目材料按各项目隔离",
                    code="invalid_collection",
                )
        self.store.replace_links(project_id, ids)
        return {"linked_collection_ids": ids}

    def enqueue_question(
        self,
        *,
        question: str,
        collection_ids: list[int],
        project_id: int | None,
    ) -> dict[str, Any]:
        normalized = question.strip()
        if not normalized:
            raise InvalidArgument("请输入问题")
        for collection_id in collection_ids:
            self.collection(collection_id)
        sources = self.store.sources(collection_ids)
        if not any(source_state(source) in {"ready", "partial"} for source in sources):
            raise Conflict(
                "当前范围没有可读取的资料，请先完成文件解析",
                code="sources_unavailable",
            )
        return self.store.enqueue_answer(
            project_id=project_id,
            collection_ids=collection_ids,
            question=normalized,
            snapshot={"sources": sources},
        )

    def ask_collection(self, collection_id: int, question: str) -> dict[str, Any]:
        return self.enqueue_question(
            question=question,
            collection_ids=[collection_id],
            project_id=None,
        )

    def ask_project(
        self, project_id: int, question: str, collection_ids: list[int]
    ) -> dict[str, Any]:
        own_id = self.project_collection(project_id)
        allowed = self.store.collections_for_project(project_id)
        ids = sorted({own_id, *collection_ids})
        if set(ids) - set(allowed):
            raise Forbidden(
                "只能检索本项目已关联的知识库",
                code="collection_not_linked",
            )
        return self.enqueue_question(
            question=question,
            collection_ids=ids,
            project_id=project_id,
        )

    def get_answer(self, answer_id: int) -> dict[str, Any]:
        answer = self.store.answer(answer_id)
        if answer is None:
            raise NotFound("回答不存在")
        allowed = (
            self.store.collections_for_project(answer["project_id"])
            if answer["project_id"]
            else answer["collection_ids"]
        )
        answer["items"] = visible_items(self.store, answer["items"], allowed)
        relations = []
        for relation in answer["relations"]:
            candidate = {
                "id": str(relation.get("id", "relation")),
                "values": [{"value": "", "citations": relation["citations"]}],
            }
            visible = visible_items(self.store, [candidate], allowed)[0]
            if visible.get("verification") != "unavailable":
                relations.append(relation)
        answer["relations"] = relations
        return answer
