"""按版本触发首次解析或管理员重新解析。"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, insert, select

from tender.adapters.pg.models import (
    Job,
    ParseRun,
    Project,
    ProjectFile,
)
from tender.api.common import engine, version_row
from tender.api.errors import ApiProblem
from tender.config.schema import parse_options
from tender.core import settings

router = APIRouter(prefix="/api/v1/versions", tags=["parsing"])


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: str | None = None
    ocr_mode: str | None = None
    force: bool = False
    reason: str | None = Field(default=None, max_length=1000)


def _validate(payload: ParseRequest) -> None:
    if payload.tier is not None and payload.tier not in {"flash", "basic", "standard", "advanced"}:
        raise ApiProblem(400, "invalid_argument", "tier 不受支持")
    if payload.ocr_mode is not None and payload.ocr_mode not in {"auto", "txt", "ocr"}:
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
    try:
        options = parse_options(
            active_config.resolved if active_config is not None else {},
            payload.tier,
            payload.ocr_mode,
        )
    except ValueError as exc:
        raise ApiProblem(400, "invalid_argument", str(exc)) from exc
    with db.begin() as connection:
        file_row = (
            connection.execute(
                select(
                    ProjectFile.id.label("project_file_id"),
                    ProjectFile.project_id,
                    ProjectFile.display_name,
                    ProjectFile.is_parseable,
                    Project.company_id,
                )
                .select_from(ProjectFile)
                .join(Project, Project.id == ProjectFile.project_id)
                .where(
                    ProjectFile.version_id == version_id,
                    ProjectFile.deleted_at.is_(None),
                    Project.company_id == settings.company_id(),
                    Project.deleted_at.is_(None),
                )
                .order_by(
                    case((ProjectFile.role == "main", 0), else_=1),
                    ProjectFile.sort_no,
                    ProjectFile.id,
                )
                .limit(1)
                .with_for_update(of=ProjectFile)
            )
            .mappings()
            .first()
        )
        if file_row is None or not file_row["is_parseable"]:
            raise ApiProblem(409, "version_not_parseable", "该版本没有可解析的项目文件")
        active = connection.execute(
            select(Job.id)
            .where(
                Job.version_id == version_id,
                Job.status.in_(("pending", "submitting", "running")),
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if active is not None:
            raise ApiProblem(409, "parse_in_flight", "该版本已有解析任务进行中", retryable=True)
        prior = connection.execute(
            select(ParseRun.id)
            .where(
                ParseRun.version_id == version_id,
                ParseRun.status.in_(("pending", "running", "completed", "partial")),
            )
            .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if prior is not None and not force:
            raise ApiProblem(409, "parse_exists", "该版本已有解析结果；如需重建请使用 force")
        job_id = f"job_{uuid4().hex}"
        snapshot = {
            **options,
            "auto_parse": True,
            "trigger": "reparse" if force else "first",
            "reason": payload.reason.strip() if payload.reason else None,
            "actor": request.headers.get("x-actor", "local-user")[:200],
        }
        snapshot_id = request.app.state.components.configs.snapshot_for_job(
            connection, active_config
        )
        connection.execute(
            insert(Job).values(
                id=job_id,
                company_id=company,
                project_id=file_row["project_id"],
                project_file_id=file_row["project_file_id"],
                version_id=version_id,
                status="pending",
                stage="submitting",
                progress={},
                config_snapshot=snapshot,
                config_snapshot_id=snapshot_id,
            )
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
