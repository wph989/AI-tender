"""按调用者能力定义的仓储端口；SQL 与共享事务由同一实现提供。"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol

from tender.ports.configuration.registry import ActiveConfig
from tender.ports.repository.knowledge.retrieval import RetrievalRepository
from tender.ports.repository.knowledge.sources import SourceReader


class KnowledgeTransaction(Protocol):
    def lock_collection(self, collection_id: int) -> None: ...

    def pending_index(self, source_id: int, run_id: int) -> bool: ...

    def insert_index(self, *, source_id: int, version_id: int, run_id: int) -> None: ...

    def lock_source(self, source_id: int) -> None: ...

    def inflight_source_job(self, source_id: int) -> bool: ...

    def insert_job(self, values: dict[str, Any]) -> None: ...

    def snapshot_for_job(self, active: ActiveConfig | None) -> int | None: ...


class KnowledgeRepository(SourceReader, RetrievalRepository, Protocol):
    def transaction(self) -> AbstractContextManager[KnowledgeTransaction]: ...

    def collection_overview(self) -> list[dict[str, Any]]:
        """全部知识库及其在用文件数，项目库排在独立库之前。"""
        ...

    def update_collection(self, collection_id: int, *, name: str, purpose: str) -> None:
        """改名与改用途；只作用于本公司未删除的知识库。"""
        ...

    def soft_delete_collection(self, collection_id: int) -> None:
        """软删除知识库；资料与历史答案的溯源记录保留。"""
        ...

    def source_for_processing(self, source_id: int) -> dict[str, Any] | None:
        """取资料以发起解析；跨公司、已删除或项目已删除时返回 ``None``。"""
        ...

    def mark_source_parseable(self, project_file_id: int) -> None:
        """把文件标记为可解析（用户显式要求处理原本判定为不支持的文件）。"""
        ...

    def has_parse_run(self, version_id: int) -> bool:
        """该版本是否已经解析过；决定重新处理是「首次」还是「重跑」。"""
        ...

    def answer(self, answer_id: int) -> dict[str, Any] | None:
        """取问答记录；跨公司时返回 ``None``。"""
        ...

    def create_collection(self, *, name: str, purpose: str) -> dict[str, Any]: ...

    def replace_links(self, project_id: int, collection_ids: list[int]) -> None: ...

    def enqueue_answer(
        self,
        *,
        project_id: int | None,
        collection_ids: list[int],
        question: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]: ...
