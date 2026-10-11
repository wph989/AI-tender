"""迁移与设计文档的 DDL 一致性（防漂移）。

DDL 的权威是设计文档（[03](../../../../docs/设计/03-数据模型与溯源设计.md) 第 5 节、
[08](../../../../docs/质量/08-动态配置中心.md) 第 7 节、
[09](../../../../docs/质量/09-评测与质量门禁.md) 第 10 节、
[12](../../../../docs/设计/12-LLM管理与模型路由.md) 第 6 节），
`alembic/versions/` 下的迁移只是它的可执行副本。

这里两侧各解析一次再按结构比对（表名 / 列名 / 索引名），不比对文本：
文档里加了列而迁移没跟上、或者迁移里手改出一个文档没有的列，都会立刻变红。
和 `packages/contract` 的坐标向量是同一个思路——同一个事实只能有一份权威，
另一侧必须由机制盯着（见 docs/工程/10 第 4.5 节）。

一个迁移对一份文档切片，`_MIGRATIONS` 是唯一需要维护的映射；
新增迁移时在这里加一行，比对逻辑本身不用改。

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

# 迁移覆盖的文档与 sql 代码块序号（同一个文件内按出现顺序从 0 开始）。
# 设计/03 里 §5.1.1（0002）、§5.1.2（0004）插在 §5.1 与 §5.2 之间，所以 0001 的块号不连续
# （0、1、5、6），0002 覆盖 §5.1.1、0004 覆盖 §5.1.2；插块时改这里，别改比对逻辑。
_SOURCES_0001: tuple[tuple[str, int], ...] = (
    ("设计/03-数据模型与溯源设计.md", 0),
    ("设计/03-数据模型与溯源设计.md", 1),
    ("设计/03-数据模型与溯源设计.md", 5),
    ("设计/03-数据模型与溯源设计.md", 6),
    ("质量/08-动态配置中心.md", 0),
    ("质量/09-评测与质量门禁.md", 0),
)
_SOURCES_0002: tuple[tuple[str, int], ...] = (("设计/03-数据模型与溯源设计.md", 2),)
_SOURCES_0003: tuple[tuple[str, int], ...] = (("设计/12-LLM管理与模型路由.md", 0),)
# 0004 只加列与索引、没有新表，所以 require_tables=False；
# 种子数据的一致性由 test_config_items_match_migration.py 负责。
_SOURCES_0004: tuple[tuple[str, int], ...] = (("设计/03-数据模型与溯源设计.md", 3),)


@dataclass(frozen=True)
class _MigrationSpec:
    file_name: str
    sources: tuple[tuple[str, int], ...]
    # 有的迁移只 ALTER 既有表（没有 CREATE TABLE），对应的文档切片自然解析不出表名
    require_tables: bool = True
    require_indexes: bool = True


_MIGRATIONS: tuple[_MigrationSpec, ...] = (
    _MigrationSpec("0011_analysis_data.py", (("设计/14-知识库与综合分析实现.md", 1),)),
    _MigrationSpec(
        "0009_provider_cooldown.py",
        (("设计/16-DeepAgents标书分析运行时.md", 1),),
        require_tables=False,
        require_indexes=False,
    ),
    _MigrationSpec("0008_deepagents_runtime.py", (("设计/16-DeepAgents标书分析运行时.md", 0),)),
    _MigrationSpec("0001_initial_schema.py", _SOURCES_0001),
    _MigrationSpec("0002_storage_and_jobs.py", _SOURCES_0002),
    _MigrationSpec("0003_llm_management.py", _SOURCES_0003),
    _MigrationSpec("0004_config_center.py", _SOURCES_0004, require_tables=False),
    _MigrationSpec("0005_knowledge_analysis.py", (("设计/14-知识库与综合分析实现.md", 0),)),
    _MigrationSpec("0006_model_capabilities.py", (("设计/12-LLM管理与模型路由.md", 1),)),
    _MigrationSpec(
        "0007_model_inputs.py",
        (("设计/12-LLM管理与模型路由.md", 2),),
        require_tables=False,
        require_indexes=False,
    ),
)

# 两处外键在文档里写成列内 REFERENCES，而它们互相引用（field_instance ↔ extraction、
# config_release ↔ regression_run），PostgreSQL 要求被引用表在建表时就存在，
# 所以 0001 把它们延后成 ALTER ... ADD CONSTRAINT。断言这些 ALTER 还在且指向的表没变，
# 否则外键会被静默丢掉——建表本身不会报错，只有数据出现孤儿行时才暴露。
_DEFERRED_FKS: tuple[tuple[str, str, str], ...] = (
    ("field_instance", "current_extraction_id", "fk_field_instance_current_extraction"),
    ("config_release", "regression_run_id", "fk_config_release_regression_run"),
)

_CREATE_TABLE_RE = re.compile(r"^CREATE TABLE (\w+) \((.*?)^\s*\);", re.S | re.M)
_ADD_COLUMN_RE = re.compile(r"^ALTER TABLE (\w+)\s+(.*?);", re.M | re.S)
_CREATE_INDEX_RE = re.compile(r"^CREATE (?:UNIQUE )?INDEX (\w+) ON (\w+)", re.M)
_SQL_FENCE_RE = re.compile(r"```sql\n(.*?)```", re.S)

# 出现在列位置上但不是列名的行首关键字（表级约束）
_CONSTRAINT_KEYWORDS = frozenset({"unique", "primary", "constraint", "foreign", "check", "exclude"})


@dataclass(frozen=True)
class _Schema:
    """从一段 DDL 文本里抽出的结构，用于两侧比对。"""

    tables: dict[str, frozenset[str]]
    indexes: dict[str, str]
    added_columns: dict[str, frozenset[str]]


def _load_migration(file_name: str) -> ModuleType:
    """import 迁移模块取 ``_STATEMENTS``，而不是从源码文本里抠字符串。

    这样比对的是「迁移真正会执行的 SQL」，将来改写源码形态（换引号、拆行）不会让测试失效。
    模块名以数字开头，不能走普通 import，用 spec_from_file_location 加载。
    """
    path = _API_ROOT / "alembic" / "versions" / file_name
    spec = importlib.util.spec_from_file_location(f"_ddl_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _doc_ddl(sources: tuple[tuple[str, int], ...]) -> str:
    blocks = []
    for relative_path, fence_no in sources:
        text = (_REPO_ROOT / "docs" / relative_path).read_text(encoding="utf-8")
        blocks.append(_SQL_FENCE_RE.findall(text)[fence_no])
    return "\n\n".join(blocks)


def _parse(
    sql: str, label: str, *, require_tables: bool = True, require_indexes: bool = True
) -> _Schema:
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
        for column in re.findall(r"\bADD COLUMN\s+(\w+)", match.group(2)):
            added.setdefault(match.group(1), set()).add(column)

    indexes = {match.group(1): match.group(2) for match in _CREATE_INDEX_RE.finditer(sql)}

    # 解析器静默失效（比如文档把 CREATE TABLE 改成小写）比比对失败更危险，这里直接拦掉
    if require_indexes:
        assert indexes, f"{label} 没解析出索引：DDL 的书写形态变了，解析器要跟进"
    if require_tables:
        assert tables, f"{label} 没解析出表：DDL 的书写形态变了，解析器要跟进"

    return _Schema(
        tables={name: frozenset(columns) for name, columns in tables.items()},
        indexes=indexes,
        added_columns={name: frozenset(columns) for name, columns in added.items()},
    )


@dataclass(frozen=True)
class _Case:
    name: str
    doc_text: str
    migration_sql: str
    module: ModuleType
    doc_schema: _Schema
    migration_schema: _Schema


def _build_cases() -> tuple[_Case, ...]:
    cases = []
    for spec in _MIGRATIONS:
        module = _load_migration(spec.file_name)
        doc_text = _doc_ddl(spec.sources)
        migration_sql = "\n\n".join(module._STATEMENTS)
        cases.append(
            _Case(
                name=spec.file_name.removesuffix(".py"),
                doc_text=doc_text,
                migration_sql=migration_sql,
                module=module,
                doc_schema=_parse(
                    doc_text,
                    f"{spec.file_name} 对应的设计文档",
                    require_tables=spec.require_tables,
                    require_indexes=spec.require_indexes,
                ),
                migration_schema=_parse(
                    migration_sql,
                    f"迁移 {spec.file_name}",
                    require_tables=spec.require_tables,
                    require_indexes=spec.require_indexes,
                ),
            )
        )
    return tuple(cases)


_CASES = _build_cases()
_CASE_BY_NAME = {case.name: case for case in _CASES}
_CASE_IDS = [case.name for case in _CASES]
_TABLE_CASES = [
    (case.name, table)
    for case in _CASES
    for table in sorted(set(case.doc_schema.tables) | set(case.migration_schema.tables))
]
_TABLE_IDS = [f"{case_name}.{table}" for case_name, table in _TABLE_CASES]

# 0001 的专项断言（延后外键、pg_trgm）只针对这一份迁移，保留原有取法。
_CASE_0001 = _CASE_BY_NAME["0001_initial_schema"]
_DOC_DDL = _CASE_0001.doc_text
_MIGRATION_SQL = _CASE_0001.migration_sql
_DOC_SCHEMA = _CASE_0001.doc_schema


@pytest.mark.parametrize("case_name", _CASE_IDS)
def test_table_names_match_docs(case_name: str) -> None:
    case = _CASE_BY_NAME[case_name]
    assert set(case.migration_schema.tables) == set(case.doc_schema.tables)


@pytest.mark.parametrize(("case_name", "table"), _TABLE_CASES, ids=_TABLE_IDS)
def test_columns_match_docs(case_name: str, table: str) -> None:
    case = _CASE_BY_NAME[case_name]
    assert case.migration_schema.tables.get(table) == case.doc_schema.tables.get(table)


@pytest.mark.parametrize("case_name", _CASE_IDS)
def test_indexes_match_docs(case_name: str) -> None:
    case = _CASE_BY_NAME[case_name]
    assert case.migration_schema.indexes == case.doc_schema.indexes


@pytest.mark.parametrize("case_name", _CASE_IDS)
def test_added_columns_match_docs(case_name: str) -> None:
    case = _CASE_BY_NAME[case_name]
    assert case.migration_schema.added_columns == case.doc_schema.added_columns


@pytest.mark.parametrize("case_name", _CASE_IDS)
def test_drop_order_is_reverse_of_creation(case_name: str) -> None:
    """删表必须严格逆序：先建的后删，否则外键会挡住 DROP。"""
    case = _CASE_BY_NAME[case_name]
    drop_order = getattr(case.module, "_TABLES_IN_DROP_ORDER", None)
    if drop_order is None:
        pytest.skip("该迁移没有显式删表清单（只有 ALTER/索引）")

    created_order = [match.group(1) for match in _CREATE_TABLE_RE.finditer(case.migration_sql)]

    assert len(drop_order) == len(set(drop_order)), "删表清单里有重复"
    assert set(drop_order) == set(case.doc_schema.tables), "删表清单与建表清单不一致"
    assert list(drop_order) == created_order[::-1]


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
