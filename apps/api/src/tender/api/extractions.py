"""抽取详情、尝试链与单字段重跑 API。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

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
                text(
                    """SELECT e.version_id, e.instance_id, e.is_current
                       FROM extraction AS e
                       JOIN document_version AS v ON v.id = e.version_id
                       JOIN document AS d ON d.id = v.document_id
                       WHERE e.id = :id AND d.company_id = :company_id
                         AND d.deleted_at IS NULL"""
                ),
                {"id": extraction_id, "company_id": settings.company_id()},
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
    with engine(request).connect() as connection:
        rows = (
            connection.execute(
                text(
                    """SELECT e.id, e.instance_id, e.run_id, e.attempt_no,
                              e.machine_attempt_no, e.trigger, e.hint, e.field_key,
                              e.group_key, e.value_json, e.value_text, e.confidence,
                              e.status, e.strategy, e.evidence_count, e.is_current,
                               e.created_at, ra.action AS review_action,
                               superseded.id AS superseded_by_id
                       FROM extraction AS e
                       LEFT JOIN LATERAL (
                           SELECT action FROM review_action
                           WHERE attempt_id = e.id
                           ORDER BY created_at DESC, id DESC LIMIT 1
                        ) AS ra ON true
                       LEFT JOIN LATERAL (
                           SELECT newer.id
                           FROM extraction AS newer
                           WHERE newer.supersedes_id = e.id
                           ORDER BY newer.attempt_no DESC, newer.id DESC
                           LIMIT 1
                       ) AS superseded ON true
                       WHERE e.instance_id = :instance_id
                       ORDER BY e.attempt_no DESC"""
                ),
                {"instance_id": instance_id},
            )
            .mappings()
            .all()
        )
        evidence_rows = (
            (
                connection.execute(
                    text(
                        """SELECT extraction_id, seq, anchor, page_no, bbox_x0, bbox_y0,
                              bbox_x1, bbox_y1, char_start, char_end, quote,
                              quote_source, match_type
                       FROM evidence
                       WHERE extraction_id = ANY(CAST(:ids AS BIGINT[]))
                       ORDER BY extraction_id, seq"""
                    ),
                    {"ids": [int(row["id"]) for row in rows]},
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
        candidates = (
            connection.execute(
                text(
                    """SELECT e.id
                       FROM extraction AS e
                       JOIN document_version AS v ON v.id = e.version_id
                       JOIN document AS d ON d.id = v.document_id
                       JOIN parse_run AS pr ON pr.id = e.run_id
                       JOIN LATERAL (
                           SELECT project_file.id
                           FROM project_file
                           WHERE project_file.version_id = e.version_id
                             AND project_file.project_id = :project_id
                             AND project_file.deleted_at IS NULL
                             AND project_file.is_parseable = true
                           ORDER BY CASE project_file.role WHEN 'main' THEN 0 ELSE 1 END,
                                    project_file.sort_no, project_file.id
                           LIMIT 1
                       ) AS pf ON true
                       JOIN LATERAL (
                           SELECT id FROM parse_run
                           WHERE version_id = e.version_id
                           ORDER BY created_at DESC, id DESC LIMIT 1
                       ) AS latest ON true
                       WHERE e.is_current = true AND d.company_id = :company_id
                         AND d.deleted_at IS NULL
                         AND e.run_id = latest.id
                         AND pr.status IN ('completed','partial')
                         AND (cardinality(CAST(:field_keys AS TEXT[])) = 0
                              OR e.field_key = ANY(CAST(:field_keys AS TEXT[])))
                         AND (:only_failed = false
                              OR e.status IN ('need_review','conflict','not_found'))
                         AND NOT EXISTS (
                             SELECT 1 FROM job
                             WHERE job.status IN ('pending','submitting','running')
                               AND job.config_snapshot->>'instance_id' = e.instance_id::text
                         )
                       ORDER BY e.field_key, e.id
                       LIMIT :limit"""
                ),
                {
                    "project_id": project_id,
                    "company_id": settings.company_id(),
                    "field_keys": payload.field_keys,
                    "only_failed": payload.only_failed,
                    "limit": payload.limit,
                },
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
