"""复现现场分类字段与内容键同时写错时，纠错反馈不能再隐藏下一处格式问题。"""

import asyncio
import copy
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import noop, summary_record
from test_analysis_combined_review import approve
from test_analysis_research import block, session
from test_analysis_topic_flow import snapshot
from test_deep_analysis import KEY, ScriptedRouter, call

from tender.application.analysis.agent import RoutedAgentModel, build_module_agent, invoke_module
from tender.application.analysis.data import module_data
from tender.application.analysis.output import output_schema, record_output
from tender.application.analysis.skills import skill_snapshot


@pytest.mark.parametrize("group", ["", "不存在的分类"])
def test_output_feedback_explains_group_and_content_errors_together(group):
    schema = output_schema(skill_snapshot(), KEY)
    bad = summary_record(
        group=group, category="甲方信息", content={"招标人名称": "不能回显的错误正文"},
    )
    original = copy.deepcopy(bad)
    with pytest.raises(ValueError) as caught:
        record_output(bad, schema)
    feedback = str(caught.value)
    assert "group" in feedback and "category" in feedback
    assert "甲方信息" in feedback
    assert "content" in feedback and "字段" in feedback and "内容" in feedback
    assert "不能回显的错误正文" not in feedback
    assert bad == original


def test_compact_agent_corrects_live_failure_shape_before_third_invalid_submission():
    async def run():
        state, saved, reviews = {}, [], []
        valid = summary_record(
            key="tenderer", kind="fact", title="招标人名称", group="甲方信息",
            content={"字段": "招标人名称", "内容": "示例建设单位"},
            quote="招标人名称：示例建设单位。", work_ids=["w1"],
        )
        bad = {k: v for k, v in valid.items() if k != "group"}
        bad.update(category="甲方信息", content={"招标人名称": "不能回显的错误正文"})
        bad_relation = bad | {"kind": "relation"}
        router = ScriptedRouter([
            call("search_document", {"query": "招标人", "work": "w1"}, "search"),
            call("complete_research", {"research_summary": "已有原文足以综合"}, "research"),
            call("submit_analysis", {"records": [bad_relation]}, "relation"),
            call("submit_analysis", {"records": [bad]}, "format"),
            call("submit_analysis", {"records": [valid]}, "fixed"),
        ])

        async def save(value):
            saved.append(copy.deepcopy(value))

        async def review(payload):
            reviews.append(copy.deepcopy(payload))
            return approve(payload)

        schema_path = KEY + "/references/output_schema.json"
        frozen = snapshot(("a",)) | {
            "__analysis_flow_version__": "research-v2",
            schema_path: skill_snapshot()[schema_path],
        }
        graph, files = build_module_agent(
            key=KEY, model=RoutedAgentModel(router=router),
            research=session([block() | {"content": "招标人名称：示例建设单位。"}]),
            state=state, snapshot=frozen, checkpointer=InMemorySaver(),
            reserve_tool=noop, save=save, review_support=noop, review_combined=review,
        )
        await invoke_module(graph, files, thread_id="format-repair", task="解析项目概况")
        for call_id in ("call_relation", "call_format"):
            feedback = state["tool_results"][call_id]["data"]["content"]
            if call_id == "call_relation":
                assert "predicate/subject_key/object_key" in feedback
                assert "group" not in feedback and "局部格式示例" not in feedback
            else:
                assert "group" in feedback and "content" in feedback
                assert "字段" in feedback and "内容" in feedback
            assert "不能回显的错误正文" not in feedback
            failed = next(s for s in saved if call_id in s.get("tool_results", {}))
            assert not module_data(failed)["records"] and not failed.get("staged_items")
        prompt = "\n".join(str(m["data"]["content"]) for m in router.requests[-1][0]
                           if m["type"] == "system")
        assert "group" in prompt and "category" in prompt
        tool = next(t["function"] for t in router.requests[-1][1]
                    if t["function"]["name"] == "submit_analysis")
        fields = tool["parameters"]["properties"]["records"]["items"]["properties"]
        assert "分类" in fields["group"]["description"]
        assert "列名" in fields["content"]["description"]
        assert state["consecutive_invalid_submissions"] == 0
        assert len(reviews) == 1
        assert [r["key"] for r in module_data(state)["records"]] == ["tenderer"]

    asyncio.run(run())


