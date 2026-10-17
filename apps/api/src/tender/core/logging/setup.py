"""日志装配与资源管理；集中维护配置状态，避免各入口重复注册处理器。"""

from __future__ import annotations

import atexit
import logging
import os
import re
import sys
import threading

import structlog

from tender.core import settings
from tender.core.logging.formatters import make_formatter
from tender.core.logging.handlers import DailyFileHandler, SafeStreamHandler

_lock = threading.RLock()
_configured = None
_handlers: list[logging.Handler] = []


class _DuplicateExceptionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # ASGI 重新抛出异常是协议要求；已由 API 入口记录的堆栈不再被 Uvicorn 打一遍。
        if record.exc_info and getattr(record.exc_info[1], "_tender_logged", False):
            return False
        return True


def get_logger(name: str):
    return structlog.get_logger(name)


def configure_logging(service: str, options: settings.LoggingSettings | None = None) -> None:
    global _configured
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", service):
        raise ValueError("日志服务名只能包含小写字母、数字、下划线和连字符")
    options = options or settings.logging_settings()
    key = (os.getpid(), service, options)
    with _lock:
        if _configured == key:
            return
        shutdown_logging()
        secrets = tuple(
            value
            for name in (
                "S3_ACCESS_KEY", "S3_SECRET_KEY", "MINERU_API_KEY", "GOTENBERG_PASS"
            )
            if (value := settings._setting(name))
        ) + settings.llm_secret_keys()
        root = logging.getLogger()
        root.setLevel(options.level)
        if options.output in {"stdout", "both"}:
            # Windows 重定向时可能默认使用本地代码页，文件和标准流都明确采用 UTF-8。
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
            stream = SafeStreamHandler(sys.stdout)
            stream.setFormatter(make_formatter(
                service, json_output=options.console_format == "json", secrets=secrets
            ))
            _handlers.append(stream)
        if options.output in {"file", "both"}:
            files = DailyFileHandler(options, service)
            files.setFormatter(make_formatter(service, json_output=True, secrets=secrets))
            _handlers.append(files)
            files.start()
        for handler in _handlers:
            handler.setLevel(options.level)
            root.addHandler(handler)
        # 只接管明确的框架 logger，不移除 pytest/宿主应用的其他根处理器。
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.task"):
            logger = logging.getLogger(name)
            logger.handlers.clear()
            logger.propagate = True
            logger.setLevel(logging.NOTSET)
        logging.getLogger("uvicorn.access").disabled = True  # 访问摘要由中间件统一生成。
        uvicorn_errors = logging.getLogger("uvicorn.error")
        if not any(isinstance(f, _DuplicateExceptionFilter) for f in uvicorn_errors.filters):
            uvicorn_errors.addFilter(_DuplicateExceptionFilter())
        for name in ("httpx", "httpcore", "sqlalchemy.engine", "boto3", "botocore"):
            logging.getLogger(name).setLevel(logging.WARNING)
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=False,
        )
        _configured = key


def shutdown_logging() -> None:
    global _configured
    with _lock:
        for handler in _handlers:
            logging.getLogger().removeHandler(handler)
            handler.close()
        _handlers.clear()
        _configured = None


atexit.register(shutdown_logging)
