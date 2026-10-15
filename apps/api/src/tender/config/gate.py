"""配置变更的逐项确认门禁；未确认的变更不能激活。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ImpactItem:
    kind: str
    ref: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "ref": self.ref}


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    blockers: tuple[str, ...]
    soft_breaches: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "blockers": list(self.blockers),
            "soft_breaches": list(self.soft_breaches),
        }


def build_impact(changed_keys: Iterable[str]) -> tuple[ImpactItem, ...]:
    """将变更参数展开为可审计的确认清单。"""
    return tuple(ImpactItem("config_changed", key) for key in sorted(set(changed_keys)))


def impact_state(
    impact: Iterable[ImpactItem],
    acknowledged: Iterable[tuple[str, str]],
) -> list[dict[str, Any]]:
    """把确认记录合进清单：页面要显示"哪几条还没人看过"。"""
    acked = set(acknowledged)
    return [{**entry.as_dict(), "acked": (entry.kind, entry.ref) in acked} for entry in impact]


def evaluate_gate(
    *,
    impact: Sequence[ImpactItem],
    acknowledged: Iterable[tuple[str, str]],
    force: bool = False,
) -> GateResult:
    """force 也不能跳过逐项确认，避免误激活未评估的解析策略。"""
    acked = set(acknowledged)
    blockers: list[str] = []
    if any((entry.kind, entry.ref) not in acked for entry in impact):
        blockers.append("impact_not_acknowledged")


    passed = not blockers
    return GateResult(passed=passed, blockers=tuple(blockers), soft_breaches=())
