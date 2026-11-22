"""解析只提交归纳正文和块定位，原文及可信位置由服务端补齐。"""


import pytest
from agent_fixtures import KEY, summary_record
from test_analysis_research import block

from tender.application.analysis.data import (
    SynthesisRecord,
    prepare_records,
)
from tender.application.analysis.output import output_schema
from tender.application.analysis.skills import skill_snapshot
from tender.application.shared.validation import validation_message


def test_summary_with_block_location_needs_no_verbatim_quote():
    row = block() | {"page_no": 9, "bbox": [1, 2, 3, 4], "anchor": "paragraph-1"}
    record = SynthesisRecord.model_validate(summary_record(
        text="提供三年质保服务", citations=[{"block_id": row["block_id"]}],
    ))
    state = {"output_schema": output_schema(skill_snapshot(), KEY)}
    item = prepare_records([record], state, {row["block_id"]: row}, KEY)[0]
    assert item["business"]["content"]["内容"] == "提供三年质保服务"
    ref = item["values"][0]["citations"][0]
    assert ref["block_id"] == row["block_id"]
    assert ref["quote"] == row["content"]
    assert {key: ref[key] for key in ("source_id", "page_no", "bbox", "anchor")} == {
        key: row[key] for key in ("source_id", "page_no", "bbox", "anchor")
    }




def test_source_location_still_rejects_an_unread_block():
    record = SynthesisRecord.model_validate(summary_record(citations=[{"block_id": "unread"}]))
    with pytest.raises(ValueError, match="block_id.*未读取"):
        prepare_records([record], {"output_schema": output_schema(skill_snapshot(), KEY)},
                        {"s1r1c0": block()}, KEY)


def test_feedback_groups_shared_reasons_and_does_not_repeat_a_field():
    message = validation_message([
        ("scope.lot_refs", "必须填写标段名称"),
        ("scope.lot_refs", "必须填写标段名称"),
        ("scope.lot_refs", "不能填写内部key"),
        ("citations.0.block_id", "请选择已读块ID"),
        ("citations.1.block_id", "请选择已读块ID"),
    ])
    assert message.count("scope.lot_refs") == 1
    assert message.count("请选择已读块ID") == 1
    assert "不能填写内部key" in message
