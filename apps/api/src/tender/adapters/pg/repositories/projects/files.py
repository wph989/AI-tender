"""项目文件及其解析任务的数据库访问。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, Engine, func, insert, select, update

from tender.adapters.pg.models import DocumentVersion, Job, Project, ProjectFile
from tender.adapters.pg.repositories.knowledge.store import sync_sources
from tender.config.registry import ConfigRegistry
from tender.ports.configuration.registry import ActiveConfig


class ProjectFileTransaction:
    """一个事务内可组合的原子数据库操作，业务判断仍由服务层完成。"""

    def __init__(self, connection: Connection, company_id: int, configs: ConfigRegistry) -> None:
        self.connection = connection
        self.configs = configs
        self.company_id = company_id

    def snapshot_for_job(self, active: ActiveConfig | None) -> int | None:
        # 快照和任务必须同事务提交；连接只在仓储内部传递。
        return self.configs.snapshot_for_job(self.connection, active)

    def lock_project(self, project_id: int) -> bool:
        found = self.connection.execute(
            select(Project.id)
            .where(
                Project.id == project_id,
                Project.company_id == self.company_id,
                Project.deleted_at.is_(None),
            )
            .with_for_update()
        ).scalar_one_or_none()
        return found is not None

    def replacement_exists(self, project_id: int, file_id: int) -> bool:
        found = self.connection.execute(
            select(ProjectFile.id).where(
                ProjectFile.id == file_id,
                ProjectFile.project_id == project_id,
                ProjectFile.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        return found is not None

    def next_sort_no(self, project_id: int) -> int:
        return int(
            self.connection.execute(
                select(func.coalesce(func.max(ProjectFile.sort_no), -1) + 1).where(
                    ProjectFile.project_id == project_id,
                    ProjectFile.deleted_at.is_(None),
                )
            ).scalar_one()
        )

    def insert_file(self, values: dict[str, Any]) -> int:
        return int(
            self.connection.execute(
                insert(ProjectFile).values(**values).returning(ProjectFile.id)
            ).scalar_one()
        )

    def sync_sources(self, project_id: int) -> None:
        sync_sources(self.connection, project_id)

    def insert_job(self, values: dict[str, Any]) -> None:
        self.connection.execute(insert(Job).values(**values))


class ProjectFileRepository:
    def __init__(self, engine: Engine, company_id: int, configs: ConfigRegistry) -> None:
        self.engine = engine
        self.configs = configs
        self.company_id = company_id

    @contextmanager
    def transaction(self) -> Iterator[ProjectFileTransaction]:
        with self.engine.begin() as connection:
            yield ProjectFileTransaction(connection, self.company_id, self.configs)

    def row(self, project_id: int, file_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        ProjectFile,
                        Project.company_id,
                        Project.deleted_at.label("project_deleted_at"),
                        DocumentVersion.original_key.label("version_original_key"),
                    )
                    .select_from(ProjectFile)
                    .join(Project, Project.id == ProjectFile.project_id)
                    .outerjoin(DocumentVersion, DocumentVersion.id == ProjectFile.version_id)
                    .where(
                        ProjectFile.project_id == project_id,
                        ProjectFile.id == file_id,
                        Project.company_id == self.company_id,
                        Project.deleted_at.is_(None),
                        ProjectFile.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def update(self, project_id: int, file_id: int, values: dict[str, object]) -> int:
        owned_project = (
            select(Project.id)
            .where(
                Project.id == project_id,
                Project.company_id == self.company_id,
                Project.deleted_at.is_(None),
            )
            .scalar_subquery()
        )
        with self.engine.begin() as connection:
            return connection.execute(
                update(ProjectFile)
                .where(
                    ProjectFile.project_id == owned_project,
                    ProjectFile.id == file_id,
                    ProjectFile.deleted_at.is_(None),
                )
                .values(**values)
            ).rowcount

    def soft_delete(self, project_id: int, file_id: int) -> int:
        owned_project = (
            select(Project.id)
            .where(
                Project.id == project_id,
                Project.company_id == self.company_id,
                Project.deleted_at.is_(None),
            )
            .scalar_subquery()
        )
        with self.engine.begin() as connection:
            return connection.execute(
                update(ProjectFile)
                .where(
                    ProjectFile.project_id == owned_project,
                    ProjectFile.id == file_id,
                    ProjectFile.deleted_at.is_(None),
                )
                .values(deleted_at=func.now())
            ).rowcount

    def project_exists(self, project_id: int) -> bool:
        with self.engine.connect() as connection:
            found = connection.execute(
                select(Project.id).where(
                    Project.id == project_id,
                    Project.company_id == self.company_id,
                    Project.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
        return found is not None
