"""验证先完整检索再逐条产出，业务 JSON 不依赖展示文本或原文存储。"""

import asyncio
import json

from synthesis_fixtures import research_calls, submission, summary_record
from test_analysis_research import block, session
from test_analysis_synthesis import execute
from test_deep_analysis import call

from tender.application.analysis.data import module_records
from tender.application.analysis.policy import load_module_skill
from tender.application.analysis.skills import skill_snapshot


def test_dimension_collects_all_evidence_before_synthesizing_independent_records():
    async def run():
        original = block()
        supplement = block() | {
            "block_id": "start", "element_id": 2, "offset": 1,
            "content": "质保自验收合格之日起算；须提供质保承诺书。",
        }
        research = session([original, supplement])

        async def retrieve(sources, query):
            return ([original] if query == "质保" else [supplement]), {}

        research.retrieve = retrieve
        warranty = summary_record(
            text="验收合格之日起质保三年",
            citations=[{"block_id": original["block_id"], "quote": "质保三年"},
                       {"block_id": "start", "quote": "质保自验收合格之日起算"}],
        )
        material = summary_record(
            key="material", title="质保承诺材料", text="提供质保承诺书",
            citations=[{"block_id": "start", "quote": "须提供质保承诺书"}],
        )
        state, saved, router = await execute([
            *research_calls()[:2],
            call("search_document", {"query": "起算点和材料"}, "supplement"),
            call("complete_research", {}, "research"),
            call("submit_analysis", submission([warranty], final=False), "warranty"),
            call("submit_analysis", submission([material], final=False), "material"),
            call("submit_analysis", {"records": [], "final": True}, "finish"),
        ], research=research)
        assert all(not s.get("staged_items") for s in saved if not s.get("research_completed"))
        business = state["draft"]["business_data"]
        assert [r["key"] for r in business["records"]] == ["warranty", "material"]
        assert all("citations" not in r and "quote" not in r for r in business["records"])
        assert len(business["records"][0]["evidence_ids"]) == 2
        assert json.loads(json.dumps(business, ensure_ascii=False)) == business
        assert module_records(business)[0]["citations"][1]["block_id"] == "start"
        # 输出限制来自真实工具 schema，不能仅靠提示词劝模型不要生成大数组。
        tool = next(t for t in router.requests[-1][1]
                    if t["function"]["name"] == "submit_analysis")
        assert tool["function"]["parameters"]["properties"]["records"]["maxItems"] == 3

    asyncio.run(run())


def test_large_submission_is_rejected_without_losing_saved_result():
    first = summary_record()
    batch = [first] + [summary_record(key=f"extra-{index}") for index in range(3)]
    state, saved, _ = asyncio.run(execute([
        *research_calls(),
        call("submit_analysis", submission([first], final=False), "first"),
        call("submit_analysis", submission(batch), "large"),
        call("submit_analysis", submission([summary_record(key="second")], final=False), "second"),
        call("submit_analysis", {"records": [], "final": True}, "finish"),
    ]))
    rejected = next(s for s in saved if "call_large" in s.get("tool_results", {}))
    assert len(rejected["staged_items"]) == 1
    assert "最多3项" in rejected["tool_results"]["call_large"]["data"]["content"]
    assert len(state["draft"]["business_data"]["records"]) == 2


def test_technical_skill_loads_adapted_category_rules_before_first_inference():
    loaded = load_module_skill(skill_snapshot(), "tech_requirement_parsing", categories=["goods"])
    assert "只输出两类内容：项目背景、技术方案要求" in loaded["instructions"]
    assert "纯参数清单" in loaded["instructions"]
    assert any("/goods/" in path for path in loaded["references"])
    assert "安装调试、测试验证、迁移与运维方案" in loaded["instructions"]


def test_missing_one_evidence_cannot_leave_a_partially_supported_record():
    hydrated = module_records({"records": [{
        "id": "record", "evidence_ids": ["known", "missing"], "verification": "supported",
    }], "evidence": {"known": {"block_id": "block", "quote": "已读原文"}}})
    assert hydrated[0]["verification"] == "unavailable" and hydrated[0]["citations"] == []
