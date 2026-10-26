"""解析 worker：单次提交与单次轮询分开，等待期间不占用 worker 槽。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from functools import wraps
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any

from tender.adapters.documents.gotenberg import GotenbergConverter
from tender.adapters.documents.pdfium import InvalidPdfError, inspect_pdf
from tender.adapters.storage.s3 import S3BlobStore
from tender.application.documents.middle_json import normalize_middle_json
from tender.core import settings
from tender.core.di import (
    create_document_parser,
    create_document_pipeline_repository,
    create_task_locks,
)
from tender.core.logging import get_logger
from tender.domain.documents.element import NormalizedElement
from tender.domain.shared.errors import (
    ConversionFailed,
    ConversionUnavailable,
    ParseFailed,
    ParseSubmissionUnknown,
    ParseUnavailable,
    ServiceRestarted,
)
from tender.ports.documents.parser import DocumentParser
from tender.ports.storage.blob_store import BlobNotFound, BlobStoreError
from tender.worker.celery_app import celery_app

_repository = create_document_pipeline_repository()
_locks = create_task_locks()
logger = get_logger(__name__)


def _store() -> S3BlobStore:
    return S3BlobStore()


def _parser(store: S3BlobStore) -> DocumentParser:
    async def load_pdf(key: str) -> bytes:
        return await asyncio.to_thread(store.read, key)

    return create_document_parser(load_pdf)


def _retry_delay(retries: int) -> int:
    return min(30, 2 ** min(max(retries, 1), 5))


def _retry_attempts(row: Mapping[str, Any]) -> int:
    # 次数随任务行持久化，Celery 新消息的 retries 不能作为退避依据。
    return int((row.get("progress") or {}).get("retry_attempts", 0))


def _schedule_retry(job_id: str, row: Mapping[str, Any]) -> None:
    _repository.schedule_attempt(job_id, _retry_delay(_retry_attempts(row)), retry=True)


def _serialize_job(*stages: str) -> Callable:
    def decorate(function: Callable[..., None]) -> Callable[..., None]:
        @wraps(function)
        def wrapped(task: Any, job_id: str) -> None:
            with _locks.lock(f"job:{job_id}", wait=False) as acquired:
                if not acquired:
                    raise task.retry(countdown=1)
                if _repository.claim_attempt(job_id, stages):
                    function(task, job_id)

        return wrapped

    return decorate


@asynccontextmanager
async def _async_version_lock(lock_key: str) -> AsyncIterator[None]:
    """转换等待同一版本锁时仍允许总时限取消，不能被同步阻塞查询绕过预算。"""
    while True:
        with _locks.lock(lock_key, wait=False) as acquired:
            if acquired:
                yield
                return
        await asyncio.sleep(0.2)


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
    return _repository.runtime_values(str(row["id"]))


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


async def _process_office_file(row: Mapping[str, Any], store: S3BlobStore) -> tuple[int, int, bool]:
    values = _runtime_values(row)
    started_at = _repository.execution_start(str(row["id"]), "convert")
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
            candidate = _repository.version_candidate(
                int(row["project_company_id"]), source_sha256, converter_version
            )
            if candidate is not None:
                inspection = None
                if not _repository.geometry_is_complete(candidate):
                    pdf_bytes = await asyncio.to_thread(store.read, str(candidate["pdf_key"]))
                    _verify_hash(pdf_bytes, str(candidate["pdf_sha256"]), "已存 PDF")
                    inspection = inspect_pdf(pdf_bytes)
                return _repository.finish_file_version(
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
            return _repository.finish_file_version(
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
    with _locks.lock(lock_key, wait=True):
        candidate = _repository.version_candidate(
            int(row["project_company_id"]), source_sha256, None
        )
        if candidate is not None:
            inspection = None
            if not _repository.geometry_is_complete(candidate):
                pdf_bytes = store.read(str(candidate["pdf_key"]))
                _verify_hash(pdf_bytes, str(candidate["pdf_sha256"]), "已存 PDF")
                inspection = inspect_pdf(pdf_bytes)
            return _repository.finish_file_version(
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
        return _repository.finish_file_version(
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
@_serialize_job("converting", "probing", "geometry")
def process_file(self: Any, job_id: str) -> None:
    row = _repository.file_job(job_id)
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
    changed = _repository.claim_file(job_id)
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
            _repository.set_job_failure(job_id, exc.code, str(exc))
            return
        except TimeoutError as exc:
            _repository.set_job_failure(job_id, "convert_timeout", str(exc))
            return
        except BlobStoreError as exc:
            _repository.reset_file_job(job_id, stage, "storage_unavailable", str(exc))
            _schedule_retry(job_id, row)
            return
        except ConversionFailed as exc:
            _repository.set_job_failure(job_id, exc.code, str(exc))
            return
        except InvalidPdfError as exc:
            _repository.set_job_failure(job_id, "invalid_pdf", str(exc))
            return
        except BlobNotFound as exc:
            _repository.set_job_failure(job_id, "storage_object_missing", str(exc))
            return
        except ValueError as exc:
            _repository.set_job_failure(job_id, "content_hash_mismatch", str(exc))
            return
        except Exception as exc:
            # 此处会吞掉异常并返回，Celery 失败信号无法代替业务入口记录堆栈。
            logger.exception("file.fail", job_id=job_id)
            _repository.set_job_failure(job_id, "preprocessing_failed", str(exc))
            return
    finally:
        store.close()

    # should_parse 时 _finish_file_version 已把 job 置为 pending/submitting；
    # 派发交给 beat（worker/dispatch.py），这里再投一次会和闸门抢方向。


def _mark_submission_unknown(job_id: str, message: str) -> None:
    _repository.set_job_failure(job_id, "parse_submission_unknown", message)


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
@_serialize_job("submitting")
def submit_parse(self: Any, job_id: str) -> None:
    row = _repository.job(job_id)
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

    claimed = _repository.claim_submission(job_id)
    if not claimed:
        return

    values = _runtime_values(row)
    started_at = _repository.execution_start(job_id, "parse")
    if _remaining(started_at, int(values["job.timeout.parse_minutes"])) <= 0:
        _repository.set_job_failure(job_id, "parse_timeout", "解析已达到任务总时限")
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
        _repository.retry_submission(job_id, exc.code, str(exc))
        _schedule_retry(job_id, row)
        return
    except ParseFailed as exc:
        _repository.set_job_failure(job_id, exc.code, str(exc))
        return
    except BlobStoreError as exc:
        _repository.retry_submission(job_id, "storage_unavailable", str(exc))
        _schedule_retry(job_id, row)
        return
    now = datetime.now(UTC)
    snapshot = asdict(submission.config_snapshot)
    try:
        _repository.save_submission(
            job_id,
            int(row["version_id"]),
            submission.provider_version,
            submission.job_id,
            snapshot,
            now,
        )
    except Exception as exc:
        # 远端已受理但本地未能保存引用时，不能再次提交同一内容来掩盖不一致。
        logger.exception("parse.save_fail", job_id=job_id)
        _mark_submission_unknown(job_id, f"MinerU 已提交但任务记录写入失败：{exc}")
        return

    _repository.schedule_attempt(job_id, _poll_delay(values, 0))


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
@_serialize_job("parsing", "resubmitting")
def poll_parse(self: Any, job_id: str) -> None:
    row = _repository.job(job_id)
    if row is None or row["status"] != "running" or row["run_id"] is None:
        return
    if row["stage"] == "resubmitting":
        _mark_submission_unknown(
            job_id,
            "MinerU 重启后的重新提交结果未知；需人工核对服务端状态后再决定是否重跑",
        )
        return

    values = _runtime_values(row)
    started_at = _repository.execution_start(job_id, "parse")
    remaining = _remaining(started_at, int(values["job.timeout.parse_minutes"]))
    attempts = int((row.get("progress") or {}).get("poll_attempts", 0))
    if remaining <= 0 or attempts >= int(values["job.poll.max_attempts"]):
        _repository.set_job_failure(job_id, "parse_timeout", "解析已达到总时限或轮询次数上限")
        return
    # 非终态分支统一按已记账次数退避；只在需要重试时计算，成功收尾不依赖轮询配置。
    def schedule_retry() -> None:
        _repository.schedule_attempt(job_id, _poll_delay(values, attempts + 1))

    # 每次真实轮询前记账；网络错误、服务重启与worker恢复不能重置次数。
    _repository.record_poll(job_id, attempts)

    store = _store()
    try:
        status, middle_json = asyncio.run(_within(remaining, _poll(row, store)))
    except TimeoutError:
        _repository.set_job_failure(job_id, "parse_timeout", "解析已达到任务总时限")
        return
    except ServiceRestarted:
        claimed = _repository.claim_resubmission(job_id)
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
            _repository.set_job_failure(job_id, failed.code, str(failed))
            return
        except (ParseUnavailable, BlobStoreError):
            _repository.resume_poll(job_id)
            schedule_retry()
            return

        if submission.provider_version != row["provider_version"]:
            _repository.set_job_failure(
                job_id,
                "provider_version_changed",
                "MinerU 重启后版本发生变化；为保留可复现快照，本次任务已停止",
            )
            return
        _repository.replace_provider_job(job_id, int(row["run_id"]), submission.job_id)
        schedule_retry()
        return
    except ParseFailed as exc:
        _repository.set_job_failure(job_id, exc.code, str(exc))
        return
    except (ParseUnavailable, BlobStoreError):
        # 网络类失败可退避重试；次数已记在任务行上，重启进程也不会重置。
        schedule_retry()
        return

    now = datetime.now(UTC)
    progress = asdict(status.progress) if status.progress is not None else {}
    if status.status in {"queued", "running"}:
        _repository.update_progress(job_id, progress, now)
        schedule_retry()
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
        except BlobStoreError:
            schedule_retry()
            return
        page_values = middle_json.payload.get("pages")
        page_count = len(page_values) if isinstance(page_values, list) else None
        backend = middle_json.backend
        schema_version = middle_json.schema_version
        page_rows = _repository.pages(int(row["version_id"]))
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
            _repository.save_parse_metadata(
                int(row["run_id"]), raw_middle_key, page_count, backend, schema_version
            )
            code = exc.code if isinstance(exc, ParseFailed) else "invalid_configuration"
            _repository.set_job_failure(job_id, code, str(exc))
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

    _repository.complete_parse(
        job_id,
        row,
        normalized_elements,
        terminal_status=terminal_status,
        raw_middle_key=raw_middle_key,
        page_count=page_count,
        backend=backend,
        schema_version=schema_version,
        elapsed_ms=elapsed_ms,
        error_code=error_code,
        error_message=error_message,
        progress=progress,
        now=now,
    )
