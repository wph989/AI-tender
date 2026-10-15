"""解析 worker：单次提交与单次轮询分开，等待期间不占用 worker 槽。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from functools import wraps
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Text,
    bindparam,
    case,
    exists,
    func,
    insert,
    literal,
    null,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tender.adapters.gotenberg import GotenbergConverter
from tender.adapters.mineru import MinerUParser
from tender.adapters.pdfium import InvalidPdfError, PdfInspection, inspect_pdf
from tender.adapters.pg.locks import acquire_lock, release_lock, try_acquire_lock
from tender.adapters.pg.models import (
    Document,
    DocumentVersion,
    Element,
    Job,
    Page,
    ParseRun,
    Project,
    ProjectFile,
)
from tender.adapters.pg.session import create_pg_engine
from tender.adapters.s3 import S3BlobStore
from tender.application.middle_json import NormalizedElement, normalize_middle_json
from tender.config.registry import ConfigRegistry
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

_engine = create_pg_engine()


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
                select(
                    Job,
                    DocumentVersion.pdf_key,
                    DocumentVersion.pdf_sha256,
                    DocumentVersion.page_count.label("version_page_count"),
                    ProjectFile.display_name,
                    Document.company_id.label("document_company_id"),
                    ParseRun.provider_job_id,
                    ParseRun.provider_version,
                    ParseRun.started_at,
                )
                .select_from(Job)
                .join(DocumentVersion, DocumentVersion.id == Job.version_id)
                .join(ProjectFile, ProjectFile.id == Job.project_file_id)
                .join(Document, Document.id == DocumentVersion.document_id)
                .outerjoin(ParseRun, ParseRun.id == Job.run_id)
                .where(Job.id == job_id)
            )
            .mappings()
            .first()
        )
    return row


def _jsonb(value: Any) -> Any:
    """Python 对象 → JSONB 绑定参数，用于 `col || :value` 这类 JSONB 合并。"""
    return literal(value, type_=JSONB)


def _retry_delay(retries: int) -> int:
    return min(30, 2 ** min(max(retries, 1), 5))


@contextmanager
def _advisory_lock(lock_key: str, *, wait: bool) -> Iterator[bool]:
    """用数据库会话锁协调重复投递，进程退出后锁会自动释放。"""
    with _engine.connect() as connection:
        if wait:
            acquire_lock(connection, lock_key)
            acquired = True
        else:
            acquired = try_acquire_lock(connection, lock_key)
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                release_lock(connection, lock_key)
                connection.commit()


def _serialize_job(function: Callable[..., None]) -> Callable[..., None]:
    @wraps(function)
    def wrapped(task: Any, job_id: str) -> None:
        with _advisory_lock(f"job:{job_id}", wait=False) as acquired:
            if not acquired:
                raise task.retry(countdown=1)
            function(task, job_id)

    return wrapped


@asynccontextmanager
async def _async_version_lock(lock_key: str) -> AsyncIterator[None]:
    """转换等待同一版本锁时仍允许总时限取消，不能被同步阻塞查询绕过预算。"""
    while True:
        with _advisory_lock(lock_key, wait=False) as acquired:
            if acquired:
                yield
                return
        await asyncio.sleep(0.2)


def _file_job(job_id: str) -> Mapping[str, Any] | None:
    with _engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    Job,
                    ProjectFile.original_key,
                    ProjectFile.sha256.label("source_sha256"),
                    ProjectFile.mime.label("source_mime"),
                    ProjectFile.size_bytes.label("source_size_bytes"),
                    ProjectFile.display_name,
                    ProjectFile.replaces_id,
                    Project.project_no,
                    Project.company_id.label("project_company_id"),
                )
                .select_from(Job)
                .join(ProjectFile, ProjectFile.id == Job.project_file_id)
                .join(Project, Project.id == Job.project_id)
                .where(Job.id == job_id)
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
                select(
                    DocumentVersion.id,
                    DocumentVersion.document_id,
                    DocumentVersion.pdf_key,
                    DocumentVersion.pdf_sha256,
                    DocumentVersion.converter,
                    DocumentVersion.converter_version,
                    DocumentVersion.is_converted,
                    DocumentVersion.page_count,
                )
                .where(
                    DocumentVersion.company_id == company_id,
                    DocumentVersion.sha256 == source_sha256,
                    DocumentVersion.converter_version.is_not_distinct_from(converter_version),
                )
                .order_by(DocumentVersion.id)
                .limit(1)
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
                select(
                    func.count().label("count"),
                    func.min(Page.page_no).label("first_page"),
                    func.max(Page.page_no).label("last_page"),
                ).where(Page.version_id == version["id"])
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


def _converter(
    *, remaining_seconds: float | None = None, extra_retries: int = 2
) -> GotenbergConverter:
    try:
        credentials = settings.gotenberg_credentials()
    except ValueError as exc:
        raise ConversionFailed("Gotenberg 凭据配置无效") from exc
    try:
        timeout_seconds = settings.gotenberg_timeout_seconds()
    except ValueError as exc:
        raise ConversionFailed("Gotenberg 超时配置无效") from exc
    # 部署参数约束单次HTTP请求；任务剩余总时限更短时不能继续等待超过任务预算。
    if remaining_seconds is not None:
        timeout_seconds = min(timeout_seconds, remaining_seconds)
    return GotenbergConverter(
        settings.gotenberg_url(),
        username=credentials[0] if credentials else None,
        password=credentials[1] if credentials else None,
        timeout_seconds=timeout_seconds,
        extra_retries=extra_retries,
    )


def _runtime_values(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return ConfigRegistry(_engine).resolved(int(row["company_id"]))


def _execution_start(job_id: str, phase: str) -> datetime:
    """阶段首启时间持久化，进程恢复和消息重试都不能重新获得完整总时限。"""
    # progress 里已有的 <phase>_started_at 保留（重试不能重置预算），没有就写 now()。
    key = bindparam("progress_key", phase + "_started_at", type_=Text)
    path = bindparam("progress_path", [phase + "_started_at"], type_=ARRAY(Text))
    with _engine.begin() as connection:
        value = connection.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                progress=func.jsonb_set(
                    Job.progress,
                    path,
                    func.coalesce(Job.progress.op("->")(key), func.to_jsonb(func.now())),
                    True,
                )
            )
            .returning(Job.progress.op("->>")(key))
        ).scalar_one()
    return datetime.fromisoformat(value)


def _remaining(started_at: datetime, minutes: int) -> float:
    # 比较秒数而非构造可能溢出的远期datetime，不引入新的人工时长上限。
    return minutes * 60 - (datetime.now(UTC) - started_at).total_seconds()


async def _within(seconds: float, operation: Any) -> Any:
    # 覆盖版本查询、读取和所有重试的累计等待，不能把总时限误当每次HTTP超时。
    async with asyncio.timeout(seconds):
        return await operation


def _poll_delay(values: Mapping[str, Any], attempts: int) -> float:
    initial = int(values["job.poll.initial_interval_ms"])
    maximum = int(values["job.poll.max_interval_ms"])
    # 达到最大间隔后不再计算巨大幂，次数预算调大也不会使退避计算溢出。
    exponent = min(max(0, attempts), max(0, (maximum // initial).bit_length()))
    return min(maximum, initial * 2**exponent) / 1000


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
                    select(DocumentVersion.document_id)
                    .select_from(ProjectFile)
                    .join(Project, Project.id == ProjectFile.project_id)
                    .outerjoin(DocumentVersion, DocumentVersion.id == ProjectFile.version_id)
                    .where(
                        ProjectFile.id == replaces_id,
                        ProjectFile.project_id == row["project_id"],
                        Project.company_id == row["project_company_id"],
                    )
                ).scalar_one_or_none()
            if document_id is None:
                document_id = connection.execute(
                    insert(Document)
                    .values(
                        company_id=row["project_company_id"],
                        title=row["display_name"],
                        project_no=row["project_no"],
                    )
                    .returning(Document.id)
                ).scalar_one()
            else:
                connection.execute(
                    select(Document.id).where(Document.id == document_id).with_for_update()
                ).one()
            version_no = int(
                connection.execute(
                    select(func.coalesce(func.max(DocumentVersion.version_no), 0) + 1).where(
                        DocumentVersion.document_id == document_id
                    )
                ).scalar_one()
            )
            version_id = int(
                connection.execute(
                    insert(DocumentVersion)
                    .values(
                        company_id=row["project_company_id"],
                        document_id=document_id,
                        version_no=version_no,
                        sha256=str(row["source_sha256"]).strip(),
                        mime=row["source_mime"],
                        size_bytes=row["source_size_bytes"],
                        original_key=row["original_key"],
                        pdf_key=pdf_key,
                        pdf_sha256=pdf_sha256,
                        is_converted=is_converted,
                        converter=converter,
                        converter_version=converter_version,
                        page_count=inspection.page_count if inspection else None,
                    )
                    .returning(DocumentVersion.id)
                ).scalar_one()
            )
            page_count = inspection.page_count if inspection else 0
        else:
            version_id = int(candidate["id"])
            page_count = int(candidate["page_count"] or 0)

        if inspection is not None:
            page_count = inspection.page_count
            page_insert = pg_insert(Page).values(
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
                ]
            )
            connection.execute(
                page_insert.on_conflict_do_update(
                    index_elements=["version_id", "page_no"],
                    set_={
                        "width_pt": page_insert.excluded.width_pt,
                        "height_pt": page_insert.excluded.height_pt,
                        "rotation": page_insert.excluded.rotation,
                        "text_layer": page_insert.excluded.text_layer,
                    },
                )
            )
            connection.execute(
                update(DocumentVersion)
                .where(DocumentVersion.id == version_id)
                .values(page_count=page_count)
            )

        connection.execute(
            update(ProjectFile)
            .where(ProjectFile.id == row["project_file_id"])
            .values(version_id=version_id)
        )
        prior_parse = connection.execute(
            select(
                exists(
                    select(ParseRun.id).where(
                        ParseRun.version_id == version_id,
                        ParseRun.status.in_(("pending", "running", "completed", "partial")),
                    )
                )
            )
        ).scalar_one()
        should_parse = auto_parse and not bool(prior_parse)
        status = "pending" if should_parse else "completed"
        stage = "submitting" if should_parse else "geometry"
        # dispatched_at 是「本阶段已投递」的一次性闩锁，派发闸门只认 dispatched_at IS NULL 的行。
        # 转换阶段占着这个闩锁，阶段推进到 submitting 时必须一并清掉，
        # 否则这条 job 永远不满足闸门条件，解析会停在 pending 不动（2026-10-01 实测踩到）。
        connection.execute(
            update(Job)
            .where(Job.id == row["id"], Job.status != "canceled")
            .values(
                version_id=version_id,
                status=status,
                stage=stage,
                progress={"pages": page_count},
                error_code=None,
                error_message=None,
                updated_at=func.now(),
                dispatched_at=case((literal(should_parse), null()), else_=Job.dispatched_at),
                finished_at=case((literal(should_parse), null()), else_=func.now()),
            )
        )
    return version_id, page_count, should_parse


async def _process_office_file(row: Mapping[str, Any], store: S3BlobStore) -> tuple[int, int, bool]:
    values = _runtime_values(row)
    started_at = _execution_start(str(row["id"]), "convert")
    remaining = _remaining(started_at, int(values["job.timeout.convert_minutes"]))
    if remaining <= 0:
        raise TimeoutError("转换已达到任务总时限")
    return await _within(
        remaining, _convert_office_file(row, store, remaining, int(values["job.retry.convert_500"]))
    )


async def _convert_office_file(
    row: Mapping[str, Any], store: S3BlobStore, remaining: float, extra_retries: int
) -> tuple[int, int, bool]:
    source_sha256 = str(row["source_sha256"]).strip().lower()
    converter_adapter = _converter(remaining_seconds=remaining, extra_retries=extra_retries)
    try:
        converter_version = await converter_adapter.version()
        lock_key = f"version:{row['project_company_id']}:{source_sha256}:{converter_version}"
        async with _async_version_lock(lock_key):
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
            update(Job)
            .where(
                Job.id == job_id,
                Job.status.in_(("pending", "running")),
                Job.stage.in_(("converting", "probing", "geometry")),
            )
            .values(status="running", updated_at=func.now())
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
            # 适配器已经消耗配置中的重试额度，外层不能再次无限倍增转换请求。
            _set_job_failure(job_id, exc.code, str(exc))
            return
        except TimeoutError as exc:
            _set_job_failure(job_id, "convert_timeout", str(exc))
            return
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
            update(Job)
            .where(Job.id == job_id, Job.status == "running")
            .values(
                status="pending",
                stage=stage,
                error_code=code,
                error_message=message[:2000],
                updated_at=func.now(),
                finished_at=None,
            )
        )


def _set_job_failure(job_id: str, code: str, message: str) -> None:
    now = datetime.now(UTC)
    with _engine.begin() as connection:
        row = (
            connection.execute(select(Job.run_id).where(Job.id == job_id).with_for_update())
            .mappings()
            .first()
        )
        if row is None:
            return
        connection.execute(
            update(Job)
            .where(Job.id == job_id, Job.status != "canceled")
            .values(
                status="failed",
                error_code=code,
                error_message=message[:2000],
                updated_at=now,
                finished_at=now,
            )
        )
        if row["run_id"] is not None:
            connection.execute(
                update(ParseRun)
                .where(ParseRun.id == row["run_id"])
                .values(
                    status="failed",
                    error_code=code,
                    error_message=message[:2000],
                    finished_at=now,
                )
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
            update(Job)
            .where(Job.id == job_id, Job.status == "pending")
            .values(status="submitting", stage="submitting", updated_at=func.now())
        ).rowcount
    if not claimed:
        return

    values = _runtime_values(row)
    started_at = _execution_start(job_id, "parse")
    if _remaining(started_at, int(values["job.timeout.parse_minutes"])) <= 0:
        _set_job_failure(job_id, "parse_timeout", "解析已达到任务总时限")
        return
    store = _store()
    try:
        submission = asyncio.run(
            _within(
                _remaining(started_at, int(values["job.timeout.parse_minutes"])),
                _submit(row, store),
            )
        )
    except TimeoutError:
        # 提交超时不能断言远端未受理，更不能自动重新提交同一任务。
        _mark_submission_unknown(job_id, "解析提交达到任务总时限，远端受理状态未知")
        return
    except ParseSubmissionUnknown as exc:
        _mark_submission_unknown(job_id, str(exc))
        return
    except ParseUnavailable as exc:
        with _engine.begin() as connection:
            connection.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "submitting")
                .values(
                    status="pending",
                    stage="submitting",
                    error_code=exc.code,
                    error_message=str(exc)[:2000],
                    updated_at=func.now(),
                )
            )
        raise self.retry(exc=exc, countdown=_retry_delay(self.request.retries)) from exc
    except ParseFailed as exc:
        _set_job_failure(job_id, exc.code, str(exc))
        return
    except BlobStoreError as exc:
        with _engine.begin() as connection:
            connection.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "submitting")
                .values(
                    status="pending",
                    stage="submitting",
                    error_code="storage_unavailable",
                    error_message=str(exc)[:2000],
                    updated_at=func.now(),
                )
            )
        raise self.retry(exc=exc, countdown=_retry_delay(self.request.retries)) from exc
    now = datetime.now(UTC)
    snapshot = asdict(submission.config_snapshot)
    try:
        with _engine.begin() as connection:
            run_id = connection.execute(
                insert(ParseRun)
                .values(
                    version_id=row["version_id"],
                    provider="mineru",
                    provider_version=submission.provider_version,
                    tier=snapshot["tier"],
                    schema_version="2.0",
                    status="running",
                    request_id=job_id,
                    provider_job_id=submission.job_id,
                    config_snapshot=snapshot,
                    started_at=now,
                )
                .returning(ParseRun.id)
            ).scalar_one()
            connection.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "submitting")
                .values(
                    run_id=run_id,
                    status="running",
                    stage="parsing",
                    progress=Job.progress.op("||")(_jsonb({})),
                    error_code=None,
                    error_message=None,
                    updated_at=now,
                )
            )
    except Exception as exc:
        # 远端已受理但本地未能保存引用时，不能再次提交同一内容来掩盖不一致。
        _mark_submission_unknown(job_id, f"MinerU 已提交但任务记录写入失败：{exc}")
        return

    poll_parse.apply_async(args=(job_id,), countdown=_poll_delay(values, 0))


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

    values = _runtime_values(row)
    started_at = _execution_start(job_id, "parse")
    remaining = _remaining(started_at, int(values["job.timeout.parse_minutes"]))
    attempts = int((row.get("progress") or {}).get("poll_attempts", 0))
    if remaining <= 0 or attempts >= int(values["job.poll.max_attempts"]):
        _set_job_failure(job_id, "parse_timeout", "解析已达到总时限或轮询次数上限")
        return
    # 每次真实轮询前记账；网络错误、服务重启与worker恢复不能重置次数。
    with _engine.begin() as connection:
        connection.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                progress=func.jsonb_set(
                    Job.progress,
                    bindparam("attempts_path", ["poll_attempts"], type_=ARRAY(Text)),
                    func.to_jsonb(bindparam("attempts", attempts + 1, type_=BigInteger)),
                    True,
                )
            )
        )

    store = _store()
    try:
        status, middle_json = asyncio.run(_within(remaining, _poll(row, store)))
    except TimeoutError:
        _set_job_failure(job_id, "parse_timeout", "解析已达到任务总时限")
        return
    except ServiceRestarted:
        with _engine.begin() as connection:
            claimed = connection.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "running", Job.stage == "parsing")
                .values(stage="resubmitting", updated_at=func.now())
            ).rowcount
        if not claimed:
            return
        try:
            submission = asyncio.run(
                _within(
                    _remaining(started_at, int(values["job.timeout.parse_minutes"])),
                    _submit(row, store),
                )
            )
        except TimeoutError:
            _mark_submission_unknown(job_id, "重新提交达到任务总时限，远端受理状态未知")
            return
        except ParseSubmissionUnknown as unknown:
            _mark_submission_unknown(job_id, str(unknown))
            return
        except ParseFailed as failed:
            _set_job_failure(job_id, failed.code, str(failed))
            return
        except (ParseUnavailable, BlobStoreError) as retryable:
            with _engine.begin() as connection:
                connection.execute(
                    update(Job)
                    .where(Job.id == job_id, Job.status == "running")
                    .values(stage="parsing", updated_at=func.now())
                )
            raise self.retry(
                exc=retryable,
                countdown=_poll_delay(values, attempts + 1),
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
                update(ParseRun)
                .where(ParseRun.id == row["run_id"])
                .values(provider_job_id=submission.job_id)
            )
            connection.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "running")
                .values(stage="parsing", updated_at=func.now())
            )
        poll_parse.apply_async(args=(job_id,), countdown=_poll_delay(values, attempts + 1))
        return
    except ParseUnavailable as exc:
        raise self.retry(exc=exc, countdown=_poll_delay(values, attempts + 1)) from exc
    except ParseFailed as exc:
        _set_job_failure(job_id, exc.code, str(exc))
        return
    except BlobStoreError as exc:
        raise self.retry(exc=exc, countdown=_poll_delay(values, attempts + 1)) from exc

    now = datetime.now(UTC)
    progress = asdict(status.progress) if status.progress is not None else {}
    if status.status in {"queued", "running"}:
        with _engine.begin() as connection:
            connection.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(progress=Job.progress.op("||")(_jsonb(progress)), updated_at=now)
            )
        poll_parse.apply_async(args=(job_id,), countdown=_poll_delay(values, attempts + 1))
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
            raise self.retry(exc=exc, countdown=_poll_delay(values, attempts + 1)) from exc
        page_values = middle_json.payload.get("pages")
        page_count = len(page_values) if isinstance(page_values, list) else None
        backend = middle_json.backend
        schema_version = middle_json.schema_version
        with _engine.connect() as connection:
            page_rows = (
                connection.execute(
                    select(Page.page_no, Page.rotation, Page.text_layer)
                    .where(Page.version_id == row["version_id"])
                    .order_by(Page.page_no)
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
                    update(ParseRun)
                    .where(ParseRun.id == row["run_id"])
                    .values(
                        raw_middle_key=raw_middle_key,
                        page_count=page_count,
                        backend=backend,
                        schema_version=schema_version,
                    )
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
            # 参数列表交给批量执行，避免 .values([...]) 超出 PostgreSQL 单语句参数上限。
            connection.execute(
                insert(Element),
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
                    select(Element.id, Element.page_no, Element.order_no).where(
                        Element.run_id == row["run_id"]
                    )
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
                        "element_id": element_ids[(element.page_no, element.order_no)],
                        "parent_element_id": element_ids[(parent.page_no, parent.order_no)],
                    }
                )
            if parent_updates:
                connection.execute(
                    update(Element)
                    .where(Element.id == bindparam("element_id"))
                    .values(parent_id=bindparam("parent_element_id")),
                    parent_updates,
                )
        connection.execute(
            update(ParseRun)
            .where(ParseRun.id == row["run_id"])
            .values(
                status=terminal_status,
                raw_middle_key=raw_middle_key,
                page_count=page_count,
                backend=backend,
                schema_version=func.coalesce(schema_version, ParseRun.schema_version),
                elapsed_ms=elapsed_ms,
                error_code=error_code,
                error_message=error_message,
                finished_at=now,
            )
        )
        connection.execute(
            update(Job)
            .where(Job.id == job_id, Job.status != "canceled")
            .values(
                status=terminal_status,
                stage="parsing",
                progress=progress,
                error_code=error_code,
                error_message=error_message,
                updated_at=now,
                finished_at=now,
            )
        )
