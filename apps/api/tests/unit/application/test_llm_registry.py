"""优先级整表展开规则（docs/设计/12-LLM管理与模型路由.md）。"""

from __future__ import annotations

import pytest

from tender.application.llm.registry import binding_rows
from tender.domain.shared.errors import PriorityLimitExceeded


def test_binding_rows_derive_priority_from_order() -> None:
    """有序数组就是优先级：第 1 个 1 级，页面不需要传数字。"""
    assert binding_rows([7, 3, 9]) == [(7, 1), (3, 2), (9, 3)]


def test_binding_rows_allow_empty_to_clear() -> None:
    assert binding_rows([]) == []


def test_binding_rows_reject_eleventh_model() -> None:
    """溢出要拒绝而不是挤掉最低级：静默丢模型会让线上配置无声变化。"""
    with pytest.raises(PriorityLimitExceeded):
        binding_rows(list(range(1, 12)))


def test_binding_rows_allow_exactly_ten() -> None:
    assert binding_rows(list(range(1, 11)))[-1] == (10, 10)


def test_binding_rows_reject_duplicate_model() -> None:
    with pytest.raises(ValueError, match="重复"):
        binding_rows([1, 2, 1])


@pytest.mark.parametrize("value", [0, -1, True])
def test_binding_rows_reject_non_positive(value: object) -> None:
    with pytest.raises(ValueError):
        binding_rows([value])  # type: ignore[list-item]
