"""按调用者能力定义的仓储端口；SQL 与共享事务由同一实现提供。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SearchCandidates:
    rows: list[dict[str, Any]]
    semantic_source_ids: list[int]


class RetrievalRepository(Protocol):
    def search_candidates(
        self,
        sources: list[dict],
        query: str,
        vector: list[float] | None,
        signature: str | None,
        *,
        limit: int,
        min_similarity: float | None,
    ) -> SearchCandidates: ...

    def embedding_config(self) -> dict[str, Any] | None:
        """绑定到语义检索的向量模型；未配置时返回 ``None``。"""
        ...

    def rerank_config(self) -> dict[str, Any] | None:
        """绑定到重排的模型；未配置时返回 ``None``。"""
        ...
