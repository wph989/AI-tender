"""执行两遍式字段抽取，并合并规则候选、低置信复抽与逐块证据。"""

from __future__ import annotations

import json
from typing import Any

from tender.application.extraction import TextChunk, _locate_quote, select_chunks, validate_result
from tender.application.fields import FieldDefinition, comparable, json_schema, rule_candidates
from tender.ports.llm import StructuredTextModel


async def extract_field(
    model: StructuredTextModel,
    field: FieldDefinition,
    elements: list[dict[str, Any]],
    chunks: list[TextChunk],
    lots: list[dict[str, Any]],
    *,
    hint: str | None = None,
    retry_model: StructuredTextModel | None = None,
) -> dict[str, Any]:
    # 低置信复抽走 retry 功能配置：第二轮可以换更强的模型，而首次抽取的范围不变。
    second_model = retry_model or model
    selected = select_chunks(field, chunks)
    by_anchor = {str(element["anchor"]): element for element in elements}
    lot_codes = {str(lot["code"]) for lot in lots if lot.get("code")}
    candidates: list[dict[str, Any]] = []
    for chunk in selected:
        first = await _extract_chunk(model, field, chunk, lots, by_anchor, lot_codes, hint, False)
        if first["status"] == "not_found":
            continue
        if first["confidence"] < 0.65 or first["status"] == "need_review":
            second = await _extract_chunk(
                second_model, field, chunk, lots, by_anchor, lot_codes, hint, True
            )
            first = _reconcile_passes(first, second)
        candidates.append(first)

    rules = _verified_rules(field, elements, by_anchor)
    return _combine(field, candidates, rules)


async def _extract_chunk(
    model: StructuredTextModel,
    field: FieldDefinition,
    chunk: TextChunk,
    lots: list[dict[str, Any]],
    by_anchor: dict[str, dict[str, Any]],
    lot_codes: set[str],
    hint: str | None,
    second_pass: bool,
) -> dict[str, Any]:
    prompt = _prompt(field, chunk, lots, hint, second_pass)
    response = await model.complete(prompt)
    try:
        raw = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"模型对字段 {field.key} 返回非法 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"模型对字段 {field.key} 必须返回 JSON 对象")
    result = validate_result(raw, field, by_anchor, lot_codes)
    result["model"] = response.model
    result["registry_model_id"] = response.registry_model_id
    return result


def _prompt(
    field: FieldDefinition,
    chunk: TextChunk,
    lots: list[dict[str, Any]],
    hint: str | None,
    second_pass: bool,
) -> str:
    independent = (
        "这是独立复核轮次。重新阅读当前正文，忽略任何先前答案，不要为了保持一致而沿用旧结论。\n"
        if second_pass
        else ""
    )
    hint_text = f"<检索提示>{hint}</检索提示>\n" if hint else ""
    lot_values = [
        {"code": lot.get("code"), "name": lot.get("name")} for lot in lots if lot.get("code")
    ]
    schema = json.dumps(json_schema(field), ensure_ascii=False)
    return (
        "你是招标文件结构化抽取助手。只依据正文作答，不能使用外部知识或推测。\n"
        "quote 必须逐字来自一个证据块；evidence 只能填写正文中出现的锚点。\n"
        "找不到字段时返回 not_found=true、value=null、value_text=未找到、quote 为空、"
        "evidence=[]、lot_code=null。\n"
        "多值字段把每项写入 value 数组，并选择能支持这些值的锚点。\n"
        "标段不明确或适用全文时 lot_code=null；只能从给定标段清单中选择。\n"
        f"{independent}{hint_text}"
        f"<字段>{field.key} / {field.label}</字段>\n"
        f"<定义>{field.description}</定义>\n"
        f"<标段清单>{json.dumps(lot_values, ensure_ascii=False)}</标段清单>\n"
        f"<输出约束>{schema}</输出约束>\n"
        f"<正文>\n{chunk.text}\n</正文>"
    )


