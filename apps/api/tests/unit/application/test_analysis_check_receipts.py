"""完整性回执防止漏项被空问题列表掩盖，分包导航与独立成果仍分别处理。"""

import asyncio
import copy

import pytest
from synthesis_fixtures import summary_record
from test_analysis_combined_review import approve, execute

from tender.application.analysis.data import module_data
from tender.application.analysis.research import AgentLimits
from tender.application.analysis.review import _merge_packets, validate
from tender.application.analysis.topic_flow import TopicIncomplete
from tender.domain.shared.errors import InvalidModelOutput


def packet(topic="a"):
    return {
        "topic": topic, "project_id": 1, "documents": [], "checks": [{
            "scope": {"kind": "common", "lot_refs": []}, "record_ids": [topic],
            "navigation_record_ids": [],
        }], "searches": [],
        "reads": [], "citations": {}, "repair_issues": [], "record_index": [],
        "records": [{"record_id": topic, "block_ids": ["b1"]}], "context_records": [],
        "evidence": [{"id": "b1", "text": "质保三年；替换部件应重新计算质保期"}],
        "context_evidence": [],
        "check_items": [{"check_id": topic + "-warranty", "topic": topic,
                         "scope": {"kind": "common", "lot_refs": []},
                         "check": "质保期限和替换部件的独立起算条件",
                         "record_ids": [topic], "navigation_record_ids": []}],
    }


def test_missing_check_receipt_cannot_publish_a_supported_but_incomplete_draft():
    async def run():
        state = {}

        async def review(payload):
            result = approve(payload)
            result.pop("check_results")
            return result

        with pytest.raises(TopicIncomplete, match="逐项回答"):
            await execute([summary_record()], state=state, review=review)
        assert not module_data(state)["records"]
        assert not state.get("quality_status")
        assert not state["topic_flow"]["audit"].get("done")

    asyncio.run(run())


@pytest.mark.parametrize("missing", [None, ["招标公告"], "招标公告", 1, False])
def test_malformed_missing_input_returns_protocol_feedback_instead_of_crashing(missing):
    payload = packet()
    result = approve(payload)
    result["issues"] = [{"topic": "a", "kind": "reference", "action": "provide_input",
        "target": "招标公告", "detail": "需要补充公告", "record_ids": [],
        "evidence_ids": ["b1"], "missing_input": missing}]
    with pytest.raises(InvalidModelOutput, match="missing_input"):
        validate(result, payload)


@pytest.mark.parametrize("response,reason", [
    ({"status": "covered", "record_ids": []}, "完整业务成果"),
    ({"status": "not_required", "record_ids": [], "block_ids": []}, "不适用"),
    ({"status": "needs_action", "record_ids": [], "issue_indexes": []}, "具体业务issues"),
    ({"status": "deferred", "record_ids": [], "block_ids": []}, "真实导航"),
    ({"status": "covered", "record_ids": ["other"]}, "实际交付"),
    ({"status": "covered_here"}, "partition"),
])
def test_receipts_cannot_claim_unexamined_or_unpublished_content_is_complete(response, reason):
    payload = packet()
    result = approve(payload)
    result["check_results"]["a-warranty"].update(response)
    with pytest.raises(InvalidModelOutput, match=reason):
        validate(result, payload)


@pytest.mark.parametrize("failure", ["deferred", "no_evidence"])
def test_partition_receipt_requires_actual_reviewed_content(failure):
    payload = packet()
    payload["check_items"][0]["coverage_mode"] = "partition"
    payload["checks"][0]["navigation_record_ids"] = ["another-packet"]
    result = approve(payload)
    receipt = result["check_results"]["a-warranty"]
    receipt["status"] = "covered_here"
    if failure == "deferred":
        receipt.update(status="deferred", record_ids=[], block_ids=[], issue_indexes=[])
    elif failure == "no_evidence":
        receipt["block_ids"] = []
    with pytest.raises(InvalidModelOutput):
        validate(result, payload)


