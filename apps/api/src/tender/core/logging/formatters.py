"""项目日志和标准 logging 共用的格式与脱敏边界。"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import UTC, datetime
from itertools import islice

import structlog

from tender.core.redaction import redact_text

MAX_RECORD_BYTES = 64 * 1024
_PRIVATE_KEYS = {
    "authorization", "cookie", "setcookie", "apikey", "xapikey", "xgoogapikey",
    "password", "passwd", "secret", "secretkey", "accesskey", "accesskeyid",
    "token", "accesstoken", "refreshtoken", "credential", "credentials",
    "requestbody", "responsebody", "prompt", "messages", "documenttext",
    "args", "kwargs", "result",
}


def sanitize(value: object, secrets: tuple[str, ...] = (), depth: int = 0) -> object:
    if depth > 8:
        return "[超过嵌套上限]"
    if isinstance(value, str):
        text = redact_text(value, secrets=secrets)
        return text if len(text) <= 16000 else text[:15980] + "[日志字段已截断]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        result = {}
        for key, item in islice(value.items(), 100):
            name = str(key)
            normalized = re.sub(r"[^a-z0-9]", "", name.lower())
            private = normalized in _PRIVATE_KEYS or normalized.endswith(
                ("password", "apikey", "secretkey", "accesstoken")
            )
            # 字段名属于格式契约，不能被短凭证的全文替换改写成另一个字段名。
            result[str(sanitize(name))] = (
                "[已隐藏]" if private else sanitize(item, secrets, depth + 1)
            )
        if len(value) > 100:
            result["_truncated"] = True
        return result
    if isinstance(value, (list, tuple)):
        result = [sanitize(item, secrets, depth + 1) for item in value[:100]]
        if len(value) > 100:
            result.append("[条目已截断]")
        return result
    # 任意对象的 repr 可能带请求正文、密钥甚至再次抛错，不让格式化触发业务行为。
    return f"<{type(value).__name__}>"


class SafeProcessorFormatter(structlog.stdlib.ProcessorFormatter):
    def format(self, record: logging.LogRecord) -> str:
        try:
            return super().format(record)
        except Exception:
            return '{"level":"error","event":"log_format_failed"}'


def make_formatter(service: str, *, json_output: bool, secrets: tuple[str, ...] = ()):
    def enrich(_, __, event):
        record = event["_record"]
        event.update(
            timestamp=datetime.fromtimestamp(record.created, UTC).isoformat(),
            service=service,
            process_id=record.process,
            logger=record.name,
            level=record.levelname.lower(),
        )
        return event

    def scrub(_, __, event):
        clean = sanitize(event, secrets)
        # 总量限制覆盖「很多短字段」的情况；始终输出一条完整、可解析的 JSON。
        raw = json.dumps(clean, ensure_ascii=False)
        if len(raw.encode("utf-8", errors="backslashreplace")) > MAX_RECORD_BYTES - 1:
            clean = {
                key: clean[key]
                for key in (
                    "timestamp", "service", "process_id", "logger", "level",
                    "request_id", "task_id", "job_id", "report_id",
                )
                if key in clean
            }
            clean.update(event="[日志记录过长，已截断]", truncated=True)
        return clean

    renderer = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json_output
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    return SafeProcessorFormatter(
        foreign_pre_chain=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.ExtraAdder(),
        ],
        processors=[
            enrich,
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            scrub,
            renderer,
        ],
    )
