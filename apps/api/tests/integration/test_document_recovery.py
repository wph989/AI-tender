"""用多连接验证配额与恢复：丢消息、退避、活跃锁和并发调度均使用真实 SQL。"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import make_url

from tender.adapters.pg.models import Job, ParseRun
from tender.adapters.pg.repositories.documents.parsing import ParseTransaction
from tender.adapters.pg.repositories.documents.pipeline import DocumentPipelineRepository
from tender.adapters.pg.repositories.jobs.coordination import TaskLocks
from tender.adapters.pg.repositories.jobs.dispatch import DispatchRepository
from tender.adapters.pg.repositories.jobs.tasks import JobRepository
from tender.core.settings import database_url
from tender.domain.shared.errors import ParseUnavailable, ServiceRestarted
from tender.ports.documents.parser import ParseJobStatus
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
    ParseRun.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE parse_run ALTER COLUMN created_at SET DEFAULT now()"))
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


@pytest.mark.parametrize(("status", "stage"), [
    ("pending", "converting"),
    ("running", "geometry"),
    ("submitting", "submitting"),
    ("running", "parsing"),
    ("running", "resubmitting"),
])
def test_lost_messages_recover_at_current_stage(database, status, stage):
    seed(database, "lost", status=status, stage=stage, dispatched=True)
    stages = tuple(dispatch.RECOVERY_TASKS)
    with DispatchRepository(database).transaction() as tx:
        assert tx.recoverable(1, 100, stages) == [("lost", stage)]
        assert tx.recoverable(2, 100, stages) == []


def test_live_execution_future_attempt_and_terminal_are_not_recovered(database):
    seed(database, "live", status="running", stage="parsing", dispatched=True)
    seed(database, "later", dispatched=True,
         next_attempt_at=datetime.now(UTC) + timedelta(minutes=1))
    seed(database, "done", status="completed", dispatched=True)
    stages = tuple(dispatch.RECOVERY_TASKS)
    with TaskLocks(database).lock("job:live") as acquired:
        assert acquired
        with DispatchRepository(database).transaction() as tx:
            assert tx.recoverable(1, 100, stages) == []
    with database.begin() as connection:
        connection.execute(text("UPDATE job SET dispatch_lease_until=now() WHERE id='live'"))
    with DispatchRepository(database).transaction() as tx:
        assert tx.recoverable(1, 100, stages) == [("live", "parsing")]


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
        stages = tuple(dispatch.RECOVERY_TASKS)
        with DispatchRepository(database).transaction() as tx:
            assert tx.recoverable(1, 1, stages) == []
        with DispatchRepository(database).transaction() as tx:
            assert tx.recoverable(1, 1, stages) == [("lost", "parsing")]


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


def seed_parse(engine, job_id="remote", *, stage="parsing", status="running"):
    with engine.begin() as connection:
        run_id = connection.execute(insert(ParseRun).values(
            version_id=11, provider="mineru", provider_version="fixture", tier="standard",
            schema_version="2.0", status="running", provider_job_id="remote-id",
            config_snapshot={}, started_at=datetime.now(UTC),
        ).returning(ParseRun.id)).scalar_one()
    seed(engine, job_id, status=status, stage=stage, dispatched=True, version_id=11, run_id=run_id)
    return run_id


def test_cancel_pending_job_finishes_without_dispatch(database):
    seed(database, "pending")
    repository = JobRepository(database, 1)
    assert repository.cancel("pending") == (True, "canceled")
    assert repository.cancel("pending") == (True, "canceled")
    assert repository.payload("pending")["finished_at"] is not None
    with DispatchRepository(database).transaction() as transaction:
        assert transaction.pending(("submitting",), 1, 1) == []


@pytest.mark.parametrize("code", ["parse_timeout", "parse_failed", "provider_version_changed"])
def test_local_parse_failure_retains_quota_until_remote_stops(database, code):
    run_id = seed_parse(database)
    seed(database, "next")
    repository = DocumentPipelineRepository(database, Mock())
    repository.set_job_failure("remote", code, "原始失败")
    payload = JobRepository(database, 1).payload("remote")
    assert payload["status"] == "draining" and payload["finished_at"] is None
    with DispatchRepository(database).transaction() as transaction:
        assert transaction.inflight(dispatch.STREAMS[1].inflight_stages, 1) == 1
    with database.connect() as connection:
        assert ParseTransaction(connection, Mock()).active_job(11) == "remote"
        assert connection.execute(select(ParseRun.status).where(
            ParseRun.id == run_id,
        )).scalar_one() == "running"
    repository.schedule_attempt("remote", 0)
    with DispatchRepository(database).transaction() as transaction:
        assert transaction.recoverable(1, 100, tuple(dispatch.RECOVERY_TASKS)) == [
            ("remote", "parsing"),
        ]
    repository.finish_remote_job("remote")
    repository.finish_remote_job("remote")
    payload = JobRepository(database, 1).payload("remote")
    assert payload["status"] == "failed" and payload["finished_at"] is not None
    assert payload["error_code"] == code and payload["error_message"] == "原始失败"
    with database.connect() as connection:
        assert connection.execute(select(ParseRun.status).where(
            ParseRun.id == run_id,
        )).scalar_one() == "failed"


@pytest.mark.parametrize("resubmitting", [False, True])
def test_unknown_submission_failure_keeps_occupancy_and_original_error(database, resubmitting):
    if resubmitting:
        seed_parse(database, stage="resubmitting")
    else:
        seed(database, "remote", status="submitting", dispatched=True, version_id=11)
    repository = DocumentPipelineRepository(database, Mock())
    repository.set_job_failure("remote", "parse_submission_unknown", "需人工核对远端")
    repository.set_job_failure("remote", "parse_timeout", "不能覆盖原始原因")
    payload = JobRepository(database, 1).payload("remote")
    assert payload["status"] == "draining" and payload["finished_at"] is None
    assert payload["error_code"] == "parse_submission_unknown"
    assert payload["error_message"] == "需人工核对远端"
    with DispatchRepository(database).transaction() as transaction:
        assert transaction.inflight(dispatch.STREAMS[1].inflight_stages, 1) == 1


def test_cancel_remote_parse_keeps_quota_and_blocks_reparse(database):
    run_id = seed_parse(database)
    seed(database, "next")
    repository = JobRepository(database, 1)
    assert JobRepository(database, 2).cancel("remote") == (False, None)
    assert repository.cancel("remote") == (True, "canceling")
    assert repository.cancel("remote") == (True, "canceling")
    assert repository.payload("remote")["finished_at"] is None
    with DispatchRepository(database).transaction() as transaction:
        assert transaction.inflight(dispatch.STREAMS[1].inflight_stages, 1) == 1
        assert transaction.recoverable(1, 100, tuple(dispatch.RECOVERY_TASKS)) == [
            ("remote", "parsing"),
        ]
    with database.connect() as connection:
        assert ParseTransaction(connection, Mock()).active_job(11) == "remote"
        state = connection.execute(
            select(ParseRun.status).where(ParseRun.id == run_id),
        ).scalar_one()
        assert state == "running"


@pytest.mark.parametrize("stopping", ["canceling", "draining"])
@pytest.mark.parametrize("remote_status", [
    "running", "completed", "partial", "failed", "canceled", "missing", "unavailable",
])
def test_cancel_poll_only_drains_remote_and_recovers(
    database, monkeypatch, remote_status, stopping,
):
    run_id = seed_parse(database)
    repository = DocumentPipelineRepository(database, Mock())
    if stopping == "canceling":
        JobRepository(database, 1).cancel("remote")
    else:
        repository.set_job_failure("remote", "parse_timeout", "原始超时原因")
        repository.schedule_attempt("remote", 0)

    def job(job_id):
        with database.connect() as connection:
            return connection.execute(select(Job, ParseRun.provider_job_id).join(
                ParseRun, ParseRun.id == Job.run_id,
            ).where(Job.id == job_id)).mappings().one()

    monkeypatch.setattr(repository, "job", job)
    monkeypatch.setattr(tasks, "_repository", repository)
    monkeypatch.setattr(tasks, "_locks", TaskLocks(database))
    parser = AsyncMock()
    if remote_status == "missing":
        parser.poll.side_effect = ServiceRestarted("远端已丢失任务")
    elif remote_status == "unavailable":
        parser.poll.side_effect = ParseUnavailable("暂时不可用")
    else:
        parser.poll.return_value = ParseJobStatus("remote-id", remote_status, None, True)
    monkeypatch.setattr(tasks, "_parser", lambda _: parser)
    store = Mock()
    monkeypatch.setattr(tasks, "_store", lambda: store)
    # 取消排空不再执行原任务或消耗已用尽的执行预算，也不能下载成果。
    monkeypatch.setattr(tasks, "_runtime_values", Mock(side_effect=AssertionError("不应恢复解析")))
    tasks.poll_parse.run("remote")
    parser.poll.assert_awaited_once_with("remote-id")
    parser.fetch_middle_json.assert_not_called()
    parser.submit.assert_not_called()
    parser.aclose.assert_awaited_once()
    store.close.assert_called_once()
    pending = remote_status in {"running", "unavailable"}
    payload = JobRepository(database, 1).payload("remote")
    finished = "canceled" if stopping == "canceling" else "failed"
    assert payload["status"] == (stopping if pending else finished)
    if stopping == "draining":
        assert payload["error_code"] == "parse_timeout"
        assert payload["error_message"] == "原始超时原因"
    assert (payload["finished_at"] is None) is pending
    with database.connect() as connection:
        state = connection.execute(
            select(ParseRun.status).where(ParseRun.id == run_id),
        ).scalar_one()
        assert state == ("running" if pending else finished)
    with DispatchRepository(database).transaction() as transaction:
        assert transaction.inflight(dispatch.STREAMS[1].inflight_stages, 1) == int(pending)
    if pending:
        repository.schedule_attempt("remote", 0)
        with DispatchRepository(database).transaction() as transaction:
            assert transaction.recoverable(1, 100, tuple(dispatch.RECOVERY_TASKS)) == [
                ("remote", "parsing"),
            ]


def test_cancel_during_submission_keeps_returned_remote_handle(database):
    seed(database, "submit", status="submitting", dispatched=True, version_id=11)
    JobRepository(database, 1).cancel("submit")
    repository = DocumentPipelineRepository(database, Mock())
    repository.save_submission("submit", 11, "fixture", "remote-id", {
        "tier": "advanced", "ocr_mode": "ocr",
    }, datetime.now(UTC))
    with database.connect() as connection:
        row = connection.execute(select(Job, ParseRun.provider_job_id).join(
            ParseRun, ParseRun.id == Job.run_id,
        )).mappings().one()
    assert row["status"] == "canceling" and row["stage"] == "parsing"
    assert row["provider_job_id"] == "remote-id" and row["finished_at"] is None


@pytest.mark.parametrize("unknown", [False, True])
def test_cancel_submission_rejected_or_unknown(database, unknown):
    seed(database, "submit", status="submitting", dispatched=True)
    JobRepository(database, 1).cancel("submit")
    repository = DocumentPipelineRepository(database, Mock())
    if unknown:
        repository.set_job_failure("submit", "parse_submission_unknown", "需人工核对")
    else:
        repository.retry_submission("submit", "unavailable", "远端未受理")
    payload = JobRepository(database, 1).payload("submit")
    assert payload["status"] == ("canceling" if unknown else "canceled")
    with DispatchRepository(database).transaction() as transaction:
        assert transaction.inflight(dispatch.STREAMS[1].inflight_stages, 1) == int(unknown)


def test_cancel_during_conversion_does_not_create_version_or_handoff(database):
    seed(database, "convert", status="running", stage="converting", dispatched=True)
    JobRepository(database, 1).cancel("convert")
    repository = DocumentPipelineRepository(database, Mock())
    result = repository.finish_file_version(
        {"id": "convert", "config_snapshot": {}}, candidate=None,
        pdf_key="fixture", pdf_sha256="fixture", converter=None, converter_version=None,
        is_converted=True, inspection=None,
    )
    assert result == (0, 0, False)
    assert repository.finish_cancellation("convert")
    assert JobRepository(database, 1).payload("convert")["status"] == "canceled"


def test_cancel_wins_against_completed_parse_write(database):
    seed_parse(database)
    JobRepository(database, 1).cancel("remote")
    with database.connect() as connection:
        row = connection.execute(select(Job).where(Job.id == "remote")).mappings().one()
    repository = DocumentPipelineRepository(database, Mock())
    repository.complete_parse(
        "remote", row, [object()], terminal_status="completed", raw_middle_key=None,
        page_count=1, backend=None, schema_version=None, elapsed_ms=1,
        error_code=None, error_message=None, progress={}, now=datetime.now(UTC),
    )
    assert JobRepository(database, 1).payload("remote")["status"] == "canceled"
