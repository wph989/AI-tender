"""字段定义、输出 schema 与规则抽取的口径。

这里盯的是「模型看到什么约束」与「规则候选从哪来」：schema 少一个 required，
模型漏字段就没有报错机会；正则写宽了会把无关句子当候选，污染后面的投票与冲突判定。
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from tender.application.fields import (
    FIELD_BY_KEY,
    FIELDS,
    comparable,
    json_schema,
    rule_candidates,
)


def _element(text: str, anchor: str = "p1b1") -> dict[str, object]:
    return {"anchor": anchor, "type": "paragraph", "text": text, "page_no": 1, "order_no": 1}


def test_field_keys_are_unique_and_groups_are_known() -> None:
    keys = [field.key for field in FIELDS]
    assert len(keys) == len(set(keys))
    # 分组决定结果面板的标签页；多一个拼错的分组键会在页面上凭空多一个标签。
    assert {field.group_key for field in FIELDS} == {
        "basic_info",
        "qualification",
        "risk",
        "scoring",
    }
    assert all(field.description and field.section_terms for field in FIELDS)
    assert FIELD_BY_KEY["project_name"].label == "项目名称"


def test_every_schema_is_closed_and_lists_all_required_keys() -> None:
    for field in FIELDS:
        schema = json_schema(field)
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        assert schema["properties"]["field_key"]["const"] == field.key
        assert schema["properties"]["evidence"]["items"]["pattern"] == "^p[1-9]\\d*b[1-9]\\d*$"


def test_anchor_pattern_accepts_only_positive_page_and_block() -> None:
    schema = json_schema(FIELD_BY_KEY["project_name"])
    pattern = re.compile(schema["properties"]["evidence"]["items"]["pattern"])

    assert pattern.fullmatch("p1b2")
    assert pattern.fullmatch("p12b345")
    # 锚点是 1-based：p0b1 / 1b2 / p1 都不合法，写进证据就是 404 的来源。
    assert not pattern.fullmatch("p0b1")
    assert not pattern.fullmatch("p1b0")
    assert not pattern.fullmatch("1b2")
    assert not pattern.fullmatch("p1")


def test_tender_no_candidate_collapses_whitespace_but_keeps_raw_quote() -> None:
    field = FIELD_BY_KEY["tender_no"]
    elements = [_element("招标编号：\n ABC-2024-001", "p2b7")]

    candidates = rule_candidates(field, elements)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["anchor"] == "p2b7"
    assert candidate["confidence"] == pytest.approx(0.82)
    # quote 是定位用的原文切片，value_text 是给人看的折叠形式，两者不能混用。
    assert candidate["quote"] == "招标编号：\n ABC-2024-001"
    assert candidate["value_text"] == "招标编号： ABC-2024-001"


def test_budget_amount_becomes_structured_cny_value() -> None:
    field = FIELD_BY_KEY["budget_amount"]

    candidates = rule_candidates(field, [_element("预算金额：人民币 1,200.50 万元")])

    assert len(candidates) == 1
    value = candidates[0]["value"]
    # 万元换算成元后再比较：金额字符串保留几位小数不是契约，数值才是。
    assert value == {"amount": "12005000.00", "currency": "CNY"}
    assert Decimal(value["amount"]) == Decimal("12005000")


def test_performance_bond_keeps_text_because_percentage_is_not_amount() -> None:
    field = FIELD_BY_KEY["performance_bond"]

    candidates = rule_candidates(field, [_element("履约保证金为合同金额的 5%")])

    assert len(candidates) == 1
    assert candidates[0]["value"] == "履约保证金为合同金额的 5%"


def test_multiple_matches_in_one_block_all_become_candidates() -> None:
    field = FIELD_BY_KEY["max_price"]

    candidates = rule_candidates(field, [_element("最高限价：100 万元；招标控制价：80 万元")])

    assert [candidate["value_text"] for candidate in candidates] == [
        "最高限价：100 万元",
        "招标控制价：80 万元",
    ]
    assert {candidate["anchor"] for candidate in candidates} == {"p1b1"}


def test_scan_all_and_non_matching_fields_produce_no_rule_candidates() -> None:
    qualification = FIELD_BY_KEY["qualification_requirements"]
    assert qualification.scan_all is True
    assert rule_candidates(qualification, [_element("投标人资格：具备一级资质")]) == []

    tender_no = FIELD_BY_KEY["tender_no"]
    assert rule_candidates(tender_no, [_element("这里没有任何编号信息")]) == []


def test_comparable_unifies_numbers_text_and_punctuation() -> None:
    assert comparable(50000) == comparable("50000")
    assert comparable(1.0) == comparable("1")
    assert comparable(Decimal("1.50")) == comparable("1.5")
    assert comparable("￥50,000 元") == comparable("￥50000元")
    # 全角与大小写差异不该造成"同一个值被当成两个候选"。
    assert comparable("ＡＢＣ") == comparable("abc")
    assert comparable({"a": 1, "b": [2, "3"]}) == comparable({"b": [2, 3], "a": 1.0})


def test_comparable_keeps_boolean_apart_from_number() -> None:
    # True 在 JSON 里是布尔，不是 1：归一化时必须保持两者的区别。
    assert comparable(True) != comparable(1)
