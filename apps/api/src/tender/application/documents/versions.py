"""版本文件、页面元素、锚点与章节树用例。"""

from __future__ import annotations

from typing import Any

from tender.application.documents.outline import build_outline
from tender.application.shared.errors import Conflict, InvalidArgument, NotFound
from tender.domain.documents.anchor import Anchor
from tender.domain.shared.errors import AnchorFormatError
from tender.ports.repository.documents.versions import VersionRepository


def bbox(row: dict[str, Any]) -> list[float] | None:
    values = (row["bbox_x0"], row["bbox_y0"], row["bbox_x1"], row["bbox_y1"])
    if any(value is None for value in values):
        return None
    return [float(value) for value in values]


class VersionService:
    def __init__(self, repository: VersionRepository, company_id: int) -> None:
        self.repository = repository

    def require_version(self, version_id: int) -> dict[str, Any]:
        version = self.repository.version(version_id)
        if version is None:
            raise NotFound("文档版本不存在")
        return version

    def pdf(self, version_id: int) -> dict[str, str]:
        version = self.require_version(version_id)
        if version["pdf_key"] is None:
            raise Conflict("PDF 基座尚未生成", code="version_not_ready")
        name = str(version["title"]).replace(chr(92), "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return {
            "key": str(version["pdf_key"]),
            "filename": f"{name or 'document'}.pdf",
            "content_type": "application/pdf",
        }

    def original(self, version_id: int) -> dict[str, str]:
        version = self.require_version(version_id)
        return {
            "key": str(version["original_key"]),
            "filename": str(version["title"]),
            "content_type": str(version["mime"]),
        }

    def pages(self, version_id: int, *, from_page: int, to_page: int | None) -> dict[str, Any]:
        if to_page is not None and to_page < from_page:
            raise InvalidArgument("to 必须大于或等于 from")
        version = self.require_version(version_id)
        page_data = self.repository.pages(version_id, from_page=from_page, to_page=to_page)
        return {
            "total": page_data["total"],
            "page_count": int(version["page_count"] or page_data["total"]),
            "pages": [
                {
                    "page_no": row["page_no"],
                    "width_pt": row["width_pt"],
                    "height_pt": row["height_pt"],
                    "rotation": row["rotation"],
                    "has_text_layer": row["text_layer"],
                }
                for row in page_data["rows"]
            ],
        }

    def elements(self, version_id: int, parse_run_id: int | None) -> dict[str, Any]:
        self.require_version(version_id)
        run_id = parse_run_id or self.repository.latest_run_id(version_id)
        if run_id is None:
            return {"run_id": None, "elements": []}
        rows = self.repository.elements(version_id, run_id)
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

    def page_elements(
        self, version_id: int, page_no: int, parse_run_id: int | None
    ) -> dict[str, Any]:
        self.require_version(version_id)
        run_id = parse_run_id or self.repository.latest_run_id(version_id)
        if run_id is None:
            return {"page_no": page_no, "elements": []}
        rows = self.repository.page_elements(version_id, run_id, page_no)
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

    def anchor(self, version_id: int, anchor: str, parse_run_id: int | None) -> dict[str, Any]:
        try:
            Anchor.parse(anchor)
        except AnchorFormatError as exc:
            raise InvalidArgument(str(exc)) from exc
        self.require_version(version_id)
        run_id = parse_run_id or self.repository.latest_run_id(version_id)
        row = self.repository.anchor(version_id, run_id, anchor) if run_id is not None else None
        if row is None:
            raise NotFound("锚点不存在或不属于当前解析 run", code="anchor_not_found")
        return {
            "anchor": row["anchor"],
            "run_id": run_id,
            "page_no": row["page_no"],
            "bbox": bbox(row),
            "text": row["text"] or "",
            "type": row["type"],
        }

    def detail(self, version_id: int) -> dict[str, Any]:
        version = self.require_version(version_id)
        detail = self.repository.detail(version_id)
        return {
            "id": version["id"],
            "document_id": version["document_id"],
            "project_id": detail["project_id"],
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
            "parse_runs": detail["runs"],
        }

    def outline(self, version_id: int, parse_run_id: int | None) -> dict[str, Any]:
        self.require_version(version_id)
        run_id = parse_run_id or self.repository.latest_run_id(version_id)
        if parse_run_id is not None and not self.repository.run_belongs_to_version(
            version_id, run_id
        ):
            raise NotFound("解析运行不存在")
        if run_id is None:
            return {"run_id": None, "items": []}
        rows = self.repository.outline_rows(version_id, run_id)
        return {"run_id": run_id, "items": build_outline(rows)}

    def resolve_anchors(
        self,
        version_id: int,
        anchors: list[str],
        parse_run_id: int | None,
    ) -> dict[str, Any]:
        ordered: list[str] = []
        for anchor in anchors:
            try:
                Anchor.parse(anchor)
            except AnchorFormatError as exc:
                raise InvalidArgument(str(exc)) from exc
            if anchor not in ordered:
                ordered.append(anchor)
        self.require_version(version_id)
        run_id = parse_run_id or self.repository.latest_run_id(version_id)
        if parse_run_id is not None and not self.repository.run_belongs_to_version(
            version_id, run_id
        ):
            raise NotFound("解析运行不存在")
        if run_id is None:
            return {"run_id": None, "items": [], "missing": ordered}
        by_anchor = {
            str(row["anchor"]): row for row in self.repository.anchors(version_id, run_id, ordered)
        }
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
