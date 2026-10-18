"""项目与项目详情的数据库访问。"""

from __future__ import annotations

import builtins
from typing import Any

from sqlalchemy import Engine, func, insert, or_, select, true, update
from sqlalchemy.orm import aliased

from tender.adapters.pg.models import (
    DocumentVersion,
    Job,
    Lot,
    ParseRun,
    Project,
    ProjectFile,
)
from tender.adapters.pg.repositories.knowledge.store import ensure_project_collection


class ProjectRepository:
    """只负责项目相关 SQL；名称是否为空、能否删除等判断留在服务层。"""

    def __init__(self, engine: Engine, company_id: int) -> None:
        self.engine = engine
        self.company_id = company_id

    def create(
        self,
        *,
        name: str,
        project_no: str | None,
        owner: str | None,
    ) -> dict[str, Any]:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    insert(Project)
                    .values(
                        company_id=self.company_id,
                        name=name,
                        project_no=project_no,
                        owner=owner,
                    )
                    .returning(
                        Project.id,
                        Project.company_id,
                        Project.name,
                        Project.project_no,
                        Project.owner,
                        Project.status,
                        Project.created_at,
                    )
                )
                .mappings()
                .one()
            )
            ensure_project_collection(connection, int(row["id"]))
        return dict(row)

    def list(
        self, *, offset: int, limit: int, keyword: str | None
    ) -> builtins.list[dict[str, Any]]:
        # 文件数与失败数一次聚合返回；否则项目列表会演变成逐项目请求。
        agg_owner = aliased(Project)
        job_owner = aliased(Project)
        latest_parse = (
            select(ParseRun.status.label("status"))
            .where(ParseRun.version_id == ProjectFile.version_id)
            .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
            .limit(1)
            .correlate(ProjectFile)
            .lateral("latest_parse")
        )
        # 旧任务账仍保留；列表只读取文档流水线，不能把退役任务的取消状态当成失败。
        latest_job = (
            select(Job.status.label("status"))
            .where(
                Job.project_file_id == ProjectFile.id,
                Job.stage.in_(
                    ("converting", "probing", "geometry", "submitting", "parsing", "resubmitting")
                ),
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(1)
            .correlate(ProjectFile)
            .lateral("latest_job")
        )
        agg = (
            select(
                ProjectFile.project_id,
                func.count(func.distinct(ProjectFile.id)).label("file_count"),
                func.max(ProjectFile.created_at).label("last_file_at"),
                func.count(func.distinct(ProjectFile.id))
                .filter(
                    or_(
                        latest_parse.c.status == "failed",
                        latest_job.c.status.in_(("failed", "canceled")),
                    )
                )
                .label("failed_count"),
            )
            .select_from(ProjectFile)
            .join(agg_owner, agg_owner.id == ProjectFile.project_id)
            .outerjoin(latest_parse, true())
            .outerjoin(latest_job, true())
            .where(
                ProjectFile.deleted_at.is_(None),
                agg_owner.company_id == self.company_id,
                agg_owner.deleted_at.is_(None),
            )
            .group_by(ProjectFile.project_id)
            .subquery("agg")
        )
        # job 没有 company_id，经项目收窄范围，避免每次刷新扫描全部公司任务。
        act = (
            select(Job.project_id, func.max(Job.updated_at).label("last_job_at"))
            .join(job_owner, job_owner.id == Job.project_id)
            .where(
                job_owner.company_id == self.company_id,
                job_owner.deleted_at.is_(None),
                Job.stage.in_(
                    ("converting", "probing", "geometry", "submitting", "parsing", "resubmitting")
                ),
            )
            .group_by(Job.project_id)
            .subquery("act")
        )
        last_activity = func.greatest(
            Project.created_at, agg.c.last_file_at, act.c.last_job_at
        ).label("last_activity_at")
        query = (
            select(
                Project.id,
                Project.company_id,
                Project.name,
                Project.project_no,
                Project.owner,
                Project.status,
                Project.created_at,
                func.coalesce(agg.c.file_count, 0).label("file_count"),
                func.coalesce(agg.c.failed_count, 0).label("failed_count"),
                last_activity,
            )
            .select_from(Project)
            .outerjoin(agg, agg.c.project_id == Project.id)
            .outerjoin(act, act.c.project_id == Project.id)
            .where(
                Project.company_id == self.company_id,
                Project.deleted_at.is_(None),
                Project.kind == "project",
            )
        )
        if keyword and keyword.strip():
            pattern = f"%{keyword.strip()}%"
            query = query.where(or_(Project.name.ilike(pattern), Project.project_no.ilike(pattern)))
        query = query.order_by(last_activity.desc(), Project.id.desc()).limit(limit).offset(offset)
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return [dict(row) for row in rows]

    def project(self, project_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        Project.id,
                        Project.company_id,
                        Project.name,
                        Project.project_no,
                        Project.owner,
                        Project.status,
                        Project.created_at,
                    ).where(
                        Project.id == project_id,
                        Project.company_id == self.company_id,
                        Project.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def files(self, project_id: int) -> builtins.list[dict[str, Any]]:
        latest = (
            select(
                ParseRun.id.label("id"),
                ParseRun.status.label("status"),
                ParseRun.tier.label("tier"),
                ParseRun.config_snapshot["ocr_mode"].as_string().label("ocr_mode"),
            )
            .where(ParseRun.version_id == DocumentVersion.id)
            .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
            .limit(1)
            .correlate(DocumentVersion)
            .lateral("latest")
        )
        newer = aliased(ProjectFile)
        replacement = (
            select(newer.id.label("id"))
            .where(newer.replaces_id == ProjectFile.id, newer.deleted_at.is_(None))
            .order_by(newer.created_at.desc(), newer.id.desc())
            .limit(1)
            .correlate(ProjectFile)
            .lateral("replacement")
        )
        latest_job = (
            select(
                Job.id.label("id"),
                Job.status.label("status"),
                Job.stage.label("stage"),
                Job.progress.label("progress"),
                Job.error_code.label("error_code"),
                Job.error_message.label("error_message"),
            )
            .where(
                Job.project_file_id == ProjectFile.id,
                Job.stage.in_(
                    ("converting", "probing", "geometry", "submitting", "parsing", "resubmitting")
                ),
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(1)
            .correlate(ProjectFile)
            .lateral("latest_job")
        )
        statement = (
            select(
                ProjectFile.id.label("project_file_id"),
                ProjectFile.project_id,
                ProjectFile.version_id,
                ProjectFile.role,
                ProjectFile.display_name,
                ProjectFile.is_parseable,
                ProjectFile.replaces_id,
                ProjectFile.sort_no,
                ProjectFile.created_at,
                ProjectFile.sha256,
                ProjectFile.mime,
                ProjectFile.size_bytes,
                DocumentVersion.page_count,
                latest.c.status.label("parse_status"),
                latest.c.tier.label("parse_tier"),
                latest.c.ocr_mode.label("parse_ocr_mode"),
                latest.c.id.label("latest_run_id"),
                replacement.c.id.label("replaced_by_id"),
                latest_job.c.id.label("latest_job_id"),
                latest_job.c.status.label("latest_job_status"),
                latest_job.c.stage.label("latest_job_stage"),
                latest_job.c.progress.label("latest_job_progress"),
                latest_job.c.error_code.label("latest_job_error_code"),
                latest_job.c.error_message.label("latest_job_error_message"),
            )
            .select_from(ProjectFile)
            .join(Project, Project.id == ProjectFile.project_id)
            .outerjoin(DocumentVersion, DocumentVersion.id == ProjectFile.version_id)
            .outerjoin(latest, true())
            .outerjoin(replacement, true())
            .outerjoin(latest_job, true())
            .where(
                ProjectFile.project_id == project_id,
                ProjectFile.deleted_at.is_(None),
                Project.company_id == self.company_id,
                Project.deleted_at.is_(None),
            )
            .order_by(ProjectFile.sort_no, ProjectFile.id)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def lots(self, project_id: int) -> builtins.list[dict[str, Any]]:
        statement = (
            select(Lot.id, Lot.code, Lot.name, Lot.sort_no)
            .where(Lot.project_id == project_id)
            .order_by(Lot.sort_no, Lot.id)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def update(self, project_id: int, values: dict[str, object]) -> int:
        with self.engine.begin() as connection:
            return connection.execute(
                update(Project)
                .where(
                    Project.id == project_id,
                    Project.company_id == self.company_id,
                    Project.deleted_at.is_(None),
                )
                .values(**values)
            ).rowcount

    def soft_delete(self, project_id: int) -> int:
        with self.engine.begin() as connection:
            return connection.execute(
                update(Project)
                .where(
                    Project.id == project_id,
                    Project.company_id == self.company_id,
                    Project.deleted_at.is_(None),
                )
                .values(deleted_at=func.now(), status="deleted")
            ).rowcount
