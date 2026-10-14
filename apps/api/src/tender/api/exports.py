"""项目抽取结果 Excel 导出；大结果集使用持久任务避免占用 API 请求。"""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import any_, case, exists, insert, select, true
from sqlalchemy.orm import aliased

from tender.adapters.pg.models import (
    Document,
    DocumentVersion,
    Evidence,
    Extraction,
    ExtractionConflict,
    FieldInstance,
    Job,
    Lot,
    ProjectFile,
    ReviewAction,
)
from tender.api.common import engine, project_row
from tender.api.errors import ApiProblem
from tender.api.storage import content_disposition
from tender.application.exporting import workbook_bytes
from tender.core import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/projects", tags=["exports"])
_XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _export_rows(
    connection: object,
    project_id: int,
    company_id: int,
    lot_id: int | None,
    include: str,
    limit: int,
) -> list[dict[str, object]]:
    # effective CTE：把「是否冲突 / 是否已复核」折算成 effective_status。
    # 只取外层用得到的列，不再 e.* —— extraction 与 field_instance 都有 lot_id，
    # 原 SQL 的 e.* + fi.lot_id 会让 effective.lot_id 变成歧义列（指定标段导出时必报错）。
    latest_action = (
        select(ReviewAction.action.label("action"))
        .where(ReviewAction.attempt_id == Extraction.id)
        .order_by(ReviewAction.created_at.desc(), ReviewAction.id.desc())
        .limit(1)
        .correlate(Extraction)
        .lateral("ra")
    )
    open_conflict = exists().where(
        ExtractionConflict.project_id == project_id,
        ExtractionConflict.status == "open",
        ExtractionConflict.field_key == Extraction.field_key,
        ExtractionConflict.lot_id.is_not_distinct_from(FieldInstance.lot_id),
        Extraction.id == any_(ExtractionConflict.candidate_ids),
    )
    effective = (
        select(
            Extraction.id,
            Extraction.version_id,
            Extraction.instance_id,
            Extraction.field_key,
            Extraction.group_key,
            Extraction.value_text,
            Extraction.confidence,
            Extraction.machine_attempt_no,
            Extraction.is_current,
            FieldInstance.lot_id,
            Lot.code.label("lot_code"),
            case(
                (open_conflict, "conflict"),
                (latest_action.c.action == "confirm", "verified"),
                (latest_action.c.action == "reject", "rejected"),
                else_=Extraction.status,
            ).label("effective_status"),
        )
        .select_from(Extraction)
        .join(FieldInstance, FieldInstance.id == Extraction.instance_id)
        .outerjoin(Lot, Lot.id == FieldInstance.lot_id)
        .outerjoin(latest_action, true())
        .cte("effective")
    )
    # file LATERAL：挑该版本唯一未被替代的文件；deleted_at 一起取出，
    # 由外层过滤，等价于原 SQL 里 LATERAL 选行 + WHERE file.deleted_at IS NULL。
    replacement = aliased(ProjectFile)
    file_lat = (
        select(
            ProjectFile.display_name.label("display_name"),
            ProjectFile.deleted_at.label("deleted_at"),
        )
        .where(
            ProjectFile.version_id == effective.c.version_id,
            ProjectFile.project_id == project_id,
            ~exists().where(
                replacement.replaces_id == ProjectFile.id,
                replacement.deleted_at.is_(None),
            ),
        )
        .order_by(
            case((ProjectFile.role == "main", 0), else_=1),
            ProjectFile.sort_no,
            ProjectFile.id,
        )
        .limit(1)
        .correlate(effective)
        .lateral("file")
    )
    review_lat = (
        select(ReviewAction.comment.label("comment"))
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
        Document.company_id == company_id,
        Document.deleted_at.is_(None),
        file_lat.c.deleted_at.is_(None),
        effective.c.is_current.is_(True),
    ]
    if lot_id is not None:
        conditions.append(effective.c.lot_id == lot_id)
    if include == "review":
        conditions.append(
            effective.c.effective_status.in_(("need_review", "conflict", "not_found"))
        )
    elif include == "verified":
        conditions.append(effective.c.effective_status == "verified")
    rows = (
        connection.execute(  # type: ignore[attr-defined]
            select(
                effective.c.field_key,
                effective.c.group_key,
                effective.c.value_text,
                effective.c.lot_code,
                effective.c.confidence,
                effective.c.effective_status.label("status"),
                effective.c.machine_attempt_no,
                file_lat.c.display_name,
                Evidence.page_no,
                Evidence.quote,
                review_lat.c.comment,
            )
            .select_from(effective)
            .join(DocumentVersion, DocumentVersion.id == effective.c.version_id)
            .join(Document, Document.id == DocumentVersion.document_id)
            .join(file_lat, true())
            .outerjoin(Evidence, Evidence.extraction_id == effective.c.id)
            .outerjoin(review_lat, true())
            .where(*conditions)
            .order_by(
                effective.c.group_key,
                effective.c.field_key,
                effective.c.id,
                Evidence.seq,
            )
            .limit(limit)
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


# response_model=None：这个端点既可能返回 xlsx 流、也可能返回排队用的 JSON，
# 联合返回标注会让 FastAPI 在装配路由时就报错（同类写法不要再出现）。
@router.get("/{project_id}/export", response_model=None)
def export_project(
    project_id: int,
    request: Request,
    format: str = Query(default="xlsx"),
    include: str = Query(default="all"),
    lot: str = Query(default="all"),
) -> Response | dict[str, object]:
    if format != "xlsx" or include not in {"all", "review", "verified"}:
        raise ApiProblem(400, "invalid_argument", "仅支持 xlsx，include 支持 all、review、verified")
    db = engine(request)
    project = project_row(db, project_id)
    lot_id: int | None = None
    if lot != "all":
        if not lot.isdecimal() or int(lot) < 1:
            raise ApiProblem(400, "invalid_argument", "lot 必须是 all 或正整数标段 ID")
        lot_id = int(lot)
        with db.connect() as connection:
            belongs = connection.execute(
                select(Lot.id).where(Lot.id == lot_id, Lot.project_id == project_id)
            ).scalar_one_or_none()
        if belongs is None:
            raise ApiProblem(404, "not_found", "标段不存在")
    with db.connect() as connection:
        rows = _export_rows(
            connection,
            project_id,
            settings.company_id(),
            lot_id,
            include,
            2001,
        )
    actor = request.headers.get("x-actor", "local-user")[:200]
    if len(rows) > 2000:
        with db.connect() as connection:
            file_row = (
                connection.execute(
                    select(ProjectFile.id, ProjectFile.version_id)
                    .where(ProjectFile.project_id == project_id, ProjectFile.deleted_at.is_(None))
                    .order_by(ProjectFile.sort_no, ProjectFile.id)
                    .limit(1)
                )
                .mappings()
                .first()
            )
        if file_row is None:
            raise ApiProblem(409, "export_unavailable", "项目没有可用于排队的文件")
        job_id = uuid4().hex
        snapshot = {
            "mode": "export",
            "include": include,
            "lot_id": lot_id,
            "actor": actor,
            "output_key": None,
        }
        # 先读活动配置（可能走 Redis 缓存）再开事务：不在事务里等网络。
        active_config = request.app.state.components.configs.active(settings.company_id())
        with db.begin() as connection:
            snapshot_id = request.app.state.components.configs.snapshot_for_job(
                connection, active_config
            )
            connection.execute(
                insert(Job).values(
                    id=job_id,
                    company_id=settings.company_id(),
                    project_id=project_id,
                    project_file_id=file_row["id"],
                    version_id=file_row["version_id"],
                    status="pending",
                    stage="exporting",
                    progress={"stage": "exporting"},
                    config_snapshot=snapshot,
                    config_snapshot_id=snapshot_id,
                )
            )
        logger.info(
            "项目 Excel 导出已排队",
            extra={"project_id": project_id, "job_id": job_id, "actor": actor, "rows": len(rows)},
        )
        return {"job_id": job_id, "status": "pending", "rows_previewed": len(rows)}

    file_name = f"{project['name']}-抽取结果.xlsx"
    body = workbook_bytes(rows)
    logger.info(
        "项目 Excel 导出完成",
        extra={"project_id": project_id, "actor": actor, "rows": len(rows)},
    )
    return Response(
        content=body,
        media_type=_XLSX_TYPE,
        headers={"Content-Disposition": content_disposition(file_name, inline=False)},
    )
