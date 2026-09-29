"""门禁判定与影响清单（设计文档 08 第 5 节、09 第 7 节）。"""

from __future__ import annotations

from tender.config import gate


def _ack_all(impact: tuple[gate.ImpactItem, ...]) -> list[tuple[str, str]]:
    return [(entry.kind, entry.ref) for entry in impact]


def test_build_impact_is_stable_and_ordered() -> None:
    """同一份变更每次生成的清单必须逐字相同，否则逐条确认会反复失效。"""
    impact = gate.build_impact(
        ["mineru.tier", "convert.max_inflight"],
        regression_failures=[{"field_key": "bid_bond_amount", "anchor": "p12b5"}],
        added_fields=["new_field"],
        removed_fields=["old_field"],
    )
    assert impact == (
        gate.ImpactItem(gate.KIND_CONFIG_CHANGED, "convert.max_inflight"),
        gate.ImpactItem(gate.KIND_CONFIG_CHANGED, "mineru.tier"),
        gate.ImpactItem(gate.KIND_FIELD_DEF_CHANGED, "new_field"),
        gate.ImpactItem(gate.KIND_FIELD_REMOVED, "old_field"),
        gate.ImpactItem(gate.KIND_REGRESSION_FAILURE, "bid_bond_amount@p12b5"),
    )


def test_field_def_key_uses_field_kind() -> None:
    impact = gate.build_impact(["extract.fields"])
    assert impact[0].kind == gate.KIND_FIELD_DEF_CHANGED


def test_impact_state_marks_acked_items() -> None:
    impact = gate.build_impact(["mineru.tier", "render.crop_dpi"])
    state = gate.impact_state(impact, [("config_changed", "render.crop_dpi")])
    assert [(entry["ref"], entry["acked"]) for entry in state] == [
        ("mineru.tier", False),
        ("render.crop_dpi", True),
    ]


def test_gate_blocks_unacknowledged_impact() -> None:
    impact = gate.build_impact(["mineru.tier"])
    result = gate.evaluate_gate(impact=impact, acknowledged=[])
    assert result.passed is False
    assert result.blockers == ("impact_not_acknowledged",)


def test_gate_passes_cold_start_with_acks() -> None:
    """回归集为空（冷启动）时只校验影响清单。"""
    impact = gate.build_impact(["mineru.tier"])
    result = gate.evaluate_gate(impact=impact, acknowledged=_ack_all(impact), regression=None)
    assert result.passed is True
    assert result.blockers == ()


def test_gate_blocks_hallucination_and_anchor_404() -> None:
    impact = gate.build_impact(["mineru.tier"])
    regression = {
        "gold_total": 10,
        "pass_count": 10,
        "baseline_rate": 0.9,
        "failures": [{"kind": "hallucination"}, {"kind": "anchor_404"}],
    }
    result = gate.evaluate_gate(
        impact=impact,
        acknowledged=_ack_all(impact),
        regression=regression,
    )
    assert "hallucination_rate_not_zero" in result.blockers
    assert "anchor_404_not_zero" in result.blockers


def test_gate_blocks_pass_rate_below_baseline() -> None:
    impact = gate.build_impact(["mineru.tier"])
    regression = {"gold_total": 10, "pass_count": 8, "baseline_rate": 0.9, "failures": []}
    result = gate.evaluate_gate(impact=impact, acknowledged=_ack_all(impact), regression=regression)
    assert result.blockers == ("pass_rate_below_baseline",)


def test_gate_allows_pass_rate_equal_to_baseline() -> None:
    impact = gate.build_impact(["mineru.tier"])
    regression = {"gold_total": 10, "pass_count": 9, "baseline_rate": 0.9, "failures": []}
    result = gate.evaluate_gate(impact=impact, acknowledged=_ack_all(impact), regression=regression)
    assert result.passed is True


def test_gate_requires_force_when_first_pass_drops_over_two_points() -> None:
    impact = gate.build_impact(["mineru.tier"])
    regression = {
        "gold_total": 10,
        "pass_count": 10,
        "baseline_rate": 0.9,
        "failures": [],
        "first_pass_rate": 0.85,
        "baseline_first_pass_rate": 0.90,
    }
    blocked = gate.evaluate_gate(
        impact=impact, acknowledged=_ack_all(impact), regression=regression
    )
    assert blocked.passed is False
    assert blocked.soft_breaches == ("first_pass_rate_drop_over_2pp",)
    forced = gate.evaluate_gate(
        impact=impact,
        acknowledged=_ack_all(impact),
        regression=regression,
        force=True,
    )
    assert forced.passed is True
    assert forced.blockers == ()


def test_gate_never_bypasses_hard_blockers_with_force() -> None:
    """硬门槛没有绕过入口：force 只对软门槛有效。"""
    impact = gate.build_impact(["mineru.tier"])
    regression = {
        "gold_total": 10,
        "pass_count": 10,
        "baseline_rate": 0.9,
        "failures": [{"kind": "hallucination"}],
    }
    result = gate.evaluate_gate(
        impact=impact,
        acknowledged=_ack_all(impact),
        regression=regression,
        force=True,
    )
    assert result.passed is False
    assert result.blockers == ("hallucination_rate_not_zero",)


def test_build_impact_skips_operational_failures() -> None:
    """replay_error / extraction_failed / gold_unavailable 不指向某一条 gold：不生成影响条目。"""
    impact = gate.build_impact(
        ["mineru.tier"],
        regression_failures=[
            {"kind": "replay_error", "message": "网关不可用"},
            {"kind": "gold_unavailable", "field_key": "budget_amount", "anchor": "p3b2"},
            {"kind": "value_mismatch", "field_key": "bid_bond_amount", "anchor": "p12b5"},
        ],
    )
    assert impact == (
        gate.ImpactItem(gate.KIND_CONFIG_CHANGED, "mineru.tier"),
        gate.ImpactItem(gate.KIND_REGRESSION_FAILURE, "bid_bond_amount@p12b5"),
    )


def test_gate_blocks_when_replay_could_not_run() -> None:
    """整轮回放失败时没有报告，不能按冷启动口径放行"不倒退"这条硬门槛。"""
    impact = gate.build_impact(["mineru.tier"])
    regression = {
        "gold_total": 0,
        "pass_count": 0,
        "baseline_rate": None,
        "failures": [{"kind": "replay_error", "message": "模型网关不可用"}],
    }
    result = gate.evaluate_gate(
        impact=impact, acknowledged=_ack_all(impact), regression=regression, force=True
    )
    assert result.passed is False
    assert result.blockers == ("regression_run_failed",)
