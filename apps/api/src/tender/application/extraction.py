"""锚点文档、章节分块、标段识别与抽取证据校验。"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from tender.application.fields import FieldDefinition


@dataclass(frozen=True, slots=True)
class TextChunk:
    section_path: str
    elements: tuple[dict[str, Any], ...]
    text: str


@dataclass(frozen=True, slots=True)
class LotCandidate:
    code: str
    name: str
    confidence: float


class _TableText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"tr"}:
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def anchor_text(element: dict[str, Any], max_chars: int = 6000) -> str:
    content = str(element.get("text") or "").strip()
    if element.get("type") == "table" and element.get("html"):
        parser = _TableText()
        parser.feed(str(element["html"]))
        table_text = " ".join(parser.parts).strip()
        content = table_text or content
    content = re.sub(r"\s+", " ", html.unescape(content)).strip()
    if len(content) > max_chars:
        content = content[:max_chars] + " [截断]"
    return f"<<{element['anchor']}>> {content}"


def build_anchor_document(
    elements: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[TextChunk]]:
    """去掉页眉页脚后按标题树构造输入；表格整体作为单个带锚点块。"""
    ordered = sorted(elements, key=lambda item: (int(item["page_no"]), int(item["order_no"])))
    included = [
        item for item in ordered if item.get("type") not in {"header", "footer", "page_number"}
    ]
    by_id = {int(item["id"]): item for item in included if item.get("id") is not None}
    title_stack: list[tuple[int, dict[str, Any]]] = []
    for item in included:
        if item.get("type") == "title":
            level = item.get("level")
            level = int(level) if isinstance(level, int) and level > 0 else 99
            while title_stack and title_stack[-1][0] >= level:
                title_stack.pop()
            title_stack.append((level, item))
        item["_section_path"] = _section_path(item, by_id, title_stack)

    chapters: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for item in included:
        is_chapter = item.get("type") == "title" and item.get("level") == 1
        if is_chapter and current:
            chapters.append(current)
            current = []
        current.append(item)
    if current:
        chapters.append(current)

    chunks: list[TextChunk] = []
    for chapter in chapters:
        path = str(chapter[0].get("_section_path") or "")
        rendered_size = sum(len(anchor_text(item)) for item in chapter)
        groups = [chapter] if rendered_size <= 12_000 else _split_at_second_level(chapter)
        for group in groups:
            chunks.extend(_bounded_chunks(group, max_chars=12_000, overlap=1, fallback_path=path))
    return included, chunks


def build_outline(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把一次 parse_run 的标题元素还原成章节树。

    不改层级、不补全缺失的父节点：层级错了要在解析阶段修，展示层猜层级只会掩盖问题。
    父节点一定排在子节点之前（worker 写入时已校验 parent_index < index），所以顺序遍历即可挂树；
    parent_id 指向的行不在入参里时挂到根，宁可少一层也不要挂到错误的分支下。
    """
    nodes: list[dict[str, Any]] = []
    by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        node = {
            "element_id": int(row["id"]),
            "anchor": row["anchor"],
            "page_no": row["page_no"],
            "level": row["level"],
            "text": row["text"] or "",
            "children": [],
        }
        parent_id = row.get("parent_id")
        parent = by_id.get(parent_id) if isinstance(parent_id, int) else None
        if parent is None:
            nodes.append(node)
        else:
            parent["children"].append(node)
        by_id[node["element_id"]] = node
    return nodes


def _section_path(
    item: dict[str, Any],
    by_id: dict[int, dict[str, Any]],
    title_stack: list[tuple[int, dict[str, Any]]],
) -> str:
    parent_id = item.get("parent_id")
    parents: list[str] = []
    seen: set[int] = set()
    while isinstance(parent_id, int) and parent_id in by_id and parent_id not in seen:
        seen.add(parent_id)
        parent = by_id[parent_id]
        parent_text = str(parent.get("text") or "").strip()
        if parent_text:
            parents.append(parent_text)
        parent_id = parent.get("parent_id")
    path = list(reversed(parents))
    if not path:
        path = [
            str(title.get("text") or "").strip() for _, title in title_stack if title.get("text")
        ]
    own = str(item.get("text") or "").strip() if item.get("type") == "title" else ""
    if own and (not path or path[-1] != own):
        path.append(own)
    return " > ".join(path)


def _split_at_second_level(chapter: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for item in chapter:
        boundary = item.get("type") == "title" and item.get("level") == 2
        if boundary and current:
            groups.append(current)
            current = []
        current.append(item)
    if current:
        groups.append(current)
    return groups


def _bounded_chunks(
    items: list[dict[str, Any]],
    *,
    max_chars: int,
    overlap: int,
    fallback_path: str,
) -> list[TextChunk]:
    result: list[TextChunk] = []
    current: list[dict[str, Any]] = []
    size = 0
    for item in items:
        rendered = anchor_text(item)
        if current and size + len(rendered) > max_chars and not item.get("continues_prev"):
            result.append(_make_chunk(current, fallback_path))
            current = current[-overlap:] if overlap else []
            size = sum(len(anchor_text(part)) for part in current)
        current.append(item)
        size += len(rendered)
    if current:
        result.append(_make_chunk(current, fallback_path))
    return result


def _make_chunk(items: list[dict[str, Any]], fallback_path: str) -> TextChunk:
    paths = [str(item.get("_section_path") or "") for item in items if item.get("_section_path")]
    section_path = paths[-1] if paths else fallback_path
    body = "\n".join(anchor_text(item) for item in items)
    prefix = f"<章节路径>{section_path}</章节路径>\n" if section_path else ""
    return TextChunk(section_path, tuple(items), prefix + body)


def select_chunks(
    field: FieldDefinition, chunks: list[TextChunk], limit: int = 8
) -> list[TextChunk]:
    """第一遍按字段关键词筛章节；开放式条款扫描全篇，定向字段取最相关章节。"""
    if field.scan_all or not field.section_terms:
        return chunks
    scored = [
        (
            sum(
                term.casefold() in chunk.section_path.casefold()
                or term.casefold() in chunk.text.casefold()
                for term in field.section_terms
            ),
            index,
            chunk,
        )
        for index, chunk in enumerate(chunks)
    ]
    matching = [item for item in scored if item[0] > 0]
    if not matching:
        return chunks[:limit]
    matching.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in matching[:limit]]


