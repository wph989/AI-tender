"""`config_item` 种子与 `tender/config/schema.ITEMS` 的一致性（防双事实源漂移）。

默认值必须在代码里有一份（读不到配置时的兜底），也必须进 `config_item`（页面与审计用）；
两份清单手工同步迟早漂移，所以这里解析迁移里的 INSERT 逐项比对。
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType

from tender.config import schema

_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION = _API_ROOT / "alembic" / "versions" / "0004_config_center.py"

# 只认迁移里那种一行一条的写法：('key', 'L1', 'int', '4'::jsonb, '描述', false),
_ROW_RE = re.compile(
    r"\('([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']*)'::jsonb,\s*'([^']*)',\s*(true|false)\)"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_seed_0004_config_center", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_rows() -> list[tuple[str, str, str, str, str, bool]]:
    module = _load_migration()
    sql = "\n".join(module._STATEMENTS)
    rows = [
        (key, layer, value_type, default, description, requires_gate == "true")
        for key, layer, value_type, default, description, requires_gate in _ROW_RE.findall(sql)
    ]
    assert rows, "迁移里没解析出种子行：写法变了，解析器要跟进"
    return rows


def test_seed_keys_match_code_registry() -> None:
    assert {row[0] for row in _seed_rows()} == set(schema.ITEMS_BY_KEY)


def test_seed_rows_match_code_registry() -> None:
    for key, layer, value_type, default, description, requires_gate in _seed_rows():
        entry = schema.ITEMS_BY_KEY[key]
        assert layer == entry.layer, key
        assert value_type == entry.value_type, key
        assert json.loads(default) == entry.default, key
        assert description == entry.description, key
        assert requires_gate is entry.requires_gate, key


def test_baseline_release_is_seeded() -> None:
    """基线 release 必须存在：否则激活前的任务没有 release 可挂快照。"""
    module = _load_migration()
    sql = "\n".join(module._STATEMENTS)
    assert "INSERT INTO config_release" in sql
    assert "system:seed" in sql
