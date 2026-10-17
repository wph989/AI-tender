"""评分修复须保留可靠成果；未知分值和未展开转引不能变成正式评分条款。"""

import asyncio

import pytest
from synthesis_fixtures import research_calls, submission, summary_record
from test_analysis_references import ReferenceReviewer
from test_analysis_research import block, session
from test_analysis_synthesis import execute
from test_deep_analysis import call, submitted_field

from tender.application.analysis_policy import load_module_skill
from tender.application.analysis_skills import skill_snapshot, verify_items
from tender.application.knowledge import validate_items

KEY = "scoring_standard_parsing"
SNAPSHOT = skill_snapshot() | {KEY + "/references/coverage.json": "[]"}
METHOD = "采用综合评分法"


def method_record():
    return summary_record(
        key="method", kind="fact", title="评标方法", group="评分总则",
        content={"总则要素": "评标方法", "原文内容": METHOD}, quote=METHOD,
    )


@pytest.mark.parametrize("component", ["资信业绩部分", "监理大纲部分", "投标报价", "其他评分因素"])
def test_named_component_can_omit_an_unknown_score(component):
    quote = component + ":见评标办法前附表"
    record = summary_record(
        key="component", kind="fact", title=component, group="总分构成",
        content={"组成部分": component}, quote=quote, structuring="partial",
    )
    state, _, _ = asyncio.run(execute([
        *research_calls(query="分值构成"),
        call("submit_analysis", submission([record]), "final"),
    ], research=session([block() | {"content": quote}]), snapshot=SNAPSHOT, key=KEY))
    assert state["draft"]["fields"][0]["output"]["content"] == {"组成部分": component}
    assert "分值" not in state["draft"]["business_data"]["records"][0]["content"]


@pytest.mark.parametrize("reference_only", [False, True])
def test_exhausted_scoring_record_becomes_a_gap_without_aborting_other_results(reference_only):
    async def run():
        index = "资信业绩部分:见评标办法前附表"
        research = session([block() | {"content": METHOD + "；" + index}])
        bad = summary_record(
            key="criteria", title="资信业绩评分", group="综合评分标准", quote=index,
            content={"评分项": "资信业绩", "评分标准（原文摘录）": index},
        )
        reviewed = []

        async def review(items):
            for item in items:
                reviewed.append(item["business"]["key"])
                if item["business"]["key"] == "method":
                    item["verification"] = "supported"
                else:
                    item.update(
                        verification="unsupported",
                        verification_claim_issues=[] if reference_only else ["原文没有满分分值"],
                        verification_references=["评标办法前附表"] if reference_only else [],
                        verification_issues=[
                            "评分细则尚未展开" if reference_only else "原文没有满分分值",
                        ],
                    )

        state, saved, _ = await execute([
            *research_calls(query="评分"),
            call("submit_analysis", submission([method_record()], final=False), "good"),
            *[call("submit_analysis", submission([bad]), n) for n in range(1, 4)],
            # 不再重发耗尽事项，维度通过空记录明确收尾，可靠结果和缺口独立保存。
            call("submit_analysis", submission(), "finish"),
        ], research=research, snapshot=SNAPSHOT, key=KEY, review=review)
        assert reviewed.count("criteria") == 3 and reviewed.count("method") == 1
        records = state["draft"]["business_data"]["records"]
        assert [r["key"] for r in records] == ["method"]
        assert "资信业绩评分" in state["draft"]["research_summary"]
        gaps = state["draft"]["business_data"]["gaps"]
        assert any(g["code"] == ("unresolved_reference" if reference_only else "unknown_condition")
                   for g in gaps)
        failed_final = next(s for s in saved if "call_3" in s.get("tool_results", {})
                            and s.get("rejected_records"))
        assert "draft" not in failed_final and "pending_final" not in failed_final
        if reference_only:
            assert not state.get("correction_failures")
            assert max(state["reference_failures"].values()) == 3
        else:
            assert max(state["correction_failures"].values()) == 3

    asyncio.run(run())