def _reconcile_passes(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    if second["status"] == "not_found":
        first["status"] = "conflict"
        first["confidence"] = min(float(first["confidence"]), 0.5)
        first["pass_conflict"] = True
        return first
    if comparable(first.get("value")) == comparable(second.get("value")):
        first["confidence"] = min(0.99, max(first["confidence"], second["confidence"]) + 0.08)
        if first["status"] != "need_review" and second["status"] != "need_review":
            first["status"] = "auto"
        first["evidence"] = _unique_evidence(first["evidence"] + second["evidence"])
        return first
    first["status"] = "conflict"
    first["confidence"] = min(float(first["confidence"]), float(second["confidence"]), 0.5)
    first["conflicting_pass"] = second
    return first


def _verified_rules(
    field: FieldDefinition,
    elements: list[dict[str, Any]],
    by_anchor: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for candidate in rule_candidates(field, elements):
        element = by_anchor.get(candidate["anchor"])
        if element is None:
            continue
        start, end, match_type = _locate_quote(str(element.get("text") or ""), candidate["quote"])
        if start is None:
            continue
        verified.append(
            {
                **candidate,
                "evidence": [
                    {
                        "anchor": candidate["anchor"],
                        "element": element,
                        "quote": candidate["quote"],
                        "char_start": start,
                        "char_end": end,
                        "match_type": match_type,
                    }
                ],
                "status": "auto",
            }
        )
    return verified


def _combine(
    field: FieldDefinition,
    candidates: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    if field.value_kind == "list":
        return _combine_list(candidates, rules)
    llm = _unique_values(candidates)
    rule_values = _unique_values(rules)
    disputed = [item for item in candidates if isinstance(item.get("conflicting_pass"), dict)]
    if disputed:
        pass_values = [part for item in disputed for part in (item, item["conflicting_pass"])]
        return _conflict_result(field, _unique_values(pass_values), rule_values)
    if not llm and not rule_values:
        return _not_found()
    if not llm:
        return _conflict_result(field, [], rule_values)
    values = llm + [
        item
        for item in rule_values
        if comparable(item["value"]) not in {comparable(x["value"]) for x in llm}
    ]
    if len(values) > 1:
        return _conflict_result(field, llm, rule_values)
    chosen = max(llm or rule_values, key=lambda item: float(item.get("confidence", 0)))
    matched_rule = bool(rule_values) and comparable(chosen["value"]) == comparable(
        rule_values[0]["value"]
    )
    evidence = _unique_evidence(
        [
            item
            for candidate in (llm + rule_values if matched_rule else llm)
            for item in candidate.get("evidence", [])
        ]
    )
    status = chosen["status"]
    confidence = float(chosen["confidence"])
    strategy = "rule+llm" if matched_rule else chosen.get("strategy", "llm")
    if matched_rule:
        confidence = min(0.99, (confidence + float(rule_values[0]["confidence"])) / 2 + 0.08)
    return {
        "value": chosen["value"],
        "value_text": chosen["value_text"],
        "confidence": confidence,
        "status": status,
        "strategy": strategy,
        "evidence": evidence,
        "lot_code": chosen.get("lot_code"),
        # 实际使用的模型跟着结果落库；发生失败转移时，以产出被采纳值的那次为准。
        "model": chosen.get("model"),
        "registry_model_id": chosen.get("registry_model_id"),
    }


def _combine_list(candidates: list[dict[str, Any]], rules: list[dict[str, Any]]) -> dict[str, Any]:
    values: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    has_conflict = False
    for item in candidates:
        candidate_values = [item]
        conflicting_pass = item.get("conflicting_pass")
        if isinstance(conflicting_pass, dict):
            has_conflict = True
            candidate_values.append(conflicting_pass)
        for candidate in candidate_values:
            raw_values = candidate.get("value")
            items = raw_values if isinstance(raw_values, list) else [raw_values]
            for value in items:
                if value is None:
                    continue
                if comparable(value) not in {comparable(entry["value"]) for entry in values}:
                    values.append({"value": value, "value_text": str(value)})
            evidence.extend(candidate.get("evidence", []))
    for item in rules:
        if comparable(item["value"]) not in {comparable(entry["value"]) for entry in values}:
            values.append({"value": item["value"], "value_text": item["value_text"]})
        evidence.extend(item.get("evidence", []))
    if not values:
        return _not_found()
    statuses = {item["status"] for item in candidates}
    status = "conflict" if has_conflict or "conflict" in statuses else "auto"
    if status == "auto" and "need_review" in statuses:
        status = "need_review"
    return {
        "value": values,
        "value_text": "\n".join(item["value_text"] for item in values),
        "confidence": min((float(item["confidence"]) for item in candidates), default=0.82),
        "status": status,
        "strategy": "rule+llm" if rules and candidates else ("rule" if rules else "llm"),
        "evidence": _unique_evidence(evidence),
        "lot_code": None,
        "model": candidates[0].get("model") if candidates else None,
        "registry_model_id": candidates[0].get("registry_model_id") if candidates else None,
    }


def _unique_values(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in values:
        key = comparable(item.get("value"))
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _unique_evidence(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in evidence:
        anchor = str(item.get("anchor", ""))
        if anchor and anchor not in seen:
            seen.add(anchor)
            result.append(item)
    return result


def _conflict_result(
    field: FieldDefinition,
    llm_values: list[dict[str, Any]],
    rule_values: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = [
        {"source": "llm", "value": item["value"], "value_text": item["value_text"]}
        for item in llm_values
    ] + [
        {"source": "rule", "value": item["value"], "value_text": item["value_text"]}
        for item in rule_values
    ]
    evidence = _unique_evidence(
        [item for candidate in (llm_values + rule_values) for item in candidate.get("evidence", [])]
    )
    return {
        "value": {"candidates": candidates},
        "value_text": "\n".join(
            f"{candidate['source']}: {candidate['value_text']}" for candidate in candidates
        )
        or "模型复抽结果不一致",
        "confidence": 0.5,
        "status": "conflict",
        "strategy": "rule+llm" if rule_values and llm_values else "llm",
        "evidence": evidence,
        "lot_code": None,
        "model": llm_values[0].get("model") if llm_values else None,
        "registry_model_id": llm_values[0].get("registry_model_id") if llm_values else None,
    }


def _not_found() -> dict[str, Any]:
    return {
        "value": None,
        "value_text": "未找到",
        "confidence": 0,
        "status": "not_found",
        "strategy": "llm",
        "evidence": [],
        "lot_code": None,
    }
