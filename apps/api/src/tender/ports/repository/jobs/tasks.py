"""数据库访问端口：用例声明所需操作，PostgreSQL 实现负责 SQL 与事务。"""

from __future__ import annotations

from typing import Any, Protocol

TERMINAL_STATUSES = frozenset({"completed", "partial", "failed", "canceled"})


class JobRepository(Protocol):
    def payload(self, job_id: str) -> dict[str, Any] | None: ...

    def cancel(self, job_id: str) -> tuple[bool, str | None]: ...
