"""按版本触发首次解析或管理员重新解析。"""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from tender.api.common import engine, version_row
from tender.api.errors import ApiProblem
from tender.core import settings

router = APIRouter(prefix="/api/v1/versions", tags=["parsing"])


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: str = Field(default="standard")
    ocr_mode: str = Field(default="auto")
    force: bool = False
    reason: str | None = Field(default=None, max_length=1000)


def _validate(payload: ParseRequest) -> None:
    if payload.tier not in {"flash", "basic", "standard", "advanced"}:
        raise ApiProblem(400, "invalid_argument", "tier 不受支持")
    if payload.ocr_mode not in {"auto", "txt", "ocr"}:
        raise ApiProblem(400, "invalid_argument", "ocr_mode 不受支持")
    if payload.force and not (payload.reason and payload.reason.strip()):
        raise ApiProblem(400, "invalid_argument", "重新解析必须填写 reason")


def _create_parse_job(
    version_id: int,
    payload: ParseRequest,
    request: Request,
    *,
    force: bool,
) -> dict[str, object]:
    db = engine(request)
    version_row(db, version_id)
    company = settings.company_id()
    # 先读活动配置（可能走 Redis 缓存）再开事务：不在事务里等网络。
    active_config = request.app.state.components.configs.active(company)
    with db.begin() as connection:
        file_row = (
            connection.execute(
                text(
                    """SELECT pf.id AS project_file_id, pf.project_id, pf.display_name,
                              pf.is_parseable, p.company_id
                       FROM project_file AS pf
                       JOIN project AS p ON p.id = pf.project_id
                       WHERE pf.version_id = :version_id AND pf.deleted_at IS NULL
                         AND p.company_id = :company_id AND p.deleted_at IS NULL
                       ORDER BY CASE pf.role WHEN 'main' THEN 0 ELSE 1 END,
                                pf.sort_no, pf.id LIMIT 1
                       FOR UPDATE OF pf"""
                ),
                {"version_id": version_id, "company_id": settings.company_id()},
            )
            .mappings()
            .first()
        )
        if file_row is None or not file_row["is_parseable"]:
            raise ApiProblem(409, "version_not_parseable", "该版本没有可解析的项目文件")
        active = connection.execute(
            text(
                """SELECT id FROM job
                   WHERE version_id = :version_id
                     AND status IN ('pending','submitting','running')
                   ORDER BY created_at DESC LIMIT 1"""
            ),
            {"version_id": version_id},
        ).scalar_one_or_none()
        if active is not None:
            raise ApiProblem(409, "parse_in_flight", "该版本已有解析任务进行中", retryable=True)
        prior = connection.execute(
            text(
                """SELECT id FROM parse_run
                   WHERE version_id = :version_id
                     AND status IN ('pending','running','completed','partial')
                   ORDER BY created_at DESC, id DESC LIMIT 1"""
            ),
            {"version_id": version_id},
        ).scalar_one_or_none()
        if prior is not None and not force:
            raise ApiProblem(409, "parse_exists", "该版本已有解析结果；如需重建请使用 force")
        if force:
            # 新 run 会重建锚点；旧结果保留历史但暂时不能继续作为已确认结果展示。
            connection.execute(
                text(
                    """UPDATE extraction AS e SET status = 'need_review', updated_at = now()
                       FROM field_instance AS fi
                       WHERE fi.id = e.instance_id AND e.version_id = :version_id
                         AND e.is_current = true AND e.status = 'verified'"""
                ),
                {"version_id": version_id},
            )
        job_id = f"job_{uuid4().hex}"
        snapshot = {
            "tier": payload.tier,
            "ocr_mode": payload.ocr_mode,
            "auto_parse": True,
            "trigger": "reparse" if force else "first",
            "reason": payload.reason.strip() if payload.reason else None,
            "actor": request.headers.get("x-actor", "local-user")[:200],
        }
        snapshot_id = request.app.state.components.configs.snapshot_for_job(
            connection, active_config
        )
        connection.execute(
            text(
                """INSERT INTO job
                       (id, company_id, project_id, project_file_id, version_id,
                        status, stage, progress, config_snapshot, config_snapshot_id)
                   VALUES
                       (:id, :company_id, :project_id, :project_file_id, :version_id,
                        'pending', 'submitting', '{}'::jsonb, CAST(:snapshot AS JSONB),
                        :config_snapshot_id)"""
            ),
            {
                "id": job_id,
                "company_id": company,
                "project_id": file_row["project_id"],
                "project_file_id": file_row["project_file_id"],
                "version_id": version_id,
                "snapshot": json.dumps(snapshot, ensure_ascii=False),
                "config_snapshot_id": snapshot_id,
            },
        )
    # 这里不再直接投递：闸门在提交侧（worker/dispatch.py），beat 按 parse.max_inflight 差额派发。
    return {
        "job_id": job_id,
        "version_id": version_id,
        "run_id": None,
        "force": force,
        "status": "pending",
    }


@router.post("/{version_id}/parse", status_code=202)
def parse_version(
    version_id: int,
    request: Request,
    payload: ParseRequest,
) -> dict[str, object]:
    _validate(payload)
    return _create_parse_job(version_id, payload, request, force=payload.force)


@router.post("/{version_id}/reparse", status_code=202)
def reparse_version(
    version_id: int,
    request: Request,
    payload: ParseRequest,
) -> dict[str, object]:
    _validate(payload.model_copy(update={"force": True}))
    return _create_parse_job(
        version_id, payload.model_copy(update={"force": True}), request, force=True
    )
