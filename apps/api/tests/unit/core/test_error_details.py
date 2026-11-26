"""错误详情必须保留可诊断内容，凭证回显和超长网关页需在落账前处理。"""

import pytest

from tender.core.error_details import (
    MAX_ERROR_LENGTH,
    error_detail,
    model_error_details,
    quota_window,
)


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


def test_long_model_error_leaves_room_for_other_models_and_failure_reasons():
    failures = [
        {"model_key": "a", "model": "A", "message": "HTTP 503\n" + "x" * MAX_ERROR_LENGTH},
        {"model_key": "a", "model": "A", "message": "有效增量间隔超时"},
        {"model_key": "b", "model": "B", "message": "HTTP 403 password=fixture-secret"},
    ]
    result = error_detail(model_error_details(failures))
    assert len(result) <= MAX_ERROR_LENGTH
    assert "A（本次失败2次）" in result and "HTTP 503" in result
    assert "有效增量间隔超时" in result
    assert "B（本次失败1次）" in result and "HTTP 403" in result
    assert "fixture-secret" not in result and "已截断" in result


@pytest.mark.parametrize(("body", "seconds"), [
    (
        '{"error":{"message":"You have reached the request limit: maximum 25 requests '
        'in 5 minutes (request id: abc)","type":"new_api_error"}}',
        300,
    ),
    ("rate limited: 30 requests per 1 minute", 60),
    ("quota resets in 90 seconds", 90),
    ("too many requests", 0),
    (None, 0),
])
def test_quota_window_reads_the_supplier_reset_period(body, seconds):
    # 网关普遍不回 Retry-After，只能从正文给出的窗口估算恢复时间。
    assert quota_window(body) == seconds
