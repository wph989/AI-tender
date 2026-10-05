"""worker 里的 SQL 引用的列必须在 DDL 里存在（2026-10-01 真机 bug 的回归）。

背景：`worker/extraction.py` 的 `_load_candidates` 曾写 `m.api_key_ciphertext`，
但 `api_key_ciphertext` 属于 `llm_provider`（见 alembic 0003 第 21 行与
docs/设计/12 第 6 节，api/llm.py 取的是 `p.api_key_ciphertext`）。这个错误只在真机
跑抽取时以 `column m.api_key_ciphertext does not exist` 暴露，而抽取这一环此前从没
在真机跑通过（见 HANDOVER 第 21 节），所以它一直躺着。

为什么值得单独一个契约测试：这类错误编译器、ruff、分层检查全都不管，只有真机才会报，
而「真机跑一遍抽取」的成本远高于一个纯文本断言。

只做一件事：**凡是 `别名.列名` 且该别名由 `表名 AS 别名` 给出来的，列名必须在 DDL 里
属于那张表**。不做通用 SQL 校验（那需要真解析器）；识别不出的语句直接跳过，
但至少要真的校验到一条语句，否则这个测试就变成了静默空转。
"""

from __future__ import annotations

import re
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2]
WORKER_DIR = API_ROOT / "src" / "tender" / "worker"
ALEMBIC_DIR = API_ROOT / "alembic" / "versions"

_CREATE_TABLE = re.compile(r"CREATE TABLE\s+(\w+)\s*\((?P<body>.*?)\);", re.S)
# 不少列是后加的（0001 的 document.company_id、0002 的 project_file.sha256…），
# 漏掉 ALTER 会把它们误判成「不存在的列」——这个测试必须先真的承认 DDL 的现状。
_ALTER_ADD = re.compile(r"ALTER TABLE\s+(\w+)\s+(.*?);", re.I | re.S)
_ALIAS = re.compile(r"\b(\w+)\s+AS\s+(\w+)\b")
_QUALIFIED = re.compile(r"\b(\w+)\.(\w+)\b")
# DDL 的列定义行：第一段是列名；约束行不是列。
_NOT_A_COLUMN = {"CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "LIKE"}


def _ddl_columns() -> dict[str, set[str]]:
    """从全部迁移里解析出 表名 → 列名集合。"""
    tables: dict[str, set[str]] = {}
    for path in sorted(ALEMBIC_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in _CREATE_TABLE.finditer(text):
            table = match.group(1)
            columns: set[str] = tables.setdefault(table, set())
            for line in match.group("body").splitlines():
                head = line.strip().split(" ")[0].strip(",")
                if not head or head.upper() in _NOT_A_COLUMN:
                    continue
                columns.add(head)
        for table, operations in _ALTER_ADD.findall(text):
            # 同一 ALTER 可以连续 ADD 多列，不能只识别第一列而误报合法 SQL。
            for column in re.findall(r"\bADD COLUMN\s+(\w+)", operations, re.I):
                tables.setdefault(table, set()).add(column)
    return tables


def _sql_blocks(source: str) -> list[str]:
    """取出模块里所有三引号字符串——本项目把 SQL 都写成这种形式。"""
    return re.findall(r'"""(.*?)"""', source, re.S)


def test_worker_sql_columns_belong_to_their_alias_target() -> None:
    tables = _ddl_columns()
    assert tables, "没有解析到任何表结构，DDL 解析器已经和迁移格式脱节"

    checked = 0
    problems: list[str] = []
    for path in sorted(WORKER_DIR.glob("*.py")):
        for sql in _sql_blocks(path.read_text(encoding="utf-8")):
            aliases = {alias: table for table, alias in _ALIAS.findall(sql)}
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
    assert not problems, "worker SQL 引用了不存在的列：\n" + "\n".join(sorted(set(problems)))
