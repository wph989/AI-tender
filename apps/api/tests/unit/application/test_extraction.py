"""锚点文档、章节路径、分块、标段识别与证据校验。

这里盯的是「模型看到的正文长什么样」和「模型给的锚点/引文能不能信」：
锚点文档少一段正文，字段就永远抽不到；校验放行一个不存在的锚点，
阶段 2 的「证据反查 404 率 = 0」当场失效。
"""

from __future__ import annotations

from typing import Any

import pytest

from tender.application.extraction import (
    TextChunk,
    _locate_quote,
    anchor_text,
    build_anchor_document,
    identify_lots,
    select_chunks,
    validate_result,
)
from tender.application.fields import FIELD_BY_KEY


def _element(
    anchor: str,
    text: str,
    *,
    element_id: int | None = None,
    type: str = "paragraph",
    page: int = 1,
    order: int = 1,
    level: int | None = None,
    parent_id: int | None = None,
    html: str | None = None,
    continues_prev: bool = False,
) -> dict[str, Any]:
    return {
        "id": element_id,
        "anchor": anchor,
        "type": type,
        "text": text,
        "page_no": page,
        "order_no": order,
        "level": level,
        "parent_id": parent_id,
        "html": html,
        "continues_prev": continues_prev,
    }


def _by_anchor(*elements: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(element["anchor"]): element for element in elements}


def _chunk(section_path: str, text: str) -> TextChunk:
    return TextChunk(section_path, (), text)


def test_anchor_text_wraps_anchor_and_collapses_whitespace() -> None:
    rendered = anchor_text(_element("p1b2", "招标   文件\n\n（草案） &amp; 附件"))

    # 换行也折叠成空格：正文里的排版换行不该进证据引文。
    assert rendered == "<<p1b2>> 招标 文件 （草案） & 附件"


def test_anchor_text_prefers_table_html_over_plain_text() -> None:
    element = _element(
        "p1b3",
        "单元格占位",
        type="table",
        html="<table><tr><td>预算</td><td>100 万</td></tr></table>",
    )

    rendered = anchor_text(element)

    assert rendered == "<<p1b3>> | 预算 | 100 万"
    assert "单元格占位" not in rendered


def test_anchor_text_truncates_over_long_block() -> None:
    rendered = anchor_text(_element("p1b4", "甲" * 7_000), max_chars=100)

    assert rendered == "<<p1b4>> " + "甲" * 100 + " [截断]"


def test_build_anchor_document_orders_and_drops_page_furniture() -> None:
    elements = [
        _element("p2b1", "正文二", element_id=3, page=2, order=1),
        _element("p1b1", "第一章 总则", element_id=1, type="title", level=1, page=1, order=1),
        _element("p1b9", "页脚", element_id=9, type="footer", page=1, order=9),
        _element("p1b2", "正文一", element_id=2, page=1, order=2, parent_id=1),
        _element("p1b0", "页眉", element_id=10, type="header", page=1, order=0),
    ]

    included, chunks = build_anchor_document(elements)

    assert [item["anchor"] for item in included] == ["p1b1", "p1b2", "p2b1"]
    # 有 parent_id 就沿标题链走；没有就退回「当前标题栈」，两条路必须给出同一个路径。
    assert included[1]["_section_path"] == "第一章 总则"
    assert included[2]["_section_path"] == "第一章 总则"
    assert len(chunks) == 1
    assert chunks[0].section_path == "第一章 总则"
    assert chunks[0].text.startswith("<章节路径>第一章 总则</章节路径>\n")
    assert [item["anchor"] for item in chunks[0].elements] == ["p1b1", "p1b2", "p2b1"]


def test_section_path_follows_title_levels() -> None:
    elements = [
        _element("p1b1", "第一章 总则", element_id=1, type="title", level=1, order=1),
        _element("p1b2", "1.1 适用范围", element_id=2, type="title", level=2, order=2),
        _element("p1b3", "本文件适用于……", element_id=3, order=3),
    ]

    included, _ = build_anchor_document(elements)

    assert included[1]["_section_path"] == "第一章 总则 > 1.1 适用范围"
    assert included[2]["_section_path"] == "第一章 总则 > 1.1 适用范围"


