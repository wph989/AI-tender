"""当前数据库文档登记所有业务表及列，避免保留与生产无关的旧表设计。"""

import re
from pathlib import Path

from test_orm_models_match_ddl import _parse_ddl_columns


def test_current_schema_tables_and_columns_match_docs():
    document = (Path(__file__).resolve().parents[4]
                / "docs/设计/03-数据模型与溯源设计.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([a-z_]+)` \| ([^|]+) \|$", document, re.M)
    documented = {table: set(re.findall(r"`([a-z_0-9]+)`", columns)) for table, columns in rows}
    actual = _parse_ddl_columns()
    assert documented, "当前物理表清单为空"
    assert documented == {table: set(columns) for table, columns in actual.items()}
