"""错误详情必须保留可诊断内容，凭证回显和超长网关页需在落账前处理。"""

import pytest

from tender.core.error_details import MAX_ERROR_LENGTH, error_detail


@pytest.mark.parametrize("body", [
    '{"api_key":"fixture-secret","message":"余额不足"}',
    'Authorization: Bearer fixture-secret',
    'x-goog-api-key=fixture-secret',
    'access_token=fixture-secret',
])
def test_common_credentials_are_hidden(body):
    result = error_detail(body)
    assert "fixture-secret" not in result
    assert "[已隐藏]" in result
    assert error_detail(result) == result


def test_known_key_is_hidden_even_inside_free_text():
    assert error_detail("无效凭证 fixture-secret，余额不足", api_key="fixture-secret") == (
        "无效凭证 [已隐藏]，余额不足"
    )


def test_long_body_keeps_more_than_500_characters_and_marks_truncation():
    body = "网关错误\n" + "x" * 1000 + "\nrequest_id=upstream-123"
    assert error_detail(body) == body
    result = error_detail(body * 20)
    assert len(result) == MAX_ERROR_LENGTH
    assert result.endswith("[上游响应过长，已截断]")
    assert error_detail(result) == result
