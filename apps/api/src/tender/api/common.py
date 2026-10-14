"""路由共享的数据访问助手；所有资源读都带单租户 company_id 条件。"""

from __future__ import annotations

from uuid import uuid4

from fastapi import Request
from sqlalchemy import Engine, case, func, insert, select, true
from sqlalchemy.engine import RowMapping

from tender.adapters.pg.locks import acquire_xact_lock
from tender.adapters.pg.models import (
    Document,
    DocumentVersion,
    Extraction,
    FieldInstance,
    Job,
    ParseRun,
    Project,
    ProjectFile,
)
from tender.config import schema
from tender.config.registry import ConfigRegistry
from tender.core import settings
from tender.ports.blob_store import BlobStore
from tender.ports.converter import OfficeConverter
from tender.ports.task_queue import TaskQueue


def engine(request: Request) -> Engine:
    return request.app.state.components.engine


def blobs(request: Request) -> BlobStore:
    return request.app.state.components.blobs


def converter(request: Request) -> OfficeConverter:
    return request.app.state.components.converter


def configs(request: Request) -> ConfigRegistry:
    return request.app.state.components.configs


def queue(request: Request) -> TaskQueue:
    return request.app.state.components.queue


def role(request: Request) -> str:
    """角色来自 `x-role` 头（本地单租户部署，默认 admin）；未知角色按最小权限处理。"""
    raw = (request.headers.get("x-role") or "admin").strip().lower()
    return raw if raw in schema.READERS else "viewer"


def actor(request: Request) -> str:
    return (request.headers.get("x-actor") or "local-user")[:200]


def project_row(db: Engine, project_id: int) -> RowMapping:
    with db.connect() as connection:
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
                    Project.company_id == settings.company_id(),
                    Project.deleted_at.is_(None),
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        from tender.api.errors import ApiProblem

        raise ApiProblem(404, "not_found", "项目不存在")
    return row


def project_file_row(db: Engine, project_id: int, file_id: int) -> RowMapping:
    with db.connect() as connection:
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
                    Project.company_id == settings.company_id(),
                    Project.deleted_at.is_(None),
                    ProjectFile.deleted_at.is_(None),
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        from tender.api.errors import ApiProblem

        raise ApiProblem(404, "not_found", "项目文件不存在")
    return row


