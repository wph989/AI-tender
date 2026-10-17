"""Celery 生命周期日志；执行状态不代替数据库里的业务成功/失败状态。"""

from __future__ import annotations

import logging
import sys
import time
from contextvars import ContextVar

from celery import signals
from structlog.contextvars import bind_contextvars, get_contextvars

from tender.adapters.celery_logging import CONTEXT_HEADER
from tender.core.logging import bind_context, clear_context, configure_logging, get_logger
from tender.core.logging.context import CONTEXT_KEYS, valid_identifier

logger = get_logger(__name__)
_stack: ContextVar[tuple] = ContextVar("tender_task_log_stack", default=())
# 周期派发即使无业务任务也持续执行，常规生命周期降为 DEBUG，避免淹没业务日志。
_PERIODIC_DISPATCH_TASKS = {
    "tender.worker.dispatch.dispatch_pending",
    "tender.worker.knowledge.dispatch_knowledge",
}


def _setup(**kwargs) -> None:
    configure_logging("beat" if "beat" in sys.argv else "worker")
    # Celery 默认成功日志会包含返回值，失败模板会包含 args/kwargs。
    # 用下方生命周期信号记录元数据与异常，避免把模型正文复制到运行日志。
    logging.getLogger("celery.app.trace").disabled = True
    logging.getLogger("celery.worker.strategy").setLevel(logging.WARNING)
    logging.getLogger("celery.beat").setLevel(logging.WARNING)


def _prerun(task_id=None, task=None, **kwargs) -> None:
    if task is None or not task.name.startswith("tender."):
        return
    _stack.set((*_stack.get(), (get_contextvars(), time.perf_counter())))
    clear_context()
    raw = (getattr(task.request, "headers", None) or {}).get(CONTEXT_HEADER, {})
    context = {
        key: value for key, value in raw.items()
        if key in CONTEXT_KEYS - {"task_id"}
        and (valid_identifier(value) or type(value) is int)
    } if isinstance(raw, dict) else {}
    bind_contextvars(**context, task_id=task_id, task_name=task.name)
    log = logger.debug if task.name in _PERIODIC_DISPATCH_TASKS else logger.info
    log("task_started", retry_count=getattr(task.request, "retries", 0))


def _postrun(task=None, state=None, **kwargs) -> None:
    if task is None or not task.name.startswith("tender.") or not _stack.get():
        return
    *parents, (previous, started) = _stack.get()
    try:
        log = (
            logger.debug
            if task.name in _PERIODIC_DISPATCH_TASKS and state == "SUCCESS"
            else logger.info
        )
        log(
            "task_finished", execution_state=state,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )
    finally:
        clear_context()
        bind_contextvars(**previous)
        _stack.set(tuple(parents))


def _failure(sender=None, task_id=None, exception=None, traceback=None, **kwargs) -> None:
    if sender is not None and sender.name.startswith("tender."):
        # 子进程异常退出时，此信号可能由没有执行上下文的主进程发出。
        with bind_context(task_id=task_id, task_name=sender.name):
            if isinstance(traceback, str):
                # Celery 父进程传入格式化字符串，放进 exc_info 会被 structlog 丢弃。
                # 显式异常字段仍经过统一脱敏与限长，原因单列以免长堆栈截掉末尾。
                logger.error(
                    "task_execution_failed", exception=traceback,
                    exception_type=type(exception).__name__ if exception is not None else None,
                    reason=str(exception) if exception is not None else None,
                )
            else:
                logger.error(
                    "task_execution_failed",
                    exc_info=(type(exception), exception, traceback)
                    if exception is not None else None,
                )


def _retry(sender=None, reason=None, **kwargs) -> None:
    if sender is not None and sender.name.startswith("tender."):
        logger.warning("task_retry", reason_type=type(reason).__name__)


def install_worker_logging() -> None:
    for signal, callback, name in (
        (signals.setup_logging, _setup, "setup"),
        (signals.worker_process_init, _setup, "child"),
        (signals.task_prerun, _prerun, "prerun"),
        (signals.task_postrun, _postrun, "postrun"),
        (signals.task_failure, _failure, "failure"),
        (signals.task_retry, _retry, "retry"),
    ):
        signal.connect(callback, weak=False, dispatch_uid=f"tender.log.{name}")