def test_entirely_rejected_batch_reports_each_distinct_error_and_record_location():
    async def run():
        from synthesis_fixtures import research_calls, submission
        from test_analysis_synthesis import execute

        wrong_group = summary_record(key="bad-group", group="错误分类")
        wrong_columns = summary_record(key="bad-columns", content={"错误列": "错误正文"})
        state, _, _ = await execute([
            *research_calls(),
            call("submit_analysis", submission([wrong_group, wrong_columns]), "bad"),
            call("submit_analysis", submission([summary_record()]), "fixed"),
        ])
        feedback = state["tool_results"]["call_bad"]["data"]["content"]
        assert "records.0" in feedback and "records.1" in feedback
        assert "group" in feedback and "content" in feedback
        assert "错误正文" not in feedback

    asyncio.run(run())


@pytest.mark.parametrize("has_valid_record", [False, True])
def test_submission_groups_six_invalid_locations_into_one_concise_fix(has_valid_record):
    async def run():
        from test_analysis_combined_review import execute

        rows = [block() | {
            "block_id": f"s1r1c{index}", "offset": index,
            "content": f"质保三年，需提交第{index}类材料。",
        } for index in range(6)]
        bad = summary_record(key="bad", work_ids=["w1"], citations=[
            {"block_id": f"unread-{index}"} for index in range(6)
        ])
        fixed = bad | {"citations": [
            {"block_id": row["block_id"], "quote": row["content"]} for row in rows
        ]}
        valid = [summary_record(key="valid", work_ids=["w1"])] if has_valid_record else []
        state, saved, _, _ = await execute([], evidence_rows=rows, synthesis_steps=[
            call("submit_analysis", {"records": [*valid, bad], "final": False}, "bad"),
            call("submit_analysis", {"records": [fixed]}, "fixed"),
        ])
        feedback = state["tool_results"]["call_bad"]["data"]["content"]
        if has_valid_record:
            feedback = json.loads(feedback)["rejected"][0]["error"]
        # 六个位置都须保留，相同的错误原因和修法只说明一次。
        assert len(feedback) < 500
        for index in range(6):
            assert f"citations.{index}.block_id" in feedback
        assert feedback.count("未读取") == 1
        assert "quote" not in feedback
        after_error = next(s for s in saved if "call_bad" in s.get("tool_results", {}))
        assert not module_data(after_error)["records"]
        expected_keys = {"bad", "valid"} if has_valid_record else {"bad"}
        assert {r["key"] for r in module_data(state)["records"]} == expected_keys

    asyncio.run(run())


def test_mixed_batch_keeps_valid_record_and_returns_complete_format_feedback():
    async def run():
        from test_analysis_combined_review import execute

        bad = summary_record(key="bad", group="", category="项目基本信息",
                             content={"质保期限": "三年"}, work_ids=["w1"])
        valid = summary_record(key="valid", work_ids=["w1"])
        state, saved, _, _ = await execute([], synthesis_steps=[
            call("submit_analysis", {"records": [valid, bad], "final": False}, "mixed"),
            call("submit_analysis", {"records": [summary_record(key="bad", work_ids=["w1"])]},
                 "fixed"),
        ])
        after_error = next(s for s in saved if "call_mixed" in s.get("tool_results", {}))
        assert [i["business"]["key"] for i in after_error["staged_items"]] == ["valid"]
        result = json.loads(after_error["tool_results"]["call_mixed"]["data"]["content"])
        feedback = result["rejected"][0]["error"]
        assert "group" in feedback and "content" in feedback
        assert "字段" in feedback and "内容" in feedback
        assert not module_data(after_error)["records"]
        assert {r["key"] for r in module_data(state)["records"]} == {"valid", "bad"}

    asyncio.run(run())
