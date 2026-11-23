"""部分文件失败时保留成功回执，并正确区分可重试与不可重试的整批失败。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tender.api.shared.errors import as_api_problem
from tender.application.projects.files import FileInput, ProjectFileService
from tender.application.shared.errors import ServiceError, Unavailable, Unprocessable
from tender.domain.shared.errors import ConversionFailed, ConversionUnavailable
from tender.ports.storage.blob_store import BlobStoreError


def run_upload(effects):
    service = ProjectFileService(
        SimpleNamespace(project_exists=lambda _: True), 1, None, None,
    )
    service.add_project_file = AsyncMock(side_effect=effects)
    result = asyncio.run(service.upload(
        project_id=1,
        files=[FileInput(f"{name}.txt", b"content") for name in "abc"[:len(effects)]],
        archive=None,
        auto_parse=True,
        tier=None,
        ocr_mode=None,
        role=None,
    ))
    return result, service.add_project_file


@pytest.mark.parametrize("failure", [
    BlobStoreError("对象存储暂时不可用"),
    ConversionUnavailable("转换服务暂时不可用"),
    ConversionFailed("文件损坏"),
])
def test_one_failed_file_does_not_discard_successes_or_stop_the_batch(failure):
    first = {"project_file_id": 1, "job_id": "job_a"}
    last = {"project_file_id": 3, "job_id": "job_c"}
    result, add = run_upload([first, failure, last])
    assert result == {
        "added": [first, last],
        "jobs": ["job_a", "job_c"],
        "skipped": [{"name": "b.txt", "reason": str(failure)}],
    }
    assert [call.kwargs["item"].name for call in add.await_args_list] == [
        "a.txt", "b.txt", "c.txt",
    ]


@pytest.mark.parametrize(("failure", "error_type", "status", "code", "retryable"), [
    (BlobStoreError("存储断开"), Unavailable, 503, "ingest_unavailable", True),
    (ConversionUnavailable("转换超时"), Unavailable, 503, "ingest_unavailable", True),
    (ServiceError("可重试失败", retryable=True), Unavailable, 503, "ingest_unavailable", True),
    (ConversionFailed("文件损坏"), Unprocessable, 422, "upload_failed", False),
])
def test_all_failed_files_keep_failure_details_and_retryability(
    failure, error_type, status, code, retryable,
):
    with pytest.raises(error_type) as caught:
        run_upload([failure, failure])
    problem = as_api_problem(caught.value)
    assert (problem.status_code, problem.code, problem.retryable) == (status, code, retryable)
    assert problem.detail == {"skipped": [
        {"name": "a.txt", "reason": str(failure)},
        {"name": "b.txt", "reason": str(failure)},
    ]}


def test_unexpected_errors_are_not_reported_as_skipped_files():
    with pytest.raises(RuntimeError, match="unexpected"):
        run_upload([RuntimeError("unexpected")])