@pytest.mark.parametrize("partition", [False, True])
def test_coverage_receipt_preserves_rejection_without_repeating_model_call(partition):
    payload = packet()
    if partition:
        payload["check_items"][0]["coverage_mode"] = "partition"
    result = approve(payload)
    receipt = result["check_results"]["a-warranty"]
    receipt["status"] = "covered_here" if partition else "covered"
    result["reviews"]["a"].update(supported=False, issues=["原文没有支持期限"])
    validate(result, payload)
    assert receipt["status"] == "needs_action"
    assert receipt["issue_indexes"] == [0]
    assert result["issues"][0]["detail"] == "原文没有支持期限"
    assert result["issues"][0]["record_ids"] == ["a"]
    assert not result["reviews"]["a"]["supported"]
    # 路由校验、返回解析及冻结回执会多次经过校验，不能重复生成同一业务问题。
    validate(result, payload)
    assert len(result["issues"]) == 1


@pytest.mark.parametrize("partition", [False, True])
def test_rejected_coverage_never_publishes_or_becomes_verified(partition):
    async def run():
        async def review(payload):
            result = approve(payload)
            for verdict in result["reviews"].values():
                verdict.update(supported=False, issues=["原文要求三年，草稿误写两年"])
            if partition:
                for check in payload["check_items"]:
                    check["coverage_mode"] = "partition"
                for receipt in result["check_results"].values():
                    receipt["status"] = "covered_here"
            return result

        state, _, _, calls = await execute([summary_record()], review=review,
                                           limits=AgentLimits(max_review_repairs=0))
        assert len(calls) == 1
        assert not module_data(state)["records"]
        assert state["quality_status"] == "needs_review"
        assert len(state["quality_issues"]) == 1
        assert "误写两年" in state["quality_issues"][0]["detail"]
        assert all(receipt[0]["status"] == "needs_action" for receipt in
                   state["topic_flow"]["audit"]["check_results"]["a"].values())

    asyncio.run(run())


def test_omitted_independent_condition_keeps_supported_fact_and_concrete_gap():
    async def run():
        async def review(payload):
            result = approve(payload)
            result["issues"] = [{"topic": "a", "kind": "omission", "action": "read",
                "target": "替换部件/质保起算条件", "detail": "原文要求的独立起算条件未核清",
                "record_ids": [], "evidence_ids": ["s1r1c0"]}]
            for receipt in result["check_results"].values():
                receipt.update(status="needs_action", summary="三年质保成立，替换部件的条件待核清",
                               issue_indexes=[0])
            return result

        state, _, _, calls = await execute([summary_record()], review=review,
                                           limits=AgentLimits(max_review_repairs=0))
        assert len(calls) == 1
        assert len(module_data(state)["records"]) == 1
        assert state["quality_status"] == "needs_review"
        assert state["quality_issues"][0]["target"] == "替换部件/质保起算条件"
        receipts = state["topic_flow"]["audit"]["check_results"]["a"]
        assert all(v[0]["status"] == "needs_action" for v in receipts.values())

    asyncio.run(run())


def test_shared_original_does_not_merge_distinct_check_identity_or_issue_owner():
    payload = _merge_packets([packet("a"), packet("b")])
    result = approve(payload)
    assert set(result["check_results"]) == {"a-warranty", "b-warranty"}
    validate(result, payload)
    wrong = copy.deepcopy(result)
    wrong["issues"] = [{"topic": "b", "kind": "omission", "target": "部件条件",
                       "detail": "待核对", "record_ids": [], "evidence_ids": ["b1"]}]
    wrong["check_results"]["a-warranty"].update(status="needs_action", issue_indexes=[0])
    with pytest.raises(InvalidModelOutput, match="主题与范围"):
        validate(wrong, payload)


@pytest.mark.parametrize("verdict", [None, False, [], {"block_ids": None}])
def test_bad_verdict_cannot_crash_or_support_a_covered_receipt(verdict):
    payload = packet()
    result = approve(payload)
    result["reviews"]["a"] = verdict
    with pytest.raises(InvalidModelOutput):
        validate(result, payload)
