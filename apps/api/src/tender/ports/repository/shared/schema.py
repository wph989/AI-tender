"""按调用者能力定义的仓储端口；SQL 与共享事务由同一实现提供。"""

from __future__ import annotations

from typing import Protocol


class SchemaReader(Protocol):
    def schema_columns(self, tables: list[str]) -> set[tuple[str, str]]:
        """当前 schema 下这些表实际存在的 (表名, 列名)。"""
        ...

    def schema_tables(self, tables: list[str]) -> set[str]:
        """当前 schema 下实际存在的表名。"""
        ...
