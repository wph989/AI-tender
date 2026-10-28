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
CHUNK_VERSION = "1"


def plain_text(element: Mapping[str, Any]) -> str:
    # 表格的完整 HTML 与纯文本同时保留信息；不沿用旧抽取的 6000 字截断。
    source = str(element.get("html") or element.get("text") or "")
    return html.unescape(re.sub(r"<[^>]+>", " ", source))


def chunk_block_id(source_id: int, parse_run_id: int, ordinal: int) -> str:
    """引文身份：同一解析批次内的块编号，索引分块与原文回退必须完全一致。"""
    return f"s{source_id}r{parse_run_id}c{ordinal}"


def chunk_bbox(row: Mapping[str, Any]) -> list[float] | None:
    """元素/分块行的定位框；四边齐全才算有效坐标。"""
    values = [row.get(f"bbox_{axis}") for axis in ("x0", "y0", "x1", "y1")]
    if any(value is None for value in values):
        return None
    return [float(value) for value in values if value is not None]


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
