"""当前基线种子必须与运行配置一致，防止展示与执行使用不同默认值。"""

import importlib.util
import json
import re
from pathlib import Path

from tender.config import schema

_PATH = Path(__file__).resolve().parents[2] / "alembic/versions/0001_current_schema.py"


def _baseline():
    spec = importlib.util.spec_from_file_location("current_seed", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_rows_match_code_registry():
    pattern = re.compile(
        r"INSERT INTO config_item .*? VALUES \('([^']+)', '([^']+)', '([^']+)', "
        r"'([^']*)', '([^']*)', (true|false),"
    )
    rows = pattern.findall("\n".join(_baseline()._STATEMENTS))
    assert {row[0] for row in rows} == set(schema.ITEMS_BY_KEY)
    for key, layer, kind, default, description, gated in rows:
        entry = schema.item(key)
        assert (layer, kind, json.loads(default), description, gated == "true") == (
            entry.layer, entry.value_type, entry.default, entry.description, entry.requires_gate,
        ), key


def test_active_baseline_release_is_seeded():
    sql = "\n".join(_baseline()._STATEMENTS)
    assert "INSERT INTO config_release" in sql
    assert "system:seed" in sql
