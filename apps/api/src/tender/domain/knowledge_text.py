"""元素到检索分块的纯规则：表格 HTML 与纯文本都保留信息，不沿用旧的 6000 字截断。

放 ``domain`` 而不是 ``application``：分块是纯函数规则，而 ``adapters/pg`` 的检索入库
也要用它（``readable_chunks`` 在仓储里拼定位信息），application 与 adapters 不能互相引用
（``pyproject.toml`` 的 import-linter 契约），纯规则只有落在最底层的 domain 才能被两边共用。
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping, Sequence
from typing import Any


def plain_text(element: Mapping[str, Any]) -> str:
    # 表格的完整 HTML 与纯文本同时保留信息；不沿用旧抽取的 6000 字截断。
    source = str(element.get("html") or element.get("text") or "")
    return html.unescape(re.sub(r"<[^>]+>", " ", source))


def split_elements(elements: Sequence[Mapping[str, Any]], size: int = 1800) -> list[dict]:
    if size < 200:
        raise ValueError("分块长度过小")
    chunks = []
    chapter = ""
    for element in elements:
        content = plain_text(element)
        if element.get("type") == "title":
            chapter = content.strip()
        for start in range(0, len(content), size):
            end = min(start + size + 150, len(content))
            if content[start:end].strip():
                chunks.append(
                    {
                        "element_id": element["id"],
                        "ordinal": len(chunks),
                        "char_start": start,
                        "char_end": end,
                        "chapter": chapter,
                        "content": content[start:end],
                    }
                )
    return chunks
