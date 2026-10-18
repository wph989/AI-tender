"""派发事务契约：在途计数、候选锁定与派发标记共享一次事务。"""

from contextlib import AbstractContextManager
from typing import Protocol


class DispatchTransaction(Protocol):
    def inflight(self, stages: tuple[str, ...], company_id: int) -> int: ...

    def pending(self, stages: tuple[str, ...], company_id: int, limit: int | None) -> list[str]: ...

    def mark_dispatched(self, job_id: str) -> None: ...


class DispatchRepository(Protocol):
    def transaction(self) -> AbstractContextManager[DispatchTransaction]: ...