@pytest.mark.parametrize("absence", ["未载明", "未明确", "未约定"])
def test_absence_placeholder_moves_to_summary_without_spending_content_retries(absence):
    async def run():
        index = "资信业绩部分:见评标办法前附表"
        bad = summary_record(
            key="score-gap", title="各评分项满分分值", group="综合评分标准", quote=index,
            content={"评分项": "资信业绩", "满分分值": "见评标办法前附表（" + absence + "）"},
        )
        reviewed = []

        async def review(items):
            reviewed.extend(i["business"]["key"] for i in items)
            for item in items:
                item["verification"] = "supported"

        state, _, _ = await execute([
            *research_calls(query="评分"),
            call("submit_analysis", submission([method_record()], final=False), "method"),
            call("submit_analysis", submission([bad]), "final"),
        ], research=session([block() | {"content": METHOD + "；" + index}]),
            snapshot=SNAPSHOT, key=KEY, review=review)
        assert reviewed == ["method"]
        assert [r["key"] for r in state["draft"]["business_data"]["records"]] == ["method"]
        assert "各评分项满分分值" in state["draft"]["research_summary"]
        assert not state.get("correction_failures") and not state.get("field_failures")

    asyncio.run(run())


def test_original_formula_quote_survives_a_plain_display_formula():
    quote = r"投标人得分=\mathbf{A}+\mathbf{B}+\mathbf{C}+\mathbf{D}"
    row = block() | {"content": quote}
    evidence = {row["block_id"]: row}
    items = validate_items([submitted_field("总分计算公式", "投标人得分=A+B+C+D", quote=quote)],
                           evidence)
    asyncio.run(verify_items(ReferenceReviewer({}), items, explain=True,
                             evidence=evidence, select_evidence=True))
    assert items[0]["verification"] == "supported"
    assert items[0]["values"][0]["value"] == "投标人得分=A+B+C+D"
    assert items[0]["values"][0]["citations"][0]["quote"] == quote


def test_reference_review_keeps_content_errors_separate_from_missing_targets():
    value = "评分标准详见附件1"
    row = block() | {"content": value}
    evidence = {row["block_id"]: row}
    items = validate_items([submitted_field("评分标准", value, quote=value)], evidence)
    asyncio.run(verify_items(ReferenceReviewer({value: "附件1具体评分条款"}), items,
                             explain=True, evidence=evidence, select_evidence=True))
    assert items[0]["verification"] == "unsupported"
    assert items[0]["verification_claim_issues"] == []
    assert items[0]["verification_references"] == ["附件1具体评分条款"]


def test_domain_rules_are_loaded_for_selected_categories_without_defaulting_to_service():
    snapshot = {
        KEY + "/SKILL.md": "按本专题业务边界解析评分",
        KEY + "/references/output_format.md": "评分输出模板",
        **{KEY + "/references/" + category + "/extraction_rules.md": category + "专属细则"
           for category in ("service", "goods", "engineering")},
    }
    loaded = load_module_skill(snapshot, KEY, categories=("goods", "engineering", "goods"))
    assert "goods专属细则" in loaded["instructions"]
    assert "engineering专属细则" in loaded["instructions"]
    assert "service专属细则" not in loaded["instructions"]
    assert len(loaded["references"]) == 3
    assert not any("专属细则" in load_module_skill(snapshot, KEY)["instructions"]
                   for _ in [None])


@pytest.mark.parametrize("key,paths", [
    ("project_basic_info_parsing", ["references/extraction_rules.md"]),
    ("bid_format_outline_parsing", [
        "references/locate_rules.md", "references/outline_extract_rules.md",
    ]),
])
def test_required_domain_references_are_loaded_before_analysis(key, paths):
    snapshot = {key + "/SKILL.md": "主规则", **{key + "/" + p: p for p in paths}}
    loaded = load_module_skill(snapshot, key)
    assert all(p in loaded["instructions"] for p in paths)
    assert len(loaded["references"]) == len(paths)
