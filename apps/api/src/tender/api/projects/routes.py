"""项目元数据与列表接口；业务逻辑全部委托给服务层。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from tender.api.shared.common import engine
from tender.api.shared.errors import as_api_problem
from tender.api.shared.logging import throttle_access_log
from tender.application.projects.service import ProjectService
from tender.application.shared.errors import ServiceError
from tender.core import settings
from tender.core.di import create_project_service

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


def _service(request: Request) -> ProjectService:
    return create_project_service(engine(request), settings.company_id())


@router.post("", status_code=201)
def create_project(payload: ProjectCreate, request: Request) -> dict[str, object]:
    try:
        return _service(request).create(
            name=payload.name,
            project_no=payload.project_no,
            owner=payload.owner,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.get("")
def list_projects(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    keyword: str | None = None,
) -> dict[str, object]:
    try:
        return _service(request).list(offset=offset, limit=limit, keyword=keyword)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.get("/{project_id}")
# 文件管理和文档预览会轮询项目详情，跟进转换与解析进度。
@throttle_access_log()
def get_project(project_id: int, request: Request) -> dict[str, object]:
    try:
        return _service(request).detail(project_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.patch("/{project_id}")
def patch_project(
    project_id: int,
    payload: ProjectPatch,
    request: Request,
) -> dict[str, object]:
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}
    try:
        return _service(request).patch(project_id, changes)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, request: Request) -> Response:
    try:
        _service(request).delete(project_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc
    return Response(status_code=204)
