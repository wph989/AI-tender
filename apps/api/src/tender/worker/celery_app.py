"""Celery worker 入口；业务任务通过 imports 注册，broker 与队列路由来自共享适配器。"""

from __future__ import annotations

from tender.adapters.celery_queue import create_celery_app

celery_app = create_celery_app()
celery_app.conf.update(
    imports=(
        "tender.worker.tasks",
        "tender.worker.extraction",
        "tender.worker.exports",
        # 回归回放由 API 直接投递到独立队列（低优先级），同样需要 worker 注册。
        "tender.worker.regression",
        # 派发任务也必须注册：beat 只负责发消息，执行它的仍是 worker。
        "tender.worker.dispatch",
        "tender.worker.knowledge",
    )
)
