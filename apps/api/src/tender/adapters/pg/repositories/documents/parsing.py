"""解析任务创建所需的数据库操作。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, Engine, case, insert, select

from tender.adapters.pg.models import Job, ParseRun, Project, ProjectFile
from tender.config.registry import ConfigRegistry
from tender.ports.configuration.registry import ActiveConfig


class ParseTransaction:
    def __init__(self, connection: Connection, configs: ConfigRegistry) -> None:
        self.connection = connection
        self.configs = configs

    def snapshot_for_job(self, active: ActiveConfig | None) -> int | None:
        # 快照和任务必须同事务提交；连接只在仓储内部传递。
        return self.configs.snapshot_for_job(self.connection, active)

    def lock_file(self, version_id: int, company_id: int) -> dict[str, Any] | None:
        row = (
            self.connection.execute(
                select(
                    ProjectFile.id.label("project_file_id"),
                    ProjectFile.project_id,
                    ProjectFile.display_name,
                    ProjectFile.is_parseable,
                    Project.company_id,
                )
                .select_from(ProjectFile)
                .join(Project, Project.id == ProjectFile.project_id)
                .where(
                    ProjectFile.version_id == version_id,
                    ProjectFile.deleted_at.is_(None),
                    Project.company_id == company_id,
                    Project.deleted_at.is_(None),
                )
                .order_by(
                    case((ProjectFile.role == "main", 0), else_=1),
                    ProjectFile.sort_no,
                    ProjectFile.id,
                )
                .limit(1)
                .with_for_update(of=ProjectFile)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def active_job(self, version_id: int) -> str | None:
        return self.connection.execute(
            select(Job.id)
            .where(
                Job.version_id == version_id,
                Job.status.in_(("pending", "submitting", "running", "canceling")),
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def prior_run(self, version_id: int) -> int | None:
        return self.connection.execute(
            select(ParseRun.id)
            .where(
                ParseRun.version_id == version_id,
                ParseRun.status.in_(("pending", "running", "completed", "partial")),
            )
            .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def insert_job(self, values: dict[str, Any]) -> None:
        self.connection.execute(insert(Job).values(**values))


class ParseRepository:
    def __init__(self, engine: Engine, company_id: int, configs: ConfigRegistry) -> None:
        self.engine = engine
        self.configs = configs
        self.company_id = company_id

    @contextmanager
    def transaction(self) -> Iterator[ParseTransaction]:
        with self.engine.begin() as connection:
            yield ParseTransaction(connection, self.configs)
