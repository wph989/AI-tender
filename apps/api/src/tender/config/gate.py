"""变更门禁与影响清单（设计文档 08 第 5 节、09 第 7 节）。

门禁在这里被写成纯函数而不是一段 SQL，原因是硬门槛必须"任何路径都绕不过"：
只要判定逻辑是函数，任何调用点都得先把回归报告与逐条确认凑齐才能拿到 passed；
写成 SQL 就容易在某个入口少查一个条件，而这种漏洞在评审时看不出来。

回归报告目前由 P3 阶段生成，本阶段先支持"报告缺失=冷启动"这一支：
回归集为空时只校验影响清单（09 第 7 节的口径）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

KIND_FIELD_DEF_CHANGED = "field_def_changed"
KIND_REGRESSION_FAILURE = "regression_failure"
KIND_FIELD_REMOVED = "field_removed"
# 08 第 7 节的注释列了前三种；L2 解析参数变更不动字段定义，但同样要有人看过
# （09 第 7.1 节第 1、4 条），所以补一种 kind，而不是把解析参数硬塞进"字段变更"。
KIND_CONFIG_CHANGED = "config_changed"

# 真正改变字段定义的配置项：只有它对应"字段增删"
FIELD_DEF_KEYS = frozenset({"extract.fields"})

# 回放报告里不进影响清单的失败：它们要么是运维问题（模型网关起不来），
# 要么是数据清理导致的（gold_unavailable），都不指向"某一条 gold 该改"。
NON_IMPACT_FAILURE_KINDS = frozenset({"replay_error", "extraction_failed", "gold_unavailable"})

# 软门槛：首次通过率较当前 active 下降超过 2 个百分点需要二次确认（09 第 7 节）
FIRST_PASS_DROP_LIMIT = 0.02


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


def build_impact(
    changed_keys: Iterable[str],
    *,
    regression_failures: Sequence[Mapping[str, Any]] = (),
    added_fields: Iterable[str] = (),
    removed_fields: Iterable[str] = (),
) -> tuple[ImpactItem, ...]:
    """自动生成变更影响清单（09 第 7.1 节）。

    顺序固定为"配置项 → 字段增删 → 回归失败"，同一份变更每次生成的清单必须逐字相同，
    否则"逐条确认"会因为清单重排而反复失效。
    """
    items: list[ImpactItem] = []
    for key in sorted(set(changed_keys)):
        kind = KIND_FIELD_DEF_CHANGED if key in FIELD_DEF_KEYS else KIND_CONFIG_CHANGED
        items.append(ImpactItem(kind, key))
    for field_key in added_fields:
        items.append(ImpactItem(KIND_FIELD_DEF_CHANGED, field_key))
    for field_key in removed_fields:
        items.append(ImpactItem(KIND_FIELD_REMOVED, field_key))
    for failure in regression_failures:
        if str(failure.get("kind") or "") in NON_IMPACT_FAILURE_KINDS:
            continue
        field_key = str(failure.get("field_key", ""))
        anchor = str(failure.get("anchor", ""))
        items.append(ImpactItem(KIND_REGRESSION_FAILURE, f"{field_key}@{anchor}"))
    return tuple(items)


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
    regression: Mapping[str, Any] | None = None,
    force: bool = False,
) -> GateResult:
    """硬门槛 + 软门槛判定；force 只对软门槛有效，硬门槛没有绕过入口。

    `regression` 的字段口径与 `regression_run` 表一致（gold_total / pass_count /
    baseline_rate / failures），failures 里 `kind` 为 `hallucination` 或 `anchor_404`
    的条目分别对应"幻觉率 = 0"与"证据反查 404 率 = 0"两条硬门槛；
    逐条计数为 0 与"率 = 0"等价，用计数避免 0 分母的除零分支。
    """
    acked = set(acknowledged)
    blockers: list[str] = []
    if any((entry.kind, entry.ref) not in acked for entry in impact):
        blockers.append("impact_not_acknowledged")

    if regression is not None:
        failures = list(regression.get("failures") or [])
        if any(str(failure.get("kind")) == "hallucination" for failure in failures):
            blockers.append("hallucination_rate_not_zero")
        if any(str(failure.get("kind")) == "anchor_404" for failure in failures):
            blockers.append("anchor_404_not_zero")
        # 整轮回放没跑起来（模型网关不可用等）：没有报告就不能激活，
        # 否则"回归集不倒退"这条硬门槛会因为空报告被静默跳过。
        if any(str(failure.get("kind")) == "replay_error" for failure in failures):
            blockers.append("regression_run_failed")

        gold_total = int(regression.get("gold_total") or 0)
        baseline = regression.get("baseline_rate")
        if gold_total > 0 and baseline is not None:
            pass_rate = int(regression.get("pass_count") or 0) / gold_total
            if pass_rate < float(baseline) - 1e-9:
                blockers.append("pass_rate_below_baseline")

    soft: list[str] = []
    first_pass = regression.get("first_pass_rate") if regression else None
    baseline_first_pass = regression.get("baseline_first_pass_rate") if regression else None
    if first_pass is not None and baseline_first_pass is not None:
        drop = float(baseline_first_pass) - float(first_pass)
        if drop > FIRST_PASS_DROP_LIMIT + 1e-9:
            soft.append("first_pass_rate_drop_over_2pp")

    passed = not blockers and (not soft or force)
    return GateResult(passed=passed, blockers=tuple(blockers), soft_breaches=tuple(soft))
