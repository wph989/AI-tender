"""Celery 生产者配置；API 与 worker 共用队列路由，避免任务落入无人消费的默认队列。"""

from __future__ import annotations

from typing import Any

from celery import Celery

from tender.core.settings import redis_url

_TASK_ROUTES = {
    "tender.worker.tasks.process_file": {"queue": "convert"},
    "tender.worker.tasks.submit_parse": {"queue": "parse"},
    "tender.worker.tasks.poll_parse": {"queue": "parse"},
    "tender.worker.tasks.extract_fields": {"queue": "extract"},
    "tender.worker.exports.export_project": {"queue": "extract"},
    # 调度器是短任务（几次数据库查询），但要保证有 worker 消费默认队列；
    # 部署命令里的 -Q 必须包含 tender（见 docs/工程/07 第 1 节）。
    "tender.worker.dispatch.dispatch_pending": {"queue": "tender"},
    # 回归回放走独立队列：低优先级 + 夜间窗口，与交互任务隔离（docs/工程/10 第 3.5 节）。
    # 它由 API 直接投递（管理员显式触发），不参与 beat 的差额派发。
    "tender.worker.regression.run_regression": {"queue": "regression"},
}

# 唤醒粒度固定 5 秒：`dispatch.interval_seconds` 只能把实际派发间隔拉长，不能缩短——
# beat 自己不读配置，靠 tick 内部节流（worker/dispatch.py）。写成配置驱动会让
# "改配置"依赖 beat 重启，恰好违背配置中心的初衷。
_BEAT_SCHEDULE = {
    "dispatch-pending": {
        "task": "tender.worker.dispatch.dispatch_pending",
        "schedule": 5.0,
    },
}


def create_celery_app() -> Celery:
    app = Celery("tender", broker=redis_url())
    app.conf.update(
        task_default_queue="tender",
        task_routes=_TASK_ROUTES,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        beat_schedule=_BEAT_SCHEDULE,
    )
    return app


class CeleryTaskQueue:
    def __init__(self, celery_app: Any | None = None) -> None:
        self._app = celery_app or create_celery_app()

    def enqueue(
        self,
        task_name: str,
        args: tuple[object, ...],
        *,
        countdown: float = 0,
    ) -> str | None:
        result = self._app.send_task(task_name, args=list(args), countdown=countdown)
        # 没有结果后端时 send_task 仍会生成任务 id；拿不到就返回 None，不编造一个。
        return getattr(result, "id", None)
