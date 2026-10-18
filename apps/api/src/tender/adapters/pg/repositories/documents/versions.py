"""文档版本、页面、元素与锚点的数据库访问。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, case, func, select

from tender.adapters.pg.models import (
    Document,
    DocumentVersion,
    Element,
    Page,
    ParseRun,
    ProjectFile,
)


class VersionRepository:
    def __init__(self, engine: Engine, company_id: int) -> None:
        self.engine = engine
        self.company_id = company_id

    def version(self, version_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        DocumentVersion.id,
                        DocumentVersion.document_id,
                        DocumentVersion.version_no,
                        DocumentVersion.sha256,
                        DocumentVersion.pdf_key,
                        DocumentVersion.pdf_sha256,
                        DocumentVersion.original_key,
                        DocumentVersion.mime,
                        DocumentVersion.size_bytes,
                        DocumentVersion.is_converted,
                        DocumentVersion.converter,
                        DocumentVersion.converter_version,
                        DocumentVersion.page_count,
                        DocumentVersion.created_at,
                        Document.title,
                        Document.company_id,
                    )
                    .select_from(DocumentVersion)
                    .join(Document, Document.id == DocumentVersion.document_id)
                    .where(
                        DocumentVersion.id == version_id,
                        Document.company_id == self.company_id,
                        Document.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def latest_run_id(self, version_id: int) -> int | None:
        with self.engine.connect() as connection:
            return connection.execute(
                select(ParseRun.id)
                .where(
                    ParseRun.version_id == version_id,
                    ParseRun.status.in_(("completed", "partial")),
                )
                .order_by(ParseRun.created_at.desc(), ParseRun.id.desc())
                .limit(1)
            ).scalar_one_or_none()

    def run_belongs_to_version(self, version_id: int, run_id: int) -> bool:
        with self.engine.connect() as connection:
            found = connection.execute(
                select(ParseRun.id).where(
                    ParseRun.id == run_id,
                    ParseRun.version_id == version_id,
                )
            ).scalar_one_or_none()
        return found is not None

    def pages(self, version_id: int, *, from_page: int, to_page: int | None) -> dict[str, Any]:
        with self.engine.connect() as connection:
            total = int(
                connection.execute(
                    select(func.count()).select_from(Page).where(Page.version_id == version_id)
                ).scalar_one()
            )
            query = select(
                Page.page_no,
                Page.width_pt,
                Page.height_pt,
                Page.rotation,
                Page.text_layer,
            ).where(Page.version_id == version_id)
            if from_page > 1:
                query = query.where(Page.page_no >= from_page)
            if to_page is not None:
                query = query.where(Page.page_no <= to_page)
            rows = connection.execute(query.order_by(Page.page_no)).mappings().all()
        return {"total": total, "rows": [dict(row) for row in rows]}

    def elements(self, version_id: int, run_id: int) -> list[dict[str, Any]]:
        statement = (
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
                Element.source,
                Element.continues_prev,
            )
            .where(Element.version_id == version_id, Element.run_id == run_id)
            .order_by(Element.page_no, Element.order_no)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def page_elements(self, version_id: int, run_id: int, page_no: int) -> list[dict[str, Any]]:
        statement = (
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
                Element.run_id == run_id,
                Element.page_no == page_no,
            )
            .order_by(Element.order_no)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def anchor(
        self, version_id: int, run_id: int, anchor: str
    ) -> dict[str, Any] | None:
        statement = select(
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
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return dict(row) if row is not None else None

    def anchors(
        self, version_id: int, run_id: int, anchors: Sequence[str]
    ) -> list[dict[str, Any]]:
        statement = select(
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
            Element.anchor.in_(anchors),
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def detail(self, version_id: int) -> dict[str, Any]:
        with self.engine.connect() as connection:
            project_id = connection.execute(
                select(ProjectFile.project_id)
                .where(ProjectFile.version_id == version_id, ProjectFile.deleted_at.is_(None))
                .order_by(
                    case((ProjectFile.role == "main", 0), else_=1),
                    ProjectFile.sort_no,
                    ProjectFile.id,
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
        return {"project_id": project_id, "runs": [dict(row) for row in runs]}

    def outline_rows(self, version_id: int, run_id: int) -> list[dict[str, Any]]:
        statement = (
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
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]