def test_level_one_title_starts_a_new_chunk() -> None:
    elements = [
        _element("p1b1", "第一章", element_id=1, type="title", level=1, order=1),
        _element("p1b2", "甲", element_id=2, order=2),
        _element("p1b3", "第二章", element_id=3, type="title", level=1, order=3),
        _element("p1b4", "乙", element_id=4, order=4),
    ]

    _, chunks = build_anchor_document(elements)

    assert [chunk.section_path for chunk in chunks] == ["第一章", "第二章"]
    assert [item["anchor"] for item in chunks[1].elements] == ["p1b3", "p1b4"]


def test_large_chapter_splits_with_one_block_overlap() -> None:
    elements = [
        _element("p1b1", "甲" * 7_000, element_id=1, order=1),
        _element("p1b2", "乙" * 7_000, element_id=2, order=2),
    ]

    _, chunks = build_anchor_document(elements)

    assert len(chunks) == 2
    # 重叠一个块是刻意的：跨块续写的句子不能因为分块被腰斩。
    assert [item["anchor"] for item in chunks[1].elements] == ["p1b1", "p1b2"]


def test_continuation_block_stays_in_previous_chunk() -> None:
    elements = [
        _element("p1b1", "甲" * 7_000, element_id=1, order=1),
        _element("p1b2", "乙" * 7_000, element_id=2, order=2, continues_prev=True),
    ]

    _, chunks = build_anchor_document(elements)

    assert len(chunks) == 1
    assert [item["anchor"] for item in chunks[0].elements] == ["p1b1", "p1b2"]


def test_select_chunks_ranks_by_terms_and_falls_back_to_prefix() -> None:
    field = FIELD_BY_KEY["project_name"]
    unrelated = _chunk("第一章 投标人须知", "投标人应当按本文件要求编制投标文件。")
    matching = _chunk("第二章 项目概况", "项目名称：某市政道路工程")

    # 命中关键词的章节优先，没命中的整章不进 prompt。
    assert select_chunks(field, [unrelated, matching]) == [matching]
    # 一个关键词都不命中时退化成前 limit 个，而不是把整份文档丢给模型。
    plain = [_chunk("第一章", "甲"), _chunk("第二章", "乙")]
    assert select_chunks(field, plain, limit=1) == plain[:1]


def test_select_chunks_keeps_all_for_open_ended_fields() -> None:
    field = FIELD_BY_KEY["qualification_requirements"]
    chunks = [_chunk("第一章", "甲"), _chunk("第二章", "乙")]

    assert select_chunks(field, chunks) == chunks


def test_identify_lots_uses_titles_only_and_dedupes() -> None:
    elements = [
        _element("p1b1", "第一标段 土建工程", element_id=1, type="title", order=1),
        _element("p1b2", "第一标段", element_id=2, type="title", order=2),
        _element("p1b3", "招标范围包括第一标段与第二标段", element_id=3, order=3),
        _element("p1b4", "Ａ包 设备采购", element_id=4, type="title", order=4),
    ]

    lots = identify_lots(elements)

    assert [lot.code for lot in lots] == ["A包", "第一标段"]
    # 正文里提到标段只用于覆盖判断，不建标段；先出现的标题保留原名。
    assert lots[1].name == "第一标段土建工程"
    assert all(lot.confidence == pytest.approx(0.9) for lot in lots)


def _valid_raw(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "field_key": "project_name",
        "value": "某市政道路工程",
        "value_text": "某市政道路工程",
        "quote": "项目名称：某市政道路工程",
        "evidence": ["p1b1"],
        "confidence": 0.9,
        "not_found": False,
        "lot_code": None,
    }
    raw.update(overrides)
    return raw


def test_validate_result_marks_auto_when_quote_matches_exactly() -> None:
    field = FIELD_BY_KEY["project_name"]
    element = _element("p1b1", "项目名称：某市政道路工程")

    result = validate_result(_valid_raw(), field, _by_anchor(element), set())

    assert result["status"] == "auto"
    evidence = result["evidence"][0]
    assert evidence["anchor"] == "p1b1"
    assert evidence["match_type"] == "exact"
    assert (evidence["char_start"], evidence["char_end"]) == (0, len(element["text"]))
    assert evidence["element"] is element


