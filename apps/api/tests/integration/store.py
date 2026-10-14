"""集成测试专用仓储：在真实仓储上补两个直连测试 schema 的 SQL 手柄。

生产代码一律走仓储方法（`KnowledgeStore` 的 ORM 取数）；只有集成测试需要用裸 SQL
造夹具数据、改终态或断言落库结果，所以这两个方法刻意留在测试侧，不往 adapters 的
`KnowledgeStore` 上加逃生口。连接语义与仓储一致：查询用独立连接，写入自成一笔事务。
"""

from __future__ import annotations

from sqlalchemy import text

from tender.adapters.pg.repositories.knowledge import KnowledgeStore


class SqlStore(KnowledgeStore):
    """集成测试仓储；除两个 SQL 手柄外与原实现完全一致。"""

    def rows(self, sql: str, params: dict | None = None) -> list[dict]:
        with self.engine.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    text(sql), {**(params or {}), "company_id": self.company_id}
                ).mappings()
            ]

    def execute(self, sql: str, params: dict | None = None) -> None:
        with self.engine.begin() as connection:
            connection.execute(text(sql), {**(params or {}), "company_id": self.company_id})
