"""保留可诊断的上游错误，同时避免供应商回显凭证和过长网关页面。"""

from __future__ import annotations

import re

MAX_ERROR_LENGTH = 16000


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