def test_unknown_anchor_cannot_produce_evidence() -> None:
    field = FIELD_BY_KEY["project_name"]
    element = _element("p1b1", "项目名称：某市政道路工程")

    result = validate_result(_valid_raw(evidence=["p9b9"]), field, _by_anchor(element), set())

    assert result["status"] == "not_found"
    assert result["value"] is None
    assert result["evidence"] == []


def test_quote_not_in_block_is_kept_for_review_with_full_text() -> None:
    field = FIELD_BY_KEY["project_name"]
    element = _element("p1b1", "项目名称：某市政道路工程")

    result = validate_result(
        _valid_raw(quote="项目名称：另一个工程"), field, _by_anchor(element), set()
    )

    assert result["status"] == "need_review"
    evidence = result["evidence"][0]
    assert evidence["match_type"] == "manual"
    assert evidence["char_start"] is None
    # 引文对不上时保留整块正文当证据，交给人工定位，而不是丢掉锚点。
    assert evidence["quote"] == "项目名称：某市政道路工程"


def test_normalized_match_maps_back_to_original_offsets() -> None:
    field = FIELD_BY_KEY["project_name"]
    text = "项目名称：某市政 道路工程（一期）"
    element = _element("p1b1", text)

    result = validate_result(
        _valid_raw(quote="项目名称:某市政道路工程(一期)", value_text="某市政道路工程"),
        field,
        _by_anchor(element),
        set(),
    )

    evidence = result["evidence"][0]
    assert evidence["match_type"] == "normalized"
    assert (evidence["char_start"], evidence["char_end"]) == (0, len(text))
    assert result["status"] == "auto"


def test_not_found_answer_drops_value_and_evidence() -> None:
    field = FIELD_BY_KEY["project_name"]
    element = _element("p1b1", "项目名称：某市政道路工程")

    result = validate_result(
        _valid_raw(not_found=True, value="某市政道路工程"), field, _by_anchor(element), set()
    )

    assert result["status"] == "not_found"
    assert result["value"] is None
    assert result["value_text"] == "未找到"
    assert result["evidence"] == []


def test_lot_code_must_come_from_known_lots() -> None:
    field = FIELD_BY_KEY["project_name"]
    element = _element("p1b1", "项目名称：某市政道路工程")
    by_anchor = _by_anchor(element)

    known = validate_result(
        _valid_raw(lot_code="第一标段"), field, by_anchor, {"第一标段", "第二标段"}
    )
    unknown = validate_result(_valid_raw(lot_code="第三标段"), field, by_anchor, {"第一标段"})

    assert known["lot_code"] == "第一标段"
    assert unknown["lot_code"] is None


def test_non_string_anchors_are_skipped_but_valid_ones_survive() -> None:
    field = FIELD_BY_KEY["project_name"]
    element = _element("p1b1", "项目名称：某市政道路工程")

    result = validate_result(_valid_raw(evidence=[5, "p1b1"]), field, _by_anchor(element), set())

    assert [item["anchor"] for item in result["evidence"]] == ["p1b1"]


@pytest.mark.parametrize(
    "override",
    [
        {"field_key": "other_field"},
        {"confidence": 1.5},
        {"confidence": True},
        {"quote": 3},
        {"evidence": "p1b1"},
    ],
)
def test_invalid_model_payload_is_rejected(override: dict[str, Any]) -> None:
    field = FIELD_BY_KEY["project_name"]
    element = _element("p1b1", "项目名称：某市政道路工程")

    with pytest.raises(ValueError):
        validate_result(_valid_raw(**override), field, _by_anchor(element), set())


def test_locate_quote_reports_which_strategy_matched() -> None:
    text = "投标截止时间：2026年3月1日"

    assert _locate_quote(text, text) == (0, len(text), "exact")
    assert _locate_quote("投标 截止时间", "投标截止时间")[2] == "normalized"
    assert _locate_quote(text, "开标时间") == (None, None, "manual")
    # 引文是空白（模型漏填）时按"人工定位"处理，不能匹配到正文第一个字符。
    assert _locate_quote(text, "   ") == (None, None, "manual")
