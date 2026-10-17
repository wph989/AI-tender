"""凭证文本清洗集中维护，让上游错误与运行日志采用相同规则。"""

from __future__ import annotations

import re
from collections.abc import Iterable


def redact_text(value: str, *, secrets: Iterable[str] = ()) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[已隐藏]")
    value = re.sub(r"(?i)((?:Bearer|Basic)\s+)[^\s\"'<>]+", r"\1[已隐藏]", value)
    value = re.sub(
        r"(?i)((?:api[_-]?key|x-api-key|x-goog-api-key|authorization|access_token|"
        r"refresh_token|password|secret)[\"']?\s*[:=]\s*[\"']?)[^\"'\s,;<>]+",
        r"\1[已隐藏]",
        value,
    )
    # 连接异常可能带完整 DSN，不能只过滤名为 password 的结构化字段。
    # 协议名限为短 ASCII，避免长篇正文被当成候选协议名反复回溯。
    value = re.sub(
        r"(\b[A-Za-z][A-Za-z0-9+.-]{0,31}://)[^\s/@]+:[^\s/@]+@",
        r"\1[已隐藏]@", value,
    )
    return value
