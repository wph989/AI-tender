"""派发查询与标记；保留提交前投递、失败可重发的既有事务语义。"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, func, select, update

from tender.adapters.pg.models import Job


def pending_jobs(stages: tuple[str, ...], company_id: int, limit: int | None):
    # 候选只取当前可派发数量，锁住行后再投递，避免重复扫描同一批任务。
    return (
        select(Job.id)
        .where(
            Job.company_id == company_id,
            Job.status == "pending",
            Job.finished_at.is_(None),
            Job.dispatched_at.is_(None),
            Job.stage.in_(stages),
        )
        .order_by(Job.created_at, Job.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


class DispatchTransaction:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def inflight(self, stages: tuple[str, ...], company_id: int) -> int:
        return int(
            self.connection.execute(
                select(func.count()).where(
                    Job.company_id == company_id,
                    Job.status.in_(("pending", "submitting", "running")),
                    Job.finished_at.is_(None),
                    Job.dispatched_at.is_not(None),
                    Job.stage.in_(stages),
                )
            ).scalar_one()
        )

    def pending(self, stages: tuple[str, ...], company_id: int, limit: int | None) -> list[str]:
        return list(self.connection.execute(pending_jobs(stages, company_id, limit)).scalars())

    def mark_dispatched(self, job_id: str) -> None:
        self.connection.execute(
            update(Job)
            .where(Job.id == job_id, Job.dispatched_at.is_(None))
            .values(dispatched_at=func.now(), updated_at=func.now())
        )


class DispatchRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def transaction(self) -> Iterator[DispatchTransaction]:
        with self.engine.begin() as connection:
            yield DispatchTransaction(connection)
