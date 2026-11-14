"""元素到检索分块的纯规则：表格 HTML 与纯文本都保留信息，不沿用旧的 6000 字截断。

放 ``domain`` 而不是 ``application``：分块是纯函数规则，而 ``adapters/pg`` 的检索入库
也要用它（``readable_chunks`` 在仓储里拼定位信息），application 与 adapters 不能互相引用
（``pyproject.toml`` 的 import-linter 契约），纯规则只有落在最底层的 domain 才能被两边共用。
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any

# 分块版本随切分规则升级：索引写入与检索回退共用这一口径，避免读取端各自硬编码。
CHUNK_VERSION = "2"


def plain_text(element: Mapping[str, Any]) -> str:
    # 表格的完整 HTML 与纯文本同时保留信息；不沿用旧抽取的 6000 字截断。
    source = str(element.get("html") or element.get("text") or "")
    return html.unescape(re.sub(r"<[^>]+>", " ", source))


def chunk_block_id(source_id: int, parse_run_id: int, ordinal: int) -> str:
    """引文身份：同一解析批次内的块编号，索引分块与原文回退必须完全一致。"""
    return f"s{source_id}r{parse_run_id}c{ordinal}"


def retrieval_block_id(source_id: int, parse_run_id: int, ordinal: int) -> str:
    """语义块有独立版本命名空间，旧报告的原文块ID不会被重新解释。"""
    return f"s{source_id}r{parse_run_id}g{CHUNK_VERSION}c{ordinal}"


def chunk_bbox(row: Mapping[str, Any]) -> list[float] | None:
    """元素/分块行的定位框；四边齐全才算有效坐标。"""
    values = [row.get(f"bbox_{axis}") for axis in ("x0", "y0", "x1", "y1")]
    if any(value is None for value in values):
        return None
    return [float(value) for value in values if value is not None]


def chunk_locations(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """读取入库时已合并的大块位置，不在使用时回到原始小块重新合并。"""
    locations = row.get("locations")
    if not locations:
        return [dict(row)]
    body = str(row.get("content") or row.get("quote") or "")
    result = []
    for place in locations:
        text = body[place["char_start"]:place["char_end"]]
        result.append({**{k: v for k, v in row.items() if k != "locations"},
                       **{k: place[k] for k in ("element_id", "anchor", "page_no", "bbox")},
                       "content": text, "quote": text})
    return result


def split_elements(elements: Sequence[Mapping[str, Any]], size: int = 1800) -> list[dict]:
    return [chunk for _, chunk in iter_element_chunks(elements, size)]


def iter_element_chunks(
    elements: Iterable[Mapping[str, Any]], size: int = 1800,
) -> Iterator[tuple[Mapping[str, Any], dict[str, Any]]]:
    """流式复用同一切分规则，让未建索引的补读可以在窗口末尾停止。"""
    if size < 200:
        raise ValueError("分块长度过小")
    ordinal = 0
    chapter = ""
    for element in elements:
        content = plain_text(element)
        if element.get("type") == "title":
            chapter = content.strip()
        for start in range(0, len(content), size):
            end = min(start + size + 150, len(content))
            if content[start:end].strip():
                yield element, (
                    {
                        "element_id": element["id"],
                        "ordinal": ordinal,
                        "char_start": start,
                        "char_end": end,
                        "chapter": chapter,
                        "content": content[start:end],
                    }
                )
                ordinal += 1


# 历史小块编号保留旧口径，新切片独立版本化，避免旧报告的证据 ID 指向不同原文。
_CHAPTER = re.compile(
    r"^第[一二三四五六七八九十百零\d]+(?:章|篇|部分|节)"
    r"|^附[录件][一二三四五六七八九十\d:：]"
)
_NUMBER = re.compile(
    r"^(\d{1,2}(?:\.\d+)*)(?:[.．、]|\s+(?![年月日时分秒元万亿%％])"
    r"|(?=[（(]|[\u4e00-\u9fff])(?![年月日时分秒元万亿]))"
)
_VARIANT = re.compile(r"[（(][A-Za-z][）)]")


def iter_retrieval_chunks(
    elements: Iterable[Mapping[str, Any]], size: int = 1800,
) -> Iterator[tuple[Mapping[str, Any], dict[str, Any]]]:
    """把相邻标题、正文与表格组织成语义块，原文元素映射只交给代码。

    只采用明确章节和编号边界；不根据年份猜项目归属，按原文顺序拼接并保留真实坐标。
    每单元最多12个原文片段，模型只读大块ID；页级大块坐标在入库前合并。
    """
    pending: list[tuple[Mapping[str, Any], dict[str, Any]]] = []
    length = 0
    chapter = ""
    section = ""
    ordinal = 0

    def flush() -> Iterator[tuple[Mapping[str, Any], dict[str, Any]]]:
        if not pending:
            return
        body = "\n".join(chunk["content"] for _, chunk in pending)
        path = " / ".join(dict.fromkeys(part for part in (chapter, section) if part))
        pages: dict[int | None, dict[str, Any]] = {}
        position = 0
        for element, chunk in pending:
            page = pages.setdefault(element.get("page_no"), {
                "element_id": element["id"], "anchor": element.get("anchor"),
                "page_no": element.get("page_no"), "char_start": position, "boxes": [],
            })
            page["char_end"] = position + len(chunk["content"])
            page["boxes"].append(chunk_bbox(element))
            position += len(chunk["content"]) + 1
        locations = []
        for page in pages.values():
            boxes = page.pop("boxes")
            # 任何区域缺坐标时保留页级定位，不能把已知的部分框当作整个大块。
            page["bbox"] = ([min(b[0] for b in boxes), min(b[1] for b in boxes),
                             max(b[2] for b in boxes), max(b[3] for b in boxes)]
                            if all(boxes) else None)
            locations.append(page)
        first_element, first_chunk = pending[0]
        yield first_element, first_chunk | {"ordinal": ordinal, "chapter": path,
                                           "content": body, "locations": locations}

    for element, chunk in iter_element_chunks(elements, size):
        text = chunk["content"].strip()
        first = chunk["char_start"] == 0
        number = _NUMBER.match(text) if first else None
        heading = first and (element.get("type") == "title" or (
            len(text) <= 80 and _CHAPTER.match(text) is not None))
        section_start = bool(number and (number[1].count(".") <= 1 or _VARIANT.search(text)))
        # 章节/父级标题紧接子标题时继续组成同一条款，避免又生成只有几个字的标题块。
        only_headings = bool(pending) and all(
            len(part["content"].strip()) <= 80 and (
                original.get("type") == "title" or _CHAPTER.match(part["content"].strip())
                or _NUMBER.match(part["content"].strip())
            ) and not part["content"].rstrip().endswith(("。", "；", ";"))
            for original, part in pending
        )
        previous_number = _NUMBER.match(pending[-1][1]["content"].strip()) if pending else None
        child_heading = only_headings and (previous_number is None or (
            number and number[1].startswith(previous_number[1].rstrip(".") + ".")
        ))
        # 表格必须携带紧邻的标题/引导句；表格之后的新正文另开单元，避免跨事项混合。
        after_table = bool(pending and pending[-1][0].get("type") == "table"
                           and element["id"] != pending[-1][0]["id"])
        if pending and (heading or section_start and not child_heading or after_table
                        or len(pending) >= 12
                        or length + len(chunk["content"]) > size):
            yield from flush()
            ordinal += 1
            pending, length = [], 0
        if heading:
            chapter, section = text, ""
        elif section_start and len(text) <= 80:
            section = text
        pending.append((element, chunk))
        length += len(chunk["content"]) + 1
    yield from flush()
