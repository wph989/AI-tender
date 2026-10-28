"""持久任务查询与取消的数据库访问。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, Engine, func, select, update

from tender.adapters.pg.models import Job, ParseRun
from tender.ports.repository.jobs.tasks import TERMINAL_STATUSES


def finish_canceled_job(connection: Connection, job_id: str, run_id: int | None) -> None:
    """调用者锁定任务行并确认执行已结束后，同事务收敛任务与解析批次。"""
    values = {
        "status": "canceled",
        "error_code": "canceled_by_user",
        "error_message": "任务已由用户取消",
        "finished_at": func.now(),
    }
    connection.execute(
        update(Job).where(Job.id == job_id).values(
            **values, updated_at=func.now(), next_attempt_at=None, dispatch_lease_until=None,
        )
    )
    if run_id is not None:
        connection.execute(
            update(ParseRun).where(
                ParseRun.id == run_id, ParseRun.status.in_(("pending", "running")),
            ).values(**values)
        )


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
            row = connection.execute(
                select(Job.status, Job.run_id).where(
                    Job.id == job_id,
                    Job.company_id == self.company_id,
                ).with_for_update()
            ).mappings().first()
            if row is None:
                return False, None
            if row["status"] in TERMINAL_STATUSES or row["status"] == "canceling":
                return True, row["status"]
            if row["status"] == "pending":
                finish_canceled_job(connection, job_id, row["run_id"])
                return True, "canceled"
            # 取消请求不等于远端停止；保留派发闩锁和在途配额，交给原执行者或恢复轮询收尾。
            connection.execute(update(Job).where(Job.id == job_id).values(
                status="canceling", error_code="canceled_by_user",
                error_message="正在取消，等待当前处理结束", updated_at=func.now(),
                next_attempt_at=func.now(), dispatch_lease_until=None,
            ))
            return True, "canceling"
