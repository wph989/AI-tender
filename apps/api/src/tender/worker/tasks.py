"""解析 worker：单次提交与单次轮询分开，等待期间不占用 worker 槽。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from functools import wraps
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import create_engine, text

from tender.adapters.gotenberg import GotenbergConverter
from tender.adapters.mineru import MinerUParser
from tender.adapters.pdfium import InvalidPdfError, PdfInspection, inspect_pdf
from tender.adapters.s3 import S3BlobStore
from tender.application.middle_json import NormalizedElement, normalize_middle_json
from tender.core import settings
from tender.domain.errors import (
    ConversionFailed,
    ConversionUnavailable,
    ParseFailed,
    ParseSubmissionUnknown,
    ParseUnavailable,
    ServiceRestarted,
)
from tender.ports.blob_store import BlobNotFound, BlobStoreError
from tender.worker.celery_app import celery_app

_engine = create_engine(settings.database_url(), pool_pre_ping=True)


def _store() -> S3BlobStore:
    return S3BlobStore()


def _parser(store: S3BlobStore) -> MinerUParser:
    async def load_pdf(key: str) -> bytes:
        return await asyncio.to_thread(store.read, key)

    return MinerUParser(
        settings.mineru_url(),
        pdf_loader=load_pdf,
        api_key=settings.mineru_api_key(),
    )


def _job(job_id: str) -> Mapping[str, Any] | None:
    with _engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT j.*, v.pdf_key, v.pdf_sha256, v.page_count AS version_page_count,
                          pf.display_name, d.company_id AS document_company_id,
                          r.provider_job_id, r.provider_version, r.started_at
                   FROM job AS j
                   JOIN document_version AS v ON v.id = j.version_id
                   JOIN project_file AS pf ON pf.id = j.project_file_id
                   JOIN document AS d ON d.id = v.document_id
                   LEFT JOIN parse_run AS r ON r.id = j.run_id
                   WHERE j.id = :job_id"""
                ),
                {"job_id": job_id},
            )
            .mappings()
            .first()
        )
    return row


def _retry_delay(retries: int) -> int:
    return min(30, 2 ** min(max(retries, 1), 5))


@contextmanager
def _advisory_lock(lock_key: str, *, wait: bool) -> Iterator[bool]:
    """用数据库会话锁协调重复投递，进程退出后锁会自动释放。"""
    with _engine.connect() as connection:
        params = {"lock_key": lock_key}
        if wait:
            connection.execute(
                text("SELECT pg_advisory_lock(hashtextextended(:lock_key, 0))"),
                params,
            )
            acquired = True
        else:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(hashtextextended(:lock_key, 0))"),
                    params,
                ).scalar_one()
            )
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:lock_key, 0))"),
                    params,
                )
                connection.commit()


def _serialize_job(function: Callable[..., None]) -> Callable[..., None]:
    @wraps(function)
    def wrapped(task: Any, job_id: str) -> None:
        with _advisory_lock(f"job:{job_id}", wait=False) as acquired:
            if not acquired:
                raise task.retry(countdown=1)
            function(task, job_id)

    return wrapped


def _file_job(job_id: str) -> Mapping[str, Any] | None:
    with _engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT j.*, pf.original_key, pf.sha256 AS source_sha256,
                          pf.mime AS source_mime, pf.size_bytes AS source_size_bytes,
                          pf.display_name, pf.replaces_id, p.project_no,
                          p.company_id AS project_company_id
                   FROM job AS j
                   JOIN project_file AS pf ON pf.id = j.project_file_id
                   JOIN project AS p ON p.id = j.project_id
                   WHERE j.id = :job_id"""
                ),
                {"job_id": job_id},
            )
            .mappings()
            .first()
        )
    return row


def _version_candidate(
    company_id: int,
    source_sha256: str,
    converter_version: str | None,
) -> Mapping[str, Any] | None:
    with _engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT id, document_id, pdf_key, pdf_sha256, converter,
                          converter_version, is_converted, page_count
                   FROM document_version
                   WHERE company_id = :company_id AND sha256 = :sha256
                     AND converter_version IS NOT DISTINCT FROM :converter_version
                   ORDER BY id
                   LIMIT 1"""
                ),
                {
                    "company_id": company_id,
                    "sha256": source_sha256,
                    "converter_version": converter_version,
                },
            )
            .mappings()
            .first()
        )
    return dict(row) if row is not None else None


