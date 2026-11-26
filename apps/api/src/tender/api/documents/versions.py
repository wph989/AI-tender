"""版本文件、页面元素、抽取结果与锚点反查接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from tender.api.shared.common import blobs, engine
from tender.api.shared.responses import (
    AnchorResponse,
    AnchorsResponse,
    ElementsResponse,
    OutlineResponse,
    PagesResponse,
    VersionResponse,
)
from tender.api.shared.storage import stream_object
from tender.application.documents.versions import VersionService
from tender.core import settings
from tender.core.di import create_version_service

router = APIRouter(prefix="/api/v1/versions", tags=["versions"])


def _service(request: Request) -> VersionService:
    return create_version_service(engine(request), settings.company_id())


@router.get("/{version_id}/file", response_model=None)
def get_pdf(version_id: int, request: Request) -> Response:
    target = _service(request).pdf(version_id)
    return stream_object(
        blobs(request),
        target["key"],
        target["filename"],
        target["content_type"],
        request.headers.get("range"),
        inline=True,
    )


@router.get("/{version_id}/original", response_model=None)
def get_original(version_id: int, request: Request) -> Response:
    target = _service(request).original(version_id)
    return stream_object(
        blobs(request),
        target["key"],
        target["filename"],
        target["content_type"],
        request.headers.get("range"),
        inline=False,
    )


@router.get("/{version_id}/pages", response_model=PagesResponse)
def get_pages(
    version_id: int,
    request: Request,
    from_page: int = Query(default=1, alias="from", ge=1),
    to_page: int | None = Query(default=None, alias="to", ge=1),
) -> dict[str, object]:
    return _service(request).pages(version_id, from_page=from_page, to_page=to_page)

@router.get("/{version_id}/elements", response_model=ElementsResponse)
def get_elements(
    version_id: int,
    request: Request,
    parse_run_id: int | None = None,
) -> dict[str, object]:
    return _service(request).elements(version_id, parse_run_id)


@router.get("/{version_id}/pages/{page_no}/elements", response_model=ElementsResponse)
def get_page_elements(
    version_id: int,
    page_no: int,
    request: Request,
    parse_run_id: int | None = None,
) -> dict[str, object]:
    return _service(request).page_elements(version_id, page_no, parse_run_id)


@router.get("/{version_id}/anchors/{anchor}", response_model=AnchorResponse)
def resolve_anchor(
    version_id: int,
    anchor: str,
    request: Request,
    parse_run_id: int | None = None,
) -> dict[str, object]:
    return _service(request).anchor(version_id, anchor, parse_run_id)


@router.get("/{version_id}", response_model=VersionResponse)
def get_version(version_id: int, request: Request) -> dict[str, object]:
    """版本详情保留解析批次和失败原因，供文档预览判断可读状态。"""
    return _service(request).detail(version_id)


@router.get("/{version_id}/outline", response_model=OutlineResponse)
def get_outline(
    version_id: int,
    request: Request,
    parse_run_id: int | None = None,
) -> dict[str, object]:
    return _service(request).outline(version_id, parse_run_id)


class AnchorResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parse_run_id: int | None = Field(default=None, ge=1)
    # 上限 200：批量反查是给前端一次性建索引用的，不做无界查询。
    anchors: list[str] = Field(min_length=1, max_length=200)


@router.post("/{version_id}/anchors/resolve", response_model=AnchorsResponse)
def resolve_anchors(
    version_id: int,
    payload: AnchorResolveRequest,
    request: Request,
) -> dict[str, object]:
    """批量锚点反查；查不到的锚点列进 missing，不整批 404。"""
    return _service(request).resolve_anchors(
        version_id,
        payload.anchors,
        payload.parse_run_id,
    )
