"""文档任务仓储：保留原有原子操作，Worker 不持有连接或 SQL 表达式。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Engine,
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

from tender.adapters.pg.models import (
    Document,
    DocumentVersion,
    Element,
    Job,
    JobConfigSnapshot,
    Page,
    ParseRun,
    Project,
    ProjectFile,
)
from tender.config.registry import ConfigRegistry
from tender.config.schema import document_execution_snapshot
from tender.domain.documents.element import NormalizedElement
from tender.domain.shared.errors import ParseFailed
from tender.ports.documents.inspection import PdfInspection


def _jsonb(value: Any) -> Any:
    return literal(value, type_=JSONB)


class DocumentPipelineRepository:
    def __init__(self, engine: Engine, configs: ConfigRegistry) -> None:
        self.engine = engine
        self.configs = configs

    def runtime_values(self, job_id: str) -> Mapping[str, Any]:
        """优先使用创建时快照；老任务首次补齐后也不能随重试读取新配置。"""
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(Job.config_snapshot, Job.config_snapshot_id, Job.company_id).where(
                        Job.id == job_id
                    )
                )
                .mappings()
                .one()
            )
            snapshot = dict(row["config_snapshot"] or {})
            if "execution" in snapshot:
                return dict(snapshot["execution"])
            frozen = None
            if row["config_snapshot_id"] is not None:
                frozen = connection.execute(
                    select(JobConfigSnapshot.resolved).where(
                        JobConfigSnapshot.id == row["config_snapshot_id"]
                    )
                ).scalar_one()
        # 旧任务没有创建时快照时，只能固定首次执行时的配置，并标记来源。
        # 活动配置可能访问 Redis，必须在锁定任务行之前读取。
        origin = "job_config_snapshot" if frozen is not None else "legacy_first_execution"
        values = document_execution_snapshot(
            frozen if frozen is not None else self.configs.resolved(int(row["company_id"]))
        )
        with self.engine.begin() as connection:
            current = connection.execute(
                select(Job.config_snapshot).where(Job.id == job_id).with_for_update()
            ).scalar_one()
            snapshot = dict(current or {})
            if "execution" not in snapshot:
                snapshot.update(
                    execution=values,
                    execution_origin=origin,
                    execution_frozen_at=datetime.now(UTC).isoformat(),
                )
                connection.execute(
                    update(Job).where(Job.id == job_id).values(config_snapshot=snapshot)
                )
            # 并发补齐时必须采用获锁者已写入的值，不能返回本次预读值。
            return dict(snapshot["execution"])

    def job(self, job_id: str) -> Mapping[str, Any] | None:
        with self.engine.connect() as connection:
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

    def file_job(self, job_id: str) -> Mapping[str, Any] | None:
        with self.engine.connect() as connection:
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

    def version_candidate(
        self,
        company_id: int,
        source_sha256: str,
        converter_version: str | None,
    ) -> Mapping[str, Any] | None:
        with self.engine.connect() as connection:
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

    def geometry_is_complete(self, version: Mapping[str, Any]) -> bool:
        page_count = version.get("page_count")
        if not isinstance(page_count, int) or page_count < 1:
            return False
        with self.engine.connect() as connection:
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

    def execution_start(self, job_id: str, phase: str) -> datetime:
        """阶段首启时间持久化，进程恢复和消息重试都不能重新获得完整总时限。"""
        # progress 里已有的 <phase>_started_at 保留（重试不能重置预算），没有就写 now()。
        key = bindparam("progress_key", phase + "_started_at", type_=Text)
        path = bindparam("progress_path", [phase + "_started_at"], type_=ARRAY(Text))
        with self.engine.begin() as connection:
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
    ) -> tuple[int, int, bool]:
        snapshot = row["config_snapshot"]
        auto_parse = isinstance(snapshot, dict) and bool(snapshot.get("auto_parse", True))
        with self.engine.begin() as connection:
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
            # dispatched_at 是本阶段已投递的闩锁，派发器只认其为空的候选。
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

    def reset_file_job(self, job_id: str, stage: str, code: str, message: str) -> None:
        with self.engine.begin() as connection:
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

    def set_job_failure(self, job_id: str, code: str, message: str) -> None:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
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

    def claim_file(self, job_id: str) -> bool:
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.status.in_(("pending", "running")),
                    Job.stage.in_(("converting", "probing", "geometry")),
                )
                .values(status="running", updated_at=func.now())
            ).rowcount
        return bool(changed)

    def claim_submission(self, job_id: str) -> bool:
        with self.engine.begin() as connection:
            claimed = connection.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "pending")
                .values(status="submitting", stage="submitting", updated_at=func.now())
            ).rowcount
        return bool(claimed)

    def retry_submission(self, job_id: str, code: str, message: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "submitting")
                .values(
                    status="pending",
                    stage="submitting",
                    error_code=code,
                    error_message=message[:2000],
                    updated_at=func.now(),
                )
            )

    def save_submission(
        self,
        job_id: str,
        version_id: int,
        provider_version: str,
        provider_job_id: str,
        snapshot: dict[str, Any],
        now: datetime,
    ) -> None:
        with self.engine.begin() as connection:
            run_id = connection.execute(
                insert(ParseRun)
                .values(
                    version_id=version_id,
                    provider="mineru",
                    provider_version=provider_version,
                    tier=snapshot["tier"],
                    schema_version="2.0",
                    status="running",
                    request_id=job_id,
                    provider_job_id=provider_job_id,
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

    def record_poll(self, job_id: str, attempts: int) -> None:
        with self.engine.begin() as connection:
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

    def claim_resubmission(self, job_id: str) -> bool:
        with self.engine.begin() as connection:
            claimed = connection.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "running", Job.stage == "parsing")
                .values(stage="resubmitting", updated_at=func.now())
            ).rowcount
        return bool(claimed)

    def resume_poll(self, job_id: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "running")
                .values(stage="parsing", updated_at=func.now())
            )

    def replace_provider_job(self, job_id: str, run_id: int, provider_job_id: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(ParseRun)
                .where(ParseRun.id == run_id)
                .values(provider_job_id=provider_job_id)
            )
            connection.execute(
                update(Job)
                .where(Job.id == job_id, Job.status == "running")
                .values(stage="parsing", updated_at=func.now())
            )

    def update_progress(self, job_id: str, progress: dict[str, Any], now: datetime) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(progress=Job.progress.op("||")(_jsonb(progress)), updated_at=now)
            )

    def pages(self, version_id: int) -> list[Mapping[str, Any]]:
        with self.engine.connect() as connection:
            page_rows = (
                connection.execute(
                    select(Page.page_no, Page.rotation, Page.text_layer)
                    .where(Page.version_id == version_id)
                    .order_by(Page.page_no)
                )
                .mappings()
                .all()
            )
        return list(page_rows)

    def save_parse_metadata(
        self,
        run_id: int,
        raw_middle_key: str | None,
        page_count: int | None,
        backend: str | None,
        schema_version: str | None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(ParseRun)
                .where(ParseRun.id == run_id)
                .values(
                    raw_middle_key=raw_middle_key,
                    page_count=page_count,
                    backend=backend,
                    schema_version=schema_version,
                )
            )

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
    ) -> None:
        with self.engine.begin() as connection:
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