def version_row(db: Engine, version_id: int) -> RowMapping:
    with db.connect() as connection:
        row = (
            connection.execute(
                select(
                    DocumentVersion.id,
                    DocumentVersion.document_id,
                    DocumentVersion.version_no,
                    DocumentVersion.sha256,
                    DocumentVersion.pdf_key,
                    DocumentVersion.pdf_sha256,
                    DocumentVersion.original_key,
                    DocumentVersion.mime,
                    DocumentVersion.size_bytes,
                    DocumentVersion.is_converted,
                    DocumentVersion.converter,
                    DocumentVersion.converter_version,
                    DocumentVersion.page_count,
                    DocumentVersion.created_at,
                    Document.title,
                    Document.company_id,
                )
                .select_from(DocumentVersion)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(
                    DocumentVersion.id == version_id,
                    Document.company_id == settings.company_id(),
                    Document.deleted_at.is_(None),
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        from tender.api.errors import ApiProblem

        raise ApiProblem(404, "not_found", "文档版本不存在")
    return row


def bbox(row: RowMapping) -> list[float] | None:
    values = (row["bbox_x0"], row["bbox_y0"], row["bbox_x1"], row["bbox_y1"])
    if any(value is None for value in values):
        return None
    return [float(value) for value in values]


def start_rerun(
    db: Engine,
    configs: ConfigRegistry,
    extraction_id: int,
    *,
    hint: str | None,
    actor: str,
) -> dict[str, object]:
    """给一个当前字段实例排一次重跑任务。

    单字段重跑与项目级批量重跑共用这一份校验：只有当前尝试、且解析 run 未变化时才能重跑；
    同一实例有在途重跑时返回 409 rerun_in_flight，批量调用方按这个错误码跳过，而不是整批失败。
    """
    from tender.api.errors import ApiProblem

    company = settings.company_id()
    # 先读活动配置（可能走 Redis 缓存）再开事务：不在事务里等网络。
    active_config = configs.active(company)
    job_id = uuid4().hex
    # 两个 LATERAL 子查询：按版本挑唯一可解析文件、挑最新解析 run，都是 PostgreSQL 侧
    # 逐行取一的写法，用 lateral() 表达而不是拆成两次往返。
    pf = (
        select(ProjectFile.id.label("project_file_id"), ProjectFile.project_id)
        .join(Project, Project.id == ProjectFile.project_id)
        .where(
            ProjectFile.version_id == Extraction.version_id,
            ProjectFile.deleted_at.is_(None),
            ProjectFile.is_parseable.is_(True),
            Project.company_id == company,
            Project.deleted_at.is_(None),
        )
        .order_by(
            case((ProjectFile.role == "main", 0), else_=1), ProjectFile.sort_no, ProjectFile.id
        )
        .limit(1)
        .correlate(Extraction)
        .lateral("pf")
    )
    latest = (
        select(ParseRun.id.label("latest_run_id"))
        .where(ParseRun.version_id == Extraction.version_id)
        .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
        .limit(1)
        .correlate(Extraction)
        .lateral("latest")
    )
    with db.begin() as connection:
        row = (
            connection.execute(
                select(
                    Extraction.id,
                    Extraction.instance_id,
                    Extraction.version_id,
                    Extraction.run_id,
                    Extraction.field_key,
                    Extraction.is_current,
                    FieldInstance.lot_id,
                    DocumentVersion.page_count,
                    pf.c.project_id,
                    pf.c.project_file_id,
                    ParseRun.status.label("parse_status"),
                    latest.c.latest_run_id,
                )
                .select_from(Extraction)
                .join(FieldInstance, FieldInstance.id == Extraction.instance_id)
                .join(DocumentVersion, DocumentVersion.id == Extraction.version_id)
                .join(Document, Document.id == DocumentVersion.document_id)
                .join(ParseRun, ParseRun.id == Extraction.run_id)
                .join(pf, true())
                .outerjoin(latest, true())
                .where(
                    Extraction.id == extraction_id,
                    Document.company_id == company,
                    Document.deleted_at.is_(None),
                )
                .with_for_update(of=Extraction)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ApiProblem(404, "not_found", "抽取结果不存在")
        if not row["is_current"]:
            raise ApiProblem(409, "attempt_not_current", "只能重跑当前字段结果")
        if row["run_id"] != row["latest_run_id"] or row["parse_status"] not in {
            "completed",
            "partial",
        }:
            raise ApiProblem(409, "anchor_not_found", "解析 run 已变化，请从当前版本重新抽取")
        acquire_xact_lock(connection, f"rerun:{row['instance_id']}")
        active = connection.execute(
            select(Job.id)
            .where(
                Job.status.in_(("pending", "submitting", "running")),
                Job.config_snapshot["instance_id"].as_string() == str(row["instance_id"]),
            )
            .limit(1)
        ).scalar_one_or_none()
        if active is not None:
            raise ApiProblem(409, "rerun_in_flight", "该字段已有重跑任务进行中", retryable=True)
        next_attempt = int(
            connection.execute(
                select(func.coalesce(func.max(Extraction.machine_attempt_no), 0) + 1).where(
                    Extraction.instance_id == row["instance_id"],
                    Extraction.run_id == row["run_id"],
                )
            ).scalar_one()
        )
        trigger = "hinted_rerun" if hint else "user_rerun"
        snapshot = {
            "mode": "rerun",
            "trigger": trigger,
            "actor": actor,
            "hint": hint,
            "field_keys": [row["field_key"]],
            "instance_id": int(row["instance_id"]),
        }
        snapshot_id = configs.snapshot_for_job(connection, active_config)
        connection.execute(
            insert(Job).values(
                id=job_id,
                company_id=company,
                project_id=row["project_id"],
                project_file_id=row["project_file_id"],
                version_id=row["version_id"],
                run_id=row["run_id"],
                status="pending",
                stage="extracting",
                progress={"stage": "extracting", "fields_total": 1, "fields_done": 0},
                config_snapshot=snapshot,
                config_snapshot_id=snapshot_id,
            )
        )
    # 这里不再直接投递：beat 按 extract.max_inflight 差额派发（worker/dispatch.py）。
    return {
        "job_id": job_id,
        "instance_id": int(row["instance_id"]),
        "field_key": row["field_key"],
        "next_machine_attempt_no": next_attempt,
    }
