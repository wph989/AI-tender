"""Python 模块重组后，历史队列消息名仍须找到实际注册的任务。"""

from contextlib import nullcontext
from types import SimpleNamespace

from tender.worker.documents import tasks as document_tasks
from tender.worker.knowledge import tasks as knowledge_tasks


def test_dispatch_uses_registered_legacy_message_names(monkeypatch):
    sent = []
    store = SimpleNamespace(
        collections_pending_index=lambda: [],
        sources=lambda _: [],
        claim_dispatchable=lambda kind, limit: [{"index": 11, "report": 12, "answer": 13}[kind]],
    )
    monkeypatch.setattr(knowledge_tasks._locks, "lock", lambda _: nullcontext(True))
    monkeypatch.setattr(knowledge_tasks, "_store", lambda: store)
    monkeypatch.setattr(knowledge_tasks._models, "maintain_tests", lambda: None)
    monkeypatch.setattr(
        knowledge_tasks.celery_app, "send_task",
        lambda name, *, args: sent.append((name, args)),
    )
    knowledge_tasks.dispatch_knowledge.run()
    assert sent == [
        ("tender.worker.knowledge.build_index", [11]),
        ("tender.worker.knowledge.analyze_project", [12]),
        ("tender.worker.knowledge.answer_question", [13]),
    ]
    for name, _ in sent:
        assert name in knowledge_tasks.celery_app.tasks
    assert document_tasks.process_file.name == "tender.worker.tasks.process_file"
    assert document_tasks.submit_parse.name == "tender.worker.tasks.submit_parse"
    assert document_tasks.poll_parse.name == "tender.worker.tasks.poll_parse"
