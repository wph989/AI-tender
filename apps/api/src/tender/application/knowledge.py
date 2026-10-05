"""资料分块、检索和引用校验的纯规则；范围由服务端先收窄，再进入这些算法。"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

CATEGORIES = {"engineering": "工程", "goods": "货物", "service": "服务"}
TOPICS = {"installation": "安装施工", "commissioning": "调试验收", "maintenance": "运维服务"}
PURPOSES = {
    "tender": "招标材料",
    "company": "企业资料",
    "history": "历史标书",
    "reference": "参考资料",
}
ITEM_KINDS = {"fact", "judgment", "suggestion", "conflict", "insufficient"}


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


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", html.unescape(text))


def citation(row: Mapping[str, Any], quote: str) -> dict:
    if not quote.strip() or normalized(quote) not in normalized(str(row["content"])):
        raise ValueError("引文必须逐字来自已读取的原文块")
    return {
        key: row.get(key)
        for key in (
            "source_id",
            "collection_id",
            "project_id",
            "project_file_id",
            "version_id",
            "parse_run_id",
            "element_id",
            "anchor",
            "page_no",
            "bbox",
            "file_name",
            "purpose",
        )
    } | {"quote": quote}


def validate_items(raw: object, read_blocks: Mapping[str, Mapping[str, Any]]) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("items 必须是数组")
    result = []
    for item in raw:
        if not isinstance(item, dict) or item.get("kind") not in ITEM_KINDS:
            raise ValueError("分析条目类型错误")
        title, body = item.get("title"), item.get("text")
        if not isinstance(title, str) or not title.strip() or not isinstance(body, str):
            raise ValueError("分析条目缺少标题或正文")
        references = item.get("citations", [])
        if not isinstance(references, list) or not references:
            raise ValueError("每条结论必须附带原文依据；未找到内容使用模块状态表示")
        refs = []
        for ref in references:
            if not isinstance(ref, dict) or str(ref.get("block_id")) not in read_blocks:
                raise ValueError("引用了未读取或不属于本次任务的块")
            quote = ref.get("quote")
            if not isinstance(quote, str):
                raise ValueError("引用缺少原文摘录")
            refs.append(citation(read_blocks[str(ref["block_id"])], quote))
        presentation = item.get("presentation", "paragraph")
        if presentation not in {"paragraph", "list", "table"}:
            raise ValueError("未知的报告展示类型")
        cells = item.get("cells", {})
        if not isinstance(cells, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in cells.items()
        ):
            raise ValueError("表格单元格必须为文字")
        clean = {
            "id": fingerprint([title, body, refs])[:20],
            "kind": item["kind"],
            "title": title,
            "text": body,
            "presentation": presentation,
            "cells": cells,
            "citations": refs,
            "verification": "pending",
        }
        result.append(clean)
    return result


def keywords(query: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9_.-]+|[\u4e00-\u9fff]+", query.lower())
    # 中文不依赖英文分词配置，长词同时生成二字词，兼顾精确名称与自然问句。
    return list(
        dict.fromkeys(
            words + [w[i : i + 2] for w in words if len(w) > 2 for i in range(len(w) - 1)]
        )
    )


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("向量维度不一致，需要重建索引")
    denominator = math.sqrt(sum(x * x for x in a) * sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / denominator if denominator else 0.0


def rank_chunks(
    rows: Sequence[Mapping[str, Any]],
    query: str,
    vector: Sequence[float] | None = None,
    limit: int = 16,
) -> list[dict]:
    tokens = keywords(query)
    lexical = sorted(
        ((sum(t in str(r["content"]).lower() for t in tokens), i) for i, r in enumerate(rows)),
        reverse=True,
    )
    lists = [[i for score, i in lexical if score > 0]]
    if vector is not None:
        semantic = sorted(
            (
                (cosine(vector, r["embedding"]), i)
                for i, r in enumerate(rows)
                if r.get("embedding") is not None
            ),
            reverse=True,
        )
        lists.append([i for _, i in semantic])
    scores: dict[int, float] = {}
    for indexes in lists:
        for rank, index in enumerate(indexes):
            scores[index] = scores.get(index, 0) + 1 / (60 + rank + 1)
    return [
        dict(rows[i]) | {"score": score}
        for i, score in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:limit]
    ]
