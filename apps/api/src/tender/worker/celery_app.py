"""Celery worker 入口；业务任务通过 imports 注册，broker 与队列路由来自共享适配器。"""

from __future__ import annotations

from tender.adapters.jobs.celery_queue import create_celery_app
from tender.worker.analysis.maintenance import install_analysis_maintenance
from tender.worker.logging import install_worker_logging

install_worker_logging()
install_analysis_maintenance()
celery_app = create_celery_app()
celery_app.conf.update(
    imports=(
        'tender.worker.documents.tasks',
        # 派发任务也必须注册：beat 只负责发消息，执行它的仍是 worker。
        "tender.worker.dispatch",
        'tender.worker.knowledge.tasks',
    )
)
