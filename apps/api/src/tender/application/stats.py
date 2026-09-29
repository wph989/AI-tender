"""指标口径与重跑按钮判定（设计文档 09 第 3、8 节）。

取数 SQL 在 `api/quality.py`，这里只做"数 → 率"的收尾计算，原因有两条：

- 除零与阈值判定只能有一份实现，否则统计报表和结果面板上的按钮会各算各的；
- 纯函数可以在没有 PostgreSQL 的环境里单测，口径在验收前就钉死。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from tender.application.fields import comparable

# 09 第 8 节：第 2 次机器结果救回率 >= 30% 时提示"重跑一次通常能修好"；
# 低于配置阈值（默认 10%）且样本量足够时收起重跑按钮。
RERUN_HINT_THRESHOLD = Decimal("0.30")
RERUN_SHOW = "show"
RERUN_SHOW_HINT = "show_hint"
RERUN_HIDE = "hide"

# 只接受 `数字d` 与 `all`：写错的窗口必须报错，静默退回默认窗口会给出错误统计。
_WINDOW_RE = re.compile(r"^(\d{1,4})d$")

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def parse_window(raw: str) -> timedelta | None:
    """解析 `7d` / `90d` / `all`；返回 None 表示不限时间。"""
    text = (raw or "").strip().lower()
    if text == "all":
        return None
    match = _WINDOW_RE.match(text)
    if match is None:
        raise ValueError(f"无法识别的统计窗口：{raw}（支持 7d / 90d / all）")
    days = int(match.group(1))
    if days <= 0:
        raise ValueError("统计窗口必须大于 0 天")
    return timedelta(days=days)


def rate(passed: int, total: int) -> float | None:
    """分母为 0 时返回 None（样本不足）。返回 0 会被页面读成"全都错了"。"""
    if total <= 0:
        return None
    return round(max(0, int(passed)) / total, 4)


def rerun_button(
    reviewed: int,
    rescue_rate: float | None,
    *,
    hide_threshold: float,
    min_sample: int,
) -> str:
    """收起重跑按钮的判定（09 第 8 节）。

    样本量不足一律 show：宁可让用户多看到一个可能没用的按钮，
    也不要因为 3 条样本的噪声把按钮藏掉。
    """
    if reviewed < max(0, int(min_sample)) or rescue_rate is None:
        return RERUN_SHOW
    value = Decimal(str(rescue_rate))
    if value < Decimal(str(hide_threshold)):
        return RERUN_HIDE
    if value >= RERUN_HINT_THRESHOLD:
        return RERUN_SHOW_HINT
    return RERUN_SHOW


def _decimal_text(value: Any) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except InvalidOperation:
        return str(value)


def _numbers(value: Any) -> set[str]:
    """递归收集树里的数值（含文本中的数字），用于跨"展示文本 ↔ 结构化值"的比对。"""
    found: set[str] = set()

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for key in sorted(item, key=str):
                walk(item[key])
            return
        if isinstance(item, (list, tuple, set)):
            for part in item:
                walk(part)
            return
        if isinstance(item, bool) or item is None:
            return
        if isinstance(item, (int, float, Decimal)):
            found.add(_decimal_text(item))
            return
        if isinstance(item, str):
            cleaned = item.replace(",", "").replace("，", "")
            for match in _NUMBER_RE.finditer(cleaned):
                found.add(_decimal_text(match.group(0)))

    walk(value)
    return found


def _leaf_texts(value: Any) -> set[str]:
    """把树里的标量叶子压成可比较文本，空值不参与。"""
    texts: set[str] = set()

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for key in sorted(item, key=str):
                walk(item[key])
            return
        if isinstance(item, (list, tuple, set)):
            for part in item:
                walk(part)
            return
        if item is None or isinstance(item, bool):
            return
        texts.add(comparable(item))

    walk(value)
    return texts


def values_match(expected: Any, got: Any) -> bool:
    """回放结果与 gold 值的比对。

    人工修正存的是用户当场填的展示文本（如 `50000元`），机器结果常常是结构化对象
    （`{"amount": "50000.00", "currency": "CNY"}`）。直接比 JSON 会把这类等价结果判成失败，
    所以顺序是：稳定形式 → 结构对齐 → 数值集合 → 叶子文本。
    宁可偶发判失败并在报告里露出明细，也不要为了"好看"放宽到把错值算成通过。
    """
    if got is None:
        return False
    if comparable(expected) == comparable(got):
        return True
    if isinstance(expected, Mapping) and isinstance(got, Mapping):
        # 结构化值：键集合必须一致，逐键递归比较（多一个 currency 键就算不同）。
        if {str(key) for key in expected} != {str(key) for key in got}:
            return False
        return all(values_match(expected[key], got[key]) for key in expected)
    if not isinstance(expected, (Mapping, list)) and not isinstance(got, (Mapping, list)):
        expected_numbers = _numbers(expected)
        got_numbers = _numbers(got)
        return bool(expected_numbers) and expected_numbers == got_numbers
    expected_numbers = _numbers(expected)
    got_numbers = _numbers(got)
    if expected_numbers and got_numbers and expected_numbers == got_numbers:
        return True
    return bool(_leaf_texts(expected) & _leaf_texts(got))
