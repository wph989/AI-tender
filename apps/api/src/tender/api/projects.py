"""项目元数据与列表接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from starlette.responses import Response

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
                text(
                    """INSERT INTO project (company_id, name, project_no, owner)
                   VALUES (:company_id, :name, :project_no, :owner)
                   RETURNING id, company_id, name, project_no, owner, status, created_at"""
                ),
                {
                    "company_id": settings.company_id(),
                    "name": name,
                    "project_no": payload.project_no,
                    "owner": payload.owner,
                },
            )
            .mappings()
            .one()
        )
    return dict(row)


@router.get("")
def list_projects(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    keyword: str | None = None,
) -> dict[str, object]:
    # 文件数与待复核数在列表里是决策信息（「这个项目还有没有活要干」），
    # 让前端逐个项目再发一次请求去数，列表一屏就是十几个请求。
    query = """SELECT p.id, p.company_id, p.name, p.project_no, p.owner, p.status,
                      p.created_at,
                      COALESCE(agg.file_count, 0) AS file_count,
                      COALESCE(agg.review_count, 0) AS review_count,
                      COALESCE(agg.failed_count, 0) AS failed_count,
                      -- 「最近活动」= 建项目、文件入库、任务状态更新三者取最大。
                      -- 只回 created_at 的话，三个月前建、昨天还在跑的项目会排在最后，
                      -- 而列表页要回答的正是「哪个项目还有活」。GREATEST 忽略 NULL，
                      -- 所以没有文件或没有任务时自动退回 p.created_at。
                      GREATEST(p.created_at, agg.last_file_at, act.last_job_at) AS last_activity_at
               FROM project AS p
               LEFT JOIN (
                   -- 子查询里就要按 company_id 过滤：只在外层过滤的话，
                   -- 这个聚合仍会把其它公司的 project_file 整表扫一遍再丢掉。
                   SELECT pf.project_id,
                          count(DISTINCT pf.id) AS file_count,
                          count(e.id) FILTER (
                              WHERE e.status IN ('need_review', 'conflict')
                          ) AS review_count,
                          max(pf.created_at) AS last_file_at,
                          -- 失败计数：卷宗脊要能一眼分出「坏了的项目」。只回待复核数的话，
                          -- 解析或抽取挂掉的项目会伪装成「没有待办」，那正是列表页最该报警的一种。
                          count(DISTINCT pf.id) FILTER (
                              WHERE latest_parse.status = 'failed'
                                    OR latest_extract.status IN ('failed', 'canceled')
                                    OR latest_job.status IN ('failed', 'canceled')
                          ) AS failed_count
                   FROM project_file AS pf
                   JOIN project AS agg_owner ON agg_owner.id = pf.project_id
                   LEFT JOIN extraction AS e
                       ON e.version_id = pf.version_id AND e.is_current
                   LEFT JOIN LATERAL (
                       SELECT pr.status
                       FROM parse_run AS pr
                       WHERE pr.version_id = pf.version_id
                       ORDER BY pr.created_at DESC, pr.id DESC LIMIT 1
                   ) AS latest_parse ON true
                   LEFT JOIN LATERAL (
                       SELECT j.status
                       FROM job AS j
                       WHERE j.project_file_id = pf.id AND j.stage = 'extracting'
                       ORDER BY j.created_at DESC, j.id DESC LIMIT 1
                   ) AS latest_extract ON true
                   LEFT JOIN LATERAL (
                       SELECT j.status FROM job AS j
                       WHERE j.project_file_id = pf.id
                       ORDER BY j.created_at DESC, j.id DESC LIMIT 1
                   ) AS latest_job ON true
                   WHERE pf.deleted_at IS NULL
                         AND agg_owner.company_id = :company_id
                         AND agg_owner.deleted_at IS NULL
                   GROUP BY pf.project_id
               ) AS agg ON agg.project_id = p.id
               LEFT JOIN (
                   -- job 上没有 company_id，只能经由 project 收窄：不圈定范围的话，
                   -- 每次刷新列表都会把全部公司的任务整表聚合一遍。
                   SELECT job.project_id, max(job.updated_at) AS last_job_at
                   FROM job
                   JOIN project AS job_owner ON job_owner.id = job.project_id
                   WHERE job_owner.company_id = :company_id
                         AND job_owner.deleted_at IS NULL
                   GROUP BY job.project_id
               ) AS act ON act.project_id = p.id
               WHERE p.company_id = :company_id AND p.deleted_at IS NULL"""
    params: dict[str, object] = {
        "company_id": settings.company_id(),
        "limit": limit,
        "offset": offset,
    }
    if keyword and keyword.strip():
        query += " AND (p.name ILIKE :keyword OR p.project_no ILIKE :keyword)"
        params["keyword"] = f"%{keyword.strip()}%"
    # 按「最近活动」倒序：这一列既然摆在行里，排序就得跟着它走，
    # 否则用户按那一列找「谁刚动过」时会以为排序坏了。
    query += " ORDER BY last_activity_at DESC, p.id DESC LIMIT :limit OFFSET :offset"
    with engine(request).connect() as connection:
        rows = connection.execute(text(query), params).mappings().all()
    return {"items": [dict(row) for row in rows], "offset": offset, "limit": limit}


@router.get("/{project_id}")
def get_project(project_id: int, request: Request) -> dict[str, object]:
    db = engine(request)
    project = dict(project_row(db, project_id))
    with db.connect() as connection:
        files = (
            connection.execute(
                text(
                    """SELECT pf.id AS project_file_id, pf.project_id, pf.version_id,
                          pf.role, pf.display_name, pf.is_parseable, pf.replaces_id,
                          pf.sort_no, pf.created_at, pf.sha256, pf.mime, pf.size_bytes,
                          v.page_count, latest.status AS parse_status,
                          -- tier 与 ocr_mode 一起带上：重新解析要沿用「上次是怎么跑的」，
                          -- 否则文件管理页发出的重新解析会把 advanced/ocr 静默降回默认档。
                          latest.tier AS parse_tier, latest.ocr_mode AS parse_ocr_mode,
                          latest.id AS latest_run_id, replacement.id AS replaced_by_id,
                          COALESCE(result.total, 0) AS extraction_count,
                          COALESCE(result.review_count, 0) AS review_count,
                          -- 已确认条数：重新解析的二次确认要列出「将失效的已确认结果数量」
                          -- （见 docs/质量/09 第 5.2 节），列表页因此必须拿到它。
                          COALESCE(result.confirmed_count, 0) AS confirmed_count,
                          extraction_job.status AS extraction_status,
                          -- 转换和解析排队时尚无 parse_run，必须返回任务才能驱动前端轮询。
                          CASE WHEN latest_job.id IS NULL THEN NULL ELSE
                              jsonb_build_object(
                                  'id', latest_job.id, 'status', latest_job.status,
                                  'stage', latest_job.stage, 'progress', latest_job.progress,
                                  'error_code', latest_job.error_code,
                                  'error_message', latest_job.error_message
                              ) END AS latest_job
                   FROM project_file AS pf
                   JOIN project AS p ON p.id = pf.project_id
                   LEFT JOIN document_version AS v ON v.id = pf.version_id
                   LEFT JOIN LATERAL (
                       SELECT pr.id, pr.status, pr.tier,
                              pr.config_snapshot ->> 'ocr_mode' AS ocr_mode
                       FROM parse_run AS pr
                       WHERE pr.version_id = v.id
                       ORDER BY pr.created_at DESC, pr.id DESC LIMIT 1
                   ) AS latest ON true
                   LEFT JOIN LATERAL (
                       SELECT newer.id
                       FROM project_file AS newer
                       WHERE newer.replaces_id = pf.id AND newer.deleted_at IS NULL
                       ORDER BY newer.created_at DESC, newer.id DESC LIMIT 1
                   ) AS replacement ON true
                   -- 只认 is_current：历史尝试是追溯用的，算进待复核数会让列表永远清不干净
                   LEFT JOIN LATERAL (
                       SELECT count(*) AS total,
                              count(*) FILTER (
                                  WHERE e.status IN ('need_review', 'conflict')
                              ) AS review_count,
                              count(*) FILTER (WHERE e.status = 'verified') AS confirmed_count
                       FROM extraction AS e
                       WHERE e.version_id = pf.version_id AND e.is_current
                   ) AS result ON true
                   -- 抽取是独立 job（stage='extracting'），文件行本身不带状态；
                   -- 不取它的话，抽取失败的文件在列表上看不出和「还没开始」的区别。
                   LEFT JOIN LATERAL (
                       SELECT j.status
                       FROM job AS j
                       WHERE j.project_file_id = pf.id AND j.stage = 'extracting'
                       ORDER BY j.created_at DESC, j.id DESC LIMIT 1
                   ) AS extraction_job ON true
                   LEFT JOIN LATERAL (
                       SELECT j.id, j.status, j.stage, j.progress, j.error_code, j.error_message
                       FROM job AS j
                       WHERE j.project_file_id = pf.id
                       ORDER BY j.created_at DESC, j.id DESC LIMIT 1
                   ) AS latest_job ON true
                   WHERE pf.project_id = :project_id AND pf.deleted_at IS NULL
                     AND p.company_id = :company_id AND p.deleted_at IS NULL
                   ORDER BY pf.sort_no, pf.id"""
                ),
                {"project_id": project_id, "company_id": settings.company_id()},
            )
            .mappings()
            .all()
        )
        lots = (
            connection.execute(
                text(
                    """SELECT id, code, name, sort_no
                   FROM lot WHERE project_id = :project_id ORDER BY sort_no, id"""
                ),
                {"project_id": project_id},
            )
            .mappings()
            .all()
        )
    return {
        **project,
        "files": [dict(row) for row in files],
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
    assignments: list[str] = []
    params: dict[str, object] = {
        "project_id": project_id,
        "company_id": settings.company_id(),
    }
    for field in ("name", "project_no", "owner"):
        if field not in fields:
            continue
        value = getattr(payload, field)
        if field == "name":
            value = value.strip() if isinstance(value, str) else value
            if not value:
                raise ApiProblem(400, "invalid_argument", "项目名称不能为空")
        assignments.append(f"{field} = :{field}")
        params[field] = value
    with engine(request).begin() as connection:
        updated = connection.execute(
            text(
                f"""UPDATE project SET {", ".join(assignments)}
                    WHERE id = :project_id AND company_id = :company_id
                      AND deleted_at IS NULL"""
            ),
            params,
        ).rowcount
    if not updated:
        raise ApiProblem(404, "not_found", "项目不存在")
    return get_project(project_id, request)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, request: Request) -> Response:
    with engine(request).begin() as connection:
        updated = connection.execute(
            text(
                """UPDATE project SET deleted_at = now(), status = 'deleted'
                   WHERE id = :project_id AND company_id = :company_id
                     AND deleted_at IS NULL"""
            ),
            {
                "project_id": project_id,
                "company_id": settings.company_id(),
            },
        ).rowcount
    if not updated:
        raise ApiProblem(404, "not_found", "项目不存在")
    return Response(status_code=204)
