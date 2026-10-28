"""远端收尾只看生命周期，成果缺失不应让取消永久占用配额。"""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from tender.adapters.documents.mineru import MinerUParser
from tender.domain.shared.errors import ParseFailed
from tender.worker.documents import tasks


@pytest.mark.parametrize("status", ["canceling", "draining"])
def test_stopping_completed_parse_does_not_require_outputs(monkeypatch, status):
    repository = Mock()
    repository.job.return_value = {
        "id": "fixture", "status": status, "stage": "parsing", "provider_job_id": "remote",
    }
    parser = MinerUParser(
        "http://fixture.invalid", pdf_loader=AsyncMock(),
        transport=httpx.MockTransport(lambda _: httpx.Response(
            200, json={"status": "completed", "files": []},
        )),
    )
    monkeypatch.setattr(tasks, "_parser", lambda _: parser)
    monkeypatch.setattr(tasks, "_repository", repository)
    store = Mock()
    monkeypatch.setattr(tasks, "_store", lambda: store)
    tasks._poll_stopping(repository.job.return_value)
    repository.finish_remote_job.assert_called_once_with("fixture")
    repository.schedule_attempt.assert_not_called()
    store.close.assert_called_once()
    assert parser._client.is_closed


def test_normal_parse_still_rejects_missing_middle_json(monkeypatch):
    parser = MinerUParser(
        "http://fixture.invalid", pdf_loader=AsyncMock(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"status": "completed"})),
    )
    monkeypatch.setattr(tasks, "_parser", lambda _: parser)
    with pytest.raises(ParseFailed, match="middle_json"):
        asyncio.run(tasks._poll({"provider_job_id": "remote"}, Mock()))


@pytest.mark.parametrize("stage", ["submitting", "resubmitting"])
def test_unknown_submission_only_waits_for_manual_reconciliation(monkeypatch, stage):
    repository = Mock()
    monkeypatch.setattr(tasks, "_repository", repository)
    parser = Mock(side_effect=AssertionError("不能重新提交或查询旧句柄"))
    monkeypatch.setattr(tasks, "_parser", parser)
    tasks._poll_stopping({"id": "unknown", "status": "draining", "stage": stage})
    repository.schedule_attempt.assert_called_once_with("unknown", 30)
    repository.finish_remote_job.assert_not_called()
