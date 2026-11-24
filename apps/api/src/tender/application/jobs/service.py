"""任务查询与取消用例。"""

from __future__ import annotations

from typing import Any

from tender.application.shared.errors import Conflict, NotFound
from tender.ports.repository.jobs.tasks import TERMINAL_STATUSES, JobRepository


class JobService:
    def __init__(self, repository: JobRepository) -> None:
        self.repository = repository

    def payload(self, job_id: str) -> dict[str, Any]:
        payload = self.repository.payload(job_id)
        if payload is None:
            raise NotFound("任务不存在")
        return payload

    def is_terminal(self, payload: dict[str, Any]) -> bool:
        return payload["status"] in TERMINAL_STATUSES

    def cancel(self, job_id: str) -> dict[str, Any]:
        found, status = self.repository.cancel(job_id)
        if not found:
            raise NotFound("任务不存在")
        if status not in {"canceled", "canceling"}:
            raise Conflict(f"任务已处于终态：{status}", code="job_not_cancelable")
        return self.payload(job_id)
