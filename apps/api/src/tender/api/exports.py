"""项目抽取结果 Excel 导出；大结果集使用持久任务避免占用 API 请求。"""

from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import text

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
    clauses = [
        "file.project_id = :project_id",
        "file.deleted_at IS NULL",
        "effective.is_current = true",
    ]
    params: dict[str, object] = {
        "project_id": project_id,
        "company_id": company_id,
        "limit": limit,
    }
    if lot_id is not None:
        clauses.append("effective.lot_id = :lot_id")
        params["lot_id"] = lot_id
    if include == "review":
        clauses.append("effective.effective_status IN ('need_review','conflict','not_found')")
    elif include == "verified":
        clauses.append("effective.effective_status = 'verified'")
    rows = (
        connection.execute(  # type: ignore[attr-defined]
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
                           -- e.* 已含 status，派生复核状态必须另命名，避免查询列歧义。
                           END AS effective_status
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
                       effective.lot_code, effective.confidence,
                       effective.effective_status AS status,
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
                ORDER BY effective.group_key, effective.field_key, effective.id, ev.seq
                LIMIT :limit"""
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
                text("SELECT 1 FROM lot WHERE id = :id AND project_id = :project_id"),
                {"id": lot_id, "project_id": project_id},
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
                    text(
                        """SELECT id, version_id FROM project_file
                           WHERE project_id = :project_id AND deleted_at IS NULL
                           ORDER BY sort_no, id LIMIT 1"""
                    ),
                    {"project_id": project_id},
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
                text(
                    """INSERT INTO job
                           (id, company_id, project_id, project_file_id, version_id,
                            status, stage, progress, config_snapshot, config_snapshot_id)
                       VALUES
                           (:id, :company_id, :project_id, :file_id, :version_id,
                            'pending', 'exporting', CAST(:progress AS JSONB),
                            CAST(:snapshot AS JSONB), :config_snapshot_id)"""
                ),
                {
                    "id": job_id,
                    "company_id": settings.company_id(),
                    "project_id": project_id,
                    "file_id": file_row["id"],
                    "version_id": file_row["version_id"],
                    "progress": json.dumps({"stage": "exporting"}),
                    "snapshot": json.dumps(snapshot, ensure_ascii=False),
                    "config_snapshot_id": snapshot_id,
                },
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
