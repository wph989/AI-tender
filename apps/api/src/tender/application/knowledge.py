"""资料分块、检索和引用校验的纯规则；范围由服务端先收窄，再进入这些算法。"""

from __future__ import annotations

import html
import json
import math
import re
import unicodedata
from bisect import bisect_left, bisect_right
from collections.abc import Mapping, Sequence
from typing import Any

from tender.domain.digest import fingerprint

# 分块与去标签的纯规则落 domain，adapters 的检索仓储也要用；这里按用例层的入口再导出。
from tender.domain.knowledge_text import plain_text, split_elements

__all__ = [
    "align_citation",
    "citation",
    "dedupe_citations",
    "dedupe_values",
    "encode",
    "fingerprint",
    "keywords",
    "merge_field_entries",
    "plain_text",
    "rank_chunks",
    "source_signature",
    "source_state",
    "split_elements",
    "validate_items",
    "value_cores",
]

CATEGORIES = {"engineering": "工程", "goods": "货物", "service": "服务"}
TOPICS = {"installation": "安装施工", "commissioning": "调试验收", "maintenance": "运维服务"}
PURPOSES = {
    "tender": "招标材料",
    "company": "企业资料",
    "history": "历史标书",
    "reference": "参考资料",
}


def encode(value: object) -> str:
    """JSONB 参数与日志正文共用的序列化口径：中文不转义、未知类型落回字符串。"""
    return json.dumps(value, ensure_ascii=False, default=str)


def source_state(source: Mapping[str, Any]) -> str:
    if not source["is_parseable"]:
        return "unsupported"
    if source.get("active_job_id"):
        return "processing"
    # 转换或提交失败可能尚无 parse_run，必须回显最新文件处理错误，不能一直显示待处理。
    if source.get("processing_status") in {"failed", "canceled"}:
        return "failed"
    if source.get("parse_status") == "completed":
        return "ready"
    if source.get("parse_status") == "partial":
        return "partial"
    if source.get("parse_status") in {"failed", "canceled"}:
        return "failed"
    return "pending"


def source_signature(sources: Sequence[Mapping[str, Any]]) -> str:
    return fingerprint(
        [
            {k: row.get(k) for k in ("source_id", "version_id", "parse_run_id", "sha256", "role")}
            for row in sources
        ]
    )


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", html.unescape(text))


CORE_SPLIT = re.compile(r"[；;，,。！!？?\n\r\t、|｜/（）()]")
CORE_MIN_LENGTH = 3
# 换块改引对证据归属影响更大，短片段很容易撞上无关原文，要求更长的匹配。
MOVE_MIN_LENGTH = 6
QUOTE_WINDOW = 40
# 单个单元格/单行超过这个长度就不再当作摘录边界，避免长段落被整段引用。
SEGMENT_LIMIT = 160
# 覆盖摘录的拼接门槛：参与拼接的片段不能太短，跨度太大就退回单元格/窗口。
SPAN_MIN_CORE = 6
SPAN_LIMIT = 320
CITATION_IDENTITY = ("block_id", "source_id", "element_id", "page_no", "quote")


