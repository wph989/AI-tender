"""文档任务持久化契约；执行入口只使用业务数据，不接触 ORM。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from tender.domain.documents.element import NormalizedElement
from tender.ports.documents.inspection import PdfInspection


class DocumentPipelineRepository(Protocol):
    def claim_attempt(self, job_id: str, stages: tuple[str, ...]) -> bool: ...

    def schedule_attempt(self, job_id: str, delay: float, *, retry: bool = False) -> None: ...

    def finish_cancellation(self, job_id: str, *, remote_finished: bool = False) -> bool: ...

    def job(self, job_id: str) -> Mapping[str, Any] | None: ...

    def file_job(self, job_id: str) -> Mapping[str, Any] | None: ...

    def version_candidate(
        self,
        company_id: int,
        source_sha256: str,
        converter_version: str | None,
    ) -> Mapping[str, Any] | None: ...

    def geometry_is_complete(self, version: Mapping[str, Any]) -> bool: ...

    def execution_start(self, job_id: str, phase: str) -> datetime: ...

    def finish_file_version(
        self,
        row: Mapping[str, Any],
        *,
        candidate: Mapping[str, Any] | None,
        pdf_key: str,
        pdf_sha256: str,
        converter: str | None,
        converter_version: str | None,
        is_converted: bool,
        inspection: PdfInspection | None,
    ) -> tuple[int, int, bool]: ...

    def reset_file_job(self, job_id: str, stage: str, code: str, message: str) -> None: ...

    def set_job_failure(self, job_id: str, code: str, message: str) -> None: ...

    def claim_file(self, job_id: str) -> bool: ...

    def claim_submission(self, job_id: str) -> bool: ...

    def retry_submission(self, job_id: str, code: str, message: str) -> None: ...

    def save_submission(
        self,
        job_id: str,
        version_id: int,
        provider_version: str,
        provider_job_id: str,
        snapshot: dict[str, Any],
        now: datetime,
    ) -> None: ...

    def record_poll(self, job_id: str, attempts: int) -> None: ...

    def claim_resubmission(self, job_id: str) -> bool: ...

    def resume_poll(self, job_id: str) -> None: ...

    def replace_provider_job(self, job_id: str, run_id: int, provider_job_id: str) -> None: ...

    def update_progress(self, job_id: str, progress: dict[str, Any], now: datetime) -> None: ...

    def pages(self, version_id: int) -> list[Mapping[str, Any]]: ...

    def save_parse_metadata(
        self,
        run_id: int,
        raw_middle_key: str | None,
        page_count: int | None,
        backend: str | None,
        schema_version: str | None,
    ) -> None: ...

    def complete_parse(
        self,
        job_id: str,
        row: Mapping[str, Any],
        normalized_elements: list[NormalizedElement],
        *,
        terminal_status: str,
        raw_middle_key: str | None,
        page_count: int | None,
        backend: str | None,
        schema_version: str | None,
        elapsed_ms: int | None,
        error_code: str | None,
        error_message: str | None,
        progress: dict[str, Any],
        now: datetime,
    ) -> None: ...

    def runtime_values(self, job_id: str) -> Mapping[str, Any]: ...
