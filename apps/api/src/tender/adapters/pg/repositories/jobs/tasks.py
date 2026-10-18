"""持久任务查询与取消的数据库访问。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, select, update

from tender.adapters.pg.models import Job
from tender.ports.repository.jobs.tasks import TERMINAL_STATUSES


class JobRepository:
    def __init__(self, engine: Engine, company_id: int) -> None:
        self.engine = engine
        self.company_id = company_id

    def payload(self, job_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        Job.id,
                        Job.status,
                        Job.stage,
                        Job.progress,
                        Job.error_code,
                        Job.error_message,
                        Job.version_id,
                        Job.run_id,
                        Job.created_at,
                        Job.updated_at,
                        Job.finished_at,
                    ).where(Job.id == job_id, Job.company_id == self.company_id)
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def cancel(self, job_id: str) -> tuple[bool, str | None]:
        """返回 (是否存在, 取消后的状态)；不存在时状态为 None。"""
        with self.engine.begin() as connection:
            canceled = connection.execute(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.company_id == self.company_id,
                    Job.status.not_in(tuple(TERMINAL_STATUSES)),
                )
                .values(
                    status="canceled",
                    error_code="canceled_by_user",
                    error_message="任务已由用户取消",
                    finished_at=func.now(),
                    updated_at=func.now(),
                )
                .returning(Job.id)
            ).scalar_one_or_none()
            if canceled is not None:
                return True, "canceled"
            current = connection.execute(
                select(Job.status).where(
                    Job.id == job_id,
                    Job.company_id == self.company_id,
                )
            ).scalar_one_or_none()
        return current is not None, current
