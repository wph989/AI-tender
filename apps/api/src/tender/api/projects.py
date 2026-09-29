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
    query = """SELECT id, company_id, name, project_no, owner, status, created_at
               FROM project
               WHERE company_id = :company_id AND deleted_at IS NULL"""
    params: dict[str, object] = {
        "company_id": settings.company_id(),
        "limit": limit,
        "offset": offset,
    }
    if keyword and keyword.strip():
        query += " AND (name ILIKE :keyword OR project_no ILIKE :keyword)"
        params["keyword"] = f"%{keyword.strip()}%"
    query += " ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset"
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
                          latest.id AS latest_run_id, replacement.id AS replaced_by_id
                   FROM project_file AS pf
                   JOIN project AS p ON p.id = pf.project_id
                   LEFT JOIN document_version AS v ON v.id = pf.version_id
                   LEFT JOIN LATERAL (
                       SELECT pr.id, pr.status
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
