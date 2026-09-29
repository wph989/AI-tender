"""异步项目导出 worker；大型结果集写入对象存储并通过 job 下载。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text

from tender.adapters.s3 import S3BlobStore
from tender.application.exporting import workbook_bytes
from tender.core import settings
from tender.ports.blob_store import BlobStoreError
from tender.worker.celery_app import celery_app

_engine = create_engine(settings.database_url(), pool_pre_ping=True)
_TERMINAL = frozenset({"completed", "partial", "failed", "canceled"})


@contextmanager
def _advisory_lock(job_id: str) -> Iterator[bool]:
    with _engine.connect() as connection:
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(hashtextextended(:key, 0))"),
                {"key": f"job:{job_id}"},
            ).scalar_one()
        )
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:key, 0))"),
                    {"key": f"job:{job_id}"},
                )
                connection.commit()


def _load_job(job_id: str) -> dict[str, Any] | None:
    with _engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT j.*, p.name AS project_name, p.deleted_at AS project_deleted_at
                       FROM job AS j JOIN project AS p ON p.id = j.project_id
                       WHERE j.id = :id"""
                ),
                {"id": job_id},
            )
            .mappings()
            .first()
        )
    return dict(row) if row is not None else None


def _export_rows(job: dict[str, Any]) -> list[dict[str, object]]:
    snapshot = job.get("config_snapshot") if isinstance(job.get("config_snapshot"), dict) else {}
    include = snapshot.get("include", "all")
    lot_id = snapshot.get("lot_id")
    clauses = [
        "file.project_id = :project_id",
        "file.deleted_at IS NULL",
        "effective.is_current = true",
    ]
    params: dict[str, object] = {
        "project_id": job["project_id"],
        "company_id": settings.company_id(),
    }
    if isinstance(lot_id, int):
        clauses.append("effective.lot_id = :lot_id")
        params["lot_id"] = lot_id
    if include == "review":
        clauses.append("effective.status IN ('need_review','conflict','not_found')")
    elif include == "verified":
        clauses.append("effective.status = 'verified'")
    with _engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    f"""WITH effective AS (
                            SELECT e.*, fi.lot_id, l.code AS lot_code,
                                   CASE
                                       WHEN EXISTS (
                                           SELECT 1 FROM extraction_conflict AS ec
                                           WHERE ec.project_id = :project_id
                                             AND ec.status = 'open'
                                             AND ec.field_key = e.field_key
                                             AND ec.lot_id IS NOT DISTINCT FROM fi.lot_id
                                             AND e.id = ANY(ec.candidate_ids)
                                       ) THEN 'conflict'
                                       WHEN ra.action = 'confirm' THEN 'verified'
                                       WHEN ra.action = 'reject' THEN 'rejected'
                                       ELSE e.status
                                   END AS status
                            FROM extraction AS e
                            JOIN field_instance AS fi ON fi.id = e.instance_id
                            LEFT JOIN lot AS l ON l.id = fi.lot_id
                            LEFT JOIN LATERAL (
                                SELECT action FROM review_action
                                WHERE attempt_id = e.id
                                ORDER BY created_at DESC, id DESC LIMIT 1
                            ) AS ra ON true
                        )
                        SELECT effective.field_key, effective.group_key, effective.value_text,
                               effective.lot_code, effective.confidence, effective.status,
                               effective.machine_attempt_no,
                               file.display_name, ev.page_no, ev.quote, review.comment
                        FROM effective
                        JOIN document_version AS v ON v.id = effective.version_id
                        JOIN document AS d ON d.id = v.document_id
                        JOIN LATERAL (
                            SELECT pf.project_id, pf.display_name, pf.deleted_at
                            FROM project_file AS pf
                            WHERE pf.version_id = v.id AND pf.project_id = :project_id
                              AND NOT EXISTS (
                                  SELECT 1 FROM project_file AS replacement
                                  WHERE replacement.replaces_id = pf.id
                                    AND replacement.deleted_at IS NULL
                              )
                            ORDER BY CASE pf.role WHEN 'main' THEN 0 ELSE 1 END,
                                     pf.sort_no, pf.id LIMIT 1
                        ) AS file ON true
                        LEFT JOIN evidence AS ev ON ev.extraction_id = effective.id
                        LEFT JOIN LATERAL (
                            SELECT comment FROM review_action
                            WHERE instance_id = effective.instance_id
                              AND action IN ('correct','supplement')
                            ORDER BY created_at DESC, id DESC LIMIT 1
                        ) AS review ON true
                        WHERE d.company_id = :company_id AND d.deleted_at IS NULL
                          AND {" AND ".join(clauses)}
                        ORDER BY effective.group_key, effective.field_key, effective.id, ev.seq"""
                ),
                params,
            )
            .mappings()
            .all()
        )
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
        connection.execute(
            text(
                """UPDATE job SET status = :status, stage = 'exporting',
                       progress = COALESCE(CAST(:progress AS JSONB), progress),
                       error_code = :error_code, error_message = :error_message,
                       updated_at = :now,
                       finished_at = CASE WHEN :terminal THEN :now ELSE NULL END
                   WHERE id = :id
                     AND (status <> 'canceled' OR :status = 'canceled')"""
            ),
            {
                "id": job_id,
                "status": status,
                "progress": json.dumps(progress, ensure_ascii=False)
                if progress is not None
                else None,
                "error_code": error_code,
                "error_message": error_message[:2000] if error_message else None,
                "now": datetime.now(UTC),
                "terminal": status in _TERMINAL,
            },
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