def _geometry_is_complete(version: Mapping[str, Any]) -> bool:
    page_count = version.get("page_count")
    if not isinstance(page_count, int) or page_count < 1:
        return False
    with _engine.connect() as connection:
        counts = (
            connection.execute(
                text(
                    """SELECT count(*) AS count, min(page_no) AS first_page,
                          max(page_no) AS last_page
                   FROM page WHERE version_id = :version_id"""
                ),
                {"version_id": version["id"]},
            )
            .mappings()
            .one()
        )
    return (
        int(counts["count"]) == page_count
        and counts["first_page"] == 1
        and counts["last_page"] == page_count
    )


def _verify_hash(content: bytes, expected: str, description: str) -> None:
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected.strip().lower():
        raise ValueError(f"{description}的 SHA-256 与数据库记录不一致")


def _converter() -> GotenbergConverter:
    try:
        credentials = settings.gotenberg_credentials()
    except ValueError as exc:
        raise ConversionFailed("Gotenberg 凭据配置无效") from exc
    return GotenbergConverter(
        settings.gotenberg_url(),
        username=credentials[0] if credentials else None,
        password=credentials[1] if credentials else None,
    )


def _finish_file_version(
    row: Mapping[str, Any],
    *,
    candidate: Mapping[str, Any] | None,
    pdf_key: str,
    pdf_sha256: str,
    converter: str | None,
    converter_version: str | None,
    is_converted: bool,
    inspection: PdfInspection | None,
) -> tuple[int, int, bool]:
    snapshot = row["config_snapshot"]
    auto_parse = isinstance(snapshot, dict) and bool(snapshot.get("auto_parse", True))
    with _engine.begin() as connection:
        if candidate is None:
            document_id = None
            replaces_id = row["replaces_id"]
            if replaces_id is not None:
                document_id = connection.execute(
                    text(
                        """SELECT dv.document_id
                           FROM project_file AS old
                           JOIN project AS p ON p.id = old.project_id
                           LEFT JOIN document_version AS dv ON dv.id = old.version_id
                           WHERE old.id = :file_id AND old.project_id = :project_id
                             AND p.company_id = :company_id"""
                    ),
                    {
                        "file_id": replaces_id,
                        "project_id": row["project_id"],
                        "company_id": row["project_company_id"],
                    },
                ).scalar_one_or_none()
            if document_id is None:
                document_id = connection.execute(
                    text(
                        """INSERT INTO document (company_id, title, project_no)
                           VALUES (:company_id, :title, :project_no)
                           RETURNING id"""
                    ),
                    {
                        "company_id": row["project_company_id"],
                        "title": row["display_name"],
                        "project_no": row["project_no"],
                    },
                ).scalar_one()
            else:
                connection.execute(
                    text("SELECT id FROM document WHERE id = :id FOR UPDATE"),
                    {"id": document_id},
                ).one()
            version_no = int(
                connection.execute(
                    text(
                        """SELECT COALESCE(MAX(version_no), 0) + 1
                           FROM document_version WHERE document_id = :document_id"""
                    ),
                    {"document_id": document_id},
                ).scalar_one()
            )
            version_id = int(
                connection.execute(
                    text(
                        """INSERT INTO document_version
                               (company_id, document_id, version_no, sha256, mime, size_bytes,
                                original_key, pdf_key, pdf_sha256, is_converted, converter,
                                converter_version, page_count)
                           VALUES
                               (:company_id, :document_id, :version_no, :sha256, :mime,
                                :size_bytes, :original_key, :pdf_key, :pdf_sha256,
                                :is_converted, :converter, :converter_version, :page_count)
                           RETURNING id"""
                    ),
                    {
                        "company_id": row["project_company_id"],
                        "document_id": document_id,
                        "version_no": version_no,
                        "sha256": str(row["source_sha256"]).strip(),
                        "mime": row["source_mime"],
                        "size_bytes": row["source_size_bytes"],
                        "original_key": row["original_key"],
                        "pdf_key": pdf_key,
                        "pdf_sha256": pdf_sha256,
                        "is_converted": is_converted,
                        "converter": converter,
                        "converter_version": converter_version,
                        "page_count": inspection.page_count if inspection else None,
                    },
                ).scalar_one()
            )
            page_count = inspection.page_count if inspection else 0
        else:
            version_id = int(candidate["id"])
            page_count = int(candidate["page_count"] or 0)

        if inspection is not None:
            page_count = inspection.page_count
            connection.execute(
                text(
                    """INSERT INTO page
                           (version_id, page_no, width_pt, height_pt, rotation, text_layer)
                       VALUES
                           (:version_id, :page_no, :width_pt, :height_pt,
                            :rotation, :text_layer)
                       ON CONFLICT (version_id, page_no) DO UPDATE SET
                           width_pt = EXCLUDED.width_pt,
                           height_pt = EXCLUDED.height_pt,
                           rotation = EXCLUDED.rotation,
                           text_layer = EXCLUDED.text_layer"""
                ),
                [
                    {
                        "version_id": version_id,
                        "page_no": page.page_no,
                        "width_pt": page.width_pt,
                        "height_pt": page.height_pt,
                        "rotation": page.rotation,
                        "text_layer": page.has_text_layer,
                    }
                    for page in inspection.pages
                ],
            )
            connection.execute(
                text("UPDATE document_version SET page_count = :page_count WHERE id = :id"),
                {"id": version_id, "page_count": page_count},
            )

        connection.execute(
            text("UPDATE project_file SET version_id = :version_id WHERE id = :file_id"),
            {"version_id": version_id, "file_id": row["project_file_id"]},
        )
        prior_parse = connection.execute(
            text(
                """SELECT EXISTS (
                       SELECT 1 FROM parse_run
                       WHERE version_id = :version_id
                         AND status IN ('pending','running','completed','partial')
                   )"""
            ),
            {"version_id": version_id},
        ).scalar_one()
        should_parse = auto_parse and not bool(prior_parse)
        status = "pending" if should_parse else "completed"
        stage = "submitting" if should_parse else "geometry"
        connection.execute(
            text(
                """UPDATE job
                   SET version_id = :version_id, status = :status, stage = :stage,
                       progress = CAST(:progress AS JSONB), error_code = NULL,
                       error_message = NULL, updated_at = now(),
                       finished_at = CASE WHEN :should_parse THEN NULL ELSE now() END
                   WHERE id = :job_id AND status <> 'canceled'"""
            ),
            {
                "job_id": row["id"],
                "version_id": version_id,
                "status": status,
                "stage": stage,
                "progress": json.dumps({"pages": page_count}),
                "should_parse": should_parse,
            },
        )
    return version_id, page_count, should_parse


