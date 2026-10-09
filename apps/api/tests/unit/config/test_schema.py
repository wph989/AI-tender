"""配置项定义、值解析、diff 与权限矩阵（设计文档 08 第 2、4、9 节）。"""

from __future__ import annotations

import pytest

from tender.config import schema


def test_defaults_cover_three_layers() -> None:
    layers = {entry.layer for entry in schema.ITEMS}
    assert layers == {schema.L1, schema.L2, schema.L3}


def test_l1_is_not_gated_but_l2_l3_are() -> None:
    """分层依据是生效代价：L1 只影响速度，L2/L3 会改变结果，必须走门禁。"""
    for entry in schema.ITEMS:
        assert entry.requires_gate is (entry.layer != schema.L1), entry.key


def test_resolve_values_merges_defaults_with_overrides() -> None:
    resolved = schema.resolve_values({"convert.max_inflight": 8})
    assert resolved["convert.max_inflight"] == 8
    assert resolved["parse.max_inflight"] == 2
    assert set(resolved) == {entry.key for entry in schema.ITEMS}


def test_resolve_values_keeps_unregistered_keys() -> None:
    """读取侧宽容：历史 release 里被移除的配置项要原样保留，回滚才不会静默改配置。"""
    assert schema.resolve_values({"not.registered": 1})["not.registered"] == 1


def test_item_rejects_unknown_key() -> None:
    """写入侧严格：未知 key 在写库前就要报错，静默丢弃会表现为"改了没生效"。"""
    with pytest.raises(schema.UnknownConfigKey):
        schema.item("not.registered")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("convert.max_inflight", True),  # bool 不是 int，避免 True 被当成 1
        ("convert.max_inflight", "4"),
        ("mineru.tier", 5),
        ("llm_aided.title_leveling", 1),
        ("extract.rerun.hide_threshold", "0.1"),
    ],
)
def test_validate_value_rejects_wrong_types(key: str, value: object) -> None:
    assert schema.validate_value(key, value) is not None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("convert.max_inflight", 4),
        ("extract.rerun.hide_threshold", 0.15),
        ("mineru.output_formats", ["middle_json", "zip"]),
        ("llm_aided.title_leveling", False),
    ],
)
def test_validate_value_accepts_expected_types(key: str, value: object) -> None:
    assert schema.validate_value(key, value) is None


def test_context_budget_has_no_upper_bound() -> None:
    """上下文预算不该被人工上限卡死：可用范围由当前绑定模型的窗口决定。"""
    assert schema.validate_value("analysis.context_tokens", 262144) is None
    assert schema.validate_value("analysis.context_tokens", 4095) is not None


def test_diff_values_only_lists_changes() -> None:
    old = {"a": 1, "b": [1, 2]}
    new = {"a": 1, "b": [1, 2, 3], "c": 5}
    assert schema.diff_values(old, new) == {
        "b": {"old": [1, 2], "new": [1, 2, 3]},
        "c": {"old": None, "new": 5},
    }


def test_diff_values_ignores_identical_values() -> None:
    """没变的 key 不进 diff：影响清单里出现无关项会淹没真正要看的东西。"""
    assert schema.diff_values({"a": 1, "b": True}, {"a": 1, "b": True}) == {}


def test_write_denial_follows_layer_permissions() -> None:
    assert schema.write_denial("operator", ["convert.max_inflight"]) is None
    assert schema.write_denial("operator", ["mineru.tier"]) is not None
    assert schema.write_denial("admin", ["extract.scope.per_lot"]) is None
    assert schema.write_denial("viewer", ["convert.max_inflight"]) is not None
    assert schema.write_denial("reviewer", ["mineru.tier"]) is not None


def test_write_denial_rejects_unknown_role() -> None:
    assert schema.write_denial("root", ["convert.max_inflight"]) is not None


def test_gated_keys_only_keeps_l2_l3() -> None:
    keys = ["convert.max_inflight", "mineru.tier", "extract.strategy.dual_route"]
    assert schema.gated_keys(keys) == {"mineru.tier", "extract.strategy.dual_route"}
