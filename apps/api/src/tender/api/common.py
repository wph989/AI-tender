"""路由共享的数据访问助手；所有资源读都带单租户 company_id 条件。"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import Engine, select
from sqlalchemy.engine import RowMapping

from tender.adapters.pg.models import (
    Document,
    DocumentVersion,
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
