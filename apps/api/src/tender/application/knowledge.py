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
    # 保留块身份：支持性校验据此回查同块原文和邻近块，判断条号、章节与资料归属。
    return {
        key: row.get(key)
        for key in (
            "block_id",
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
    """校验字段-值结构：{field, group, sort_order, values:[{value, citations}], note}。

    - field 是解析字段名；group 是展示分类（如“甲方信息”），前端按它分组。
    - sort_order 是字段在所属分组内的展示顺序，前端按它稳定排序；同序按提交顺序。
    - 证据绑定在具体值上：同一字段出现多个值（如交货期 30 日与 45 日）时，
      每个值带自己的引用，前端才能分别定位各自原文并提醒不一致。
    """
    if not isinstance(raw, list):
        raise ValueError("结果必须是字段数组")
    result = []
    for order, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError("字段条目必须是对象")
        field = entry.get("field")
        values = entry.get("values")
        if not isinstance(field, str) or not field.strip():
            raise ValueError("字段条目缺少字段名")
        group = entry.get("group", "")
        if not isinstance(group, str):
            raise ValueError("字段分类必须是文字")
        sort_order = entry.get("sort_order")
        if sort_order is None:
            # 未提供时按提交顺序展示，模型只需在有意调整展示顺序时填写。
            sort_order = order
        if not isinstance(sort_order, int) or isinstance(sort_order, bool) or sort_order < 0:
            raise ValueError("字段展示顺序必须是非负整数")
        if not isinstance(values, list) or not values:
            raise ValueError("字段条目缺少解析值列表")
        clean_values = []
        for value_entry in values:
            if not isinstance(value_entry, dict):
                raise ValueError("解析值必须是对象")
            value = value_entry.get("value")
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"字段“{field[:60]}”存在空解析值")
            references = value_entry.get("citations", [])
            if not isinstance(references, list) or not references:
                raise ValueError(f"字段“{field[:60]}”的每个解析值必须附带原文依据")
            refs = []
            for ref in references:
                if not isinstance(ref, dict) or str(ref.get("block_id")) not in read_blocks:
                    raise ValueError("引用了未读取或不属于本次任务的块")
                quote = ref.get("quote")
                if not isinstance(quote, str):
                    raise ValueError("引用缺少原文摘录")
                try:
                    refs.append(citation(read_blocks[str(ref["block_id"])], quote))
                except ValueError as exc:
                    # 大批提交只报“引文无效”无法知道应补读哪一块，导致模型反复重写无关节点。
                    raise ValueError(
                        f"字段“{field[:80]}”引用 {str(ref['block_id'])[:60]} 校验失败：{exc}"
                    ) from exc
            clean_values.append({"value": value, "citations": refs})
        note = entry.get("note", "")
        if not isinstance(note, str):
            raise ValueError("备注必须是文字")
        clean = {
            "id": fingerprint([field, clean_values])[:20],
            "field": field,
            "group": group,
            "sort_order": sort_order,
            "values": clean_values,
            "note": note,
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
