"""人工复核、反向标注和 gold 样本沉淀接口。"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from tender.api.common import engine
from tender.api.errors import ApiProblem
from tender.application.extraction import _locate_quote
from tender.core import settings

router = APIRouter(prefix="/api/v1", tags=["reviews"])


class ReviewEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor: str = Field(min_length=4, max_length=40)
    quote: str | None = Field(default=None, max_length=4000)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: int = Field(ge=1)
    action: Literal["confirm", "correct", "supplement", "reject"]
    review_mode: Literal["item", "batch", "spot_check"]
    new_value: Any = None
    evidence: list[ReviewEvidence] = Field(default_factory=list, max_length=30)
    comment: str | None = Field(default=None, max_length=2000)


def _text_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return "" if value is None else str(value)


@router.post("/instances/{instance_id}/reviews", status_code=201)
def create_review(
    instance_id: int,
    payload: ReviewRequest,
    request: Request,
) -> dict[str, object]:
    action = payload.action
    if action in {"correct", "supplement"}:
        if payload.new_value is None or not _text_value(payload.new_value):
            raise ApiProblem(400, "invalid_argument", "修正或补充必须填写新值")
        if not payload.evidence:
            raise ApiProblem(422, "anchor_required", "人工修正必须绑定至少一个原文锚点")
    if action == "reject" and not (payload.comment and payload.comment.strip()):
        raise ApiProblem(400, "invalid_argument", "驳回时必须填写原因")

    db = engine(request)
    actor = request.headers.get("x-actor", "local-user")[:200]
    with db.begin() as connection:
        instance = (
            connection.execute(
                text(
                    """SELECT fi.id, fi.version_id, fi.field_key, fi.lot_id,
                              fi.current_extraction_id, d.company_id
                       FROM field_instance AS fi
                       JOIN document_version AS v ON v.id = fi.version_id
                       JOIN document AS d ON d.id = v.document_id
                       WHERE fi.id = :instance_id AND d.company_id = :company_id
                         AND d.deleted_at IS NULL
                       FOR UPDATE OF fi"""
                ),
                {"instance_id": instance_id, "company_id": settings.company_id()},
            )
            .mappings()
            .first()
        )
        if instance is None:
            raise ApiProblem(404, "not_found", "字段实例不存在")
        if instance["current_extraction_id"] != payload.attempt_id:
            raise ApiProblem(409, "attempt_not_current", "复核目标已变化，请刷新结果后重试")
        current = (
            connection.execute(
                text(
                    """SELECT e.*, pr.config_snapshot AS parse_config
                       FROM extraction AS e
                       LEFT JOIN parse_run AS pr ON pr.id = e.run_id
                       WHERE e.id = :attempt_id AND e.instance_id = :instance_id
                       FOR UPDATE OF e"""
                ),
                {"attempt_id": payload.attempt_id, "instance_id": instance_id},
            )
            .mappings()
            .first()
        )
        if current is None:
            raise ApiProblem(404, "not_found", "抽取尝试不存在")
        if action in {"correct", "supplement"} and current["run_id"] is None:
            raise ApiProblem(409, "anchor_not_found", "该结果没有可用解析 run")

        resolved_evidence: list[dict[str, object]] = []
        if action in {"correct", "supplement"}:
            for selected in payload.evidence:
                element = (
                    connection.execute(
                        text(
                            """SELECT id, anchor, page_no, bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                                      text, source
                               FROM element
                               WHERE version_id = :version_id AND run_id = :run_id
                                 AND anchor = :anchor"""
                        ),
                        {
                            "version_id": instance["version_id"],
                            "run_id": current["run_id"],
                            "anchor": selected.anchor,
                        },
                    )
                    .mappings()
                    .first()
                )
                if element is None:
                    raise ApiProblem(
                        422,
                        "anchor_not_found",
                        f"锚点 {selected.anchor} 不属于当前文档版本的解析结果",
                    )
                source_text = str(element["text"] or "")
                start = selected.char_start
                end = selected.char_end
                quote = selected.quote
                if (start is None) != (end is None):
                    raise ApiProblem(400, "invalid_argument", "char_start 和 char_end 必须同时提供")
                if start is not None and end is not None:
                    if start >= end or end > len(source_text):
                        raise ApiProblem(422, "anchor_not_found", "字符选区超出锚点原文范围")
                    selected_text = source_text[start:end]
                    if quote is not None and quote != selected_text:
                        raise ApiProblem(
                            422, "anchor_not_found", "引用文本与所选锚点字符范围不一致"
                        )
                    quote = selected_text
                elif not quote:
                    quote = source_text
                else:
                    # 只有锚点还不够：客户端可能被篡改，引用片段必须能在该锚点原文中反查到。
                    located_start, located_end, _ = _locate_quote(source_text, quote)
                    if located_start is None or located_end is None:
                        raise ApiProblem(422, "anchor_not_found", "引用文本不属于所选锚点原文")
                    start, end = located_start, located_end
                if not quote:
                    raise ApiProblem(422, "anchor_not_found", "锚点没有可用原文")
                resolved_evidence.append(
                    {
                        "anchor": selected.anchor,
                        "element": dict(element),
                        "quote": quote,
                        "char_start": start,
                        "char_end": end,
                    }
                )

        result_attempt_id: int | None = None
        value_text = _text_value(payload.new_value) if action in {"correct", "supplement"} else None
        if action in {"correct", "supplement"}:
            previous_id = int(current["id"])
            connection.execute(
                text("UPDATE extraction SET is_current = false, updated_at = now() WHERE id = :id"),
                {"id": previous_id},
            )
            attempt_no = int(
                connection.execute(
                    text(
                        "SELECT COALESCE(max(attempt_no), 0) + 1 FROM extraction "
                        "WHERE instance_id = :id"
                    ),
                    {"id": instance_id},
                ).scalar_one()
            )
            evidence_count = len(resolved_evidence)
            result_attempt_id = int(
                connection.execute(
                    text(
                        """INSERT INTO extraction
                               (instance_id, version_id, run_id, attempt_no, machine_attempt_no,
                                trigger, field_key, group_key, lot_id, value_json, value_text,
                                confidence, status, strategy, evidence_count, supersedes_id,
                                is_current, created_by, field_def_version)
                           VALUES
                               (:instance_id, :version_id, :run_id, :attempt_no, NULL,
                                'manual_edit', :field_key, :group_key, :lot_id,
                                CAST(:value AS JSONB), :value_text, 1, 'verified', 'manual',
                                :evidence_count, :supersedes_id, true, :actor, 1)
                           RETURNING id"""
                    ),
                    {
                        "instance_id": instance_id,
                        "version_id": instance["version_id"],
                        "run_id": current["run_id"],
                        "attempt_no": attempt_no,
                        "field_key": instance["field_key"],
                        "group_key": current["group_key"],
                        "lot_id": instance["lot_id"],
                        "value": json.dumps(payload.new_value, ensure_ascii=False),
                        "value_text": value_text,
                        "evidence_count": evidence_count,
                        "supersedes_id": previous_id,
                        "actor": actor,
                    },
                ).scalar_one()
            )
            for sequence, item in enumerate(resolved_evidence, start=1):
                element = item["element"]
                connection.execute(
                    text(
                        """INSERT INTO evidence
                               (extraction_id, version_id, seq, anchor, element_id, page_no,
                                bbox_x0, bbox_y0, bbox_x1, bbox_y1, char_start, char_end,
                                quote, quote_source, match_type)
                           VALUES
                               (:extraction_id, :version_id, :seq, :anchor, :element_id, :page_no,
                                :bbox_x0, :bbox_y0, :bbox_x1, :bbox_y1, :char_start, :char_end,
                                :quote, :quote_source, 'manual')"""
                    ),
                    {
                        "extraction_id": result_attempt_id,
                        "version_id": instance["version_id"],
                        "seq": sequence,
                        "anchor": item["anchor"],
                        "element_id": element["id"],
                        "page_no": element["page_no"],
                        "bbox_x0": element["bbox_x0"],
                        "bbox_y0": element["bbox_y0"],
                        "bbox_x1": element["bbox_x1"],
                        "bbox_y1": element["bbox_y1"],
                        "char_start": item["char_start"],
                        "char_end": item["char_end"],
                        "quote": item["quote"],
                        "quote_source": element["source"] or "native",
                    },
                )
            connection.execute(
                text(
                    """UPDATE field_instance SET current_extraction_id = :extraction_id
                       WHERE id = :instance_id"""
                ),
                {"extraction_id": result_attempt_id, "instance_id": instance_id},
            )

        evidence_json = (
            [
                {
                    "anchor": item["anchor"],
                    "quote": item["quote"],
                    "char_start": item["char_start"],
                    "char_end": item["char_end"],
                    "match_type": "manual",
                }
                for item in resolved_evidence
            ]
            if resolved_evidence
            else None
        )
        review_action_id = int(
            connection.execute(
                text(
                    """INSERT INTO review_action
                           (instance_id, attempt_id, result_attempt_id, action, review_mode,
                            old_value, new_value, evidence, actor, comment)
                       VALUES
                           (:instance_id, :attempt_id, :result_attempt_id, :action, :review_mode,
                            CAST(:old_value AS JSONB), CAST(:new_value AS JSONB),
                            CAST(:evidence AS JSONB), :actor, :comment)
                       RETURNING id"""
                ),
                {
                    "instance_id": instance_id,
                    "attempt_id": payload.attempt_id,
                    "result_attempt_id": result_attempt_id,
                    "action": action,
                    "review_mode": payload.review_mode,
                    "old_value": json.dumps(current["value_json"], ensure_ascii=False)
                    if current["value_json"] is not None
                    else None,
                    "new_value": json.dumps(payload.new_value, ensure_ascii=False)
                    if payload.new_value is not None
                    else None,
                    "evidence": json.dumps(evidence_json, ensure_ascii=False)
                    if evidence_json is not None
                    else None,
                    "actor": actor,
                    "comment": payload.comment.strip() if payload.comment else None,
                },
            ).scalar_one()
        )
        connection.execute(
            text(
                """UPDATE review_task SET status = 'resolved', resolved_action_id = :action_id,
                       resolved_at = now()
                   WHERE extraction_id = :attempt_id AND status = 'open'"""
            ),
            {"action_id": review_action_id, "attempt_id": payload.attempt_id},
        )
        if action in {"correct", "supplement"}:
            param_snapshot = (
                current["parse_config"] if isinstance(current["parse_config"], dict) else {}
            )
            connection.execute(
                text(
                    """INSERT INTO gold_item
                           (source_instance_id, version_id, field_key, expected,
                            expected_anchors, origin, param_snapshot)
                       VALUES
                           (:instance_id, :version_id, :field_key, CAST(:expected AS JSONB),
                            CAST(:anchors AS TEXT[]), :origin, CAST(:snapshot AS JSONB))"""
                ),
                {
                    "instance_id": instance_id,
                    "version_id": instance["version_id"],
                    "field_key": instance["field_key"],
                    "expected": json.dumps(payload.new_value, ensure_ascii=False),
                    "anchors": [item["anchor"] for item in resolved_evidence],
                    "origin": action,
                    "snapshot": json.dumps(param_snapshot, ensure_ascii=False),
                },
            )

    return {
        "review_action_id": review_action_id,
        "instance_id": instance_id,
        "result_attempt_id": result_attempt_id,
        "converged": True,
    }
