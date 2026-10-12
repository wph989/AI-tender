"""补跑入口与配置中心保持相同的输出预算边界，避免保存后补跑仍被旧下限拒绝。"""

import pytest
from pydantic import ValidationError

from tender.api.knowledge import RetryInput


@pytest.mark.parametrize("value", [1, 511, 16385, 262144])
def test_retry_accepts_positive_output_budget_without_upper_bound(value: int) -> None:
    assert RetryInput(max_output_tokens=value).max_output_tokens == value


@pytest.mark.parametrize("value", [0, -1, 1.5])
def test_retry_rejects_non_positive_or_fractional_output_budget(value: float) -> None:
    with pytest.raises(ValidationError):
        RetryInput(max_output_tokens=value)


def test_retry_omitted_output_budget_uses_current_config() -> None:
    assert RetryInput().max_output_tokens is None


@pytest.mark.parametrize("value", [1, 7201, 172800])
def test_retry_timeout_matches_positive_unbounded_config(value: int) -> None:
    assert RetryInput(timeout_seconds=value).timeout_seconds == value


def test_retry_zero_timeout_is_rejected_instead_of_expiring_immediately() -> None:
    with pytest.raises(ValidationError):
        RetryInput(timeout_seconds=0)
