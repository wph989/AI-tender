"""把 MinerU MiddleJson 块转换为本系统的页内元素与锚点。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from tender.domain.anchor import Anchor
from tender.domain.bbox import Bbox
from tender.domain.errors import ParseFailed

BboxOrigin = Literal["top_left", "bottom_left"]
BboxRotation = Literal["visual", "unrotated"]


@dataclass(frozen=True, slots=True)
class NormalizedElement:
    page_no: int
    order_no: int
    anchor: str
    element_type: str
    level: int | None
    parent_index: int | None
    bbox: Bbox | None
    text: str | None
    html: str | None
    source: str
    continues_prev: bool
    mineru_locator: str


def normalize_middle_json(
    payload: Mapping[str, object],
    *,
    expected_page_count: int,
    page_rotations: Mapping[int, int],
    page_has_text_layer: Mapping[int, bool],
    bbox_origin: BboxOrigin | None,
    bbox_rotation: BboxRotation | None,
    require_all_pages: bool,
    force_ocr: bool = False,
) -> list[NormalizedElement]:
    """校验 MiddleJson 并生成稳定锚点；未经校准的坐标保持为空。"""
    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ParseFailed("MiddleJson 必须包含非空 pages 数组")
    if expected_page_count < 1 or len(pages) > expected_page_count:
        raise ParseFailed("MiddleJson 页数与 PDF 页面几何不一致")
    if require_all_pages and len(pages) != expected_page_count:
        raise ParseFailed("MinerU completed 结果页数与 PDF 页面数不一致")

    indexed_pages: list[tuple[int, Mapping[str, object], int]] = []
    seen_pages: set[int] = set()
    has_explicit_page_numbers = True
    for ordinal, raw_page in enumerate(pages, start=1):
        if not isinstance(raw_page, dict):
            raise ParseFailed(f"MiddleJson 第 {ordinal} 页必须是对象")
        page_no = _page_number(raw_page, ordinal)
        if page_no is None:
            has_explicit_page_numbers = False
            page_no = ordinal
        if page_no < 1 or page_no > expected_page_count or page_no in seen_pages:
            raise ParseFailed(f"MiddleJson 页码非法或重复：{page_no}")
        seen_pages.add(page_no)
        indexed_pages.append((page_no, raw_page, ordinal - 1))

    if not require_all_pages and len(pages) < expected_page_count and not has_explicit_page_numbers:
        raise ParseFailed("partial MiddleJson 缺少物理页索引，无法安全映射页面")
    if require_all_pages and seen_pages != set(range(1, expected_page_count + 1)):
        raise ParseFailed("MinerU completed 结果缺少 PDF 页面")

    elements: list[NormalizedElement] = []
    active_titles: list[tuple[int, int]] = []
    anchors: set[str] = set()
    for page_no, page, raw_page_index in sorted(indexed_pages):
        rotation = page_rotations.get(page_no)
        has_text_layer = page_has_text_layer.get(page_no)
        if rotation not in {0, 90, 180, 270} or has_text_layer is None:
            raise ParseFailed(f"PDF 第 {page_no} 页缺少有效页面几何")
        raw_blocks = page.get("blocks")
        # MinerU 用 exclude_defaults 序列化 MiddleJson，而 PageInfo.blocks 的默认值是空列表，
        # 于是「整页无块」的空白页会把 blocks 键整体省略，而不是写出 []。
        # 缺字段与空数组语义相同，这里统一补成空列表；只有显式给出非数组值才算数据损坏。
        if raw_blocks is None:
            raw_blocks = []
        elif not isinstance(raw_blocks, list):
            raise ParseFailed(f"MiddleJson 第 {page_no} 页 blocks 必须是数组")

        order_no = 0
        for raw_block_index, raw_block in enumerate(raw_blocks):
            if not isinstance(raw_block, dict):
                raise ParseFailed(
                    f"MiddleJson 第 {page_no} 页第 {raw_block_index + 1} 块必须是对象"
                )
            raw_type = raw_block.get("type")
            if not isinstance(raw_type, str) or not raw_type.strip():
                raise ParseFailed(f"MiddleJson 第 {page_no} 页第 {raw_block_index + 1} 块缺少 type")
            element_type = _element_type(raw_type)
            if element_type is None:
                # 页眉、页脚和页码不参与锚点编号，原始 MiddleJson 仍完整归档供审计。
                continue

            order_no += 1
            anchor = str(Anchor(page_no, order_no))
            if anchor in anchors:
                raise ParseFailed(f"MiddleJson 产生重复锚点：{anchor}")
            anchors.add(anchor)

            level = _title_level(raw_block) if element_type == "title" else None
            if element_type == "title":
                if level is not None:
                    while active_titles and active_titles[-1][1] >= level:
                        active_titles.pop()
                    parent_index = active_titles[-1][0] if active_titles else None
                    active_titles.append((len(elements), level))
                else:
                    # 缺少显式层级的标题不进入层级栈，避免把连续标题误连成父子链。
                    parent_index = active_titles[-1][0] if active_titles else None
            else:
                parent_index = active_titles[-1][0] if active_titles else None

            bbox = _normalized_bbox(
                raw_block.get("bbox"),
                rotation=rotation,
                origin=bbox_origin,
                rotation_mode=bbox_rotation,
                page_no=page_no,
                block_no=raw_block_index + 1,
            )
            source = _source(raw_block, has_text_layer, force_ocr)
            elements.append(
                NormalizedElement(
                    page_no=page_no,
                    order_no=order_no,
                    anchor=anchor,
                    element_type=element_type,
                    level=level,
                    parent_index=parent_index,
                    bbox=bbox,
                    text=_block_text(raw_block) or None,
                    html=_block_html(raw_block),
                    source=source,
                    continues_prev=raw_block.get("continues_prev") is True,
                    mineru_locator=_locator(raw_block, page_no, raw_page_index, raw_block_index),
                )
            )

    return elements


def _page_number(page: Mapping[str, object], ordinal: int) -> int | None:
    page_idx = page.get("page_idx")
    if page_idx is not None:
        if not isinstance(page_idx, int) or isinstance(page_idx, bool) or page_idx < 0:
            raise ParseFailed(f"MiddleJson 第 {ordinal} 页 page_idx 非法")
        return page_idx + 1
    page_no = page.get("page_no")
    if page_no is not None:
        if not isinstance(page_no, int) or isinstance(page_no, bool) or page_no < 1:
            raise ParseFailed(f"MiddleJson 第 {ordinal} 页 page_no 非法")
        return page_no
    return None


def _element_type(raw_type: str) -> str | None:
    normalized = raw_type.strip().lower()
    if normalized in {"header", "footer", "page_number", "page_no"}:
        return None
    if normalized in {"title", "table", "list", "equation"}:
        return normalized
    if normalized in {"image", "figure", "picture"}:
        return "figure"
    if normalized in {"interline_equation", "formula"}:
        return "equation"
    return "text"


def _title_level(block: Mapping[str, object]) -> int | None:
    value = block.get("level", block.get("title_level"))
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 6:
        return None
    return value


def _normalized_bbox(
    raw_bbox: object,
    *,
    rotation: int,
    origin: BboxOrigin | None,
    rotation_mode: BboxRotation | None,
    page_no: int,
    block_no: int,
) -> Bbox | None:
    if raw_bbox is None:
        return None
    if not isinstance(raw_bbox, list) or len(raw_bbox) != 4:
        raise ParseFailed(f"MiddleJson p{page_no}b{block_no} bbox 必须是四个数或 null")
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in raw_bbox):
        raise ParseFailed(f"MiddleJson p{page_no}b{block_no} bbox 含非数值")
    try:
        bbox = Bbox.from_raw(raw_bbox)
        valid = bbox.is_valid()
    except (ArithmeticError, ValueError) as exc:
        raise ParseFailed(f"MiddleJson p{page_no}b{block_no} bbox 非法") from exc
    if not valid:
        raise ParseFailed(f"MiddleJson p{page_no}b{block_no} bbox 越界或面积为零")
    if origin is None or (rotation != 0 and rotation_mode is None):
        return None

    x0, y0, x1, y1 = bbox.x0, bbox.y0, bbox.x1, bbox.y1
    if origin == "bottom_left":
        y0, y1 = Decimal(1) - y1, Decimal(1) - y0
    if rotation_mode == "unrotated":
        if rotation == 90:
            x0, y0, x1, y1 = Decimal(1) - y1, x0, Decimal(1) - y0, x1
        elif rotation == 180:
            x0, y0, x1, y1 = Decimal(1) - x1, Decimal(1) - y1, Decimal(1) - x0, Decimal(1) - y0
        elif rotation == 270:
            x0, y0, x1, y1 = y0, Decimal(1) - x1, y1, Decimal(1) - x0
    result = Bbox(x0, y0, x1, y1)
    if not result.is_valid():
        raise ParseFailed(f"MiddleJson p{page_no}b{block_no} bbox 校正后越界")
    return result


def _source(block: Mapping[str, object], has_text_layer: bool, force_ocr: bool) -> str:
    raw_source = block.get("source")
    if isinstance(raw_source, str) and raw_source in {"native", "ocr"}:
        return raw_source
    return "ocr" if force_ocr or not has_text_layer else "native"


def _block_text(block: Mapping[str, object]) -> str:
    for key in ("text", "content", "lines", "caption", "latex", "formula"):
        if key not in block:
            continue
        value = block[key]
        if key == "lines" and isinstance(value, list):
            text = "\n".join(_inline_text(line) for line in value)
        else:
            text = _inline_text(value)
        if text:
            return text
    return ""


def _inline_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_inline_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", "latex", "formula", "value", "caption"):
            if key in value:
                return _inline_text(value[key])
    return ""


def _block_html(block: Mapping[str, object]) -> str | None:
    for key in ("html", "table_html", "content_html"):
        value = block.get(key)
        if isinstance(value, str):
            return value
    return None


def _locator(
    block: Mapping[str, object], page_no: int, raw_page_index: int, raw_block_index: int
) -> str:
    for key in ("locator", "block_id", "id", "index"):
        value = block.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            return f"pages[{raw_page_index}].blocks[{raw_block_index}].{key}={value}"
    return f"pages[{raw_page_index}].blocks[{raw_block_index}]@p{page_no}"
