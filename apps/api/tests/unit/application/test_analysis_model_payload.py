"""按真实工具请求验证模型负担精简，不以删减领域约束换取更短提示。"""

import asyncio
import json
import re

import pytest
from synthesis_fixtures import noop, summary_record
from test_analysis_combined_review import execute
from test_analysis_compact_protocol import ledger
from test_analysis_prompt_budget import FakeRequest
from test_analysis_research import block, session

from tender.application.analysis.agent import ResearchMiddleware
from tender.application.analysis.policy import load_module_skill
from tender.application.analysis.protocol import ResearchLedger
from tender.application.analysis.research import ToolArgumentError
from tender.application.analysis.search_control import TopicSearch
from tender.application.analysis.skills import MODULES, skill_snapshot
from tender.application.analysis.topic_flow import TopicFlow


def test_actual_synthesis_schema_omits_generated_fields_and_keeps_business_attributes():
    async def run():
        state, _, router, _ = await execute(
            [summary_record(key=str(index)) for index in range(5)],
            search_args={"query": "质保", "work": "w1"},
        )
        tool = next(
            t["function"]
            for t in router.requests[-1][1]
            if t["function"]["name"] == "submit_analysis"
        )
        schema = tool["parameters"]
        record = schema["properties"]["records"]["items"]
        fields = record["properties"]
        assert not {"text", "sort_order"} & fields.keys()
        assert {
            "conditions",
            "materials",
            "scoring",
            "structuring",
            "scope",
            "parent_key",
        } <= fields.keys()
        assert [i["business"]["sort_order"] for i in state["staged_items"]] == list(range(5))

    asyncio.run(run())


def test_revised_record_keeps_generated_order_and_research_receipt_is_only_delta():
    async def run():
        state, _, _, _ = await execute(
            [
                summary_record(key="first"),
                summary_record(key="second"),
                summary_record(key="first", title="更新后的质保期限"),
            ]
        )
        records = {i["business"]["key"]: i["business"] for i in state["staged_items"]}
        assert records["first"]["sort_order"] == 0
        assert records["second"]["sort_order"] == 1
        assert records["first"]["title"] == "更新后的质保期限"
        receipt = json.loads(state["tool_results"]["call_research"]["data"]["content"])
        assert "works" not in receipt
        assert receipt["changed_works"][0]["items"][0]["status"] == "found"

    asyncio.run(run())


@pytest.mark.parametrize("key", MODULES)
def test_phase_prompts_keep_rules_once_and_load_output_format_only_for_synthesis(key):
    async def run():
        snapshot = skill_snapshot()
        skill = load_module_skill(snapshot, key, categories=["goods"])
        state = {
            "business_topics": json.loads(snapshot[key + "/references/coverage.json"]),
            "output_schema": json.loads(snapshot[key + "/references/output_schema.json"]),
        }
        research = session([block()])
        flow = TopicFlow(state, research)
        flow.data.update(protocol="research-v2", output_mode="after-research", phase="research")
        middleware = ResearchMiddleware(research, state, noop, noop, skill=skill, topic_flow=flow)

        async def capture(request):
            return request

        first = await middleware.topic_model_call(FakeRequest(), capture)
        daily = await middleware.topic_model_call(FakeRequest(), capture)
        for request in (first, daily):
            text = request.system_message.content
            assert "## 事项组织" not in text
            assert "必须登记状态的主题（coverage.json）" not in text
            for path in skill["references"]:
                if path.endswith("extraction_rules.md") or "output_format.md" not in path:
                    rule = re.sub(r"\s*<!-- topics: .*? -->", "", snapshot[path])
                    assert text.count(rule.strip()) == 1
            assert len(text) < len(skill["instructions"]) + len(flow.prompt())
        # 局部领域小节不等于完整Skill，显式回读仍须返回完整文件。
        assert skill["path"] not in middleware.loaded_skill_paths
        flow.data["phase"] = "synthesis"
        synthesis = await middleware.topic_model_call(FakeRequest(), capture)
        assert "## 事项组织" in synthesis.system_message.content
        assert "输出格式声明：" in synthesis.system_message.content
        assert "```json" not in synthesis.system_message.content

    asyncio.run(run())


def test_search_derives_topic_from_work_id_and_rejects_unknown_work():
    book, flow, _, _ = ledger()
    work = book.works()[0]
    selected = TopicSearch(flow).begin("search_document", {"query": "质保", "work": work["id"]})
    assert {v["topic"] for v in selected} == {work["topic"]}
    with pytest.raises(ToolArgumentError):
        TopicSearch(flow).begin("search_document", {"query": "质保", "work": "w999"})


def test_one_query_can_derive_multiple_topics_without_resetting_each_work_budget():
    research = session([block()])
    state = {"business_topics": [{"key": key, "checks": ["核对条件"]} for key in ("a", "b")]}
    flow = TopicFlow(state, research)
    flow.data.update(protocol="research-v2", output_mode="after-research", phase="research")
    works = [w["id"] for w in ResearchLedger(flow).works()]
    control = TopicSearch(flow)
    for index in range(3):
        args = {"query": str(index), "work": works}
        selected = control.begin("search_document", args)
        assert {w["topic"] for w in selected} == {"a", "b"}
        control.end(selected, {"blocks": []}, set(research.seen))
    from tender.application.analysis.research import WorkClosed

    with pytest.raises(WorkClosed):
        control.begin("search_document", {"query": "再换关键词", "work": works})
    assert all(control.ledger[w]["attempts"] == 3 for w in works)


def test_work_prompt_groups_scope_without_repeating_internal_task_identity():
    book, flow, _, _ = ledger()
    entry = flow.entries[0]
    entry["checks"].append("范围与例外")
    prompt = json.loads(ResearchLedger(flow).prompt())
    assert len(prompt["works"]) == 1
    group = prompt["works"][0]
    assert group["scope"] == entry["scope"]
    assert [w["check"] for w in group["items"]] == entry["checks"]
    assert all("task_id" not in w and "scope" not in w for w in group["items"])


def test_custom_domain_constraints_under_generic_headings_are_retained():
    key = "project_basic_info_parsing"
    snapshot = skill_snapshot()
    snapshot[key + "/SKILL.md"] += (
        "\n## 适用场景\n禁止将代理机构地址作为项目地址。\n"
        "\n## 本项目的检索与输出\n只有采购人公告能够改变截止日期。\n"
        "\n## 新增业务限制\n预算与最高限价分别核对。\n"
    )
    skill = load_module_skill(snapshot, key)
    for rule in ("禁止将代理机构地址作为项目地址", "只有采购人公告能够改变截止日期",
                 "预算与最高限价分别核对"):
        assert rule in skill["model_rules"]
