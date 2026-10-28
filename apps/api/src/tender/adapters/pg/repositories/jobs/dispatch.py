"""派发查询与标记；保留提交前投递、失败可重发的既有事务语义。"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import Connection, Engine, func, or_, select, update

from tender.adapters.pg.locks import acquire_xact_lock, try_acquire_xact_lock
from tender.adapters.pg.models import Job

DISPATCH_LEASE = timedelta(seconds=60)


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
            or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= func.now()),
        )
        .order_by(Job.created_at, Job.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )


class DispatchTransaction:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def lock_stream(self, company_id: int, stream: str) -> None:
        # 候选行锁只能防重复领取；公司/资源锁才能保护跨行的总配额。
        acquire_xact_lock(self.connection, f"document_dispatch:{company_id}:{stream}")

    def inflight(self, stages: tuple[str, ...], company_id: int) -> int:
        return int(
            self.connection.execute(
                select(func.count()).where(
                    Job.company_id == company_id,
                    Job.status.in_(("pending", "submitting", "running", "canceling", "draining")),
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
            .where(Job.id == job_id)
            .values(
                dispatched_at=func.now(),
                dispatch_lease_until=func.now() + DISPATCH_LEASE,
            )
        )

    def recoverable(
        self, company_id: int, limit: int, stages: tuple[str, ...]
    ) -> list[tuple[str, str]]:
        """返回 ``(job_id, stage)``；派发哪条消息由调度侧的 stage→任务表决定。"""
        rows = self.connection.execute(
            select(Job.id, Job.stage)
            .where(
                Job.company_id == company_id,
                Job.status.in_(("pending", "submitting", "running", "canceling", "draining")),
                Job.stage.in_(stages),
                Job.finished_at.is_(None),
                Job.dispatched_at.is_not(None),
                or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= func.now()),
                or_(Job.dispatch_lease_until.is_(None), Job.dispatch_lease_until <= func.now()),
            )
            .order_by(Job.dispatch_lease_until.asc().nullsfirst(), Job.created_at, Job.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        result = []
        for job_id, stage in rows:
            # 不抢占活跃执行者；非阻塞取锁避免与执行者的锁顺序形成死锁。
            if not try_acquire_xact_lock(self.connection, f"job:{job_id}"):
                # 活跃任务延长扫描租约，让后续批次能轮到失联任务；不触碰其执行预算。
                self.connection.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .values(
                        dispatch_lease_until=func.now() + DISPATCH_LEASE,
                    )
                )
                continue
            result.append((job_id, stage))
        return result


class DispatchRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def transaction(self) -> Iterator[DispatchTransaction]:
        with self.engine.begin() as connection:
            yield DispatchTransaction(connection)
