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
    assert schema.validate_value("analysis.context_tokens", 1) is None
    assert schema.validate_value("analysis.context_tokens", 0) is not None


@pytest.mark.parametrize("value", [1, 511, 16385, 262144])
def test_output_budget_accepts_positive_integers_without_upper_bound(value: int) -> None:
    """同时覆盖原下限和上限之外的合法值，防止旧范围重新阻断配置保存。"""
    assert schema.validate_value("analysis.max_output_tokens", value) is None


@pytest.mark.parametrize("value", [0, -1, 1.5, True, "8192"])
def test_output_budget_rejects_non_positive_or_non_integer_values(value: object) -> None:
    assert schema.validate_value("analysis.max_output_tokens", value) is not None


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
    assert schema.write_denial("admin", ["extract.rerun.min_sample"]) is None
    assert schema.write_denial("viewer", ["convert.max_inflight"]) is not None
    assert schema.write_denial("reviewer", ["mineru.tier"]) is not None


def test_write_denial_rejects_unknown_role() -> None:
    assert schema.write_denial("root", ["convert.max_inflight"]) is not None


def test_gated_keys_only_keeps_l2_l3() -> None:
    keys = ["convert.max_inflight", "mineru.tier", "extract.strategy.dual_route"]
    assert schema.gated_keys(keys) == {"mineru.tier", "extract.strategy.dual_route"}


@pytest.mark.parametrize("key", [
    entry.key for entry in schema.ITEMS if entry.key.startswith("analysis.")
])
def test_analysis_budgets_have_no_artificial_maximum(key: str) -> None:
    assert schema.validate_value(key, 1000000) is None
    assert schema.validate_value(key, 1) is None
    assert schema.validate_value(key, -1) is not None


@pytest.mark.parametrize("value", [-0.1, 1.1, float("inf"), float("nan")])
def test_ratio_must_be_finite_and_between_zero_and_one(value: float) -> None:
    assert schema.validate_value("extract.rerun.hide_threshold", value) is not None


def test_nonnegative_budgets_keep_pause_and_no_retry_semantics() -> None:
    for key in ("convert.max_inflight", "parse.max_inflight", "extract.max_inflight",
                "analysis.max_subagent_retries", "job.retry.convert_500"):
        assert schema.validate_value(key, 0) is None
    assert schema.validate_value("analysis.max_inflight", 0) is not None


def test_unimplemented_controls_are_readonly_even_for_admin() -> None:
    assert schema.write_denial("admin", ["preprocess.denoise"]) is not None
    assert schema.write_denial("admin", ["mineru.page_range"]) is not None
    assert schema.write_denial("admin", ["mineru.tier"]) is None


def test_poll_maximum_cannot_be_smaller_than_initial_interval() -> None:
    assert schema.validate_values(schema.resolve_values({"job.poll.max_interval_ms": 1000}))
    values = schema.resolve_values({"job.poll.initial_interval_ms": 1000})
    assert schema.validate_values(values) is None


def test_parse_defaults_and_explicit_overrides_use_validated_active_values() -> None:
    values = {"mineru.tier": "advanced", "mineru.ocr_mode": "ocr"}
    assert schema.parse_options(values) == {"tier": "advanced", "ocr_mode": "ocr"}
    assert schema.parse_options(values, "basic") == {"tier": "basic", "ocr_mode": "ocr"}
    with pytest.raises(ValueError):
        schema.parse_options(values, "unsupported")
