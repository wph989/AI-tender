"""跨文件冲突查看与裁定、项目复核进度统计；裁定走 /api/v1/conflicts/{id}/resolve。"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from tender.api.common import engine, project_row
from tender.api.errors import ApiProblem
from tender.application.fields import FIELD_BY_KEY
from tender.core import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/projects", tags=["project-results"])


class ConflictDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["resolve", "dismiss"]
    resolved_id: int | None = Field(default=None, ge=1)
    comment: str | None = Field(default=None, max_length=2000)


@router.get("/{project_id}/conflicts")
def list_conflicts(project_id: int, request: Request) -> dict[str, object]:
    db = engine(request)
    project_row(db, project_id)
    with db.connect() as connection:
        conflicts = (
            connection.execute(
                text(
                    """SELECT id, field_key, lot_id, candidate_ids, resolved_id,
                              status, created_at
                       FROM extraction_conflict
                       WHERE project_id = :project_id
                       ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END,
                                created_at DESC, id DESC"""
                ),
                {"project_id": project_id},
            )
            .mappings()
            .all()
        )
        ids = sorted({int(item) for conflict in conflicts for item in conflict["candidate_ids"]})
        candidates = (
            connection.execute(
                text(
                    """SELECT DISTINCT ON (e.id) e.id, e.version_id, e.field_key,
                              e.value_json, e.value_text, e.confidence, e.status,
                              pf.display_name, pf.role, first_ev.anchor,
                              first_ev.page_no, first_ev.quote
                       FROM extraction AS e
                       JOIN project_file AS pf ON pf.version_id = e.version_id
                       LEFT JOIN LATERAL (
                           SELECT anchor, page_no, quote FROM evidence
                           WHERE extraction_id = e.id ORDER BY seq LIMIT 1
                       ) AS first_ev ON true
                       WHERE e.id = ANY(CAST(:ids AS BIGINT[]))
                         AND pf.project_id = :project_id AND pf.deleted_at IS NULL
                         AND NOT EXISTS (
                             SELECT 1 FROM project_file AS replacement
                             WHERE replacement.replaces_id = pf.id
                               AND replacement.deleted_at IS NULL
                         )
                       ORDER BY e.id, pf.id"""
                ),
                {"ids": ids, "project_id": project_id},
            )
            .mappings()
            .all()
            if ids
            else []
        )
    by_id = {int(row["id"]): dict(row) for row in candidates}
    items = []
    for conflict in conflicts:
        field = FIELD_BY_KEY.get(str(conflict["field_key"]))
        items.append(
            {
                "id": conflict["id"],
                "field_key": conflict["field_key"],
                "field_label": field.label if field else conflict["field_key"],
                "lot_id": conflict["lot_id"],
                "candidate_ids": list(conflict["candidate_ids"]),
                "candidates": [
                    by_id[item] for item in conflict["candidate_ids"] if int(item) in by_id
                ],
                "resolved_id": conflict["resolved_id"],
                "status": conflict["status"],
                "created_at": conflict["created_at"],
            }
        )
    return {"items": items, "total": len(items)}


conflicts_router = APIRouter(prefix="/api/v1/conflicts", tags=["conflicts"])


@conflicts_router.post("/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: int,
    payload: ConflictDecision,
    request: Request,
) -> dict[str, object]:
    """裁定冲突；项目从冲突行反查，对外路径不再重复携带项目 ID。

    归属校验与行锁放在同一条 SQL 里：越权与不存在都返回 404，不泄露资源存在性。
    """
    db = engine(request)
    actor = request.headers.get("x-actor", "local-user")[:200]
    with db.begin() as connection:
        conflict = (
            connection.execute(
                text(
                    """SELECT ec.id, ec.project_id, ec.candidate_ids, ec.status
                       FROM extraction_conflict AS ec
                       JOIN project AS p ON p.id = ec.project_id
                       WHERE ec.id = :conflict_id AND p.company_id = :company_id
                         AND p.deleted_at IS NULL
                       FOR UPDATE OF ec"""
                ),
                {"conflict_id": conflict_id, "company_id": settings.company_id()},
            )
            .mappings()
            .first()
        )
        if conflict is None:
            raise ApiProblem(404, "not_found", "冲突记录不存在")
        if conflict["status"] != "open":
            raise ApiProblem(409, "conflict_resolved", "该冲突已处理")
        resolved_id = payload.resolved_id
        if payload.action == "resolve":
            if resolved_id is None or resolved_id not in conflict["candidate_ids"]:
                raise ApiProblem(400, "invalid_argument", "裁定结果必须来自冲突候选项")
            status = "resolved"
        else:
            if resolved_id is not None:
                raise ApiProblem(400, "invalid_argument", "dismiss 不接受 resolved_id")
            status = "dismissed"
        connection.execute(
            text(
                """UPDATE extraction_conflict SET status = :status, resolved_id = :resolved_id
                   WHERE id = :conflict_id"""
            ),
            {"status": status, "resolved_id": resolved_id, "conflict_id": conflict_id},
        )
    logger.info(
        "项目冲突已裁定",
        extra={
            "project_id": conflict["project_id"],
            "conflict_id": conflict_id,
            "actor": actor,
            "action": payload.action,
            "resolved_id": resolved_id,
            "comment": payload.comment,
        },
    )
    return {"id": conflict_id, "status": status, "resolved_id": resolved_id}


@router.get("/{project_id}/stats")
def project_stats(project_id: int, request: Request) -> dict[str, object]:
    db = engine(request)
    project_row(db, project_id)
    with db.connect() as connection:
        totals = (
            connection.execute(
                text(
                    """SELECT count(DISTINCT ra.instance_id) AS reviewed,
                              count(*) FILTER (WHERE ra.action = 'confirm') AS confirmed,
                              count(*) FILTER (WHERE ra.action = 'correct') AS corrected,
                              count(*) FILTER (WHERE ra.action = 'supplement') AS supplemented
                       FROM review_action AS ra
                       JOIN field_instance AS fi ON fi.id = ra.instance_id
                       JOIN document_version AS v ON v.id = fi.version_id
                       JOIN project_file AS pf ON pf.version_id = v.id
                       WHERE pf.project_id = :project_id AND pf.deleted_at IS NULL"""
                ),
                {"project_id": project_id},
            )
            .mappings()
            .one()
        )
        pending = int(
            connection.execute(
                text(
                    """SELECT count(*) FROM review_task AS rt
                       JOIN extraction AS e ON e.id = rt.extraction_id AND e.is_current = true
                       JOIN document_version AS v ON v.id = e.version_id
                       JOIN project_file AS pf ON pf.version_id = v.id
                       WHERE pf.project_id = :project_id AND pf.deleted_at IS NULL
                         AND rt.status = 'open'"""
                ),
                {"project_id": project_id},
            ).scalar_one()
        )
        review_rows = (
            connection.execute(
                text(
                    """SELECT fi.id AS instance_id, e.machine_attempt_no, ra.action, ra.review_mode
                       FROM review_action AS ra
                       JOIN extraction AS e ON e.id = ra.attempt_id
                       JOIN field_instance AS fi ON fi.id = ra.instance_id
                       JOIN document_version AS v ON v.id = e.version_id
                       JOIN project_file AS pf ON pf.version_id = v.id
                       WHERE pf.project_id = :project_id AND pf.deleted_at IS NULL
                         AND e.machine_attempt_no IS NOT NULL"""
                ),
                {"project_id": project_id},
            )
            .mappings()
            .all()
        )
    reviewed = int(totals["reviewed"] or 0)
    confirmed = int(totals["confirmed"] or 0)
    corrected = int(totals["corrected"] or 0)
    supplemented = int(totals["supplemented"] or 0)
    first_success: dict[int, int] = {}
    for row in review_rows:
        if row["action"] != "confirm":
            continue
        instance_id = int(row["instance_id"])
        attempt_no = int(row["machine_attempt_no"])
        first_success[instance_id] = min(first_success.get(instance_id, attempt_no), attempt_no)
    cumulative = {}
    for attempt_no in range(1, 6):
        passed = sum(success_at <= attempt_no for success_at in first_success.values())
        cumulative[str(attempt_no)] = round(passed / reviewed, 4) if reviewed else 0.0
    by_mode: dict[str, int] = {"item": 0, "batch": 0, "spot_check": 0}
    for row in review_rows:
        if row["review_mode"] in by_mode:
            by_mode[str(row["review_mode"])] += 1
    return {
        "reviewed": reviewed,
        "confirmed": confirmed,
        "corrected": corrected,
        "supplemented": supplemented,
        "pending_review": pending,
        "cumulative_pass": cumulative,
        "manual_fallback_rate": round((corrected + supplemented) / reviewed, 4)
        if reviewed
        else 0.0,
        "by_review_mode": by_mode,
    }
