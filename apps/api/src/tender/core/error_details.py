"""保留可诊断的上游错误，同时避免供应商回显凭证和过长网关页面。"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from tender.domain.errors import ModelCallFailed, ModelUnavailable

MAX_ERROR_LENGTH = 16000


def retry_after(response: object) -> float:
    """仅采纳合法秒数或 HTTP 日期；不把供应商正文或凭证写进异常。"""
    headers = response.headers
    value = headers.get("Retry-After", "")
    try:
        seconds = float(value)
    except ValueError:
        try:
            until = parsedate_to_datetime(value)
            now = (
                parsedate_to_datetime(headers["Date"])
                if "Date" in headers
                else datetime.now(UTC)
            )
            seconds = (until - now).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 0
    return seconds if math.isfinite(seconds) and seconds > 0 else 0


def error_detail(value: str | None, *, api_key: str | None = None) -> str | None:
    if not value:
        return None
    # 部分网关会在错误消息里原样引用密钥；先替换已知凭证，再处理常见凭证字段。
    if api_key:
        value = value.replace(api_key, "[已隐藏]")
    value = re.sub(r"(?i)(Bearer\s+)[^\s\"'<>]+", r"\1[已隐藏]", value)
    value = re.sub(
        r"(?i)((?:api[_-]?key|x-api-key|x-goog-api-key|authorization|access_token|"
        r"password|secret)[\"']?\s*[:=]\s*[\"']?)[^\"'\s,;<>]+",
        r"\1[已隐藏]",
        value,
    )
    # 截断需要明确标记，避免把半截响应当成供应商返回的全部内容。
    suffix = "\n[上游响应过长，已截断]"
    if len(value) > MAX_ERROR_LENGTH:
        value = value[: MAX_ERROR_LENGTH - len(suffix)] + suffix
    return value


def upstream_error(summary: str, body: str | None, *, api_key: str | None = None) -> str:
    value = summary + ("\n上游响应：\n" + body if body else "")
    return error_detail(value, api_key=api_key) or summary


def raise_for_status(
    response: object,
    *,
    name: str,
    api_key: str | None = None,
    retry_statuses: frozenset[int] = frozenset({408, 429}),
) -> None:
    """上游失败统一落账正文与状态码；凭证只在调用方传入一次，避免各适配器漏传。"""
    status_code = response.status_code
    if status_code in retry_statuses or status_code >= 500:
        error = ModelUnavailable(
            upstream_error(f"{name}暂不可用：HTTP {status_code}", response.text, api_key=api_key),
            http_status=status_code,
        )
        error.retry_after = retry_after(response)
        raise error
    if not response.is_success:
        raise ModelCallFailed(
            upstream_error(f"{name}拒绝请求：HTTP {status_code}", response.text, api_key=api_key),
            http_status=status_code,
        )
