"""保留可诊断的上游错误，同时避免供应商回显凭证和过长网关页面。"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from tender.core.redaction import redact_text
from tender.domain.errors import ModelCallFailed, ModelUnavailable

MAX_ERROR_LENGTH = 16000

_WINDOW_PATTERN = re.compile(
    r"\b(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b", re.IGNORECASE
)


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
    value = redact_text(value, secrets=(api_key,) if api_key else ())
    # 截断需要明确标记，避免把半截响应当成供应商返回的全部内容。
    suffix = "\n[上游响应过长，已截断]"
    if len(value) > MAX_ERROR_LENGTH:
        value = value[: MAX_ERROR_LENGTH - len(suffix)] + suffix
    return value


def upstream_error(summary: str, body: str | None, *, api_key: str | None = None) -> str:
    value = summary + ("\n上游响应：\n" + body if body else "")
    return error_detail(value, api_key=api_key) or summary


def quota_window(body: str | None) -> float:
    """从限流正文里识别配额窗口（如「maximum 25 requests in 5 minutes」）。

    网关普遍不回 Retry-After；固定等待撑不过分钟级窗口，只能按正文给出的恢复周期等。
    """
    if not body:
        return 0
    seconds = 0.0
    for value, unit in _WINDOW_PATTERN.findall(body):
        scale = 3600 if unit[0] in "hH" else 60 if unit[0] in "mM" else 1
        seconds = max(seconds, float(value) * scale)
    return seconds


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
        # Retry-After 是供应商的明确承诺；缺失时按正文的配额窗口估算恢复时间。
        # 头部是承诺、正文窗口是估算，取较大值；任一都不给时才交给指数退避。
        error.retry_after = max(retry_after(response), quota_window(response.text))
        raise error
    if not response.is_success:
        raise ModelCallFailed(
            upstream_error(f"{name}拒绝请求：HTTP {status_code}", response.text, api_key=api_key),
            http_status=status_code,
        )
