"""跨文件冲突查看与裁定、项目复核进度统计；裁定走 /api/v1/conflicts/{id}/resolve。"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, exists, func, select, true, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import aliased

from tender.adapters.pg.models import (
    DocumentVersion,
    Evidence,
    Extraction,
    ExtractionConflict,
    FieldInstance,
    Project,
    ProjectFile,
    ReviewAction,
    ReviewTask,
)
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
                select(
                    ExtractionConflict.id,
                    ExtractionConflict.field_key,
                    ExtractionConflict.lot_id,
                    ExtractionConflict.candidate_ids,
                    ExtractionConflict.resolved_id,
                    ExtractionConflict.status,
                    ExtractionConflict.created_at,
                )
                .where(ExtractionConflict.project_id == project_id)
                .order_by(
                    case((ExtractionConflict.status == "open", 0), else_=1),
                    ExtractionConflict.created_at.desc(),
                    ExtractionConflict.id.desc(),
                )
            )
            .mappings()
            .all()
        )
        ids = sorted({int(item) for conflict in conflicts for item in conflict["candidate_ids"]})
        first_ev = (
            select(Evidence.anchor, Evidence.page_no, Evidence.quote)
            .where(Evidence.extraction_id == Extraction.id)
            .order_by(Evidence.seq)
            .limit(1)
            .correlate(Extraction)
            .lateral("first_ev")
        )
        replacement = aliased(ProjectFile)
        candidates = (
            (
                connection.execute(
                    select(
                        Extraction.id,
                        Extraction.version_id,
                        Extraction.field_key,
                        Extraction.value_json,
                        Extraction.value_text,
                        Extraction.confidence,
                        Extraction.status,
                        ProjectFile.display_name,
                        ProjectFile.role,
                        first_ev.c.anchor,
                        first_ev.c.page_no,
                        first_ev.c.quote,
                    )
                    .select_from(Extraction)
                    .join(ProjectFile, ProjectFile.version_id == Extraction.version_id)
                    .outerjoin(first_ev, true())
                    .where(
                        Extraction.id.in_(ids),
                        ProjectFile.project_id == project_id,
                        ProjectFile.deleted_at.is_(None),
                        ~exists().where(
                            replacement.replaces_id == ProjectFile.id,
                            replacement.deleted_at.is_(None),
                        ),
                    )
                    .ext(distinct_on(Extraction.id))
                    .order_by(Extraction.id, ProjectFile.id)
                )
                .mappings()
                .all()
            )
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
                select(
                    ExtractionConflict.id,
                    ExtractionConflict.project_id,
                    ExtractionConflict.candidate_ids,
                    ExtractionConflict.status,
                )
                .select_from(ExtractionConflict)
                .join(Project, Project.id == ExtractionConflict.project_id)
                .where(
                    ExtractionConflict.id == conflict_id,
                    Project.company_id == settings.company_id(),
                    Project.deleted_at.is_(None),
                )
                .with_for_update(of=ExtractionConflict)
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
            update(ExtractionConflict)
            .where(ExtractionConflict.id == conflict_id)
            .values(status=status, resolved_id=resolved_id)
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
                select(
                    func.count(func.distinct(ReviewAction.instance_id)).label("reviewed"),
                    func.count().filter(ReviewAction.action == "confirm").label("confirmed"),
                    func.count().filter(ReviewAction.action == "correct").label("corrected"),
                    func.count().filter(ReviewAction.action == "supplement").label("supplemented"),
                )
                .select_from(ReviewAction)
                .join(FieldInstance, FieldInstance.id == ReviewAction.instance_id)
                .join(DocumentVersion, DocumentVersion.id == FieldInstance.version_id)
                .join(ProjectFile, ProjectFile.version_id == DocumentVersion.id)
                .where(ProjectFile.project_id == project_id, ProjectFile.deleted_at.is_(None))
            )
            .mappings()
            .one()
        )
        pending = int(
            connection.execute(
                select(func.count())
                .select_from(ReviewTask)
                .join(
                    Extraction,
                    (Extraction.id == ReviewTask.extraction_id) & Extraction.is_current.is_(True),
                )
                .join(DocumentVersion, DocumentVersion.id == Extraction.version_id)
                .join(ProjectFile, ProjectFile.version_id == DocumentVersion.id)
                .where(
                    ProjectFile.project_id == project_id,
                    ProjectFile.deleted_at.is_(None),
                    ReviewTask.status == "open",
                )
            ).scalar_one()
        )
        review_rows = (
            connection.execute(
                select(
                    FieldInstance.id.label("instance_id"),
                    Extraction.machine_attempt_no,
                    ReviewAction.action,
                    ReviewAction.review_mode,
                )
                .select_from(ReviewAction)
                .join(Extraction, Extraction.id == ReviewAction.attempt_id)
                .join(FieldInstance, FieldInstance.id == ReviewAction.instance_id)
                .join(DocumentVersion, DocumentVersion.id == Extraction.version_id)
                .join(ProjectFile, ProjectFile.version_id == DocumentVersion.id)
                .where(
                    ProjectFile.project_id == project_id,
                    ProjectFile.deleted_at.is_(None),
                    Extraction.machine_attempt_no.is_not(None),
                )
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
