"""迁移与设计文档的 DDL 一致性（防漂移）。

DDL 的权威是设计文档（[03](../../../../docs/设计/03-数据模型与溯源设计.md) 第 5 节、
[08](../../../../docs/质量/08-动态配置中心.md) 第 7 节、
[09](../../../../docs/质量/09-评测与质量门禁.md) 第 10 节），
`alembic/versions/0001_initial_schema.py` 只是它的可执行副本。

这里两侧各解析一次再按结构比对（表名 / 列名 / 索引名），不比对文本：
文档里加了列而迁移没跟上、或者迁移里手改出一个文档没有的列，都会立刻变红。
和 `packages/contract` 的坐标向量是同一个思路——同一个事实只能有一份权威，
另一侧必须由机制盯着（见 docs/工程/10 第 4.5 节）。

跑法：`uv run pytest`（迁移模块 import sqlalchemy / alembic，系统 python 里没有）。
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

_API_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_MIGRATION_PATH = _API_ROOT / "alembic" / "versions" / "0001_initial_schema.py"

# 迁移覆盖的文档与 sql 代码块序号（同一个文件内按出现顺序从 0 开始）
_SOURCES: tuple[tuple[str, int], ...] = (
    ("设计/03-数据模型与溯源设计.md", 0),
    ("设计/03-数据模型与溯源设计.md", 1),
    ("设计/03-数据模型与溯源设计.md", 2),
    ("设计/03-数据模型与溯源设计.md", 3),
    ("质量/08-动态配置中心.md", 0),
    ("质量/09-评测与质量门禁.md", 0),
)

# 两处外键在文档里写成列内 REFERENCES，而它们互相引用（field_instance ↔ extraction、
# config_release ↔ regression_run），PostgreSQL 要求被引用表在建表时就存在，
# 所以迁移把它们延后成 ALTER ... ADD CONSTRAINT。断言这些 ALTER 还在且指向的表没变，
# 否则外键会被静默丢掉——建表本身不会报错，只有数据出现孤儿行时才暴露。
_DEFERRED_FKS: tuple[tuple[str, str, str], ...] = (
    ("field_instance", "current_extraction_id", "fk_field_instance_current_extraction"),
    ("config_release", "regression_run_id", "fk_config_release_regression_run"),
)

_CREATE_TABLE_RE = re.compile(r"^CREATE TABLE (\w+) \((.*?)^\);", re.S | re.M)
_ADD_COLUMN_RE = re.compile(r"^ALTER TABLE (\w+)\s+ADD COLUMN (\w+)", re.M)
_CREATE_INDEX_RE = re.compile(r"^CREATE (?:UNIQUE )?INDEX (\w+) ON (\w+)", re.M)

# 出现在列位置上但不是列名的行首关键字（表级约束）
_CONSTRAINT_KEYWORDS = frozenset({"unique", "primary", "constraint", "foreign", "check", "exclude"})


@dataclass(frozen=True)
class _Schema:
    """从一段 DDL 文本里抽出的结构，用于两侧比对。"""

    tables: dict[str, frozenset[str]]
    indexes: dict[str, str]
    added_columns: dict[str, frozenset[str]]


def _load_migration() -> ModuleType:
    """import 迁移模块取 ``_STATEMENTS``，而不是从源码文本里抠字符串。

    这样比对的是「迁移真正会执行的 SQL」，将来改写源码形态（换引号、拆行）不会让测试失效。
    模块名以数字开头，不能走普通 import，用 spec_from_file_location 加载。
    """
    spec = importlib.util.spec_from_file_location("_ddl_0001", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _doc_ddl() -> str:
    blocks = []
    for relative_path, fence_no in _SOURCES:
        text = (_REPO_ROOT / "docs" / relative_path).read_text(encoding="utf-8")
        blocks.append(re.findall(r"```sql\n(.*?)```", text, re.S)[fence_no])
    return "\n\n".join(blocks)


def _parse(sql: str, label: str) -> _Schema:
    tables: dict[str, set[str]] = {}
    for match in _CREATE_TABLE_RE.finditer(sql):
        columns: set[str] = set()
        for line in match.group(2).splitlines():
            line = line.strip()
            if not line or line.startswith("--"):
                continue
            token = re.match(r"(\w+)\s", line)
            if token is None or token.group(1).lower() in _CONSTRAINT_KEYWORDS:
                continue
            columns.add(token.group(1))
        tables[match.group(1)] = columns

    added: dict[str, set[str]] = {}
    for match in _ADD_COLUMN_RE.finditer(sql):
        added.setdefault(match.group(1), set()).add(match.group(2))

    indexes = {match.group(1): match.group(2) for match in _CREATE_INDEX_RE.finditer(sql)}

    # 解析器静默失效（比如文档把 CREATE TABLE 改成小写）比比对失败更危险，这里直接拦掉
    assert tables and indexes, f"{label} 没解析出表或索引：DDL 的书写形态变了，解析器要跟进"

    return _Schema(
        tables={name: frozenset(columns) for name, columns in tables.items()},
        indexes=indexes,
        added_columns={name: frozenset(columns) for name, columns in added.items()},
    )


_DOC_DDL = _doc_ddl()
_MIGRATION_SQL = "\n\n".join(_load_migration()._STATEMENTS)
_DOC_SCHEMA = _parse(_DOC_DDL, "设计文档")
_MIGRATION_SCHEMA = _parse(_MIGRATION_SQL, "迁移")

_ALL_TABLE_NAMES = sorted(set(_DOC_SCHEMA.tables) | set(_MIGRATION_SCHEMA.tables))


def test_table_names_match_docs() -> None:
    assert set(_MIGRATION_SCHEMA.tables) == set(_DOC_SCHEMA.tables)


@pytest.mark.parametrize("table", _ALL_TABLE_NAMES)
def test_columns_match_docs(table: str) -> None:
    assert _MIGRATION_SCHEMA.tables.get(table) == _DOC_SCHEMA.tables.get(table)


def test_indexes_match_docs() -> None:
    assert _MIGRATION_SCHEMA.indexes == _DOC_SCHEMA.indexes


def test_added_columns_match_docs() -> None:
    assert _MIGRATION_SCHEMA.added_columns == _DOC_SCHEMA.added_columns


@pytest.mark.parametrize(
    ("table", "column", "constraint"),
    _DEFERRED_FKS,
    ids=[f"{table}.{column}" for table, column, _ in _DEFERRED_FKS],
)
def test_deferred_foreign_key_is_still_added(table: str, column: str, constraint: str) -> None:
    documented = re.search(rf"{column}\s+BIGINT\s+REFERENCES\s+(\w+)\(", _DOC_DDL)
    assert documented is not None, f"文档里 {column} 不再是列内 REFERENCES，本测试需要跟进"

    assert re.search(
        rf"ALTER TABLE {table}\s+ADD CONSTRAINT {constraint}\s+"
        rf"FOREIGN KEY \({column}\) REFERENCES {documented.group(1)}\(id\)",
        _MIGRATION_SQL,
    ), f"迁移里缺少延后补的 {constraint}，外键会被静默丢掉"

    # 建表时不能再写成列内 REFERENCES，否则同一个外键会被建两次
    assert not re.search(rf"{column}\s+BIGINT\s+REFERENCES", _MIGRATION_SQL)


def test_trigram_extension_is_created() -> None:
    """文档的 DDL 里没有 CREATE EXTENSION：它是迁移必须补的第一处补充。

    element.text 的 gin_trgm_ops 索引依赖 pg_trgm，缺了它整个迁移在第一条索引就失败。
    """
    assert "gin_trgm_ops" in _DOC_DDL, "文档不再用 trigram 索引，这条补充可以删掉了"
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in _MIGRATION_SQL


def test_drop_order_is_reverse_of_creation() -> None:
    """删表必须严格逆序：先建的后删，否则外键会挡住 DROP。"""
    drop_order = tuple(_load_migration()._TABLES_IN_DROP_ORDER)
    created_order = [match.group(1) for match in _CREATE_TABLE_RE.finditer(_MIGRATION_SQL)]

    assert len(drop_order) == len(set(drop_order)), "删表清单里有重复"
    assert set(drop_order) == set(_DOC_SCHEMA.tables), "删表清单与建表清单不一致"
    assert list(drop_order) == created_order[::-1]
