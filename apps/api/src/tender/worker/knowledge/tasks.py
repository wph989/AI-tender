"""知识任务入口：注册消息、互斥、调度与调用已装配用例。"""

from __future__ import annotations

import asyncio

from tender.application.knowledge.content import source_state
from tender.core.di import (
    create_analysis_executor,
    create_knowledge_executor,
    create_model_runtime_repository,
    create_task_locks,
    create_worker_knowledge_store,
    run_analysis_async,
)
from tender.ports.repository.knowledge.store import KnowledgeStore
from tender.worker.celery_app import celery_app

_locks = create_task_locks()
_models = create_model_runtime_repository()


def _store() -> KnowledgeStore:
    return create_worker_knowledge_store()


@celery_app.task(name="tender.worker.knowledge.dispatch_knowledge")
def dispatch_knowledge() -> None:
    with _locks.lock("knowledge_dispatch") as acquired:
        if not acquired:
            return
        db = _store()
        _models.maintain_tests()
        for source in db.sources(db.collections_pending_index()):
            if source_state(source) not in {"ready", "partial"} or source["index_id"]:
                continue
            db.create_index(source)
        # 小批次派发限制消息积压；长任务定期续约，重复消息由会话锁拒绝。
        for kind, task in (
            ("index", "build_index"),
            ("report", "analyze_project"),
            ("answer", "answer_question"),
        ):
            for record_id in db.claim_dispatchable(kind, 2):
                # 这是持久化队列消息的任务名，不能随 Python 模块路径调整而重命名。
                celery_app.send_task(f"tender.worker.knowledge.{task}", args=[record_id])


@celery_app.task(name="tender.worker.knowledge.build_index")
def build_index(index_id: int) -> None:
    with _locks.lock(f"knowledge_index:{index_id}") as acquired:
        if acquired:
            asyncio.run(_build_index(index_id))


@celery_app.task(name="tender.worker.knowledge.analyze_project")
def analyze_project(report_id: int) -> None:

    with _locks.lock(f"analysis_report:{report_id}") as acquired:
        if acquired:
            run_analysis_async(_analyze_project(report_id))


@celery_app.task(name="tender.worker.knowledge.answer_question")
def answer_question(answer_id: int) -> None:
    with _locks.lock(f"knowledge_answer:{answer_id}") as acquired:
        if acquired:
            asyncio.run(_answer_question(answer_id))


async def _build_index(index_id: int) -> None:
    await create_knowledge_executor(_store()).build_index(index_id)


async def _analyze_project(report_id: int) -> None:
    await create_analysis_executor(_store()).execute(report_id)


async def _answer_question(answer_id: int) -> None:
    await create_knowledge_executor(_store()).answer_question(answer_id)
