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
    bind_contextvars(**context, task_id=task_id)
    log = logger.debug if task.name in _PERIODIC_DISPATCH_TASKS else logger.info
    # 任务名只在生命周期记录一次，业务日志用 task_id 关联，避免每条重复完整模块名。
    retries = getattr(task.request, "retries", 0)
    log("task.start", task=task.name.removeprefix("tender.worker."),
        **({"retry_count": retries} if retries else {}))


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
        # 失败与重试信号已记录详情，不再跟一条 INFO 的“结束”，以免被误读为成功。
        if state == "SUCCESS":
            log("task.end", duration_ms=round((time.perf_counter() - started) * 1000, 3))
        elif state not in {"FAILURE", "RETRY"}:
            logger.warning("task.stop", status=state,
                           duration_ms=round((time.perf_counter() - started) * 1000, 3))
    finally:
        clear_context()
        bind_contextvars(**previous)
        _stack.set(tuple(parents))


def _failure(sender=None, task_id=None, exception=None, traceback=None, **kwargs) -> None:
    if sender is not None and sender.name.startswith("tender."):
        # 子进程异常退出时，此信号可能由没有执行上下文的主进程发出。
        with bind_context(task_id=task_id):
            if isinstance(traceback, str):
                # Celery 父进程传入格式化字符串，放进 exc_info 会被 structlog 丢弃。
                # 显式异常字段仍经过统一脱敏与限长，格式化器会保留长堆栈的首尾。
                logger.error(
                    "task.fail", exception=traceback,
                    task=sender.name.removeprefix("tender.worker."),
                )
            else:
                logger.error(
                    "task.fail", task=sender.name.removeprefix("tender.worker."),
                    exc_info=(type(exception), exception, traceback or exception.__traceback__)
                    if exception is not None else None,
                )


def _retry(sender=None, reason=None, einfo=None, **kwargs) -> None:
    if sender is not None and sender.name.startswith("tender."):
        # Retry 包装器的类型恒为 Retry；保留实际重试原因及 Celery 提供的堆栈。
        logger.warning("task.retry", exception=getattr(einfo, "traceback", None),
                       reason=str(reason) if einfo is None else None,
                       task=sender.name.removeprefix("tender.worker."))


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
