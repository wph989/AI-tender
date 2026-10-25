"""按调用者能力定义的仓储端口；SQL 与共享事务由同一实现提供。"""

from __future__ import annotations

from typing import Any, Protocol

from tender.ports.repository.jobs.lifecycle import TaskLifecycle
from tender.ports.repository.knowledge.retrieval import RetrievalRepository
from tender.ports.repository.knowledge.sources import SourceReader


class KnowledgeExecutionRepository(SourceReader, RetrievalRepository, TaskLifecycle, Protocol):
    def answer(self, answer_id: int) -> dict[str, Any] | None:
        """取问答记录；跨公司时返回 ``None``。"""
        ...

    def mark_answer_running(self, answer_id: int) -> None:
        """问答开始执行。"""
        ...

    def save_answer(
        self,
        answer_id: int,
        *,
        items: list[Any],
        relations: list[Any],
        snapshot: dict[str, Any],
    ) -> None:
        """写回问答结果与本次检索口径。"""
        ...

    def index_for_build(self, index_id: int) -> dict[str, Any] | None:
        """取索引任务（含所属知识库）以执行构建；跨公司时返回 ``None``。"""
        ...

    def mark_index_running(self, index_id: int) -> None:
        """索引任务开始执行。"""
        ...

    def complete_index(
        self,
        index_id: int,
        *,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """用重建的分块与向量收口索引：整批替换旧分块，再写完成态与嵌入空间。"""
        ...