async def _process_office_file(row: Mapping[str, Any], store: S3BlobStore) -> tuple[int, int, bool]:
    source_sha256 = str(row["source_sha256"]).strip().lower()
    converter_adapter = _converter()
    try:
        converter_version = await converter_adapter.version()
        lock_key = f"version:{row['project_company_id']}:{source_sha256}:{converter_version}"
        with _advisory_lock(lock_key, wait=True):
            candidate = _version_candidate(
                int(row["project_company_id"]), source_sha256, converter_version
            )
            if candidate is not None:
                inspection = None
                if not _geometry_is_complete(candidate):
                    pdf_bytes = await asyncio.to_thread(store.read, str(candidate["pdf_key"]))
                    _verify_hash(pdf_bytes, str(candidate["pdf_sha256"]), "已存 PDF")
                    inspection = inspect_pdf(pdf_bytes)
                return _finish_file_version(
                    row,
                    candidate=candidate,
                    pdf_key=str(candidate["pdf_key"]),
                    pdf_sha256=str(candidate["pdf_sha256"]).strip(),
                    converter=(str(candidate["converter"]) if candidate["converter"] else None),
                    converter_version=converter_version,
                    is_converted=bool(candidate["is_converted"]),
                    inspection=inspection,
                )

            original = await asyncio.to_thread(store.read, str(row["original_key"]))
            _verify_hash(original, source_sha256, "原件")
            result = await converter_adapter.to_pdf(
                BytesIO(original),
                filename=str(row["display_name"]),
                trace_id=str(row["id"]),
            )
            if result.converter_version != converter_version:
                raise ConversionUnavailable("Gotenberg 转换期间版本发生变化，请重试")
            inspection = inspect_pdf(result.pdf_bytes)
            pdf_sha256 = hashlib.sha256(result.pdf_bytes).hexdigest()
            pdf_key = f"converted/{source_sha256}/{pdf_sha256}.pdf"
            await asyncio.to_thread(
                store.put,
                pdf_key,
                result.pdf_bytes,
                content_type="application/pdf",
            )
            return _finish_file_version(
                row,
                candidate=None,
                pdf_key=pdf_key,
                pdf_sha256=pdf_sha256,
                converter=result.converter,
                converter_version=result.converter_version,
                is_converted=True,
                inspection=inspection,
            )
    finally:
        await converter_adapter.aclose()


