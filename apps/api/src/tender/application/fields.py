"""字段定义与规则抽取入口；集中维护 schema，避免提示词和结果 API 各自漂移。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    key: str
    label: str
    group_key: str
    value_kind: str
    description: str
    section_terms: tuple[str, ...]
    rule_pattern: str | None = None
    scan_all: bool = False


FIELDS: tuple[FieldDefinition, ...] = (
    FieldDefinition(
        "project_name",
        "项目名称",
        "basic_info",
        "string",
        "招标项目或采购项目的正式名称",
        ("项目概况", "项目名称", "采购项目", "招标公告", "项目基本情况"),
    ),
    FieldDefinition(
        "tender_no",
        "招标编号",
        "basic_info",
        "string",
        "招标编号、采购编号或项目编号",
        ("招标编号", "采购编号", "项目编号", "投标人须知前附表"),
        r"(?:招标|采购|项目)编号\s*[:：]?\s*[A-Za-z0-9（）()/_—.-]{3,}",
    ),
    FieldDefinition(
        "budget_amount",
        "预算金额",
        "basic_info",
        "object",
        "项目预算或采购预算金额，保留币种与单位",
        ("预算", "资金来源", "项目概况"),
        r"(?:预算金额|采购预算|项目预算|预算总额)\s*(?:为|[:：])?\s*(?:人民币)?\s*[￥¥]?\s*[\d,，]+(?:\.\d+)?\s*(?:元|万元|亿元)?",
    ),
    FieldDefinition(
        "max_price",
        "最高限价",
        "basic_info",
        "object",
        "最高投标限价、招标控制价或最高限价",
        ("最高限价", "招标控制价", "投标报价"),
        r"(?:最高投标限价|最高限价|招标控制价)\s*(?:为|[:：])?\s*(?:人民币)?\s*[￥¥]?\s*[\d,，]+(?:\.\d+)?\s*(?:元|万元|亿元)?",
    ),
    FieldDefinition(
        "bid_bond_amount",
        "投标保证金",
        "basic_info",
        "object",
        "投标保证金的金额或免缴要求",
        ("投标保证金", "保证金", "投标人须知前附表"),
        r"(?:投标保证金|投标担保)\D{0,20}(?:人民币)?\s*[￥¥]?\s*[\d,，]+(?:\.\d+)?\s*(?:元|万元|亿元)?",
    ),
    FieldDefinition(
        "submission_deadline",
        "投标截止时间",
        "basic_info",
        "string",
        "提交投标文件的截止日期和时间",
        ("投标截止", "递交投标文件", "提交投标文件", "投标人须知前附表"),
        r"(?:投标截止时间|递交投标文件截止时间|提交投标文件截止时间)\D{0,24}20\d{2}年?\d{1,2}月?\d{1,2}日?(?:\s*[0-2]?\d[:：时点]\d{0,2}分?)?",
    ),
    FieldDefinition(
        "opening_time",
        "开标时间",
        "basic_info",
        "string",
        "开标日期和时间",
        ("开标时间", "开标地点", "开标"),
        r"开标时间\D{0,20}20\d{2}年?\d{1,2}月?\d{1,2}日?(?:\s*[0-2]?\d[:：时点]\d{0,2}分?)?",
    ),
    FieldDefinition(
        "delivery_period",
        "工期或交付期",
        "basic_info",
        "string",
        "合同工期、服务期限或交付期限",
        ("工期", "服务期限", "交付期", "合同履行"),
        r"(?:计划工期|工期|服务期限|交付期限)\D{0,20}\d{1,4}\s*(?:日历天|天|个月|月|年)",
    ),
    FieldDefinition(
        "bid_validity",
        "投标有效期",
        "basic_info",
        "string",
        "投标有效期及其计算起点",
        ("投标有效期", "有效期"),
        r"投标有效期\D{0,20}\d{1,4}\s*(?:日历天|天|日)",
    ),
    FieldDefinition(
        "payment_terms",
        "付款方式",
        "basic_info",
        "list",
        "合同付款节点、比例和条件",
        ("付款", "支付", "合同价款", "结算"),
        scan_all=True,
    ),
    FieldDefinition(
        "qualification_requirements",
        "资格要求",
        "qualification",
        "list",
        "投标人或供应商资格条件，每项独立列出",
        ("投标人资格", "资格条件", "资格要求", "资质要求", "资格审查"),
        scan_all=True,
    ),
    FieldDefinition(
        "rejection_clauses",
        "否决投标条款",
        "risk",
        "list",
        "废标、否决投标或无效投标的条件",
        ("否决投标", "废标", "无效投标", "不予受理"),
        scan_all=True,
    ),
    FieldDefinition(
        "scoring_criteria",
        "评分标准",
        "scoring",
        "list",
        "评审因素、评分细则及分值",
        ("评标办法", "评分标准", "评审因素", "技术评分", "商务评分"),
        scan_all=True,
    ),
    FieldDefinition(
        "performance_bond",
        "履约保证金",
        "basic_info",
        "object",
        "履约保证金比例、金额或免缴条件",
        ("履约保证金", "履约担保", "合同条款"),
        r"(?:履约保证金|履约担保)\D{0,20}(?:\d+(?:\.\d+)?\s*%)",
    ),
)


FIELD_BY_KEY = {field.key: field for field in FIELDS}


def json_schema(field: FieldDefinition) -> dict[str, Any]:
    """单字段输出 schema 在服务端校验；不依赖模型厂商对 JSON Schema 的支持。"""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "field_key": {"const": field.key},
            "value": {"type": ["string", "number", "object", "array", "null"]},
            "value_text": {"type": "string"},
            "quote": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {"type": "string", "pattern": "^p[1-9]\\d*b[1-9]\\d*$"},
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "not_found": {"type": "boolean"},
            "lot_code": {"type": ["string", "null"]},
        },
        "required": [
            "field_key",
            "value",
            "value_text",
            "quote",
            "evidence",
            "confidence",
            "not_found",
            "lot_code",
        ],
    }


def rule_candidates(field: FieldDefinition, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """仅对高确定性字段跑规则路，原文证据随候选一起返回以便独立比对。"""
    if field.rule_pattern is None:
        return []
    pattern = re.compile(field.rule_pattern, re.IGNORECASE)
    candidates: list[dict[str, Any]] = []
    for element in elements:
        source = element.get("text") or ""
        for match in pattern.finditer(source):
            quote = match.group(0).strip()
            if not quote:
                continue
            value_text = re.sub(r"\s+", " ", quote)
            value_json: Any = _rule_value(field, value_text)
            candidates.append(
                {
                    "value": value_json,
                    "value_text": value_text,
                    "quote": quote,
                    "anchor": element["anchor"],
                    "confidence": 0.82,
                }
            )
    return candidates


def comparable(value: Any) -> str:
    """结构化值按稳定形式比较，数值 50000 与字符串 "50000" 视为一致。"""
    import json
    from collections.abc import Mapping

    def normalize(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {str(key): normalize(item[key]) for key in sorted(item, key=str)}
        if isinstance(item, list):
            return [normalize(part) for part in item]
        if isinstance(item, (int, float, Decimal)) and not isinstance(item, bool):
            try:
                number = Decimal(str(item)).normalize()
                return format(number, "f")
            except InvalidOperation:
                return str(item)
        if isinstance(item, str):
            raw = unicodedata.normalize("NFKC", item).casefold()
            return re.sub(r"[\s\u3000,，。:：;；()（）\[\]【】]", "", raw)
        return item

    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _rule_value(field: FieldDefinition, text: str) -> Any:
    if field.value_kind == "object" and field.key != "performance_bond":
        amount = re.search(r"[￥¥]?\s*([\d,，]+(?:\.\d+)?)\s*(元|万元|亿元)?", text)
        if amount is not None:
            try:
                number = Decimal(amount.group(1).replace(",", "").replace("，", ""))
                multiplier = {
                    "元": Decimal(1),
                    "万元": Decimal(10_000),
                    "亿元": Decimal(100_000_000),
                }.get(amount.group(2), Decimal(1))
                return {"amount": str(number * multiplier), "currency": "CNY"}
            except InvalidOperation:
                pass
    return text
