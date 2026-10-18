"""优先级整表展开与转移深度夹取（设计文档 12 第 3、4 节）。"""

from __future__ import annotations

import pytest

from tender.application.llm.registry import binding_rows, effective_limit
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


def test_effective_limit_defaults_to_three() -> None:
    assert effective_limit(None, 10) == 3


def test_effective_limit_clamps_to_bound_count() -> None:
    """只绑了 2 个模型时"前 3 个有效"没有意义，夹到 2。"""
    assert effective_limit(3, 2) == 2


def test_effective_limit_clamps_to_ten_and_at_least_one() -> None:
    assert effective_limit(99, 12) == 10
    assert effective_limit(0, 5) == 1


def test_effective_limit_without_bindings_is_zero() -> None:
    assert effective_limit(3, 0) == 0
