"""数据库访问端口：用例声明所需操作，PostgreSQL 实现负责 SQL 与事务。"""

from __future__ import annotations

import builtins
from typing import Any, Protocol


class ProjectRepository(Protocol):
    def create(
        self, *, name: str, project_no: str | None, owner: str | None
    ) -> dict[str, Any]: ...

    def list(
        self, *, offset: int, limit: int, keyword: str | None
    ) -> builtins.list[dict[str, Any]]: ...

    def project(self, project_id: int) -> dict[str, Any] | None: ...

    def files(self, project_id: int) -> builtins.list[dict[str, Any]]: ...

    def lots(self, project_id: int) -> builtins.list[dict[str, Any]]: ...

    def update(self, project_id: int, values: dict[str, object]) -> int: ...

    def soft_delete(self, project_id: int) -> int: ...
