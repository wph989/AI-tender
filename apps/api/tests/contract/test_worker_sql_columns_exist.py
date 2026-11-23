"""裸 SQL 中的 `别名.列名` 必须属于当前基线对应的物理表。

SQL 列引用不会被 Python 编译器、Ruff 或分层检查验证，需要独立核对物理结构。
与 ORM 和文档契约共用基线解析器，避免不同测试维护不同的表、列事实源。

扫描范围包括 `worker/` 与 `adapters/pg/`。
当前 Worker 不允许直接访问数据库，导入边界由 test_layer_boundaries.py 检查；
ORM 表达不到的系统目录查询留在 adapters/pg/locks.py 与
repositories/analysis/runtime.py。这里仅核对能够识别的裸 SQL 列引用。

只做一件事：**凡是 `别名.列名` 且该别名由 `表名 AS 别名` 或 `FROM/JOIN 表名 别名`
给出来的，列名必须在 DDL 里属于那张表**。不做通用 SQL 校验（那需要真解析器）；
识别不出的语句直接跳过，但至少要真的校验到一条语句，否则这个测试就变成了静默空转。
"""

from __future__ import annotations

import re
from pathlib import Path

from test_orm_models_match_ddl import _parse_ddl_columns

API_ROOT = Path(__file__).resolve().parents[2]
SQL_DIRS = (
    API_ROOT / "src" / "tender" / "worker",
    API_ROOT / "src" / "tender" / "adapters" / "pg",
)
_ALIAS = re.compile(r"\b(\w+)\s+AS\s+(\w+)\b")
# 适配层的 pg_locks 查询用简写别名（`FROM agent_module_run a`），不带 AS 关键字。
_IMPLICIT_ALIAS = re.compile(r"\b(?:FROM|JOIN)\s+(\w+)\s+(\w+)\b", re.I)
# 简写别名会把紧跟表名的关键字一起吞进来（`FROM pg_database WHERE`），
# 这些不是别名，直接丢弃，避免把 `WHERE.` 之类的假限定名混进比对。
_SQL_KEYWORDS = {
    "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "FULL", "CROSS",
    "ON", "AND", "OR", "GROUP", "ORDER", "LIMIT", "OFFSET", "UNION", "SET",
    "SELECT", "VALUES", "RETURNING", "USING", "AS", "WITH", "HAVING",
}
_QUALIFIED = re.compile(r"\b(\w+)\.(\w+)\b")


def _sql_blocks(source: str) -> list[str]:
    """取出模块里所有三引号字符串——本项目把 SQL 都写成这种形式。"""
    return re.findall(r'"""(.*?)"""', source, re.S)


def _aliases(sql: str) -> dict[str, str]:
    """本语句里的 `别名 → 表名`；兼容 `AS` 与简写两种写法。"""
    found = {alias: table for table, alias in _ALIAS.findall(sql)}
    for table, alias in _IMPLICIT_ALIAS.findall(sql):
        if alias.upper() not in _SQL_KEYWORDS:
            found.setdefault(alias, table)
    return found


def test_sql_columns_belong_to_their_alias_target() -> None:
    tables = {table: set(columns) for table, columns in _parse_ddl_columns().items()}
    assert tables, "没有解析到任何表结构，DDL 解析器已经和迁移格式脱节"

    checked = 0
    problems: list[str] = []
    for directory in SQL_DIRS:
        for path in sorted(directory.rglob("*.py")):
            for sql in _sql_blocks(path.read_text(encoding="utf-8")):
                aliases = _aliases(sql)
                if not aliases:
                    continue
                checked += 1
                for qualifier, column in _QUALIFIED.findall(sql):
                    table = aliases.get(qualifier)
                    if table is None:
                        continue  # 不是本语句里的别名（例如命名参数），跳过
                    if table not in tables:
                        continue  # 表不在迁移里（视图/CTE 之类），跳过
                    if column not in tables[table]:
                        problems.append(f"{path.name}: {qualifier}.{column} 不属于 {table}")

    assert checked > 0, "没有校验到任何带别名的语句，这个测试已经空转"
    assert not problems, "裸 SQL 引用了不存在的列：\n" + "\n".join(sorted(set(problems)))
