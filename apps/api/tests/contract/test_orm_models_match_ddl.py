"""ORM 模型与迁移 DDL 的一致性契约（事实源链条的最后一跳）。

当前基线 SQL 是物理结构的权威；文档登记表与列，ORM只表达访问映射。
前两跳由 test_ddl_matches_docs 守住，这里守最后一跳：Base.metadata 的
表名、列名、可空性、列类型必须与把全部迁移顺序执行后的库完全一致。

只比对这四样：models 包刻意不复制默认值/索引/约束/外键行级行为（见包 docstring），
在模型里再写一份等于制造第二事实源，两边都能自洽地漂移，反而没有测试抓得住。

解析器失效（迁移换了书写形态）必须显式失败，不能让比对静默空转。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql

from tender.adapters.pg.models import Base

_API_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_DIR = _API_ROOT / "alembic" / "versions"

# alembic 自己管理的版本表不归业务模型管
_IGNORED_TABLES = frozenset({"alembic_version"})

_CREATE_TABLE_RE = re.compile(r"^CREATE TABLE (\w+) \((.*?)^\s*\);", re.S | re.M)
_ALTER_TABLE_RE = re.compile(r"^ALTER TABLE (\w+)\s+(.*?);", re.S | re.M)
_ADD_COLUMN_RE = re.compile(r"ADD COLUMN\s+(\w+)\s+(.+)$", re.M)
_ALTER_COLUMN_TYPE_RE = re.compile(r"ALTER COLUMN\s+(\w+)\s+TYPE\s+(.+)$", re.M)
_TABLE_PK_RE = re.compile(r"^(?:CONSTRAINT\s+\w+\s+)?PRIMARY KEY\s*\(([^)]+)\)")
_TYPE_RE = re.compile(
    r"^(DOUBLE PRECISION\[\]|DOUBLE PRECISION|TIMESTAMPTZ|TIMESTAMP WITH TIME ZONE"
    r"|BIGSERIAL|SMALLSERIAL|SERIAL|BIGINT\[\]|BIGINT|SMALLINT|INTEGER|INT"
    r"|TEXT\[\]|TEXT|BOOLEAN|JSONB|BYTEA|UUID|NUMERIC\([^)]*\)|CHAR\(\d+\)|VARCHAR\(\d+\))"
)
_TYPE_ALIASES = {
    "BIGSERIAL": "BIGINT",
    "SMALLSERIAL": "SMALLINT",
    "SERIAL": "INTEGER",
    "INT": "INTEGER",
    "TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE",
}
# 列位置上但不是列名的行首关键字（表级约束）
_CONSTRAINT_KEYWORDS = frozenset({"constraint", "primary", "unique", "foreign", "check", "exclude"})
# 库里的列定义总量（含 alembic_version 之外的全部业务列）；低于它就是解析器漏读了
_MIN_EXPECTED_COLUMNS = 350


def _norm(type_text: str) -> str:
    """归一化类型文本：统一大小写并去掉全部空白，抵消 DDL 与编译器的排版差异。"""
    return "".join(type_text.upper().split())


def _statement_text() -> str:
    """按文件名顺序拼接全部迁移的 _STATEMENTS，等价于顺序执行到 head。"""
    parts: list[str] = []
    for path in sorted(_ALEMBIC_DIR.glob("[0-9]*.py")):
        spec = importlib.util.spec_from_file_location(f"_orm_ddl_{path.stem}", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        statements = getattr(module, "_STATEMENTS", None)
        assert statements, f"{path.name} 没有 _STATEMENTS，迁移的书写形态变了"
        parts.extend(statements)
    assert len(parts) >= 12, "没有读到全部迁移：glob 模式或文件命名变了"
    return "\n\n".join(parts)


def _column_type(rest: str, label: str) -> tuple[str, bool]:
    """从列定义的类型起头处解析出「归一化类型 + 是否可空」。"""
    rest = rest.upper().replace("CHARACTER VARYING", "VARCHAR").replace("CHARACTER", "CHAR")
    match = _TYPE_RE.match(rest)
    assert match is not None, f"{label} 的列类型没解析出来：{rest}（解析器要跟进）"
    raw_type = match.group(1)
    tail = rest[match.end() :]
    assert tail == "" or tail.startswith(" "), f"{label} 的类型后有未识别字符：{rest}"
    serial = raw_type.upper() in {"BIGSERIAL", "SMALLSERIAL", "SERIAL"}
    # SERIAL 系列隐含 NOT NULL（建列时等价于 NOT NULL DEFAULT nextval(...)）
    nullable = "NOT NULL" not in tail and "PRIMARY KEY" not in tail and not serial
    return _norm(_TYPE_ALIASES.get(raw_type.upper(), raw_type)), nullable


def _parse_ddl_columns() -> dict[str, dict[str, tuple[str, bool]]]:
    sql = _statement_text()
    tables: dict[str, dict[str, tuple[str, bool]]] = {}

    for match in _CREATE_TABLE_RE.finditer(sql):
        table, body = match.group(1), match.group(2)
        if table in _IGNORED_TABLES:
            continue
        columns = tables.setdefault(table, {})
        pk_columns: set[str] = set()
        for raw_line in body.splitlines():
            line = raw_line.split("--", 1)[0].strip().rstrip(",")
            if not line:
                continue
            head = line.split(None, 1)[0]
            if head.lower() in _CONSTRAINT_KEYWORDS:
                pk = _TABLE_PK_RE.match(line)
                if pk is not None:
                    pk_columns.update(column.strip() for column in pk.group(1).split(","))
                continue
            rest = line[len(head) :].strip()
            assert rest, f"{table}.{head} 没有类型（解析器要跟进）：{line}"
            columns[head.strip('"')] = _column_type(rest, f"{table}.{head}")
        # 联合主键的列必然 NOT NULL；解析不到说明前面漏了列，直接 KeyError 暴露
        for column in pk_columns:
            columns[column] = (columns[column][0], False)

    for match in _ALTER_TABLE_RE.finditer(sql):
        table, body = match.group(1), match.group(2)
        if table in _IGNORED_TABLES:
            continue
        for add in _ADD_COLUMN_RE.finditer(body):
            column, rest = add.group(1), add.group(2).strip().rstrip(",")
            tables.setdefault(table, {})[column] = _column_type(rest, f"{table}.{column}")
        for change in _ALTER_COLUMN_TYPE_RE.finditer(body):
            column, rest = change.group(1), change.group(2).strip().rstrip(",")
            # 类型迁移不改变可空性；按正式迁移更新类型，避免仍拿初始DDL比较head模型。
            assert column in tables[table], f"修改了未知列类型：{table}.{column}"
            kind, _ = _column_type(rest, f"{table}.{column}")
            tables[table][column] = kind, tables[table][column][1]

    # 下线迁移仍保留在历史链中，但 head 的模型不再承载被移除的表和列。
    for table, column in re.findall(r"ALTER TABLE (\w+) DROP COLUMN (\w+);", sql):
        assert column in tables[table], f"删除了未知列：{table}.{column}"
        del tables[table][column]
    for table in re.findall(r"DROP TABLE (\w+);", sql):
        assert table in tables, f"删除了未知表：{table}"
        del tables[table]
    return tables


def _parse_model_columns() -> dict[str, dict[str, tuple[str, bool]]]:
    dialect = postgresql.dialect()
    tables: dict[str, dict[str, tuple[str, bool]]] = {}
    for name, table in Base.metadata.tables.items():
        assert name not in _IGNORED_TABLES, f"{name} 不该出现在业务模型里"
        assert table.primary_key.columns, f"模型 {name} 没有主键定义"
        tables[name] = {
            column.name: (_norm(column.type.compile(dialect=dialect)), column.nullable)
            for column in table.columns
        }
    return tables


_DDL_COLUMNS = _parse_ddl_columns()
_MODEL_COLUMNS = _parse_model_columns()
_ALL_TABLES = sorted(set(_DDL_COLUMNS) | set(_MODEL_COLUMNS))


def test_ddl_parser_read_enough_tables_and_columns() -> None:
    """解析器自身的闸门：漏读必须报错，而不是让比对悄悄变成空转。"""
    total = sum(len(columns) for columns in _DDL_COLUMNS.values())
    assert len(_DDL_COLUMNS) >= 30, f"只解析到 {len(_DDL_COLUMNS)} 张表，迁移读取或解析器已脱节"
    assert total >= _MIN_EXPECTED_COLUMNS, f"只解析到 {total} 个列，解析器已脱节"


def test_table_sets_match() -> None:
    missing = sorted(set(_DDL_COLUMNS) - set(_MODEL_COLUMNS))
    extra = sorted(set(_MODEL_COLUMNS) - set(_DDL_COLUMNS))
    assert not missing and not extra, f"模型缺表 {missing}，模型多表 {extra}"


@pytest.mark.parametrize("table", _ALL_TABLES)
def test_columns_match(table: str) -> None:
    ddl = _DDL_COLUMNS.get(table)
    model = _MODEL_COLUMNS.get(table)
    assert ddl is not None, f"模型里多出表 {table}"
    assert model is not None, f"模型缺表 {table}"

    missing = sorted(set(ddl) - set(model))
    extra = sorted(set(model) - set(ddl))
    assert not missing and not extra, f"{table} 列名不一致：模型缺 {missing}，模型多 {extra}"

    mismatched = [
        f"{column}: 模型 {model[column]} ≠ 迁移 {ddl[column]}"
        for column in sorted(set(model) & set(ddl))
        if model[column] != ddl[column]
    ]
    assert not mismatched, f"{table} 的类型/可空性不一致：\n" + "\n".join(mismatched)
