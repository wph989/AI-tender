"""装配点使用的组合契约；业务用例依赖各自的窄端口，不依赖本接口。"""

from __future__ import annotations

from typing import Protocol

from tender.ports.repository.analysis.reports import ReportRepository, ReportTransaction
from tender.ports.repository.knowledge.dispatch import KnowledgeDispatchRepository
from tender.ports.repository.knowledge.execution import KnowledgeExecutionRepository
from tender.ports.repository.knowledge.management import KnowledgeRepository, KnowledgeTransaction


class KnowledgeSession(ReportTransaction, KnowledgeTransaction, Protocol):
    def __enter__(self) -> KnowledgeSession: ...

    def __exit__(self, *exc: object) -> None: ...


class KnowledgeStore(
    ReportRepository,
    KnowledgeRepository,
    KnowledgeExecutionRepository,
    KnowledgeDispatchRepository,
    Protocol,
):
    # 同一实现仍可提供跨表事务；组合返回类型满足两个业务的事务子集。
    def transaction(self) -> KnowledgeSession: ...
