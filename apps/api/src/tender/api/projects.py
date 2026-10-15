"""项目元数据与列表接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, insert, or_, select, true, update
from sqlalchemy.orm import aliased
from starlette.responses import Response

from tender.adapters.pg.models import (
    DocumentVersion,
    Job,
    Lot,
    ParseRun,
    Project,
    ProjectFile,
)
from tender.adapters.pg.repositories.knowledge import ensure_project_collection
from tender.api.common import engine, project_row
from tender.api.errors import ApiProblem
from tender.core import settings

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    project_no: str | None = Field(default=None, max_length=200)
    owner: str | None = Field(default=None, max_length=200)


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    project_no: str | None = Field(default=None, max_length=200)
    owner: str | None = Field(default=None, max_length=200)


@router.post("", status_code=201)
def create_project(payload: ProjectCreate, request: Request) -> dict[str, object]:
    name = payload.name.strip()
    if not name:
        raise ApiProblem(400, "invalid_argument", "项目名称不能为空")
    with engine(request).begin() as connection:
        row = (
            connection.execute(
                insert(Project)
                .values(
                    company_id=settings.company_id(),
                    name=name,
                    project_no=payload.project_no,
                    owner=payload.owner,
                )
                .returning(
                    Project.id,
                    Project.company_id,
                    Project.name,
                    Project.project_no,
                    Project.owner,
                    Project.status,
                    Project.created_at,
                )
            )
            .mappings()
            .one()
        )
        ensure_project_collection(connection, int(row["id"]))
    return dict(row)


@router.get("")
def list_projects(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    keyword: str | None = None,
) -> dict[str, object]:
    # 文件数与处理失败数直接决定项目列表的状态，
    # 让前端逐个项目再发一次请求去数，列表一屏就是十几个请求。
    company = settings.company_id()
    agg_owner = aliased(Project)
    job_owner = aliased(Project)
    # 子查询里就要按 company_id 过滤：只在外层过滤的话，
    # 这个聚合仍会把其它公司的 project_file 整表扫一遍再丢掉。
    latest_parse = (
        select(ParseRun.status.label("status"))
        .where(ParseRun.version_id == ProjectFile.version_id)
        .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
        .limit(1)
        .correlate(ProjectFile)
        .lateral("latest_parse")
    )
    # 旧任务账仍保留；列表只读取文档流水线，不能把退役任务的取消状态当成解析失败。
    latest_job = (
        select(Job.status.label("status"))
        .where(
            Job.project_file_id == ProjectFile.id,
            Job.stage.in_(
                ("converting", "probing", "geometry", "submitting", "parsing", "resubmitting")
            ),
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
        .correlate(ProjectFile)
        .lateral("latest_job")
    )
    agg = (
        select(
            ProjectFile.project_id,
            func.count(func.distinct(ProjectFile.id)).label("file_count"),
            func.max(ProjectFile.created_at).label("last_file_at"),
            # 解析或转换失败的文件需要在列表提示，不能被已有版本掩盖。
            func.count(func.distinct(ProjectFile.id))
            .filter(
                or_(
                    latest_parse.c.status == "failed",
                    latest_job.c.status.in_(("failed", "canceled")),
                )
            )
            .label("failed_count"),
        )
        .select_from(ProjectFile)
        .join(agg_owner, agg_owner.id == ProjectFile.project_id)
        .outerjoin(latest_parse, true())
        .outerjoin(latest_job, true())
        .where(
            ProjectFile.deleted_at.is_(None),
            agg_owner.company_id == company,
            agg_owner.deleted_at.is_(None),
        )
        .group_by(ProjectFile.project_id)
        .subquery("agg")
    )
    # job 上没有 company_id，只能经由 project 收窄：不圈定范围的话，
    # 每次刷新列表都会把全部公司的任务整表聚合一遍。
    act = (
        select(Job.project_id, func.max(Job.updated_at).label("last_job_at"))
        .join(job_owner, job_owner.id == Job.project_id)
        .where(
            job_owner.company_id == company, job_owner.deleted_at.is_(None),
            Job.stage.in_(
                ("converting", "probing", "geometry", "submitting", "parsing", "resubmitting")
            ),
        )
        .group_by(Job.project_id)
        .subquery("act")
    )
    # 「最近活动」= 建项目、文件入库、任务状态更新三者取最大。
    # 只回 created_at 的话，三个月前建、昨天还在跑的项目会排在最后，
    # 而列表页要回答的正是「哪个项目还有活」。GREATEST 忽略 NULL，
    # 所以没有文件或没有任务时自动退回 p.created_at。
    last_activity = func.greatest(Project.created_at, agg.c.last_file_at, act.c.last_job_at).label(
        "last_activity_at"
    )
    query = (
        select(
            Project.id,
            Project.company_id,
            Project.name,
            Project.project_no,
            Project.owner,
            Project.status,
            Project.created_at,
            func.coalesce(agg.c.file_count, 0).label("file_count"),
            func.coalesce(agg.c.failed_count, 0).label("failed_count"),
            last_activity,
        )
        .select_from(Project)
        .outerjoin(agg, agg.c.project_id == Project.id)
        .outerjoin(act, act.c.project_id == Project.id)
        .where(
            Project.company_id == company,
            Project.deleted_at.is_(None),
            Project.kind == "project",
        )
    )
    if keyword and keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.where(or_(Project.name.ilike(pattern), Project.project_no.ilike(pattern)))
    # 按「最近活动」倒序：这一列既然摆在行里，排序就得跟着它走，
    # 否则用户按那一列找「谁刚动过」时会以为排序坏了。
    query = query.order_by(last_activity.desc(), Project.id.desc()).limit(limit).offset(offset)
    with engine(request).connect() as connection:
        rows = connection.execute(query).mappings().all()
    return {"items": [dict(row) for row in rows], "offset": offset, "limit": limit}


@router.get("/{project_id}")
def get_project(project_id: int, request: Request) -> dict[str, object]:
    db = engine(request)
    project = dict(project_row(db, project_id))
    # tier 与 ocr_mode 一起带上：重新解析要沿用「上次是怎么跑的」，
    # 否则文件管理页发出的重新解析会把 advanced/ocr 静默降回默认档。
    latest = (
        select(
            ParseRun.id.label("id"),
            ParseRun.status.label("status"),
            ParseRun.tier.label("tier"),
            ParseRun.config_snapshot["ocr_mode"].as_string().label("ocr_mode"),
        )
        .where(ParseRun.version_id == DocumentVersion.id)
        .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
        .limit(1)
        .correlate(DocumentVersion)
        .lateral("latest")
    )
    newer = aliased(ProjectFile)
    replacement = (
        select(newer.id.label("id"))
        .where(newer.replaces_id == ProjectFile.id, newer.deleted_at.is_(None))
        .order_by(newer.created_at.desc(), newer.id.desc())
        .limit(1)
        .correlate(ProjectFile)
        .lateral("replacement")
    )
    # 转换和解析排队时尚无 parse_run，必须返回任务才能驱动前端轮询。
    latest_job = (
        select(
            Job.id.label("id"),
            Job.status.label("status"),
            Job.stage.label("stage"),
            Job.progress.label("progress"),
            Job.error_code.label("error_code"),
            Job.error_message.label("error_message"),
        )
        .where(
            Job.project_file_id == ProjectFile.id,
            Job.stage.in_(
                ("converting", "probing", "geometry", "submitting", "parsing", "resubmitting")
            ),
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
        .correlate(ProjectFile)
        .lateral("latest_job")
    )
    with db.connect() as connection:
        files = (
            connection.execute(
                select(
                    ProjectFile.id.label("project_file_id"),
                    ProjectFile.project_id,
                    ProjectFile.version_id,
                    ProjectFile.role,
                    ProjectFile.display_name,
                    ProjectFile.is_parseable,
                    ProjectFile.replaces_id,
                    ProjectFile.sort_no,
                    ProjectFile.created_at,
                    ProjectFile.sha256,
                    ProjectFile.mime,
                    ProjectFile.size_bytes,
                    DocumentVersion.page_count,
                    latest.c.status.label("parse_status"),
                    latest.c.tier.label("parse_tier"),
                    latest.c.ocr_mode.label("parse_ocr_mode"),
                    latest.c.id.label("latest_run_id"),
                    replacement.c.id.label("replaced_by_id"),
                    latest_job.c.id.label("latest_job_id"),
                    latest_job.c.status.label("latest_job_status"),
                    latest_job.c.stage.label("latest_job_stage"),
                    latest_job.c.progress.label("latest_job_progress"),
                    latest_job.c.error_code.label("latest_job_error_code"),
                    latest_job.c.error_message.label("latest_job_error_message"),
                )
                .select_from(ProjectFile)
                .join(Project, Project.id == ProjectFile.project_id)
                .outerjoin(DocumentVersion, DocumentVersion.id == ProjectFile.version_id)
                .outerjoin(latest, true())
                .outerjoin(replacement, true())
                .outerjoin(latest_job, true())
                .where(
                    ProjectFile.project_id == project_id,
                    ProjectFile.deleted_at.is_(None),
                    Project.company_id == settings.company_id(),
                    Project.deleted_at.is_(None),
                )
                .order_by(ProjectFile.sort_no, ProjectFile.id)
            )
            .mappings()
            .all()
        )
        lots = (
            connection.execute(
                select(Lot.id, Lot.code, Lot.name, Lot.sort_no)
                .where(Lot.project_id == project_id)
                .order_by(Lot.sort_no, Lot.id)
            )
            .mappings()
            .all()
        )
    file_items = []
    for row in files:
        item = dict(row)
        # 任务字段按列取回后在 Python 侧组装成对象，避免把 jsonb_build_object 塞进 SQL。
        job_id = item.pop("latest_job_id")
        job = {
            "id": job_id,
            "status": item.pop("latest_job_status"),
            "stage": item.pop("latest_job_stage"),
            "progress": item.pop("latest_job_progress"),
            "error_code": item.pop("latest_job_error_code"),
            "error_message": item.pop("latest_job_error_message"),
        }
        item["latest_job"] = None if job_id is None else job
        file_items.append(item)
    return {
        **project,
        "files": file_items,
        "lots": [dict(row) for row in lots],
    }


@router.patch("/{project_id}")
def patch_project(
    project_id: int,
    payload: ProjectPatch,
    request: Request,
) -> dict[str, object]:
    fields = payload.model_fields_set
    if not fields:
        raise ApiProblem(400, "invalid_argument", "至少需要修改一个项目字段")
    values: dict[str, object] = {}
    for field in ("name", "project_no", "owner"):
        if field not in fields:
            continue
        value = getattr(payload, field)
        if field == "name":
            value = value.strip() if isinstance(value, str) else value
            if not value:
                raise ApiProblem(400, "invalid_argument", "项目名称不能为空")
        values[field] = value
    with engine(request).begin() as connection:
        updated = connection.execute(
            update(Project)
            .where(
                Project.id == project_id,
                Project.company_id == settings.company_id(),
                Project.deleted_at.is_(None),
            )
            .values(**values)
        ).rowcount
    if not updated:
        raise ApiProblem(404, "not_found", "项目不存在")
    return get_project(project_id, request)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, request: Request) -> Response:
    with engine(request).begin() as connection:
        updated = connection.execute(
            update(Project)
            .where(
                Project.id == project_id,
                Project.company_id == settings.company_id(),
                Project.deleted_at.is_(None),
            )
            .values(deleted_at=func.now(), status="deleted")
        ).rowcount
    if not updated:
        raise ApiProblem(404, "not_found", "项目不存在")
    return Response(status_code=204)
