"""只传递明确的关联字段，避免把请求正文顺带放进 Celery 消息头。"""

from __future__ import annotations

import re
from contextlib import contextmanager

from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    get_contextvars,
    reset_contextvars,
)

CONTEXT_KEYS = frozenset({"request_id", "task_id", "job_id", "report_id", "run_id"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


def valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def get_context() -> dict[str, str | int]:
    return {
        key: value
        for key, value in get_contextvars().items()
        if key in CONTEXT_KEYS and (valid_identifier(value) or type(value) is int)
    }


def clear_context() -> None:
    clear_contextvars()


@contextmanager
def bind_context(**values: object):
    """支持嵌套并恢复原值，避免同一线程复用后把上一任务的 ID 带进下一任务。"""
    tokens = bind_contextvars(**values)
    try:
        yield
    finally:
        reset_contextvars(**tokens)
