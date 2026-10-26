"""知识任务入口：注册消息、互斥、调度与调用已装配用例。"""

from __future__ import annotations

import asyncio

from tender.application.knowledge.execution import dispatch_ready
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

# 持久化队列消息名：历史消息按这些名字查找任务，不能随 Python 模块路径调整而改名。
DISPATCH_TASKS = {
    "index": "tender.worker.knowledge.build_index",
    "report": "tender.worker.knowledge.analyze_project",
    "answer": "tender.worker.knowledge.answer_question",
}


def _store() -> KnowledgeStore:
    return create_worker_knowledge_store()


@celery_app.task(name="tender.worker.knowledge.dispatch_knowledge")
def dispatch_knowledge() -> None:
    with _locks.lock("knowledge_dispatch") as acquired:
        if not acquired:
            return
        _models.maintain_tests()
        # 索引登记与任务领取归用例层；入口只按 kind 投递消息。长任务定期续约，
        # 重复消息由会话锁拒绝。
        for kind, record_id in dispatch_ready(_store()):
            celery_app.send_task(DISPATCH_TASKS[kind], args=[record_id])


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