def _process_pdf_file(row: Mapping[str, Any], store: S3BlobStore) -> tuple[int, int, bool]:
    source_sha256 = str(row["source_sha256"]).strip().lower()
    lock_key = f"version:{row['project_company_id']}:{source_sha256}:pdf"
    with _advisory_lock(lock_key, wait=True):
        candidate = _version_candidate(int(row["project_company_id"]), source_sha256, None)
        if candidate is not None:
            inspection = None
            if not _geometry_is_complete(candidate):
                pdf_bytes = store.read(str(candidate["pdf_key"]))
                _verify_hash(pdf_bytes, str(candidate["pdf_sha256"]), "已存 PDF")
                inspection = inspect_pdf(pdf_bytes)
            return _finish_file_version(
                row,
                candidate=candidate,
                pdf_key=str(candidate["pdf_key"]),
                pdf_sha256=str(candidate["pdf_sha256"]).strip(),
                converter=None,
                converter_version=None,
                is_converted=False,
                inspection=inspection,
            )

        pdf_bytes = store.read(str(row["original_key"]))
        _verify_hash(pdf_bytes, source_sha256, "PDF 原件")
        inspection = inspect_pdf(pdf_bytes)
        return _finish_file_version(
            row,
            candidate=None,
            pdf_key=str(row["original_key"]),
            pdf_sha256=source_sha256,
            converter=None,
            converter_version=None,
            is_converted=False,
            inspection=inspection,
        )


@celery_app.task(bind=True, name="tender.worker.tasks.process_file", max_retries=None)
@_serialize_job
def process_file(self: Any, job_id: str) -> None:
    row = _file_job(job_id)
    if row is None:
        return
    status = str(row["status"])
    stage = str(row["stage"])
    if status == "pending" and stage == "submitting":
        # 转换已完成、等解析派发：这里不再自己投递，beat 按 parse.max_inflight 差额派发。
        return
    if status not in {"pending", "running"}:
        return
    if status == "running" and stage not in {"converting", "probing", "geometry"}:
        return
    with _engine.begin() as connection:
        changed = connection.execute(
            text(
                """UPDATE job SET status = 'running', updated_at = now()
                   WHERE id = :job_id AND status IN ('pending','running')
                     AND stage IN ('converting','probing','geometry')"""
            ),
            {"job_id": job_id},
        ).rowcount
    if not changed:
        return

    extension = PurePosixPath(str(row["display_name"]).lower()).suffix
    store = _store()
    try:
        try:
            if extension == ".pdf":
                _, _, should_parse = _process_pdf_file(row, store)
            else:
                _, _, should_parse = asyncio.run(_process_office_file(row, store))
        except ConversionUnavailable as exc:
            _reset_file_job(job_id, stage, exc.code, str(exc))
            raise self.retry(exc=exc, countdown=_retry_delay(self.request.retries)) from exc
        except BlobStoreError as exc:
            _reset_file_job(job_id, stage, "storage_unavailable", str(exc))
            raise self.retry(exc=exc, countdown=_retry_delay(self.request.retries)) from exc
        except ConversionFailed as exc:
            _set_job_failure(job_id, exc.code, str(exc))
            return
        except InvalidPdfError as exc:
            _set_job_failure(job_id, "invalid_pdf", str(exc))
            return
        except BlobNotFound as exc:
            _set_job_failure(job_id, "storage_object_missing", str(exc))
            return
        except ValueError as exc:
            _set_job_failure(job_id, "content_hash_mismatch", str(exc))
            return
        except Exception as exc:
            _set_job_failure(job_id, "preprocessing_failed", str(exc))
            return
    finally:
        store.close()

    # should_parse 时 _finish_file_version 已把 job 置为 pending/submitting；
    # 派发交给 beat（worker/dispatch.py），这里再投一次会和闸门抢方向。