def match_text(text: str) -> str:
    """值回查用的比较文本：全半角与空白差异不参与比较，避免排版差异被当成新事实。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", html.unescape(text)))


def _index_map(text: str) -> tuple[str, list[int]]:
    """比较文本与每个字符在原文中的下标：匹配位置可还原成逐字来自原文的切片。"""
    chars: list[str] = []
    indexes: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            continue
        for piece in unicodedata.normalize("NFKC", char):
            chars.append(piece)
            indexes.append(index)
    return "".join(chars), indexes


def value_cores(value: str) -> list[str]:
    """切出可回查原文的值片段，长片段优先：整值、去标签后的值、标点切分片段。

    模型常用“标签：值”或“标段一（…）份额100%”这类表述，标签和括号往往不在原文里，
    只按整值回查会把正确取值判成无依据，所以继续用去标签、去标点的片段回查。
    """
    candidates = [value, *re.split(r"[:：]", value)[1:], *CORE_SPLIT.split(value)]
    cores: list[str] = []
    seen: set[str] = set()
    for candidate in sorted(candidates, key=lambda item: len(match_text(item)), reverse=True):
        core = match_text(candidate)
        if len(core) < CORE_MIN_LENGTH or core in seen:
            continue
        seen.add(core)
        cores.append(core)
    return cores


def _boundaries(content: str) -> list[int]:
    """比较文本里可作摘录边界的位置：单元格或换行分隔之后的第一个字符。"""
    boundaries = [0]
    normalized_index = 0
    run_length = 0
    strong = False
    for char in content:
        if char.isspace():
            run_length += 1
            strong = strong or char in "\n\r\t\u3000"
            continue
        if run_length and (strong or run_length >= 2) and boundaries[-1] != normalized_index:
            boundaries.append(normalized_index)
        run_length, strong = 0, False
        normalized_index += len(unicodedata.normalize("NFKC", char))
    if boundaries[-1] != normalized_index:
        boundaries.append(normalized_index)
    return boundaries


def locate_in(row: Mapping[str, Any], value: str) -> tuple[str, str] | None:
    """在块内定位取值的原文位置，返回（最长命中片段, 建议摘录）。

    - 命中片段够长且彼此相距不远时，摘录取覆盖它们的最小跨度：值由多处原文组成
      （如“分值构成”下面逐条列出）时，摘录能覆盖各条，不会只截到标题行。
    - 跨度太大或片段太短时退回单元格/窗口：表格里命中片段占值大半用单元格最精确，
      只是值的零头时用窗口，避免把金额等其余事实摘掉。
    """
    content = str(row.get("content") or "")
    cores = value_cores(value)
    if not cores or not content:
        return None
    text, indexes = _index_map(content)
    hits: list[tuple[int, int, str]] = []
    for core in cores:
        start = text.find(core)
        if start >= 0:
            hits.append((start, start + len(core), core))
    if not hits:
        return None
    longest = max(hits, key=lambda hit: len(hit[2]))
    spans = [hit for hit in hits if len(hit[2]) >= SPAN_MIN_CORE]
    if spans:
        left = min(hit[0] for hit in spans)
        right = max(hit[1] for hit in spans)
        if right - left <= SPAN_LIMIT:
            return longest[2], content[indexes[left] : indexes[right - 1] + 1].strip()
    start, end = longest[0], longest[1]
    left = max(0, start - QUOTE_WINDOW)
    right = min(len(text), end + QUOTE_WINDOW)
    window = content[indexes[left] : indexes[right - 1] + 1].strip()
    boundaries = _boundaries(content)
    segment_left = boundaries[bisect_right(boundaries, start) - 1]
    segment_right = boundaries[bisect_left(boundaries, end)]
    if (
        segment_left < segment_right
        and segment_right - segment_left <= SEGMENT_LIMIT
        and len(longest[2]) * 2 >= len(match_text(value))
    ):
        return longest[2], content[indexes[segment_left] : indexes[segment_right - 1] + 1].strip()
    return longest[2], window


def core_is_specific(core: str, value: str) -> bool:
    """命中片段必须足够具体才改写定位：表头等短通用词会把定位带偏到无关位置。

    例如“预估监理费”能命中表格表头，但真正承载“标段二 400 万元”的原文行
    里并不含这几个字；只有命中片段本身占值的一大部分时才说明找到了值所在位置。
    """
    total = len(match_text(value))
    return len(core) >= 6 or len(core) * 3 >= total


def citation_identity(ref: Mapping[str, Any]) -> tuple[str, ...]:
    """同一处定位的身份：同一元素、同一页、同一段原文摘录。"""
    return tuple(str(ref.get(key)) for key in CITATION_IDENTITY)


def dedupe_citations(refs: Sequence[dict]) -> list[dict]:
    """同一处原文只留一条引用；同一元素里互相包含的摘录按同一处只保留更完整的一条。"""
    unique: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    for ref in refs:
        key = citation_identity(ref)
        if key in seen:
            continue
        text = match_text(str(ref.get("quote") or ""))
        merged = False
        for index, kept in enumerate(unique):
            if (kept.get("source_id"), kept.get("element_id")) != (
                ref.get("source_id"),
                ref.get("element_id"),
            ):
                continue
            kept_text = match_text(str(kept.get("quote") or ""))
            if not text or not kept_text:
                continue
            if text in kept_text or kept_text in text:
                if len(text) > len(kept_text):
                    unique[index] = ref
                merged = True
                break
        if merged:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


def dedupe_values(values: Sequence[dict]) -> list[dict]:
    """同一字段的相同取值合并为一条、引用取并集：同一事实不必重复展示。"""
    unique: list[dict] = []
    index: dict[str, dict] = {}
    for value in values:
        key = match_text(str(value.get("value") or ""))
        existing = index.get(key)
        if existing is None:
            merged = {
                "value": value.get("value"),
                "citations": dedupe_citations(list(value.get("citations") or [])),
            }
            index[key] = merged
            unique.append(merged)
            continue
        existing["citations"] = dedupe_citations(
            [*existing["citations"], *(value.get("citations") or [])]
        )
    return unique


def covered_cores(cores: Sequence[str], text: str, value: str) -> set[str]:
    """原文覆盖了哪些够具体的取值片段：覆盖越多说明定位越完整，用来判断是否值得改写。"""
    return {core for core in cores if core_is_specific(core, value) and core in text}


def align_citation(
    read_blocks: Mapping[str, Mapping[str, Any]], ref: Mapping[str, Any], value: str
) -> dict:
    """把引用收敛到该值真正出现的原文：真实定位优先于随手复制的同块其它摘录。

    只校验“摘录逐字来自该块”会放过“用单位名称的摘录支撑地址”这类假定位：
    同一块里写着多个事实，摘录与值其实是两回事。这里按值回查原文位置，
    并且只在确实覆盖了更多取值片段时改写——引文已经覆盖的片段不比新摘录少时保持原样，
    避免把模型给出的更完整原文换成更窄的片段。
    本块确实没有该值、同一来源其它已读块唯一含该值时才改引；值本身是概括、原文里没有对应
    文字时保持原引用，是否成立仍交给支持性校验，运行时不做无法判定的改写。
    """
    cores = value_cores(value)
    if not cores:
        return dict(ref)
    covered = covered_cores(cores, match_text(str(ref.get("quote") or "")), value)
    current = read_blocks.get(str(ref.get("block_id")))
    if current is not None:
        located = locate_in(current, value)
        if located is not None and core_is_specific(located[0], value):
            if covered_cores(cores, match_text(located[1]), value) > covered:
                return {**dict(ref), "quote": located[1]}
    # 本块确实没有该值才考虑换块；短片段不足以证明同一事实，不换。
    hits: list[tuple[Mapping[str, Any], tuple[str, str]]] = []
    for row in read_blocks.values():
        # 原文件与补充文件可能分别证明修订前后状态，不能把旧条款改引成新条款。
        # 文本匹配只能纠正同一来源内的位置，跨来源是否必要交给支持性校验。
        if row.get("source_id") != ref.get("source_id"):
            continue
        located = locate_in(row, value)
        if located is None or len(located[0]) < MOVE_MIN_LENGTH:
            continue
        if not core_is_specific(located[0], value):
            continue
        if covered_cores(cores, match_text(located[1]), value) > covered:
            hits.append((row, located))
    if not hits:
        return dict(ref)
    preferred = (
        [hit for hit in hits if str(hit[0].get("element_id")) == str(ref.get("element_id"))]
        or hits
    )
    longest = max(len(hit[1][0]) for hit in preferred)
    best = [hit for hit in preferred if len(hit[1][0]) == longest]
    places = {(str(hit[0].get("source_id")), str(hit[0].get("element_id"))) for hit in best}
    if len(places) > 1:
        # 同一段文字出现在多处，无法确定指向哪一处，保持原引用交给支持性校验。
        return dict(ref)
    row, located = best[0]
    return citation(row, located[1])


def merge_field_entries(entries: Sequence[dict], *, is_outline: bool = False) -> list[dict]:
    """把同一“分组:字段名”的多个已核实版本合并成一行：值去重、引用去重、id 重算。

    同一字段常在多批提交里被拆开或改写；按 id 并存会表现为重复行与重复定位。
    只合并全部已核实的版本，未核实的保持独立，避免把待校验内容并进已通过结果。
    """
    # 大纲已按节点 id 累计更新；同组同名材料仍可能属于不同父级，不能按字段名再次归并。
    # 展示历史大纲同样保留原节点，避免把不同父路径的要求拼到一起。
    if is_outline:
        return list(entries)
    merged: dict[str, dict] = {}
    others: list[dict] = []
    for entry in entries:
        if entry.get("business") or entry.get("record_id"):
            # 同名展示字段不代表同一业务要求，必须保留各自的身份、条件与适用范围。
            others.append(entry)
            continue
        if entry.get("verification") != "supported":
            others.append(entry)
            continue
        label = str(entry.get("group", "")) + "\u0000" + str(entry.get("field", ""))
        target = merged.get(label)
        if target is None:
            merged[label] = {**entry, "values": dedupe_values(list(entry.get("values") or []))}
            continue
        target["values"] = dedupe_values([*target["values"], *(entry.get("values") or [])])
        target["sort_order"] = min(
            int(target.get("sort_order") or 0), int(entry.get("sort_order") or 0)
        )
        notes = dict.fromkeys(
            part for part in (target.get("note"), entry.get("note")) if part
        )
        target["note"] = "；".join(notes)[:600]
        # id 用合并后的内容重算，与 validate_items 的取值公式一致，保证跨请求稳定。
        target["id"] = fingerprint([target["field"], target["values"]])[:20]
    return [*merged.values(), *others]


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


def validate_items(
    raw: object,
    read_blocks: Mapping[str, Mapping[str, Any]],
    *,
    align: bool = True,
) -> list[dict]:
    """校验字段-值结构：{field, group, sort_order, values:[{value, citations}], note}。

    - field 是解析字段名；group 是展示分类（如“甲方信息”），前端按它分组。
    - sort_order 是字段在所属分组内的展示顺序，前端按它稳定排序；同序按提交顺序。
    - 证据绑定在具体值上：同一字段出现多个值（如交货期 30 日与 45 日）时，
      每个值带自己的引用，前端才能分别定位各自原文并提醒不一致。
    - 值的引用会按值回查原文收敛到它真正所在的位置；同一位置和相同取值在此去重，
      避免“用同块其它事实当依据”的假定位和同一事实的重复行。
    - align=False 供格式大纲使用：节点级引文必须同时覆盖名称和全部编制要求，
      按值收窄会让后续“逐字来自引文”的校验看不到要求原文。
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
                    registered = citation(read_blocks[str(ref["block_id"])], quote)
                    refs.append(
                        align_citation(read_blocks, registered, value) if align else registered
                    )
                except ValueError as exc:
                    # 大批提交只报“引文无效”无法知道应补读哪一块，导致模型反复重写无关节点。
                    raise ValueError(
                        f"字段“{field[:80]}”引用 {str(ref['block_id'])[:60]} 校验失败：{exc}"
                    ) from exc
            clean_values.append({"value": value, "citations": refs})
        clean_values = dedupe_values(clean_values)
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
