"""抽取详情、尝试链与单字段重跑 API。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Text, case, cast, exists, select, true
from sqlalchemy.orm import aliased

from tender.adapters.pg.models import (
    Document,
    DocumentVersion,
    Evidence,
    Extraction,
    Job,
    ParseRun,
    ProjectFile,
    ReviewAction,
)
from tender.api.common import configs, engine, project_row, start_rerun
from tender.api.errors import ApiProblem
from tender.api.versions import get_extractions
from tender.application.fields import FIELD_BY_KEY
from tender.core import settings

router = APIRouter(prefix="/api/v1", tags=["extractions"])


class RerunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hint: str | None = Field(default=None, max_length=1000)


def _row_for_extraction(request: Request, extraction_id: int) -> dict[str, object]:
    with engine(request).connect() as connection:
        row = (
            connection.execute(
                select(Extraction.version_id, Extraction.instance_id, Extraction.is_current)
                .select_from(Extraction)
                .join(DocumentVersion, DocumentVersion.id == Extraction.version_id)
                .join(Document, Document.id == DocumentVersion.document_id)
                .where(
                    Extraction.id == extraction_id,
                    Document.company_id == settings.company_id(),
                    Document.deleted_at.is_(None),
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise ApiProblem(404, "not_found", "抽取结果不存在")
    return dict(row)


@router.get("/extractions/{extraction_id}")
def get_extraction(extraction_id: int, request: Request) -> dict[str, object]:
    row = _row_for_extraction(request, extraction_id)
    items = get_extractions(int(row["version_id"]), request)["items"]
    extraction = next((item for item in items if item["id"] == extraction_id), None)
    if extraction is None:
        raise ApiProblem(404, "not_found", "当前结果不存在")
    return extraction


@router.get("/extractions/{extraction_id}/attempts")
def get_attempts(extraction_id: int, request: Request) -> dict[str, object]:
    selected = _row_for_extraction(request, extraction_id)
    instance_id = int(selected["instance_id"])
    newer = aliased(Extraction)
    latest_action = (
        select(ReviewAction.action.label("action"))
        .where(ReviewAction.attempt_id == Extraction.id)
        .order_by(ReviewAction.created_at.desc(), ReviewAction.id.desc())
        .limit(1)
        .correlate(Extraction)
        .lateral("ra")
    )
    superseded = (
        select(newer.id.label("id"))
        .where(newer.supersedes_id == Extraction.id)
        .order_by(newer.attempt_no.desc(), newer.id.desc())
        .limit(1)
        .correlate(Extraction)
        .lateral("superseded")
    )
    with engine(request).connect() as connection:
        rows = (
            connection.execute(
                select(
                    Extraction.id,
                    Extraction.instance_id,
                    Extraction.run_id,
                    Extraction.attempt_no,
                    Extraction.machine_attempt_no,
                    Extraction.trigger,
                    Extraction.hint,
                    Extraction.field_key,
                    Extraction.group_key,
                    Extraction.value_json,
                    Extraction.value_text,
                    Extraction.confidence,
                    Extraction.status,
                    Extraction.strategy,
                    Extraction.evidence_count,
                    Extraction.is_current,
                    Extraction.created_at,
                    latest_action.c.action.label("review_action"),
                    superseded.c.id.label("superseded_by_id"),
                )
                .select_from(Extraction)
                .outerjoin(latest_action, true())
                .outerjoin(superseded, true())
                .where(Extraction.instance_id == instance_id)
                .order_by(Extraction.attempt_no.desc())
            )
            .mappings()
            .all()
        )
        evidence_rows = (
            (
                connection.execute(
                    select(
                        Evidence.extraction_id,
                        Evidence.seq,
                        Evidence.anchor,
                        Evidence.page_no,
                        Evidence.bbox_x0,
                        Evidence.bbox_y0,
                        Evidence.bbox_x1,
                        Evidence.bbox_y1,
                        Evidence.char_start,
                        Evidence.char_end,
                        Evidence.quote,
                        Evidence.quote_source,
                        Evidence.match_type,
                    )
                    .where(Evidence.extraction_id.in_([int(row["id"]) for row in rows]))
                    .order_by(Evidence.extraction_id, Evidence.seq)
                )
                .mappings()
                .all()
            )
            if rows
            else []
        )
    evidence_by_id: dict[int, list[dict[str, object]]] = {}
    for evidence in evidence_rows:
        values = (
            evidence["bbox_x0"],
            evidence["bbox_y0"],
            evidence["bbox_x1"],
            evidence["bbox_y1"],
        )
        evidence_by_id.setdefault(int(evidence["extraction_id"]), []).append(
            {
                "anchor": evidence["anchor"],
                "page_no": evidence["page_no"],
                "bbox": [float(value) for value in values]
                if all(value is not None for value in values)
                else None,
                "char_start": evidence["char_start"],
                "char_end": evidence["char_end"],
                "quote": evidence["quote"],
                "quote_source": evidence["quote_source"],
                "match_type": evidence["match_type"],
            }
        )
    items: list[dict[str, object]] = []
    for row in rows:
        status = str(row["status"])
        if row["review_action"] == "confirm":
            status = "verified"
        elif row["review_action"] == "reject":
            status = "rejected"
        items.append(
            {
                "id": row["id"],
                "instance_id": row["instance_id"],
                "run_id": row["run_id"],
                "attempt_no": row["attempt_no"],
                "machine_attempt_no": row["machine_attempt_no"],
                "trigger": row["trigger"],
                "hint": row["hint"],
                "field_key": row["field_key"],
                "group_key": row["group_key"],
                "value": row["value_json"],
                "value_text": row["value_text"],
                "confidence": float(row["confidence"] or 0),
                "status": status,
                "strategy": row["strategy"],
                "evidence_count": row["evidence_count"],
                "is_current": row["is_current"],
                "review_action": row["review_action"],
                "superseded_by_id": row["superseded_by_id"],
                "created_at": row["created_at"],
                "evidence": evidence_by_id.get(int(row["id"]), []),
            }
        )
    return {"instance_id": instance_id, "items": items, "total": len(items)}


@router.post("/extractions/{extraction_id}/rerun", status_code=202)
def rerun_extraction(
    extraction_id: int,
    payload: RerunRequest,
    request: Request,
) -> dict[str, object]:
    db = engine(request)
    hint = payload.hint.strip() if payload.hint and payload.hint.strip() else None
    actor = request.headers.get("x-actor", "local-user")[:200]
    return start_rerun(db, configs(request), extraction_id, hint=hint, actor=actor)


class ProjectRerunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 空列表 = 全部字段类型；指定了就只重跑这些字段。
    field_keys: list[str] = Field(default_factory=list, max_length=100)
    only_failed: bool = False
    hint: str | None = Field(default=None, max_length=1000)
    # 默认 50：一次点到几百条会把队列与模型配额一起打满，宁可让调用方分批。
    limit: int = Field(default=50, ge=1, le=200)


@router.post("/projects/{project_id}/rerun", status_code=202)
def rerun_project(
    project_id: int,
    payload: ProjectRerunRequest,
    request: Request,
) -> dict[str, object]:
    """项目级批量重跑：按字段类型 / 仅失败项筛出当前结果，逐条排重跑任务。

    单条冲突不拖垮整批：已有在途重跑的实例计进 skipped，其余校验错误照常抛出。
    """
    unknown = sorted({key for key in payload.field_keys if key not in FIELD_BY_KEY})
    if unknown:
        raise ApiProblem(400, "invalid_argument", f"未知字段：{', '.join(unknown)}")
    db = engine(request)
    project_row(db, project_id)
    hint = payload.hint.strip() if payload.hint and payload.hint.strip() else None
    actor = request.headers.get("x-actor", "local-user")[:200]
    with db.connect() as connection:
        pf = (
            select(ProjectFile.id.label("id"))
            .where(
                ProjectFile.version_id == Extraction.version_id,
                ProjectFile.project_id == project_id,
                ProjectFile.deleted_at.is_(None),
                ProjectFile.is_parseable.is_(True),
            )
            .order_by(
                case((ProjectFile.role == "main", 0), else_=1),
                ProjectFile.sort_no,
                ProjectFile.id,
            )
            .limit(1)
            .correlate(Extraction)
            .lateral("pf")
        )
        latest = (
            select(ParseRun.id.label("id"))
            .where(ParseRun.version_id == Extraction.version_id)
            .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
            .limit(1)
            .correlate(Extraction)
            .lateral("latest")
        )
        # 字段类型与「仅失败项」都按需拼条件：空列表 / False 等价于原 SQL 里的
        # cardinality(...)=0 与 :only_failed = false 短路。
        conditions = [
            Extraction.is_current.is_(True),
            Document.company_id == settings.company_id(),
            Document.deleted_at.is_(None),
            Extraction.run_id == latest.c.id,
            ParseRun.status.in_(("completed", "partial")),
            ~exists().where(
                Job.status.in_(("pending", "submitting", "running")),
                Job.config_snapshot["instance_id"].as_string()
                == cast(Extraction.instance_id, Text),
            ),
        ]
        if payload.field_keys:
            conditions.append(Extraction.field_key.in_(payload.field_keys))
        if payload.only_failed:
            conditions.append(Extraction.status.in_(("need_review", "conflict", "not_found")))
        candidates = (
            connection.execute(
                select(Extraction.id)
                .select_from(Extraction)
                .join(DocumentVersion, DocumentVersion.id == Extraction.version_id)
                .join(Document, Document.id == DocumentVersion.document_id)
                .join(ParseRun, ParseRun.id == Extraction.run_id)
                .join(pf, true())
                .join(latest, true())
                .where(*conditions)
                .order_by(Extraction.field_key, Extraction.id)
                .limit(payload.limit)
            )
            .scalars()
            .all()
        )
    items: list[dict[str, object]] = []
    skipped = 0
    for extraction_id in candidates:
        try:
            items.append(
                start_rerun(db, configs(request), int(extraction_id), hint=hint, actor=actor)
            )
        except ApiProblem as exc:
            # 候选查询已排除在途实例，这里只兜并发竞态；其他校验错误照常抛出。
            if exc.code != "rerun_in_flight":
                raise
            skipped += 1
    return {
        "project_id": project_id,
        "queued": len(items),
        "skipped": skipped,
        "items": items,
    }
