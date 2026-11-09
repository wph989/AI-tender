"""提交批次与校验批次对齐：每次最多三条，单条失败不拖垮同批其余事项。"""

import asyncio
import json

import pytest
from synthesis_fixtures import research_calls, submission, summary_record
from test_analysis_synthesis import execute
from test_deep_analysis import call

from tender.application.analysis.skills import verify_items
from tender.ports.llm.chat import Completion


def broken(**kwargs):
    return summary_record(
        citations=[{"block_id": "missing", "quote": "不存在的原文"}], **kwargs,
    )


def test_submit_analysis_accepts_three_records():
    records = [summary_record(key=f"item-{index}") for index in range(3)]
    state, _, _ = asyncio.run(execute([
        *research_calls(),
        call("submit_analysis", submission(records), "batch"),
    ]))
    assert [r["key"] for r in state["draft"]["business_data"]["records"]] == [
        "item-0", "item-1", "item-2",
    ]


def test_six_independent_items_use_two_submissions():
    records = [summary_record(key=f"item-{index}") for index in range(6)]
    state, _, _ = asyncio.run(execute([
        *research_calls(),
        call("submit_analysis", submission(records[:3], final=False), "batch1"),
        call("submit_analysis", submission(records[3:]), "batch2"),
    ]))
    assert len(state["draft"]["business_data"]["records"]) == 6
    submitted = [
        value for value in state["tool_results"].values()
        if value.get("data", {}).get("name") == "submit_analysis"
    ]
    # 六条独立事项只需两批，不再逐条提交六次。
    assert len(submitted) == 2


def test_schema_reports_max_items_three():
    async def run():
        _, _, router = await execute([
            *research_calls(),
            call("submit_analysis", submission([summary_record()]), "final"),
        ])
        params = {
            tool["function"]["name"]: tool["function"]["parameters"]
            for tool in router.requests[0][1]
        }
        assert params["submit_analysis"]["properties"]["records"]["maxItems"] == 3

    asyncio.run(run())


def test_batch_with_one_invalid_record_stages_valid_records_without_final():
    valid = summary_record(key="valid")
    other = summary_record(key="other")
    state, saved, _ = asyncio.run(execute([
        *research_calls(),
        call("submit_analysis", submission(
            [valid, broken(key="broken"), other], final=False,
        ), "batch"),
        call("submit_analysis", {"records": [], "final": True}, "finish"),
    ]))
    after_batch = next(s for s in saved if "call_batch" in s.get("tool_results", {}))
    assert "draft" not in after_batch
    assert {entry["business"]["key"] for entry in after_batch["staged_items"]} == {
        "valid", "other",
    }
    result = json.loads(after_batch["tool_results"]["call_batch"]["data"]["content"])
    assert result["accepted"] is True
    assert [item["key"] for item in result["rejected"]] == ["broken"]
    assert "已保存有效事项" in result["note"]
    assert {r["key"] for r in state["draft"]["business_data"]["records"]} == {
        "valid", "other",
    }


def test_final_batch_with_invalid_record_does_not_publish():
    valid = summary_record(key="valid")
    state, _, _ = asyncio.run(execute([
        *research_calls(),
        call("submit_analysis", submission(
            [valid, broken(key="broken")], final=False,
        ), "batch"),
        # 失败记录让 final 整体不成立，已通过的记录只能继续暂存。
        call("submit_analysis", submission(
            [summary_record(key="replacement"), broken(key="broken")],
        ), "final"),
        call("submit_analysis", submission([summary_record(key="replacement")]), "finish"),
    ]))
    published = [r["key"] for r in state["draft"]["business_data"]["records"]]
    assert "broken" not in published
    assert set(published) == {"valid", "replacement"}
    error = state["tool_results"]["call_final"]["data"]["content"]
    assert "请修正后重新提交 final=true" in error


def test_batch_invalid_submission_keeps_consecutive_limit():
    def duplicated(key):
        record = summary_record(key=key)
        return submission([record, dict(record)], final=False)

    with pytest.raises(ValueError, match="连续三次提交无效结果"):
        asyncio.run(execute([
            *research_calls(),
            call("submit_analysis", duplicated("a"), "bad1"),
            call("submit_analysis", duplicated("b"), "bad2"),
            call("submit_analysis", duplicated("c"), "bad3"),
        ]))


def test_batch_review_batches_units_in_groups_of_three():
    items = [
        {
            "field": f"字段{index}", "group": "", "sort_order": index, "note": "",
            "values": [{
                "value": "质保三年",
                "citations": [{"block_id": "s1r1c0", "quote": "质保三年"}],
            }],
        }
        for index in range(7)
    ]
    batches = []

    class Reviewer:
        async def complete(self, prompt):
            sent = json.loads(prompt.rsplit("\n", 1)[1])
            batches.append(len(sent))
            return Completion(content=json.dumps({"reviews": [
                {"supported": True, "unsupported_claims": []} for _ in sent
            ]}), model="fixture")

    asyncio.run(verify_items(Reviewer(), items, explain=True))
    assert batches == [3, 3, 1]
    assert all(item["verification"] == "supported" for item in items)
