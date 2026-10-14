"""异步项目导出 worker；大型结果集写入对象存储并通过 job 下载。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import any_, case, func, literal, select, true, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased

from tender.adapters.pg.locks import release_lock, try_acquire_lock
from tender.adapters.pg.models import (
    Document,
    DocumentVersion,
    Evidence,
    Extraction,
    ExtractionConflict,
    FieldInstance,
    Job,
    Lot,
    Project,
    ProjectFile,
    ReviewAction,
)
from tender.adapters.pg.session import create_pg_engine
from tender.adapters.s3 import S3BlobStore
from tender.application.exporting import workbook_bytes
from tender.core import settings
from tender.ports.blob_store import BlobStoreError
from tender.worker.celery_app import celery_app

_engine = create_pg_engine()
_TERMINAL = frozenset({"completed", "partial", "failed", "canceled"})


@contextmanager
def _advisory_lock(job_id: str) -> Iterator[bool]:
    with _engine.connect() as connection:
        acquired = try_acquire_lock(connection, f"job:{job_id}")
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                release_lock(connection, f"job:{job_id}")
                connection.commit()


def _load_job(job_id: str) -> dict[str, Any] | None:
    with _engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    Job,
                    Project.name.label("project_name"),
                    Project.deleted_at.label("project_deleted_at"),
                )
                .join(Project, Project.id == Job.project_id)
                .where(Job.id == job_id)
            )
            .mappings()
            .first()
        )
    return dict(row) if row is not None else None


def _effective_cte(project_id: int) -> Any:
    """交叉文件的「有效取值」口径：冲突优先，其次人工动作，最后回落到机器状态。

    与同步导出共用同一段 CASE，两侧不能各写一套。
    """
    latest_action = (
        select(ReviewAction.action)
        .where(ReviewAction.attempt_id == Extraction.id)
        .order_by(ReviewAction.created_at.desc(), ReviewAction.id.desc())
        .limit(1)
        .correlate(Extraction)
        .lateral("ra")
    )
    conflict = (
        select(ExtractionConflict.id)
        .where(
            ExtractionConflict.project_id == project_id,
            ExtractionConflict.status == "open",
            ExtractionConflict.field_key == Extraction.field_key,
            ExtractionConflict.lot_id.is_not_distinct_from(FieldInstance.lot_id),
            Extraction.id == any_(ExtractionConflict.candidate_ids),
        )
        .exists()
    )
    effective_status = case(
        (conflict, "conflict"),
        (latest_action.c.action == "confirm", "verified"),
        (latest_action.c.action == "reject", "rejected"),
        else_=Extraction.status,
    ).label("effective_status")
    # fi.lot_id 必须换名：e.* 自带同名 lot_id，
    # 同名列会让后续 effective.lot_id 报「column reference is ambiguous」。
    return (
        select(
            Extraction,
            FieldInstance.lot_id.label("fi_lot_id"),
            Lot.code.label("lot_code"),
            effective_status,
        )
        .join(FieldInstance, FieldInstance.id == Extraction.instance_id)
        .outerjoin(Lot, Lot.id == FieldInstance.lot_id)
        .outerjoin(latest_action, true())
        .cte("effective")
    )


def _export_query(job: dict[str, Any]) -> Any:
    snapshot = job.get("config_snapshot") if isinstance(job.get("config_snapshot"), dict) else {}
    include = snapshot.get("include", "all")
    lot_id = snapshot.get("lot_id")
    project_id = job["project_id"]
    effective = _effective_cte(project_id)

    # 引用未删除替身的那一版文件：同一 version 可能挂在多个 project_file 下。
    replacement = aliased(ProjectFile)
    current_file = (
        select(ProjectFile.project_id, ProjectFile.display_name, ProjectFile.deleted_at)
        .where(
            ProjectFile.version_id == DocumentVersion.id,
            ProjectFile.project_id == project_id,
            ~select(replacement.id)
            .where(replacement.replaces_id == ProjectFile.id, replacement.deleted_at.is_(None))
            .exists(),
        )
        .order_by(
            case((ProjectFile.role == "main", 0), else_=1), ProjectFile.sort_no, ProjectFile.id
        )
        .limit(1)
        .correlate(DocumentVersion)
        .lateral("file")
    )
    latest_review = (
        select(ReviewAction.comment)
        .where(
            ReviewAction.instance_id == effective.c.instance_id,
            ReviewAction.action.in_(("correct", "supplement")),
        )
        .order_by(ReviewAction.created_at.desc(), ReviewAction.id.desc())
        .limit(1)
        .correlate(effective)
        .lateral("review")
    )

    conditions = [
        current_file.c.project_id == project_id,
        current_file.c.deleted_at.is_(None),
        effective.c.is_current.is_(True),
    ]
    if isinstance(lot_id, int):
        conditions.append(effective.c.fi_lot_id == lot_id)
    if include == "review":
        conditions.append(
            effective.c.effective_status.in_(("need_review", "conflict", "not_found"))
        )
    elif include == "verified":
        conditions.append(effective.c.effective_status == "verified")

    return (
        select(
            effective.c.field_key,
            effective.c.group_key,
            effective.c.value_text,
            effective.c.lot_code,
            effective.c.confidence,
            effective.c.effective_status.label("status"),
            effective.c.machine_attempt_no,
            current_file.c.display_name,
            Evidence.page_no,
            Evidence.quote,
            latest_review.c.comment,
        )
        .select_from(effective)
        .join(DocumentVersion, DocumentVersion.id == effective.c.version_id)
        .join(Document, Document.id == DocumentVersion.document_id)
        .join(current_file, true())
        .outerjoin(Evidence, Evidence.extraction_id == effective.c.id)
        .outerjoin(latest_review, true())
        .where(
            Document.company_id == settings.company_id(),
            Document.deleted_at.is_(None),
            *conditions,
        )
        .order_by(effective.c.group_key, effective.c.field_key, effective.c.id, Evidence.seq)
    )


def _export_rows(job: dict[str, Any]) -> list[dict[str, object]]:
    with _engine.connect() as connection:
        rows = connection.execute(_export_query(job)).mappings().all()
    return [
        {
            "字段名": row["field_key"],
            "分组": row["group_key"],
            "值": row["value_text"],
            "适用范围": f"标段 {row['lot_code']}" if row["lot_code"] else "全文",
            "来源文件": row["display_name"],
            "页码": row["page_no"],
            "原文片段": row["quote"],
            "置信度": float(row["confidence"] or 0),
            # 人工修正产生的行没有机器序号，导出时写"人工"而不是留空。
            "尝试次数": row["machine_attempt_no"]
            if row["machine_attempt_no"] is not None
            else "人工",
            "复核状态": row["status"],
            "修正说明": row["comment"],
        }
        for row in rows
    ]


def _set_state(
    job_id: str,
    status: str,
    *,
    progress: dict[str, object] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    with _engine.begin() as connection:
        conditions = [Job.id == job_id]
        if status != "canceled":
            conditions.append(Job.status != "canceled")
        now = datetime.now(UTC)
        connection.execute(
            update(Job)
            .where(*conditions)
            .values(
                status=status,
                stage="exporting",
                # progress=None 表示不改动既有进度，保留 COALESCE 语义。
                progress=func.coalesce(
                    literal(progress, type_=JSONB)
                    if progress is not None
                    else literal(None, type_=JSONB),
                    Job.progress,
                ),
                error_code=error_code,
                error_message=error_message[:2000] if error_message else None,
                updated_at=now,
                finished_at=now if status in _TERMINAL else None,
            )
        )


@celery_app.task(bind=True, name="tender.worker.exports.export_project", max_retries=5)
def export_project(self: Any, job_id: str) -> None:
    with _advisory_lock(job_id) as acquired:
        if not acquired:
            raise self.retry(countdown=1)
        job = _load_job(job_id)
        if job is None or job["status"] in _TERMINAL:
            return
        if int(job["company_id"]) != settings.company_id() or job["project_deleted_at"] is not None:
            _set_state(job_id, "canceled", error_code="project_unavailable")
            return
        _set_state(job_id, "running", progress={"stage": "exporting", "percent": 20})
        store = S3BlobStore()
        try:
            rows = _export_rows(job)
            content = workbook_bytes(rows)
            key = f"exports/{job['project_id']}/{job_id}.xlsx"
            store.put(
                key,
                content,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            _set_state(
                job_id,
                "completed",
                progress={
                    "stage": "exporting",
                    "percent": 100,
                    "rows": len(rows),
                    "output_key": key,
                },
            )
        except BlobStoreError as exc:
            _set_state(job_id, "pending", error_code="storage_unavailable", error_message=str(exc))
            if self.request.retries >= self.max_retries:
                _set_state(
                    job_id, "failed", error_code="storage_unavailable", error_message=str(exc)
                )
                return
            raise self.retry(exc=exc, countdown=min(60, 2 ** (self.request.retries + 1))) from exc
        except Exception as exc:
            _set_state(job_id, "failed", error_code="export_failed", error_message=str(exc))
        finally:
            store.close()
