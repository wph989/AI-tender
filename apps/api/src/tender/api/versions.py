"""版本文件、页面元素、抽取结果与锚点反查接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select
from sqlalchemy.engine import Connection
from starlette.responses import Response

from tender.adapters.pg.models import (
    Element,
    Page,
    ParseRun,
    ProjectFile,
)
from tender.api.common import bbox, engine, version_row
from tender.api.errors import ApiProblem
from tender.api.storage import stream_object
from tender.application.document_outline import build_outline
from tender.domain.anchor import Anchor
from tender.domain.errors import AnchorFormatError

router = APIRouter(prefix="/api/v1/versions", tags=["versions"])


def _latest_run_id(connection: Connection, version_id: int) -> int | None:
    """最近一次可用的解析 run；锚点与章节树都只在 run 内唯一。"""
    return connection.execute(
        select(ParseRun.id)
        .where(ParseRun.version_id == version_id, ParseRun.status.in_(("completed", "partial")))
        .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _run_belongs_to_version(connection: Connection, version_id: int, run_id: int) -> bool:
    """显式指定 run 时校验归属：拿别份文档的 run_id 会拼出错误的章节树与锚点。"""
    found = connection.execute(
        select(ParseRun.id).where(ParseRun.id == run_id, ParseRun.version_id == version_id)
    ).scalar_one_or_none()
    return found is not None


@router.get("/{version_id}/file")
def get_pdf(version_id: int, request: Request) -> Response:
    row = version_row(engine(request), version_id)
    if row["pdf_key"] is None:
        raise ApiProblem(409, "version_not_ready", "PDF 基座尚未生成")
    name = str(row["title"]).replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return stream_object(
        request.app.state.components.blobs,
        str(row["pdf_key"]),
        f"{name or 'document'}.pdf",
        "application/pdf",
        request.headers.get("range"),
        inline=True,
    )


@router.get("/{version_id}/original")
def get_original(version_id: int, request: Request) -> Response:
    row = version_row(engine(request), version_id)
    return stream_object(
        request.app.state.components.blobs,
        str(row["original_key"]),
        str(row["title"]),
        str(row["mime"]),
        request.headers.get("range"),
        inline=False,
    )


@router.get("/{version_id}/pages")
def get_pages(
    version_id: int,
    request: Request,
    from_page: int = Query(default=1, alias="from", ge=1),
    to_page: int | None = Query(default=None, alias="to", ge=1),
) -> dict[str, object]:
    if to_page is not None and to_page < from_page:
        raise ApiProblem(400, "invalid_argument", "to 必须大于或等于 from")
    db = engine(request)
    version = version_row(db, version_id)
    with db.connect() as connection:
        total = int(
            connection.execute(
                select(func.count()).select_from(Page).where(Page.version_id == version_id)
            ).scalar_one()
        )
        query = select(
            Page.page_no, Page.width_pt, Page.height_pt, Page.rotation, Page.text_layer
        ).where(Page.version_id == version_id)
        if from_page > 1:
            query = query.where(Page.page_no >= from_page)
        if to_page is not None:
            query = query.where(Page.page_no <= to_page)
        rows = connection.execute(query.order_by(Page.page_no)).mappings().all()
    return {
        "total": total,
        "page_count": int(version["page_count"] or total),
        "pages": [
            {
                "page_no": row["page_no"],
                "width_pt": row["width_pt"],
                "height_pt": row["height_pt"],
                "rotation": row["rotation"],
                "has_text_layer": row["text_layer"],
            }
            for row in rows
        ],
    }


@router.get("/{version_id}/elements")
def get_elements(
    version_id: int,
    request: Request,
    parse_run_id: int | None = None,
) -> dict[str, object]:
    db = engine(request)
    version_row(db, version_id)
    with db.connect() as connection:
        run_id = parse_run_id
        if run_id is None:
            run_id = _latest_run_id(connection, version_id)
        if run_id is None:
            return {"run_id": None, "elements": []}
        rows = (
            connection.execute(
                select(
                    Element.id,
                    Element.parent_id,
                    Element.anchor,
                    Element.type,
                    Element.level,
                    Element.page_no,
                    Element.order_no,
                    Element.bbox_x0,
                    Element.bbox_y0,
                    Element.bbox_x1,
                    Element.bbox_y1,
                    Element.text,
                    Element.html,
                    Element.source,
                    Element.continues_prev,
                )
                .where(Element.version_id == version_id, Element.run_id == run_id)
                .order_by(Element.page_no, Element.order_no)
            )
            .mappings()
            .all()
        )
    return {
        "run_id": run_id,
        "elements": [
            {
                "id": row["id"],
                "parent_id": row["parent_id"],
                "anchor": row["anchor"],
                "type": row["type"],
                "level": row["level"],
                "page_no": row["page_no"],
                "order_no": row["order_no"],
                "bbox": bbox(row),
                "text": row["text"] or "",
                "source": row["source"],
                "continues_prev": row["continues_prev"],
            }
            for row in rows
        ],
    }


@router.get("/{version_id}/pages/{page_no}/elements")
def get_page_elements(
    version_id: int,
    page_no: int,
    request: Request,
    parse_run_id: int | None = None,
) -> dict[str, object]:
    db = engine(request)
    version_row(db, version_id)
    with db.connect() as connection:
        chosen_run = parse_run_id
        if chosen_run is None:
            chosen_run = _latest_run_id(connection, version_id)
        if chosen_run is None:
            return {"page_no": page_no, "elements": []}
        rows = (
            connection.execute(
                select(
                    Element.anchor,
                    Element.type,
                    Element.page_no,
                    Element.bbox_x0,
                    Element.bbox_y0,
                    Element.bbox_x1,
                    Element.bbox_y1,
                    Element.text,
                    Element.source,
                    Element.continues_prev,
                    Element.order_no,
                )
                .where(
                    Element.version_id == version_id,
                    Element.run_id == chosen_run,
                    Element.page_no == page_no,
                )
                .order_by(Element.order_no)
            )
            .mappings()
            .all()
        )
    return {
        "page_no": page_no,
        "elements": [
            {
                "anchor": row["anchor"],
                "type": row["type"],
                "page_no": row["page_no"],
                "order_no": row["order_no"],
                "bbox": bbox(row),
                "text": row["text"] or "",
                "source": row["source"],
                "continues_prev": row["continues_prev"],
            }
            for row in rows
        ],
    }


@router.get("/{version_id}/anchors/{anchor}")
def resolve_anchor(
    version_id: int,
    anchor: str,
    request: Request,
    parse_run_id: int | None = None,
) -> dict[str, object]:
    try:
        Anchor.parse(anchor)
    except AnchorFormatError as exc:
        raise ApiProblem(400, "invalid_argument", str(exc)) from exc
    db = engine(request)
    version_row(db, version_id)
    with db.connect() as connection:
        run_id = parse_run_id
        if run_id is None:
            run_id = _latest_run_id(connection, version_id)
        row = None
        if run_id is not None:
            row = (
                connection.execute(
                    select(
                        Element.anchor,
                        Element.type,
                        Element.page_no,
                        Element.bbox_x0,
                        Element.bbox_y0,
                        Element.bbox_x1,
                        Element.bbox_y1,
                        Element.text,
                    ).where(
                        Element.version_id == version_id,
                        Element.run_id == run_id,
                        Element.anchor == anchor,
                    )
                )
                .mappings()
                .first()
            )
    if row is None:
        raise ApiProblem(404, "anchor_not_found", "锚点不存在或不属于当前解析 run")
    return {
        "anchor": row["anchor"],
        "run_id": run_id,
        "page_no": row["page_no"],
        "bbox": bbox(row),
        "text": row["text"] or "",
        "type": row["type"],
    }


@router.get("/{version_id}")
def get_version(version_id: int, request: Request) -> dict[str, object]:
    """版本详情保留解析批次和失败原因，供文档预览判断可读状态。"""
    db = engine(request)
    version = version_row(db, version_id)
    with db.connect() as connection:
        # 文档预览通过项目编号返回分析页，避免为了导航额外拉取项目详情。
        project_id = connection.execute(
            select(ProjectFile.project_id)
            .where(ProjectFile.version_id == version_id, ProjectFile.deleted_at.is_(None))
            .order_by(
                case((ProjectFile.role == "main", 0), else_=1), ProjectFile.sort_no, ProjectFile.id
            )
            .limit(1)
        ).scalar_one_or_none()
        runs = (
            connection.execute(
                select(
                    ParseRun.id,
                    ParseRun.provider,
                    ParseRun.provider_version,
                    ParseRun.tier,
                    ParseRun.backend,
                    ParseRun.status,
                    ParseRun.page_count,
                    ParseRun.config_snapshot["ocr_mode"].as_string().label("ocr_mode"),
                    ParseRun.elapsed_ms,
                    ParseRun.error_code,
                    ParseRun.error_message,
                    ParseRun.started_at,
                    ParseRun.finished_at,
                    ParseRun.created_at,
                )
                .where(ParseRun.version_id == version_id)
                .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
            )
            .mappings()
            .all()
        )
    return {
        "id": version["id"],
        "document_id": version["document_id"],
        "project_id": project_id,
        "version_no": version["version_no"],
        "title": version["title"],
        "sha256": version["sha256"],
        "pdf_sha256": version["pdf_sha256"],
        "mime": version["mime"],
        "size_bytes": version["size_bytes"],
        "is_converted": version["is_converted"],
        "converter": version["converter"],
        "converter_version": version["converter_version"],
        "page_count": version["page_count"],
        "created_at": version["created_at"],
        "parse_runs": [dict(row) for row in runs],
    }


@router.get("/{version_id}/outline")
def get_outline(
    version_id: int,
    request: Request,
    parse_run_id: int | None = None,
) -> dict[str, object]:
    db = engine(request)
    version_row(db, version_id)
    with db.connect() as connection:
        run_id = parse_run_id
        if run_id is None:
            run_id = _latest_run_id(connection, version_id)
        elif not _run_belongs_to_version(connection, version_id, run_id):
            raise ApiProblem(404, "not_found", "解析运行不存在")
        if run_id is None:
            return {"run_id": None, "items": []}
        rows = (
            connection.execute(
                select(
                    Element.id,
                    Element.parent_id,
                    Element.anchor,
                    Element.page_no,
                    Element.level,
                    Element.text,
                )
                .where(
                    Element.version_id == version_id,
                    Element.run_id == run_id,
                    Element.type == "title",
                )
                .order_by(Element.page_no, Element.order_no)
            )
            .mappings()
            .all()
        )
    return {"run_id": run_id, "items": build_outline([dict(row) for row in rows])}


class AnchorResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parse_run_id: int | None = Field(default=None, ge=1)
    # 上限 200：批量反查是给前端一次性建索引用的，不做无界查询。
    anchors: list[str] = Field(min_length=1, max_length=200)


@router.post("/{version_id}/anchors/resolve")
def resolve_anchors(
    version_id: int,
    payload: AnchorResolveRequest,
    request: Request,
) -> dict[str, object]:
    """批量锚点反查；查不到的锚点列进 missing，不整批 404（前端要一次拿到能用的那部分）。"""
    ordered: list[str] = []
    for anchor in payload.anchors:
        try:
            Anchor.parse(anchor)
        except AnchorFormatError as exc:
            raise ApiProblem(400, "invalid_argument", str(exc)) from exc
        if anchor not in ordered:
            ordered.append(anchor)
    db = engine(request)
    version_row(db, version_id)
    with db.connect() as connection:
        run_id = payload.parse_run_id
        if run_id is None:
            run_id = _latest_run_id(connection, version_id)
        elif not _run_belongs_to_version(connection, version_id, run_id):
            raise ApiProblem(404, "not_found", "解析运行不存在")
        if run_id is None:
            return {"run_id": None, "items": [], "missing": ordered}
        rows = (
            connection.execute(
                select(
                    Element.anchor,
                    Element.type,
                    Element.page_no,
                    Element.bbox_x0,
                    Element.bbox_y0,
                    Element.bbox_x1,
                    Element.bbox_y1,
                    Element.text,
                ).where(
                    Element.version_id == version_id,
                    Element.run_id == run_id,
                    Element.anchor.in_(ordered),
                )
            )
            .mappings()
            .all()
        )
    by_anchor = {str(row["anchor"]): row for row in rows}
    items: list[dict[str, object]] = []
    missing: list[str] = []
    for anchor in ordered:
        row = by_anchor.get(anchor)
        if row is None:
            missing.append(anchor)
            continue
        items.append(
            {
                "anchor": anchor,
                "page_no": row["page_no"],
                "bbox": bbox(row),
                "text": row["text"] or "",
                "type": row["type"],
            }
        )
    return {"run_id": run_id, "items": items, "missing": missing}