def _reset_file_job(job_id: str, stage: str, code: str, message: str) -> None:
    with _engine.begin() as connection:
        connection.execute(
            text(
                """UPDATE job
                   SET status = 'pending', stage = :stage, error_code = :code,
                       error_message = :message, updated_at = now(), finished_at = NULL
                   WHERE id = :job_id AND status = 'running'"""
            ),
            {"job_id": job_id, "stage": stage, "code": code, "message": message[:2000]},
        )


def _set_job_failure(job_id: str, code: str, message: str) -> None:
    now = datetime.now(UTC)
    with _engine.begin() as connection:
        row = (
            connection.execute(
                text("SELECT run_id FROM job WHERE id = :job_id FOR UPDATE"),
                {"job_id": job_id},
            )
            .mappings()
            .first()
        )
        if row is None:
            return
        connection.execute(
            text(
                """UPDATE job
                   SET status = 'failed', error_code = :code, error_message = :message,
                       updated_at = :now, finished_at = :now
                   WHERE id = :job_id AND status <> 'canceled'"""
            ),
            {"job_id": job_id, "code": code, "message": message[:2000], "now": now},
        )
        if row["run_id"] is not None:
            connection.execute(
                text(
                    """UPDATE parse_run
                       SET status = 'failed', error_code = :code, error_message = :message,
                           finished_at = :now
                       WHERE id = :run_id"""
                ),
                {
                    "run_id": row["run_id"],
                    "code": code,
                    "message": message[:2000],
                    "now": now,
                },
            )


def _mark_submission_unknown(job_id: str, message: str) -> None:
    _set_job_failure(job_id, "parse_submission_unknown", message)


async def _submit(row: Mapping[str, Any], store: S3BlobStore) -> Any:
    parser = _parser(store)
    try:
        return await parser.submit(
            str(row["pdf_key"]),
            pdf_sha256=str(row["pdf_sha256"]).strip(),
            tier=str(row["config_snapshot"].get("tier", "standard")),
            ocr_mode=str(row["config_snapshot"].get("ocr_mode", "auto")),
        )
    finally:
        await parser.aclose()


