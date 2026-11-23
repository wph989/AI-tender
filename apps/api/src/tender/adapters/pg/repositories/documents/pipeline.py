"""文档任务仓储：保留原有原子操作，Worker 不持有连接或 SQL 表达式。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
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
    or_,
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
    Page,
    ParseRun,
    Project,
    ProjectFile,
)
from tender.adapters.pg.repositories.jobs.dispatch import DISPATCH_LEASE
from tender.adapters.pg.repositories.jobs.tasks import finish_canceled_job
from tender.domain.documents.element import NormalizedElement
from tender.domain.shared.errors import ParseFailed
from tender.ports.documents.inspection import PdfInspection


def _jsonb(value: Any) -> Any:
    return literal(value, type_=JSONB)


class DocumentPipelineRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def claim_attempt(self, job_id: str, stages: tuple[str, ...]) -> bool:
        # 调用者已持有 job 会话锁；旧阶段消息不能恢复派发标记、绕过下一阶段配额。
        with self.engine.begin() as connection:
            return bool(connection.execute(
                update(Job).where(
                    Job.id == job_id,
                    Job.stage.in_(stages),
                    Job.status.in_(("pending", "submitting", "running", "canceling", "draining")),
                    Job.finished_at.is_(None),
                    or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= func.now()),
                ).values(
                    dispatched_at=func.coalesce(Job.dispatched_at, func.now()),
                    next_attempt_at=None,
                    dispatch_lease_until=func.now() + DISPATCH_LEASE,
                )
            ).rowcount)

    def schedule_attempt(self, job_id: str, delay: float, *, retry: bool = False) -> None:
        # 先持久化下一轮时间，调度器负责消息；进程退出不会丢掉后续轮询。
        with self.engine.begin() as connection:
            connection.execute(update(Job).where(
                Job.id == job_id,
                Job.status.in_(("pending", "submitting", "running", "canceling", "draining")),
                Job.finished_at.is_(None),
            ).values(
                next_attempt_at=func.now() + timedelta(seconds=delay),
                dispatch_lease_until=None,
                # Celery 新消息的 retries 为零，次数必须随下一轮时间同事务保存。
                progress=(Job.progress.op("||")(func.jsonb_build_object(
                    "retry_attempts",
                    func.coalesce(Job.progress["retry_attempts"].as_integer(), 0) + 1,
                )) if retry else Job.progress),
            ))

    def finish_cancellation(self, job_id: str, *, remote_finished: bool = False) -> bool:
        """本地处理已退出或远端确认结束时才释放取消任务的配额。"""
        with self.engine.begin() as connection:
            row = connection.execute(
                select(Job.status, Job.stage, Job.run_id).where(Job.id == job_id).with_for_update()
            ).mappings().first()
            if row is None or row["status"] != "canceling":
                return False
            if not remote_finished and row["stage"] in {"submitting", "parsing", "resubmitting"}:
                return False
            finish_canceled_job(connection, job_id, row["run_id"])
            return True

    def finish_remote_job(self, job_id: str) -> None:
        """远端确认停止后才释放占用，保留原来的失败原因。"""
        with self.engine.begin() as connection:
            row = connection.execute(select(
                Job.status, Job.run_id, Job.error_code, Job.error_message,
            ).where(Job.id == job_id).with_for_update()).mappings().first()
            if row is None:
                return
            if row["status"] == "canceling":
                finish_canceled_job(connection, job_id, row["run_id"])
            elif row["status"] == "draining":
                values = dict(
                    status="failed", error_code=row["error_code"],
                    error_message=row["error_message"], finished_at=func.now(),
                )
                connection.execute(update(Job).where(Job.id == job_id).values(
                    **values, updated_at=func.now(), next_attempt_at=None,
                    dispatch_lease_until=None,
                ))
                if row["run_id"] is not None:
                    connection.execute(update(ParseRun).where(
                        ParseRun.id == row["run_id"],
                        ParseRun.status.in_(("pending", "running")),
                    ).values(**values))

    def runtime_values(self, job_id: str) -> Mapping[str, Any]:
        """只使用创建时冻结的预算，重试和恢复不能改变执行条件。"""
        with self.engine.connect() as connection:
            snapshot = connection.execute(
                select(Job.config_snapshot).where(Job.id == job_id)
            ).scalar_one()
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
            status = connection.execute(
                select(Job.status).where(Job.id == row["id"]).with_for_update()
            ).scalar_one()
            if status in {"canceling", "canceled"}:
                # 转换期间收到取消后不再创建版本或交接解析，外层退出时统一收尾。
                return 0, 0, False
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
                    next_attempt_at=None,
                    dispatch_lease_until=None,
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
                connection.execute(
                    select(Job.run_id, Job.status, Job.stage)
                    .where(Job.id == job_id).with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                return
            if row["status"] in {"canceled", "draining"}:
                return
            if row["status"] == "canceling":
                if row["stage"] == "parsing" or code == "parse_submission_unknown":
                    # 网络故障或未知提交不能证明远端停止；保留占用并等待恢复/人工核对。
                    connection.execute(update(Job).where(Job.id == job_id).values(
                        error_code=code, error_message=message[:2000], updated_at=now,
                        next_attempt_at=now + timedelta(seconds=30), dispatch_lease_until=None,
                    ))
                else:
                    finish_canceled_job(connection, job_id, row["run_id"])
                return
            if row["stage"] == "parsing" or code == "parse_submission_unknown":
                # 本地失败不代表远端已停止；只排空原任务，不再执行或重新提交。
                connection.execute(update(Job).where(Job.id == job_id).values(
                    status="draining", error_code=code, error_message=message[:2000],
                    updated_at=now, next_attempt_at=now + timedelta(seconds=30),
                    dispatch_lease_until=None,
                ))
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
            row = connection.execute(
                select(Job.status, Job.run_id).where(Job.id == job_id).with_for_update()
            ).mappings().one()
            if row["status"] == "canceling":
                # 适配器明确返回未受理的可重试错误，此时取消无需再次提交。
                finish_canceled_job(connection, job_id, row["run_id"])
                return
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
            status = connection.execute(
                select(Job.status).where(Job.id == job_id).with_for_update()
            ).scalar_one()
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
                .where(Job.id == job_id, Job.status.in_(("submitting", "canceling")))
                .values(
                    run_id=run_id,
                    status="canceling" if status == "canceling" else "running",
                    stage="parsing",
                    next_attempt_at=now,
                    dispatch_lease_until=None,
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
                .where(Job.id == job_id, Job.status.in_(("running", "canceling")))
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
                .where(Job.id == job_id, Job.status.in_(("running", "canceling")))
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
            status = connection.execute(
                select(Job.status).where(Job.id == job_id).with_for_update()
            ).scalar_one()
            if status == "canceling":
                # 轮询返回与取消并发时仍以取消为准，不落元素、不发布解析成果。
                finish_canceled_job(connection, job_id, row["run_id"])
                return
            if status == "canceled":
                return
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
