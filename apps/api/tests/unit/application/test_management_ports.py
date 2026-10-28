"""管理用例通过端口运行；假事务不提供引擎或连接，以验证数据库细节不会泄漏。"""

import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from tender.api.shared.errors import install_error_handlers
from tender.application.documents.parsing import ParseService
from tender.application.jobs.service import JobService
from tender.application.shared.errors import Conflict
from tender.ports.configuration.registry import ActiveConfig
from tender.ports.repository.llm.management import RecordConflict


@pytest.mark.parametrize("inflight", [False, True])
def test_parse_use_case_keeps_snapshot_and_job_in_one_injected_transaction(inflight):
    events = []
    written = []
    active = ActiveConfig(7, 1, {}, {})

    class Transaction:
        def lock_file(self, version_id, company_id):
            return {"is_parseable": True, "project_id": 3, "project_file_id": 4}

        def active_job(self, version_id):
            return "already-running" if inflight else None

        def prior_run(self, version_id):
            return None

        def snapshot_for_job(self, current):
            assert current is active
            events.append("snapshot")
            return 8

        def insert_job(self, row):
            events.append("job")
            written.append(row)

    class Repository:
        @contextmanager
        def transaction(self):
            events.append("begin")
            try:
                yield Transaction()
            except Exception:
                events.append("rollback")
                raise
            else:
                events.append("commit")

    def current_config(company_id):
        events.append("config")
        return active

    service = ParseService(
        Repository(), 1, SimpleNamespace(active=current_config),
        SimpleNamespace(version=lambda _: {"id": 2}),
    )
    if inflight:
        with pytest.raises(Conflict, match="解析任务进行中"):
            service.create_job(2, tier=None, ocr_mode=None, force=False, reason=None, actor="test")
        assert events == ["config", "begin", "rollback"]
        assert written == []
    else:
        result = service.create_job(
            2, tier=None, ocr_mode=None, force=False, reason=None, actor="test",
        )
        assert events == ["config", "begin", "snapshot", "job", "commit"]
        assert written[0]["id"] == result["job_id"]
        assert written[0]["config_snapshot_id"] == 8


def test_repository_conflict_retains_existing_http_contract():
    app = FastAPI()
    install_error_handlers(app)
    response = asyncio.run(app.exception_handlers[RecordConflict](None, RecordConflict()))
    assert response.status_code == 409
    assert json.loads(response.body)["error"]["code"] == "version_conflict"


def test_canceling_job_is_accepted_and_keeps_progress_stream_open():
    payload = {"id": "fixture", "status": "canceling", "finished_at": None}
    service = JobService(SimpleNamespace(
        cancel=lambda _: (True, "canceling"), payload=lambda _: payload,
    ), 1)
    assert service.cancel("fixture") == payload
    assert not service.is_terminal(payload)
    assert service.is_terminal(payload | {"status": "canceled"})