def identify_lots(elements: list[dict[str, Any]]) -> list[LotCandidate]:
    """只把标题里的明确标段编号视为可自动识别范围，正文提及用于覆盖的编号风险太高。"""
    pattern = re.compile(
        r"(第[一二三四五六七八九十百\d]+标段|[A-ZＡ-Ｚ]标段|第[一二三四五六七八九十百\d]+包|[A-ZＡ-Ｚ]包)"
    )
    seen: dict[str, LotCandidate] = {}
    for element in elements:
        if element.get("type") != "title":
            continue
        title = re.sub(r"\s+", "", str(element.get("text") or ""))
        for match in pattern.finditer(title):
            code = unicodedata.normalize("NFKC", match.group(1))
            seen.setdefault(code, LotCandidate(code, title, 0.9))
    return sorted(seen.values(), key=lambda lot: lot.code)


def validate_result(
    raw: dict[str, Any],
    field: FieldDefinition,
    by_anchor: dict[str, dict[str, Any]],
    lot_codes: set[str],
) -> dict[str, Any]:
    """只接受当前 run 的锚点；引用不一致会被保留为需复核证据而不会静默改写。"""
    if raw.get("field_key") != field.key:
        raise ValueError("模型返回的 field_key 与请求字段不一致")
    confidence = raw.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise ValueError("模型 confidence 必须位于 0 到 1")
    not_found = raw.get("not_found") is True
    quote = raw.get("quote")
    evidence = raw.get("evidence")
    if not isinstance(quote, str) or not isinstance(evidence, list):
        raise ValueError("模型结果缺少 quote 或 evidence")
    if not_found:
        return {
            "value": None,
            "value_text": "未找到",
            "quote": "",
            "evidence": [],
            "confidence": float(confidence),
            "status": "not_found",
            "lot_code": None,
            "strategy": "llm",
            "rule_value": None,
        }

    valid: list[dict[str, Any]] = []
    quote_mismatch = False
    for anchor in evidence:
        if not isinstance(anchor, str):
            continue
        element = by_anchor.get(anchor)
        if element is None:
            continue
        text = str(element.get("text") or "")
        start, end, match_type = _locate_quote(text, quote)
        quote_mismatch = quote_mismatch or start is None
        excerpt = quote if start is not None else text
        valid.append(
            {
                "anchor": anchor,
                "element": element,
                "quote": excerpt,
                "char_start": start,
                "char_end": end,
                "match_type": match_type if start is not None else "manual",
            }
        )
    if not valid:
        return {
            "value": None,
            "value_text": "未找到",
            "quote": "",
            "evidence": [],
            "confidence": float(confidence),
            "status": "not_found",
            "lot_code": None,
            "strategy": "llm",
            "rule_value": None,
        }
    value_text = raw.get("value_text")
    if not isinstance(value_text, str):
        value_text = str(raw.get("value") if raw.get("value") is not None else "")
    lot_code = raw.get("lot_code")
    if not isinstance(lot_code, str) or lot_code not in lot_codes:
        lot_code = None
    return {
        "value": raw.get("value"),
        "value_text": value_text[:4000],
        "quote": quote,
        "evidence": valid,
        "confidence": float(confidence),
        "status": "need_review" if quote_mismatch else "auto",
        "lot_code": lot_code,
        "strategy": "llm",
        "rule_value": None,
    }


def _locate_quote(text: str, quote: str) -> tuple[int | None, int | None, str]:
    if not quote.strip():
        return None, None, "manual"
    direct = text.find(quote)
    if direct >= 0:
        return direct, direct + len(quote), "exact"
    normalized_text, text_map = _normalized_with_offsets(text)
    normalized_quote = _normalize(quote)
    index = normalized_text.find(normalized_quote)
    if index < 0 or not normalized_quote:
        return None, None, "manual"
    return text_map[index], text_map[index + len(normalized_quote) - 1] + 1, "normalized"


def _normalized_with_offsets(value: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    positions: list[int] = []
    for index, char in enumerate(value):
        normalized = unicodedata.normalize("NFKC", char)
        for part in normalized:
            if part.isspace():
                continue
            chars.append(part)
            positions.append(index)
    return "".join(chars), positions


def _normalize(value: str) -> str:
    return "".join(
        part for char in unicodedata.normalize("NFKC", value) for part in char if not part.isspace()
    )
