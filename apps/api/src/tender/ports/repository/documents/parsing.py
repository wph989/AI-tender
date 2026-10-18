"""数据库访问端口：用例声明所需操作，PostgreSQL 实现负责 SQL 与事务。"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol

from tender.ports.configuration.registry import ActiveConfig


class ParseTransaction(Protocol):
    def snapshot_for_job(self, active: ActiveConfig | None) -> int | None: ...

    def lock_file(self, version_id: int, company_id: int) -> dict[str, Any] | None: ...

    def active_job(self, version_id: int) -> str | None: ...

    def prior_run(self, version_id: int) -> int | None: ...

    def insert_job(self, values: dict[str, Any]) -> None: ...


class ParseRepository(Protocol):
    def transaction(self) -> AbstractContextManager[ParseTransaction]: ...