@celery_app.task(bind=True, name="tender.worker.tasks.submit_parse", max_retries=None)
@_serialize_job
def submit_parse(self: Any, job_id: str) -> None:
    row = _job(job_id)
    if row is None:
        return
    status = str(row["status"])
    if status == "submitting":
        # 上次进程可能在 MinerU 已受理后、provider_job_id 落库前退出，重放会产生重复任务。
        _mark_submission_unknown(
            job_id,
            "MinerU 提交结果未知；需人工核对服务端状态后再决定是否重跑",
        )
        return
    if status != "pending":
        return

    with _engine.begin() as connection:
        claimed = connection.execute(
            text(
                """UPDATE job
                   SET status = 'submitting', stage = 'submitting', updated_at = now()
                   WHERE id = :job_id AND status = 'pending'"""
            ),
            {"job_id": job_id},
        ).rowcount
    if not claimed:
        return

    store = _store()
    try:
        submission = asyncio.run(_submit(row, store))
    except ParseSubmissionUnknown as exc:
        _mark_submission_unknown(job_id, str(exc))
        return
    except ParseUnavailable as exc:
        with _engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE job
                       SET status = 'pending', stage = 'submitting',
                           error_code = :code, error_message = :message, updated_at = now()
                       WHERE id = :job_id AND status = 'submitting'"""
                ),
                {
                    "job_id": job_id,
                    "code": exc.code,
                    "message": str(exc)[:2000],
                },
            )
        raise self.retry(exc=exc, countdown=_retry_delay(self.request.retries)) from exc
    except ParseFailed as exc:
        _set_job_failure(job_id, exc.code, str(exc))
        return
    except BlobStoreError as exc:
        with _engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE job
                       SET status = 'pending', stage = 'submitting',
                           error_code = 'storage_unavailable', error_message = :message,
                           updated_at = now()
                       WHERE id = :job_id AND status = 'submitting'"""
                ),
                {"job_id": job_id, "message": str(exc)[:2000]},
            )
        raise self.retry(exc=exc, countdown=_retry_delay(self.request.retries)) from exc
    now = datetime.now(UTC)
    snapshot = asdict(submission.config_snapshot)
    try:
        with _engine.begin() as connection:
            run_id = connection.execute(
                text(
                    """INSERT INTO parse_run
                           (version_id, provider, provider_version, tier, schema_version,
                            status, request_id, provider_job_id, config_snapshot, started_at)
                       VALUES
                           (:version_id, 'mineru', :provider_version, :tier, '2.0',
                            'running', :request_id, :provider_job_id,
                            CAST(:config_snapshot AS JSONB), :now)
                       RETURNING id"""
                ),
                {
                    "version_id": row["version_id"],
                    "provider_version": submission.provider_version,
                    "tier": snapshot["tier"],
                    "request_id": job_id,
                    "provider_job_id": submission.job_id,
                    "config_snapshot": json.dumps(snapshot),
                    "now": now,
                },
            ).scalar_one()
            connection.execute(
                text(
                    """UPDATE job
                       SET run_id = :run_id, status = 'running', stage = 'parsing',
                           progress = CAST(:progress AS JSONB), error_code = NULL,
                           error_message = NULL, updated_at = :now
                       WHERE id = :job_id AND status = 'submitting'"""
                ),
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "progress": json.dumps({}),
                    "now": now,
                },
            )
    except Exception as exc:
        # 远端已受理但本地未能保存引用时，不能再次提交同一内容来掩盖不一致。
        _mark_submission_unknown(job_id, f"MinerU 已提交但任务记录写入失败：{exc}")
        return

    poll_parse.apply_async(args=(job_id,), countdown=2)


async def _poll(row: Mapping[str, Any], store: S3BlobStore) -> tuple[Any, Any | None]:
    parser = _parser(store)
    try:
        status = await parser.poll(str(row["provider_job_id"]))
        middle_json = None
        if status.status in {"completed", "partial"} and status.has_middle_json:
            middle_json = await parser.fetch_middle_json(str(row["provider_job_id"]))
        return status, middle_json
    finally:
        await parser.aclose()


