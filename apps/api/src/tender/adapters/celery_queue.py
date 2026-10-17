"""Celery 生产者配置；API 与 worker 共用队列路由，避免任务落入无人消费的默认队列。"""

from __future__ import annotations

from typing import Any

from celery import Celery

from tender.adapters.celery_logging import install_publish_logging
from tender.core.settings import redis_url

_TASK_ROUTES = {
    "tender.worker.knowledge.dispatch_knowledge": {"queue": "tender"},
    "tender.worker.knowledge.build_index": {"queue": "analysis"},
    "tender.worker.knowledge.analyze_project": {"queue": "analysis"},
    "tender.worker.knowledge.answer_question": {"queue": "analysis"},
    "tender.worker.tasks.process_file": {"queue": "convert"},
    "tender.worker.tasks.submit_parse": {"queue": "parse"},
    "tender.worker.tasks.poll_parse": {"queue": "parse"},
    # 调度器是短任务（几次数据库查询），但要保证有 worker 消费默认队列；
    # 部署命令里的 -Q 必须包含 tender（见 docs/工程/07 第 1 节）。
    "tender.worker.dispatch.dispatch_pending": {"queue": "tender"},
}

# 每秒唤醒，再由派发任务按当前配置节流，使1秒间隔也能生效而无需重启beat。
_BEAT_SCHEDULE = {
    "dispatch-knowledge": {
        "task": "tender.worker.knowledge.dispatch_knowledge",
        "schedule": 15.0,
    },
    "dispatch-pending": {
        "task": "tender.worker.dispatch.dispatch_pending",
        "schedule": 1.0,
    },
}


def create_celery_app() -> Celery:
    install_publish_logging()
    app = Celery("tender", broker=redis_url())
    app.conf.update(
        task_default_queue="tender",
        task_routes=_TASK_ROUTES,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        beat_schedule=_BEAT_SCHEDULE,
        worker_hijack_root_logger=False,
        worker_redirect_stdouts=False,
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
