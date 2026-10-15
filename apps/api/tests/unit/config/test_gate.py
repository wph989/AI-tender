"""配置门禁只处理逐项确认，退役功能不能再影响发布。"""

import pytest

from tender.config import gate


def test_build_impact_is_stable_ordered_and_unique():
    impact = gate.build_impact(["mineru.tier", "convert.max_inflight", "mineru.tier"])
    assert impact == (
        gate.ImpactItem("config_changed", "convert.max_inflight"),
        gate.ImpactItem("config_changed", "mineru.tier"),
    )


def test_impact_state_marks_only_matching_acknowledgements():
    impact = gate.build_impact(["mineru.tier", "render.crop_dpi"])
    state = gate.impact_state(impact, [("config_changed", "render.crop_dpi")])
    assert [(entry["ref"], entry["acked"]) for entry in state] == [
        ("mineru.tier", False), ("render.crop_dpi", True),
    ]


@pytest.mark.parametrize("force", [False, True])
def test_gate_never_bypasses_missing_confirmation(force):
    impact = gate.build_impact(["mineru.tier", "render.crop_dpi"])
    result = gate.evaluate_gate(
        impact=impact, acknowledged=[("config_changed", "mineru.tier")], force=force,
    )
    assert result.as_dict() == {
        "passed": False, "blockers": ["impact_not_acknowledged"], "soft_breaches": [],
    }


@pytest.mark.parametrize("keys", [[], ["mineru.tier", "convert.max_inflight"]])
def test_gate_passes_when_every_change_is_acknowledged(keys):
    impact = gate.build_impact(keys)
    result = gate.evaluate_gate(
        impact=impact, acknowledged=[(entry.kind, entry.ref) for entry in impact],
    )
    assert result.passed and not result.blockers
