"""项目日志和标准 logging 共用的格式与脱敏边界。"""

from __future__ import annotations

import json
import logging
import math
import re
from datetime import datetime
from itertools import islice
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog

from tender.core.redaction import redact_text

MAX_RECORD_BYTES = 64 * 1024
_BEIJING = ZoneInfo("Asia/Shanghai")
_SOURCE_ROOT = Path(__file__).resolve().parents[3]
_LEADING_FIELDS = (
    "timestamp", "level", "event", "location", "request_id", "task_id", "job_id",
    "report_id", "run_id", "module_key", "invocation_id",
)
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


def format_location(pathname: str, lineno: int) -> str:
    # 项目代码保留包内路径，既区分同名文件，也避免每条重复部署目录。
    path = Path(pathname)
    try:
        path = path.relative_to(_SOURCE_ROOT)
    except ValueError:
        pass
    return f"{path.as_posix()}:{lineno}"


def make_formatter(
    *, json_output: bool, secrets: tuple[str, ...] = (), include_exception: bool = True,
):
    def enrich(_, __, event):
        record = event["_record"]
        if not event["_from_structlog"]:
            # 其他 handler 可能先格式化同一 LogRecord；这些缓存会被 ExtraAdder 重复带入。
            event.pop("message", None)
            event.pop("asctime", None)
        event.update(
            timestamp=datetime.fromtimestamp(record.created, _BEIJING).isoformat(
                timespec="milliseconds"
            ),
            level=record.levelname.lower(),
        )
        # 访问摘要可指定接口定义处；其余日志使用实际调用行，而非 logger 的名称。
        event.setdefault("location", format_location(record.pathname, record.lineno))
        return event

    def scrub(_, __, event):
        if not include_exception and (trace := event.pop("exception", None)):
            # 普通日志只显示错误摘要；完整堆栈由同目录的文本错误文件承载。
            event.setdefault("error", str(trace).rstrip().splitlines()[-1][:500])
        # 固定公共字段靠前，业务字段按名称排列；空值省略，0/False 仍有业务含义。
        ordered = {
            key: event[key]
            for key in dict.fromkeys((*_LEADING_FIELDS, "exception", *sorted(event)))
            if key in event and event[key] is not None and event[key] != ""
        }
        if isinstance(ordered.get("exception"), str):
            trace = redact_text(ordered["exception"], secrets=secrets)
            # 长堆栈保留首尾，异常类型和最终原因通常在末尾，不能只截取开头。
            if len(trace) > 16000:
                trace = trace[:7900] + "\n[堆栈中段已截断]\n" + trace[-7900:]
            ordered["exception"] = trace
        clean = sanitize(ordered, secrets)
        # 先移除导致超限的业务字段；保留字段的最终字节上限由 render_limited 再校验。
        raw = json.dumps(clean, ensure_ascii=False)
        if len(raw.encode("utf-8", errors="backslashreplace")) > MAX_RECORD_BYTES - 1:
            clean = {
                key: clean[key]
                for key in (
                    *_LEADING_FIELDS, "error", "exception",
                )
                if key in clean
            }
            clean["truncated"] = True
        # 堆栈先参与限长保障其不丢失，展示时放最后，便于先浏览摘要。
        if "exception" in clean:
            clean["exception"] = clean.pop("exception")
        return clean

    renderer = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json_output
        else structlog.dev.ConsoleRenderer(
            colors=False, sort_keys=False, pad_event_to=0,
            exception_formatter=structlog.dev.plain_traceback,
        )
    )

    def render_limited(logger, name, event):
        # 文本 renderer 会弹出字段；每次用副本渲染，按真实 UTF-8 字节数（含换行）验收。
        rendered = renderer(logger, name, event.copy())
        while len(rendered.encode("utf-8", errors="backslashreplace")) >= MAX_RECORD_BYTES:
            event["truncated"] = True
            # 保留字段也可能各自很长，不能把删掉业务字段当成总量限制已完成。
            key = max(event, key=lambda k: len(
                json.dumps(event[k], ensure_ascii=False).encode("utf-8", errors="backslashreplace")
            ))
            value = event[key]
            if isinstance(value, str) and len(value) > 128:
                if key == "exception":
                    quarter = len(value) // 4
                    event[key] = value[:quarter] + "\n[堆栈中段已截断]\n" + value[-quarter:]
                else:
                    event[key] = value[:len(value) // 2] + "[日志字段已截断]"
            else:
                event[key] = "[日志字段已截断]"
            if "exception" in event:
                event["exception"] = event.pop("exception")
            rendered = renderer(logger, name, event.copy())
        return rendered

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
            render_limited,
        ],
    )