@celery_app.task(bind=True, name="tender.worker.tasks.poll_parse", max_retries=None)
@_serialize_job
def poll_parse(self: Any, job_id: str) -> None:
    row = _job(job_id)
    if row is None or row["status"] != "running" or row["run_id"] is None:
        return
    if row["stage"] == "resubmitting":
        _mark_submission_unknown(
            job_id,
            "MinerU 重启后的重新提交结果未知；需人工核对服务端状态后再决定是否重跑",
        )
        return

    store = _store()
    try:
        status, middle_json = asyncio.run(_poll(row, store))
    except ServiceRestarted:
        with _engine.begin() as connection:
            claimed = connection.execute(
                text(
                    """UPDATE job SET stage = 'resubmitting', updated_at = now()
                       WHERE id = :job_id AND status = 'running' AND stage = 'parsing'"""
                ),
                {"job_id": job_id},
            ).rowcount
        if not claimed:
            return
        try:
            submission = asyncio.run(_submit(row, store))
        except ParseSubmissionUnknown as unknown:
            _mark_submission_unknown(job_id, str(unknown))
            return
        except ParseFailed as failed:
            _set_job_failure(job_id, failed.code, str(failed))
            return
        except (ParseUnavailable, BlobStoreError) as retryable:
            with _engine.begin() as connection:
                connection.execute(
                    text(
                        """UPDATE job SET stage = 'parsing', updated_at = now()
                           WHERE id = :job_id AND status = 'running'"""
                    ),
                    {"job_id": job_id},
                )
            raise self.retry(
                exc=retryable,
                countdown=_retry_delay(self.request.retries),
            ) from retryable

        if submission.provider_version != row["provider_version"]:
            _set_job_failure(
                job_id,
                "provider_version_changed",
                "MinerU 重启后版本发生变化；为保留可复现快照，本次任务已停止",
            )
            return
        with _engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE parse_run SET provider_job_id = :provider_job_id
                       WHERE id = :run_id"""
                ),
                {"run_id": row["run_id"], "provider_job_id": submission.job_id},
            )
            connection.execute(
                text(
                    """UPDATE job SET stage = 'parsing', updated_at = now()
                       WHERE id = :job_id AND status = 'running'"""
                ),
                {"job_id": job_id},
            )
        poll_parse.apply_async(args=(job_id,), countdown=2)
        return
    except ParseUnavailable as exc:
        raise self.retry(exc=exc, countdown=_retry_delay(self.request.retries)) from exc
    except ParseFailed as exc:
        _set_job_failure(job_id, exc.code, str(exc))
        return
    except BlobStoreError as exc:
        raise self.retry(exc=exc, countdown=_retry_delay(self.request.retries)) from exc

    now = datetime.now(UTC)
    progress = asdict(status.progress) if status.progress is not None else {}
    if status.status in {"queued", "running"}:
        with _engine.begin() as connection:
            connection.execute(
                text(
                    """UPDATE job
                       SET progress = CAST(:progress AS JSONB), updated_at = :now
                       WHERE id = :job_id"""
                ),
                {"job_id": job_id, "progress": json.dumps(progress), "now": now},
            )
        poll_parse.apply_async(args=(job_id,), countdown=_retry_delay(self.request.retries))
        return

    terminal_status = status.status
    raw_middle_key = None
    page_count = None
    backend = None
    schema_version = None
    normalized_elements: list[NormalizedElement] = []
    if middle_json is not None:
        raw_middle_key = f"mineru/{row['version_id']}/{row['run_id']}/middle.json"
        try:
            store.put(raw_middle_key, middle_json.raw_bytes, content_type="application/json")
        except BlobStoreError as exc:
            raise self.retry(exc=exc, countdown=_retry_delay(self.request.retries)) from exc
        page_values = middle_json.payload.get("pages")
        page_count = len(page_values) if isinstance(page_values, list) else None
        backend = middle_json.backend
        schema_version = middle_json.schema_version
        with _engine.connect() as connection:
            page_rows = (
                connection.execute(
                    text(
                        """SELECT page_no, rotation, text_layer FROM page
                           WHERE version_id = :version_id ORDER BY page_no"""
                    ),
                    {"version_id": row["version_id"]},
                )
                .mappings()
                .all()
            )
        page_rotations = {int(item["page_no"]): int(item["rotation"]) for item in page_rows}
        page_text_layers = {int(item["page_no"]): bool(item["text_layer"]) for item in page_rows}
        snapshot = row["config_snapshot"]
        try:
            normalized_elements = normalize_middle_json(
                middle_json.payload,
                expected_page_count=int(row["version_page_count"] or 0),
                page_rotations=page_rotations,
                page_has_text_layer=page_text_layers,
                bbox_origin=settings.mineru_bbox_origin(),
                bbox_rotation=settings.mineru_bbox_rotation(),
                require_all_pages=terminal_status == "completed",
                force_ocr=isinstance(snapshot, dict) and snapshot.get("ocr_mode") == "ocr",
            )
        except (ParseFailed, ValueError) as exc:
            with _engine.begin() as connection:
                connection.execute(
                    text(
                        """UPDATE parse_run
                           SET raw_middle_key = :raw_middle_key, page_count = :page_count,
                               backend = :backend, schema_version = :schema_version
                           WHERE id = :run_id"""
                    ),
                    {
                        "run_id": row["run_id"],
                        "raw_middle_key": raw_middle_key,
                        "page_count": page_count,
                        "backend": backend,
                        "schema_version": schema_version,
                    },
                )
            code = exc.code if isinstance(exc, ParseFailed) else "invalid_configuration"
            _set_job_failure(job_id, code, str(exc))
            return
    elapsed_ms = None
    started_at = row.get("started_at")
    if isinstance(started_at, datetime):
        elapsed_ms = max(0, int((now - started_at).total_seconds() * 1000))
    error_code = status.error_code
    error_message = status.error_message
    if terminal_status == "partial" and middle_json is None:
        error_code = error_code or "parse_incomplete"
        error_message = error_message or "MinerU 返回 partial，但没有可用的 MiddleJson"

    with _engine.begin() as connection:
        if normalized_elements:
            connection.execute(
                text(
                    """INSERT INTO element
                           (version_id, run_id, page_no, order_no, anchor, type, level,
                            bbox_x0, bbox_y0, bbox_x1, bbox_y1, text, html, source,
                            continues_prev, mineru_locator)
                       VALUES
                           (:version_id, :run_id, :page_no, :order_no, :anchor, :type, :level,
                            :bbox_x0, :bbox_y0, :bbox_x1, :bbox_y1, :text, :html, :source,
                            :continues_prev, :mineru_locator)"""
                ),
                [
                    {
                        "version_id": row["version_id"],
                        "run_id": row["run_id"],
                        "page_no": element.page_no,
                        "order_no": element.order_no,
                        "anchor": element.anchor,
                        "type": element.element_type,
                        "level": element.level,
                        "bbox_x0": element.bbox.x0 if element.bbox else None,
                        "bbox_y0": element.bbox.y0 if element.bbox else None,
                        "bbox_x1": element.bbox.x1 if element.bbox else None,
                        "bbox_y1": element.bbox.y1 if element.bbox else None,
                        "text": element.text,
                        "html": element.html,
                        "source": element.source,
                        "continues_prev": element.continues_prev,
                        "mineru_locator": element.mineru_locator,
                    }
                    for element in normalized_elements
                ],
            )
            inserted_rows = (
                connection.execute(
                    text(
                        """SELECT id, page_no, order_no FROM element
                           WHERE run_id = :run_id"""
                    ),
                    {"run_id": row["run_id"]},
                )
                .mappings()
                .all()
            )
            element_ids = {
                (int(item["page_no"]), int(item["order_no"])): int(item["id"])
                for item in inserted_rows
            }
            parent_updates = []
            for index, element in enumerate(normalized_elements):
                if element.parent_index is None:
                    continue
                if not 0 <= element.parent_index < index:
                    raise ParseFailed(f"元素父节点顺序非法：{element.anchor}")
                parent = normalized_elements[element.parent_index]
                parent_updates.append(
                    {
                        "id": element_ids[(element.page_no, element.order_no)],
                        "parent_id": element_ids[(parent.page_no, parent.order_no)],
                    }
                )
            if parent_updates:
                connection.execute(
                    text("UPDATE element SET parent_id = :parent_id WHERE id = :id"),
                    parent_updates,
                )
        connection.execute(
            text(
                """UPDATE parse_run
                   SET status = :status, raw_middle_key = :raw_middle_key,
                       page_count = :page_count, backend = :backend,
                       schema_version = COALESCE(:schema_version, schema_version),
                       elapsed_ms = :elapsed_ms, error_code = :error_code,
                       error_message = :error_message, finished_at = :now
                   WHERE id = :run_id"""
            ),
            {
                "run_id": row["run_id"],
                "status": terminal_status,
                "raw_middle_key": raw_middle_key,
                "page_count": page_count,
                "backend": backend,
                "schema_version": schema_version,
                "elapsed_ms": elapsed_ms,
                "error_code": error_code,
                "error_message": error_message,
                "now": now,
            },
        )
        updated_rows = connection.execute(
            text(
                """UPDATE job
                   SET status = :status, stage = 'parsing',
                       progress = CAST(:progress AS JSONB), error_code = :error_code,
                       error_message = :error_message, updated_at = :now, finished_at = :now
                   WHERE id = :job_id AND status <> 'canceled'"""
            ),
            {
                "job_id": job_id,
                "status": terminal_status,
                "progress": json.dumps(progress),
                "error_code": error_code,
                "error_message": error_message,
                "now": now,
            },
        )
        updated_count = updated_rows.rowcount

    # 任务被取消时上面的更新不生效，不能因为解析结果已经存在就接着排抽取。
    if terminal_status in {"completed", "partial"} and normalized_elements and updated_count:
        # 解析 job 与抽取 job 分开保存，避免解析终态被模型重试覆盖。
        from tender.worker.extraction import create_extraction_job

        create_extraction_job(
            int(row["project_id"]),
            int(row["project_file_id"]),
            int(row["version_id"]),
            int(row["run_id"]),
        )
