"""解析只提交归纳正文和块定位，原文及可信位置由服务端补齐。"""

import asyncio

import pytest
from synthesis_fixtures import summary_record
from test_analysis_combined_review import execute
from test_analysis_research import block
from test_deep_analysis import KEY, call

from tender.application.analysis.data import (
    CoverageInput,
    SynthesisRecord,
    module_data,
    prepare_coverage,
    prepare_records,
)
from tender.application.analysis.output import output_schema
from tender.application.analysis.skills import skill_snapshot
from tender.application.shared.validation import validation_message


@pytest.mark.parametrize("reference", [
    {"block_id": "s1r1c0"},
    {"block_id": "s1r1c0", "quote": "服务期内提供三年质保，这是AI归纳的结论"},
])
def test_summary_with_block_location_needs_no_verbatim_quote(reference):
    row = block() | {"page_no": 9, "bbox": [1, 2, 3, 4], "anchor": "paragraph-1"}
    record = SynthesisRecord.model_validate(summary_record(
        text="提供三年质保服务", citations=[reference],
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


def test_coverage_location_uses_the_same_contract():
    row = block() | {"content": "本项目不收取投标保证金。"}
    coverage = CoverageInput(
        topic="deposit", scope={"kind": "common", "lot_refs": []},
        status="not_applicable", detail="无需提交投标保证金",
        citations=[{"block_id": row["block_id"]}],
    )
    entries, items = prepare_coverage(
        [coverage], {}, {row["block_id"]: row}, [{"key": "deposit", "title": "保证金"}], KEY,
    )
    assert items[0]["values"][0]["value"] == "无需提交投标保证金"
    assert entries[0]["citations"][0]["quote"] == row["content"]


def test_source_location_still_rejects_an_unread_block():
    record = SynthesisRecord.model_validate(summary_record(citations=[{"block_id": "unread"}]))
    with pytest.raises(ValueError, match="block_id.*未读取"):
        prepare_records([record], {"output_schema": output_schema(skill_snapshot(), KEY)},
                        {"s1r1c0": block()}, KEY)


def test_compact_flow_publishes_summaries_without_quote_repair_calls():
    async def run():
        records = [summary_record(key="bid_limit_price", citations=[{"block_id": "s1r1c0"}]),
                   summary_record(key="bid_security", citations=[{
                       "block_id": "s1r1c0", "quote": "不需要复制原文的AI总结",
                   }])]
        state, _, router, reviews = await execute(records)
        assert len(reviews) == 1
        assert {r["key"] for r in module_data(state)["records"]} == {
            "bid_limit_price", "bid_security",
        }
        assert state["consecutive_invalid_submissions"] == 0
        assert not any(event["action"] == "read_document" for event in state["research"]["events"])
        tool = next(t["function"] for t in router.requests[-1][1]
                    if t["function"]["name"] == "submit_analysis")
        reference = tool["parameters"]["properties"]["records"]["items"]["properties"][
            "citations"]["items"]
        assert set(reference["properties"]) == {"block_id"}

    asyncio.run(run())


def test_partial_final_submission_explains_shared_error_once_and_preserves_valid_draft():
    async def run():
        good = summary_record(key="valid", work_ids=["w1"])
        bad = [summary_record(key=key, work_ids=["w1"], citations=[{"block_id": "unread"}])
               for key in ("bid_limit_price", "bid_security")]
        fixed = [record | {"citations": [{"block_id": "s1r1c0"}]} for record in bad]
        state, saved, _, _ = await execute([], synthesis_steps=[
            call("submit_analysis", {"records": [good, *bad], "final": True}, "bad"),
            call("submit_analysis", {"records": fixed, "final": True}, "fixed"),
        ])
        after = next(s for s in saved if "call_bad" in s.get("tool_results", {}))
        assert [r["business"]["key"] for r in after["staged_items"]] == ["valid"]
        message = state["tool_results"]["call_bad"]["data"]["content"]
        assert "bid_limit_price" in message and "bid_security" in message
        assert message.count("未读取") == 1
        assert "预校验" not in message and "final=false" not in message
        assert len(message) < 240

    asyncio.run(run())


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
