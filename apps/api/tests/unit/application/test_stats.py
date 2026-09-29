"""指标口径与重跑按钮判定（设计文档 09 第 3、8 节）。"""

from __future__ import annotations

from datetime import timedelta

import pytest

from tender.application import stats


def test_parse_window_accepts_days_and_all() -> None:
    assert stats.parse_window("7d") == timedelta(days=7)
    assert stats.parse_window("90d") == timedelta(days=90)
    assert stats.parse_window("all") is None


def test_parse_window_rejects_unknown_forms() -> None:
    """写错的窗口必须报错：静默退回默认窗口会给出一个看似正常的错误统计。"""
    with pytest.raises(ValueError):
        stats.parse_window("90天")
    with pytest.raises(ValueError):
        stats.parse_window("0d")


def test_rate_returns_none_for_empty_sample() -> None:
    """样本不足返回 None，而不是 0——0 会被页面读成"全都错了"。"""
    assert stats.rate(0, 0) is None
    assert stats.rate(3, 4) == 0.75


def test_rerun_button_keeps_button_under_min_sample() -> None:
    assert stats.rerun_button(3, 0.0, hide_threshold=0.10, min_sample=30) == stats.RERUN_SHOW


def test_rerun_button_hides_below_threshold() -> None:
    assert stats.rerun_button(40, 0.05, hide_threshold=0.10, min_sample=30) == stats.RERUN_HIDE


def test_rerun_button_hints_when_rescue_rate_high() -> None:
    assert stats.rerun_button(40, 0.35, hide_threshold=0.10, min_sample=30) == stats.RERUN_SHOW_HINT


def test_values_match_accepts_structured_amount_from_manual_text() -> None:
    """人工填的是"50000元"，机器给结构化值时不能判成失败，否则报告会全红。"""
    assert stats.values_match("50000元", {"amount": "50000.00", "currency": "CNY"}) is True


def test_values_match_rejects_different_amount() -> None:
    assert stats.values_match("50000元", {"amount": "80000", "currency": "CNY"}) is False


def test_values_match_requires_same_keys_for_structured_values() -> None:
    assert stats.values_match({"amount": "50000"}, {"amount": "50000", "currency": "CNY"}) is False


def test_values_match_handles_not_found() -> None:
    assert stats.values_match("50000", None) is False
