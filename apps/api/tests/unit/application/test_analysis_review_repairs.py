"""审查发现的状态回退问题需用真实 Agent 图验证，避免仅修复局部报错。"""

import asyncio

import pytest
from synthesis_fixtures import COMMON, research_calls, submission, summary_record
from test_analysis_synthesis import execute
from test_deep_analysis import KEY, SKILL, call


@pytest.mark.parametrize("reference_only", [False, True])
def test_exhausted_coverage_proof_becomes_pending_without_losing_verified_records(reference_only):
    reviewed = []
    coverage = [{
        "topic": "warranty", "scope": COMMON, "status": "not_applicable",
        "record_keys": [], "detail": "该主题不适用",
        "citations": [{"block_id": "s1r1c0", "quote": "质保三年"}],
    }]

    async def review(items):
        for item in items:
            if item["business"]["kind"] != "coverage":
                item["verification"] = "supported"
                continue
            reviewed.append(item["id"])
            item.update(
                verification="unsupported",
                verification_issues=["不适用证明缺少可靠依据"],
                verification_claim_issues=[] if reference_only else ["原文不能证明不适用"],
                verification_references=["附件A"] if reference_only else [],
            )

    state, saved, _ = asyncio.run(execute([
        *research_calls(),
        call("submit_analysis", submission([summary_record()], final=False), "good"),
        *[call("submit_analysis", submission(coverage=coverage, final=False), n)
          for n in range(1, 4)],
        call("complete_research", {}, "confirm_again"),
        # 额度耗尽的相同证明不能被再次提交恢复成“不适用”。
        call("submit_analysis", submission(coverage=coverage), "finish"),
    ], snapshot=SKILL | {KEY + "/references/coverage.json": '[{"key":"warranty"}]'},
        review=review))
    assert len(reviewed) == 3
    data = state["draft"]["business_data"]
    assert [r["key"] for r in data["records"]] == ["warranty"]
    assert data["coverage"][0]["status"] == "pending"
    assert any(g["key"] == "record:" + reviewed[0] for g in data["gaps"])
    assert any(s.get("rejected_records") for s in saved)


def test_absence_rewrite_keeps_the_previous_verified_record():
    state, _, _ = asyncio.run(execute([
        *research_calls(),
        call("submit_analysis", submission([summary_record()], final=False), "good"),
        call("submit_analysis", submission([
            summary_record(text="质保期限未载明"),
        ], final=False), "absence"),
        call("submit_analysis", {"records": [], "final": True}, "finish"),
    ]))
    data = state["draft"]["business_data"]
    assert len(data["records"]) == 1
    assert data["records"][0]["content"] == summary_record()["content"]
    assert data["records"][0]["verification"] == "supported"
    assert any(g["code"] == "unknown_condition" for g in data["gaps"])


def test_repeated_research_confirmation_cannot_clear_exhausted_record_gap():
    async def review(items):
        for item in items:
            item.update(verification="unsupported", verification_issues=["原文不支持该断言"])

    state, saved, _ = asyncio.run(execute([
        *research_calls(),
        *[call("submit_analysis", submission([summary_record()], final=False), n)
          for n in range(1, 4)],
        call("complete_research", {}, "confirm_again"),
        call("submit_analysis", {"records": [], "gaps": [], "final": True}, "finish"),
    ], review=review))
    rejected = next(s for s in saved if s.get("rejected_records"))
    expected = next(g for g in rejected["business_gaps"] if g["key"].startswith("record:"))
    confirmed = next(s for s in saved if "call_confirm_again" in s.get("tool_results", {}))
    assert expected in confirmed["business_gaps"]
    assert expected in state["draft"]["business_data"]["gaps"]
    assert state["draft"]["business_data"]["records"] == []
