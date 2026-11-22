"""Celery 生产者配置；API 与 worker 共用队列路由，避免任务落入无人消费的默认队列。"""

from __future__ import annotations

from typing import Any

from celery import Celery, Task

from tender.adapters.jobs.celery_logging import install_publish_logging
from tender.core.logging.context import new_short_id
from tender.core.settings import redis_url

_TASK_ROUTES = {
    "tender.worker.knowledge.dispatch_knowledge": {"queue": "tender"},
    "tender.worker.knowledge.build_index": {"queue": "analysis"},
    "tender.worker.knowledge.analyze_project": {"queue": "analysis"},
    "tender.worker.knowledge.answer_question": {"queue": "analysis"},
    "tender.worker.tasks.process_file": {"queue": "convert"},
    "tender.worker.tasks.submit_parse": {"queue": "parse"},
    "tender.worker.tasks.poll_parse": {"queue": "poll"},
    # 调度器是短任务（几次数据库查询），但要保证有 worker 消费默认队列；
    # 部署命令里的 -Q 必须包含 tender（见 docs/工程/07-部署与实施计划.md）。
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


class TenderTask(Task):
    def apply_async(
        self, args=None, kwargs=None, task_id=None, producer=None, link=None,
        link_error=None, shadow=None, **options,
    ):
        # eager 模式也走同一生成规则；普通模式会把 ID 交给 TenderCelery.send_task。
        return super().apply_async(
            args=args, kwargs=kwargs, task_id=task_id or new_short_id(),
            producer=producer, link=link, link_error=link_error, shadow=shadow,
            **options,
        )

    def apply(
        self, args=None, kwargs=None, link=None, link_error=None, task_id=None,
        retries=None, throw=None, logfile=None, loglevel=None, headers=None, **options,
    ):
        # 同步 eager 执行也有短 task_id，避免日志关联字段因执行方式而改变。
        return super().apply(
            args=args, kwargs=kwargs, link=link, link_error=link_error,
            task_id=task_id or new_short_id(), retries=retries, throw=throw,
            logfile=logfile, loglevel=loglevel, headers=headers, **options,
        )


class TenderCelery(Celery):
    task_cls = TenderTask

    def send_task(self, name: str, *args, **kwargs):
        if name.startswith("tender."):
            # Celery 的 task_id 是 send_task 的第 5 个位置参数，也常以关键字传入。
            if len(args) > 4:
                if not args[4]:
                    args = (*args[:4], new_short_id(), *args[5:])
            elif not kwargs.get("task_id"):
                kwargs["task_id"] = new_short_id()
        return super().send_task(name, *args, **kwargs)


def create_celery_app() -> Celery:
    install_publish_logging()
    app = TenderCelery("tender", broker=redis_url())
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
