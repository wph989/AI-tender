"""用多连接验证配额与恢复：丢消息、退避、活跃锁和并发调度均使用真实 SQL。"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, text
from sqlalchemy.engine import make_url

from tender.adapters.pg.models import Job
from tender.adapters.pg.repositories.documents.pipeline import DocumentPipelineRepository
from tender.adapters.pg.repositories.jobs.coordination import TaskLocks
from tender.adapters.pg.repositories.jobs.dispatch import DispatchRepository
from tender.core.settings import database_url
from tender.worker import dispatch
from tender.worker.documents import tasks

pytestmark = pytest.mark.skipif(os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库")


@pytest.fixture
def database():
    schema = "test_dispatch_" + uuid4().hex
    base = create_engine(database_url())
    with base.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(database_url()).update_query_dict({"options": f"-csearch_path={schema}"})
    engine = create_engine(url)
    Job.__table__.create(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with base.begin() as connection:
            # 隔离 schema 仅由本测试的 UUID 创建，清理不触及业务库对象。
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def seed(engine, job_id, *, status="pending", stage="submitting", dispatched=False, **extra):
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(insert(Job).values(
            id=job_id, company_id=1, project_id=1, project_file_id=1,
            status=status, stage=stage, progress={}, config_snapshot={},
            created_at=now, updated_at=now,
            dispatched_at=now if dispatched else None, **extra,
        ))


def test_running_remote_parse_keeps_quota(database, monkeypatch):
    seed(database, "remote", status="running", stage="parsing", dispatched=True)
    seed(database, "next")
    monkeypatch.setattr(dispatch, "_repository", DispatchRepository(database))
    send = Mock()
    monkeypatch.setattr(dispatch.celery_app, "send_task", send)
    assert dispatch.dispatch_stream(dispatch.STREAMS[1], 1, 1) == 0
    send.assert_not_called()


def test_parallel_dispatch_cannot_overbook(database, monkeypatch):
    seed(database, "one")
    seed(database, "two")
    monkeypatch.setattr(dispatch, "_repository", DispatchRepository(database))
    send = Mock()
    monkeypatch.setattr(dispatch.celery_app, "send_task", send)
    start = Barrier(2)

    def run():
        start.wait(timeout=5)
        return dispatch.dispatch_stream(dispatch.STREAMS[1], 1, 1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(run), pool.submit(run)]
        assert sum(item.result(timeout=10) for item in results) == 1
    assert send.call_count == 1


@pytest.mark.parametrize(("status", "stage", "task"), [
    ("pending", "converting", "process_file"),
    ("running", "geometry", "process_file"),
    ("submitting", "submitting", "submit_parse"),
    ("running", "parsing", "poll_parse"),
    ("running", "resubmitting", "poll_parse"),
])
def test_lost_messages_recover_at_current_stage(database, status, stage, task):
    seed(database, "lost", status=status, stage=stage, dispatched=True)
    with DispatchRepository(database).transaction() as tx:
        assert tx.recoverable(1, 100) == [("lost", task)]
        assert tx.recoverable(2, 100) == []


def test_live_execution_future_attempt_and_terminal_are_not_recovered(database):
    seed(database, "live", status="running", stage="parsing", dispatched=True)
    seed(database, "later", dispatched=True,
         next_attempt_at=datetime.now(UTC) + timedelta(minutes=1))
    seed(database, "done", status="completed", dispatched=True)
    with TaskLocks(database).lock("job:live") as acquired:
        assert acquired
        with DispatchRepository(database).transaction() as tx:
            assert tx.recoverable(1, 100) == []
    with database.begin() as connection:
        connection.execute(text("UPDATE job SET dispatch_lease_until=now() WHERE id='live'"))
    with DispatchRepository(database).transaction() as tx:
        assert tx.recoverable(1, 100) == [("live", "poll_parse")]


def test_failed_publish_remains_recoverable(database, monkeypatch):
    seed(database, "lost", status="running", stage="parsing", dispatched=True)
    monkeypatch.setattr(dispatch, "_repository", DispatchRepository(database))
    send = Mock(side_effect=ConnectionError("模拟 broker 不可用"))
    monkeypatch.setattr(dispatch.celery_app, "send_task", send)
    assert dispatch.recover_pending(1) == 0
    send.side_effect = None
    assert dispatch.recover_pending(1) == 1
    assert dispatch.recover_pending(1) == 0


def test_persisted_attempt_blocks_early_duplicates(database):
    seed(database, "poll", status="running", stage="parsing", dispatched=True)
    repository = DocumentPipelineRepository(database, Mock())
    assert repository.claim_attempt("poll", ("parsing",))
    repository.schedule_attempt("poll", 60)
    assert not repository.claim_attempt("poll", ("parsing",))
    repository.schedule_attempt("poll", 0)
    assert repository.claim_attempt("poll", ("parsing",))


def test_active_first_batch_does_not_starve_lost_message(database):
    seed(database, "active", status="running", stage="parsing", dispatched=True)
    seed(database, "lost", status="running", stage="parsing", dispatched=True)
    with TaskLocks(database).lock("job:active") as acquired:
        assert acquired
        with DispatchRepository(database).transaction() as tx:
            assert tx.recoverable(1, 1) == []
        with DispatchRepository(database).transaction() as tx:
            assert tx.recoverable(1, 1) == [("lost", "poll_parse")]


def test_late_conversion_message_cannot_latch_undispatched_parse(database, monkeypatch):
    seed(database, "handoff", stage="submitting")
    repository = DocumentPipelineRepository(database, Mock())
    monkeypatch.setattr(tasks, "_repository", repository)
    monkeypatch.setattr(tasks, "_locks", TaskLocks(database))
    tasks.process_file.run("handoff")
    with database.connect() as connection:
        assert connection.execute(text(
            "SELECT dispatched_at FROM job WHERE id='handoff'"
        )).scalar_one() is None
    monkeypatch.setattr(dispatch, "_repository", DispatchRepository(database))
    send = Mock()
    monkeypatch.setattr(dispatch.celery_app, "send_task", send)
    assert dispatch.recover_pending(1) == 0
    assert dispatch.dispatch_stream(dispatch.STREAMS[1], 0, 1) == 0
    assert dispatch.dispatch_stream(dispatch.STREAMS[1], 1, 1) == 1


def test_retry_count_survives_new_repository_and_message(database):
    seed(database, "retry", dispatched=True)
    for count in range(1, 4):
        # 每次均由新仓储/消息执行，不依赖 Celery Request.retries 或进程内计数。
        repository = DocumentPipelineRepository(database, Mock())
        assert repository.claim_attempt("retry", ("submitting",))
        repository.schedule_attempt("retry", 0, retry=True)
        with database.connect() as connection:
            row = connection.execute(text("SELECT * FROM job WHERE id='retry'")).mappings().one()
        assert row["progress"]["retry_attempts"] == count
        assert row["next_attempt_at"] is not None and row["dispatch_lease_until"] is None
