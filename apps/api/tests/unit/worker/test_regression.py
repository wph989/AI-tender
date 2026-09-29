"""回归回放的汇总口径：报告结构、失败分类与队列隔离（设计文档 09 第 7、10 节）。"""

from __future__ import annotations

from tender.adapters.celery_queue import _TASK_ROUTES
from tender.worker.regression import _Outcome, _summarise


def _item(field_key: str, anchors: list[str], expected: object = "50000") -> dict[str, object]:
    return {"field_key": field_key, "expected": expected, "expected_anchors": anchors}


def test_summarise_counts_pass_and_fail_per_field() -> None:
    outcomes = [
        _Outcome(_item("bid_bond_amount", ["p12b5"]), "pass", value="50000", anchor_checked=True),
        _Outcome(
            _item("bid_bond_amount", ["p12b5"]),
            "value_mismatch",
            value="80000",
            anchor_checked=True,
        ),
        _Outcome(_item("budget_amount", ["p3b2"]), "pass", value="100", anchor_checked=True),
    ]
    report = _summarise(outcomes, baseline=0.9)
    assert (report["gold_total"], report["pass_count"], report["fail_count"]) == (3, 2, 1)
    assert report["baseline_rate"] == 0.9
    by_field = {entry["field_key"]: entry for entry in report["by_field"]}
    assert by_field["bid_bond_amount"] == {
        "field_key": "bid_bond_amount",
        "total": 2,
        "pass": 1,
        "fail": 1,
        "pass_rate": 0.5,
    }
    assert by_field["budget_amount"]["pass_rate"] == 1.0


def test_summarise_keeps_unavailable_gold_out_of_the_rate() -> None:
    """文档被清理掉的 gold 只列明细，不进通过率——否则分母会被无法回放的条目撑大。"""
    outcomes = [
        _Outcome(_item("bid_bond_amount", ["p12b5"]), "pass", value="50000"),
        _Outcome(_item("budget_amount", ["p3b2"]), "gold_unavailable", message="找不到解析产物"),
    ]
    report = _summarise(outcomes, baseline=None)
    assert (report["gold_total"], report["pass_count"]) == (1, 1)
    kinds = [entry["kind"] for entry in report["failures"]]
    assert kinds == ["gold_unavailable"]


def test_summarise_reports_anchor_hit_only_over_checked_items() -> None:
    outcomes = [
        _Outcome(_item("a_field", ["p1b1"]), "pass", anchor_checked=True, anchor_resolved=True),
        _Outcome(_item("b_field", ["p2b1"]), "pass", anchor_checked=True, anchor_resolved=False),
        _Outcome(_item("c_field", ["p3b1"]), "pass", anchor_checked=False),
    ]
    report = _summarise(outcomes, baseline=None)
    assert report["anchor_hit"] == 0.5


def test_summarise_defaults_anchor_hit_to_one_without_evidence() -> None:
    """没有任何证据可查时报 1.0（没有样本），不能报 0（全都没查到）。"""
    report = _summarise([_Outcome(_item("a_field", ["p1b1"]), "pass")], baseline=None)
    assert report["anchor_hit"] == 1.0


def test_regression_task_runs_in_its_own_queue() -> None:
    """低优先级隔离队列：漏了这条路由，回放会落进默认队列与交互任务抢 worker。"""
    assert _TASK_ROUTES["tender.worker.regression.run_regression"]["queue"] == "regression"
