"""保留可诊断的上游错误，同时避免供应商回显凭证和过长网关页面。"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from tender.core.redaction import redact_text
from tender.domain.shared.errors import ModelCallFailed, ModelUnavailable

MAX_ERROR_LENGTH = 16000
_TRUNCATED = "\n[上游响应过长，已截断]"

_WINDOW_PATTERN = re.compile(
    r"\b(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b", re.IGNORECASE
)


def model_error_details(failures: Iterable[Mapping], *, limit: int = MAX_ERROR_LENGTH) -> str:
    """按模型保留实际失败次数与去重后的错误正文，运行和展示使用同一说明。"""
    groups: dict[str, list[Mapping]] = {}
    for failure in failures:
        groups.setdefault(str(failure["model_key"]), []).append(failure)
    details: list[tuple[str, list[str]]] = []
    for items in groups.values():
        messages = list(dict.fromkeys(
            redact_text(item["message"]) for item in items if item.get("message")
        ))
        name, provider = items[-1]["model"], items[-1].get("provider")
        label = f"{provider} / {name}" if provider else name
        details.append((f"{redact_text(label)}（本次失败{len(items)}次）：\n", messages))
    if not details:
        return ""
    full = "\n\n".join(title + "\n".join(messages) for title, messages in details)
    if len(full) <= limit:
        return full
    # 先给每个不同原因留出摘要，再把剩余额度分给长正文，避免前面的响应占满全文。
    budget = limit - len(_TRUNCATED) - 2 * (len(details) - 1)
    title_budget = max(1, budget // (2 * len(details)))
    titles = [_shorten(title.rstrip(), title_budget) + "\n" for title, _ in details]
    message_budget = budget - sum(map(len, titles))
    sizes = [len(message) for _, messages in details for message in messages]
    message_budget -= sum(max(0, len(messages) - 1) for _, messages in details)
    caps: dict[int, int] = {}
    # 短原因只消耗自身长度，让较长条目平分余下的空间。
    for index, size in sorted(enumerate(sizes), key=lambda entry: entry[1]):
        caps[index] = min(size, max(0, message_budget // (len(sizes) - len(caps))))
        message_budget -= caps[index]
    lengths = iter(caps[index] for index in range(len(sizes)))
    return "\n\n".join(
        title + "\n".join(_shorten(message, next(lengths)) for message in messages)
        for title, (_, messages) in zip(titles, details, strict=True)
    ) + _TRUNCATED


def _shorten(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit - 1] + "…" if limit > 0 else ""


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
    if len(value) > MAX_ERROR_LENGTH:
        value = value[: MAX_ERROR_LENGTH - len(_TRUNCATED)] + _TRUNCATED
    return value


def stream_error_status(payload: object) -> int | None:
    """流内错误没有失败HTTP响应，只采纳供应商明确给出的合法错误码。"""
    if not isinstance(payload, dict):
        return None
    code = payload.get("code")
    if isinstance(code, str) and re.fullmatch(r"[45]\d{2}", code):
        code = int(code)
    # 不把布尔值、符号错误名或任意文本推测成限流／过载，避免错误重试权限拒绝。
    return code if type(code) is int and 400 <= code <= 599 else None


def raise_stream_error(response: object, payload: object, *, name: str,
                       api_key: str | None = None) -> None:
    """流内报告的错误码参与重试分类，摘要仍保留实际HTTP响应状态。"""
    status = stream_error_status(payload)
    if status is None:
        return
    body = json.dumps(payload, ensure_ascii=False)
    message = upstream_error(
        f"{name}流内错误码 {status}（HTTP {response.status_code}）", body, api_key=api_key,
    )
    if status in {408, 429} or status >= 500:
        error = ModelUnavailable(message, http_status=status)
        error.retry_after = max(retry_after(response), quota_window(body))
        raise error
    raise ModelCallFailed(message, http_status=status)


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
