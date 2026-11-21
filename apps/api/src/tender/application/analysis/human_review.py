"""把机器候选与人工确认版本分开，编制只消费当前资料上的人工裁定。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tender.application.analysis.data import data_gap, scope_covers

REVIEW_BUCKETS = ("lots", "facts", "requirements", "format_nodes", "relations")
CORRECTABLE_KINDS = frozenset({"fact", "requirement"})


class RecordReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    snapshot_id: int = Field(gt=0)
    record_id: str = Field(min_length=1, max_length=200)
    previous_review_id: int | None = Field(gt=0)
    decision: Literal["confirmed", "corrected", "rejected"]
    note: str = Field(default="", max_length=2000)
    corrected_text: str | None = Field(default=None, min_length=1, max_length=16000)

    @model_validator(mode="after")
    def check_decision(self) -> RecordReviewInput:
        if (self.decision == "corrected") != (self.corrected_text is not None):
            raise ValueError("仅修正事项时填写修正内容")
        if self.decision != "confirmed" and not self.note:
            raise ValueError("修正或驳回时请填写理由")
        return self


def coverage_review_id(item: dict) -> str | None:
    if item["status"] == "not_applicable" and item.get("citations"):
        return item.get("review_id")
    return None


def review_record(data: dict, record_id: str) -> dict | None:
    for bucket in REVIEW_BUCKETS:
        for record in data[bucket]:
            if record["id"] == record_id:
                return record
    for item in data["coverage"]:
        if coverage_review_id(item) == record_id:
            return {**item, "id": record_id, "kind": "coverage"}
    return None


def review_projection(data: dict, signatures: dict, signature: str, reviews: dict, *,
                      current: bool) -> dict:
    """原始快照上叠加状态，历史正文、原证据与历史裁定仍可查看。"""
    def project(record: dict, record_id: str) -> None:
        review = reviews.get(record_id)
        record["human_review"] = review
        if not current or signatures.get(record["module_key"]) != signature:
            status = "outdated"
        else:
            status = review["decision"] if review else "pending"
        record["human_review_status"] = status

    for bucket in REVIEW_BUCKETS:
        for record in data[bucket]:
            project(record, record["id"])
    for item in data["coverage"]:
        if record_id := coverage_review_id(item):
            project(item, record_id)
    return data


def reviewed_compilation(data: dict) -> dict:
    """旧结论、未审条款及其依赖从编制输出中移除，缺口仍明确报告。"""
    machine_relation_ids = {r["id"] for r in data["relations"]}
    result = {
        **data,
        "gaps": [g for g in data["gaps"] if g["code"] != "conflict"
                 or g.get("record_id") not in machine_relation_ids],
        "coverage": [],
    }
    approved_ids: set[str] = set()
    for bucket in REVIEW_BUCKETS:
        result[bucket] = []
        for record in data[bucket]:
            if record["human_review_status"] not in {"confirmed", "corrected"}:
                result["gaps"].append(data_gap(
                    "input_review_required" if record["human_review_status"] == "outdated"
                    else "human_review_required",
                    "资料已变更，须重跑并复核" if record["human_review_status"] == "outdated"
                    else "事项尚未获人工确认",
                    record["scope"], record_id=record["id"], module_key=record["module_key"],
                ))
                continue
            # 机器快照上的关系标记不能决定人工版正文的效力。
            record = {
                k: v for k, v in record.items() if k not in {"superseded_in", "conflicts_in"}
            }
            if record["human_review_status"] == "corrected":
                # 修正正文时机器抽出的条件与评分不再代表新结论，仍保留人工核对过的原文。
                record = {
                    **record, "text": record["human_review"]["corrected_text"], "content": {},
                    "conditions": {"expression": "", "logic": "text", "terms": [],
                                   "exceptions": []},
                    "materials": [], "scoring": None, "structuring": "partial",
                }
            result[bucket].append(record)
            approved_ids.add(record["id"])

    if len(result["lots"]) != len(data["lots"]):
        result["gaps"].append(data_gap("lot_catalog_unknown", "标段目录尚未完成逐项人工确认"))

    # 父章节未确认时不能把子节点当根节点；关系也不能指向编制端看不到的事实。
    while unlinked := {r["id"] for r in result["format_nodes"]
                       if r.get("parent_id") and r["parent_id"] not in approved_ids}:
        approved_ids -= unlinked
        result["format_nodes"] = [r for r in result["format_nodes"] if r["id"] not in unlinked]
        for record_id in sorted(unlinked):
            result["gaps"].append(data_gap("human_review_required", "上级编制章节尚未确认",
                                           record_id=record_id))
    result["format_nodes"] = [{
        **r, "requirement_ids": [key for key in r.get("requirement_ids", [])
                                 if key in approved_ids],
    } for r in result["format_nodes"]]
    endpoints = {r["id"]: r for bucket in ("facts", "requirements", "format_nodes")
                 for r in result[bucket]}
    relations, result["relations"] = result["relations"], []
    for relation in relations:
        subject = endpoints.get(relation.get("subject_id"))
        target = endpoints.get(relation.get("object_id"))
        scope = relation["scope"]
        if not subject or not target or any(
            side.get("effective_status", "active") != "active"
            or not scope_covers(side["scope"], scope)
            or (relation.get(key) is not None and relation[key] != side["text"])
            for side, key in ((subject, "subject_text"), (target, "object_text"))
        ):
            result["gaps"].append(data_gap(
                "unresolved_relation", "关系端点尚未确认或正文已修正", scope,
                record_id=relation["id"], module_key=relation["module_key"],
            ))
            continue
        result["relations"].append(relation)
        if relation["predicate"] == "supersedes":
            target.setdefault("superseded_in", []).append(scope)
        elif relation["predicate"] == "conflicts":
            for side in (subject, target):
                side.setdefault("conflicts_in", []).append(scope)
            result["gaps"].append(data_gap("conflict", relation["text"], scope,
                                           record_id=relation["id"]))
    for item in data["coverage"]:
        linked = item.get("record_ids", [])
        reviewed = bool(linked) and all(record_id in approved_ids for record_id in linked)
        if ((item["status"] == "extracted" and reviewed)
                or (coverage_review_id(item) and item.get("human_review_status") == "confirmed")):
            result["coverage"].append(item)
        elif item["status"] in {"extracted", "not_applicable"}:
            result["coverage"].append({**item, "status": "pending",
                                       "detail": "覆盖结论尚未通过人工复核"})
            result["gaps"].append(data_gap(
                "human_review_required", "专题覆盖结论尚未通过人工复核",
                item["scope"], module_key=item.get("module_key"), topic=item.get("topic"),
            ))
        else:
            # 原缺件或待核对原因仍然有效，不替换成人工复核提示。
            result["coverage"].append(item)
    return result
