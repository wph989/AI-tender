"""复现报告30的范围冲突、机械参数纠错和迟迟无法保存成果的问题。"""

import asyncio
import copy
import json

import pytest
from langchain_core.messages import AIMessage
from synthesis_fixtures import COMMON, submission, summary_record
from test_analysis_research import block
from test_analysis_topic_flow import execute, prepared_flow, search
from test_deep_analysis import call

from tender.application.analysis.data import module_data
from tender.application.analysis.research import ToolArgumentError
from tender.application.analysis.search_control import TopicSearch
from tender.application.analysis.topic_flow import TopicFlow, TopicUpdate, identity

UNKNOWN = {"kind": "unknown", "lot_refs": []}
CHECK = "核对独立事项及全部条件"


def test_unknown_scope_is_saved_before_scope_confirmation_and_then_reused():
    async def run():
        state, saved, _, audited = await execute([
            search("a"),
            call("submit_analysis", submission([summary_record(scope=UNKNOWN)], final=False) | {
                "topic_updates": [{"topic": "a"}]}, "unknown"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [{"topic": "a", "checked": [CHECK]}]}, "confirmed"),
        ], keys=("a",))
        early = next(s for s in saved if module_data(s)["records"])
        record = module_data(early)["records"][0]
        assert record["scope"] == UNKNOWN and record["verification"] == "supported"
        assert not early.get("draft")
        assert early["topic_flow"]["entries"]
        assert all(e["status"] != "ready" for e in early["topic_flow"]["entries"].values())
        assert len(state["draft"]["fields"]) == 1 and audited
        assert state["draft"]["fields"][0]["business"]["scope"] == COMMON
        assert len(state["topic_flow"]["entries"]) == 1

    asyncio.run(run())


def test_incremental_batches_derive_keys_evidence_and_ready_state_without_empty_submit():
    async def run():
        reviewed = []

        async def review(items):
            reviewed.extend(i["business"]["key"] for i in items)
            for item in items:
                item["verification"] = "supported"

        state, saved, router, _ = await execute([
            search("a"),
            call("submit_analysis", submission([summary_record(key="first")], final=False),
                 "first"),
            call("submit_analysis", submission([summary_record(key="second", title="另一事项")]) | {
                "topic_updates": [{"topic": "a", "checked": [CHECK]}]}, "second"),
        ], keys=("a",), review=review)
        assert reviewed == ["first", "second"]
        entry = next(iter(state["topic_flow"]["entries"].values()))
        assert entry["record_keys"] == ["first", "second"]
        assert entry["evidence_ids"] == ["s1r1c0"] and entry["status"] == "ready"
        assert len(state["draft"]["fields"]) == 2 and len(router.requests) == 3
        assert any(len(module_data(s)["records"]) == 1 for s in saved)

    asyncio.run(run())


def test_minimal_update_uses_declared_topic_when_evidence_has_multiple_owners():
    flow, state, _ = prepared_flow(("a", "b"))
    flow.data["evidence_topics"]["s1r1c0"] = ["a", "b"]
    new = copy.deepcopy(state["staged_items"][0])
    new["business"]["key"] = "new"
    updates = flow.prepare_updates([new], [TopicUpdate(topic="b")])
    assert len(updates) == 1 and updates[0].topic == "b"
    assert updates[0].record_keys == ["new"]


def test_confirming_one_scope_keeps_other_saved_facts_pending_without_reclassifying_them():
    flow, state, _ = prepared_flow()
    first = state["staged_items"][0]
    first["business"]["scope"] = UNKNOWN
    other = copy.deepcopy(first)
    other["business"]["key"] = "other"
    state["staged_items"].append(other)
    entry = flow.entries[0]
    entry.update(scope=UNKNOWN, record_keys=["warranty", "other"])
    flow.data["entries"] = {identity("a", UNKNOWN): entry}
    revised = copy.deepcopy(first)
    revised["business"]["scope"] = COMMON
    updates = flow.prepare_updates([revised], [])
    flow.validate_records([revised], updates)
    flow.apply(updates, {"warranty", "other"})
    pending = next(e for e in flow.entries if e["scope"] == UNKNOWN)
    confirmed = next(e for e in flow.entries if e["scope"] == COMMON)
    assert pending["record_keys"] == ["other"] and pending["status"] != "ready"
    assert confirmed["record_keys"] == ["warranty"]
    assert other["business"]["scope"] == UNKNOWN


def test_reading_text_alone_does_not_complete_checks_or_bypass_scope_validation():
    flow, state, _ = prepared_flow()
    record = copy.deepcopy(state["staged_items"][0])
    record["business"].update(key="new", scope=UNKNOWN)
    updates = flow.prepare_updates([record], [])
    flow.validate_records([record], updates)
    flow.apply(updates, {"warranty", "new"})
    unknown = next(e for e in flow.entries if e["scope"] == UNKNOWN)
    assert unknown["checked"] == [] and unknown["status"] != "ready"
    bad = [TopicUpdate(topic="a", scope=COMMON, record_keys=["new"])]
    with pytest.raises(ValueError, match="范围.*不一致"):
        flow.validate_records([record], bad)


@pytest.mark.parametrize("work", ["期限；数量", ["期限", "数量"], "ids"])
def test_one_search_can_cover_multiple_checks_without_copying_long_labels(work):
    flow, _, research = prepared_flow()
    flow.entries[0].update(checks=["期限", "数量"], checked=[], requested_status="researching")
    flow.sync()
    control = TopicSearch(flow)
    if work == "ids":
        work = [c["id"] for c in control.choices(["a"])]
    selected = control.begin("search_document", {"topic_keys": ["a"], "work": work})
    control.end(selected, {"blocks": []}, set(research.seen))
    assert {w["work"] for w in selected} == {"期限", "数量"}
    assert TopicSearch.summary(flow.state)["research_calls"] == 1
    assert all(value["attempts"] == 1 for value in control.ledger.values())


def test_batched_research_closes_without_renewing_budget_by_changing_selection():
    flow, state, research = prepared_flow()
    flow.entries[0].update(checks=["期限", "数量"], checked=[], requested_status="researching")
    flow.sync()
    control = TopicSearch(flow)
    for index in range(3):
        work = control.begin("search_document", {"topic_keys": ["a"], "query": str(index),
                                                 "work": ["期限", "数量"]})
        control.end(work, {"blocks": []}, set(research.seen))
    restored = TopicFlow(copy.deepcopy(state), research)
    control = TopicSearch(restored)
    with pytest.raises(ToolArgumentError, match="耗尽"):
        control.begin("search_document", {"topic_keys": ["a"], "work": ["期限", "数量"]})
    assert control.summary(restored.state)["exhausted_work"] == 2


def test_loaded_core_rule_reads_return_short_feedback_and_do_not_repeat_full_text():
    async def run():
        state, _, router, _ = await execute([
            AIMessage(content="", tool_calls=[search("a"), call("read_file", {
                "file_path": "/skills/project-basic-info-parsing/SKILL.md"}, "rule")]),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [{"topic": "a", "checked": [CHECK]}]}, "submit"),
        ], keys=("a",))
        result = json.loads(state["tool_results"]["call_rule"]["data"]["content"])
        assert result["already_loaded"] is True
        assert len(result["note"]) < 100 and len(router.requests) == 2
        prompt = str(router.requests[0][0])
        assert prompt.count("你分析当前专题") == 1

    asyncio.run(run())


def test_unknown_scope_has_a_concrete_followup_instead_of_an_unactionable_gate():
    flow, state, _ = prepared_flow()
    state["staged_items"][0]["business"]["scope"] = UNKNOWN
    entry = flow.entries[0]
    entry["scope"] = UNKNOWN
    entry["requested_status"] = "ready"
    flow.sync()
    assert [w["work"] for w in TopicSearch(flow).choices(["a"])] == ["确认适用范围"]


def test_rules_not_in_current_context_can_still_be_read_on_demand():
    async def run():
        state, _, _, _ = await execute([
            search("a"),
            call("read_file", {"file_path": "/skills/project-basic-info-parsing/SKILL.md",
                               "offset": 0, "limit": 1000}, "needed"),
            call("read_file", {"file_path": "/skills/project-basic-info-parsing/SKILL.md",
                               "offset": 0, "limit": 1000}, "duplicate"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [{"topic": "a", "checked": [CHECK]}]}, "submit"),
        ], keys=("a",))
        needed = state["tool_results"]["call_needed"]["data"]["content"]
        duplicate = state["tool_results"]["call_duplicate"]["data"]["content"]
        assert "检索项目概况" in needed
        assert json.loads(duplicate)["already_loaded"]

    asyncio.run(run())


def test_new_evidence_still_marks_saved_unknown_facts_for_review():
    flow, state, research = prepared_flow()
    state["staged_items"][0]["business"]["scope"] = UNKNOWN
    flow.entries[0]["scope"] = UNKNOWN
    research.seen["new"] = block() | {"content": "质保改为一年"}
    flow.evidence({"s1r1c0"}, ["a"], {"blocks": [{"id": "new"}]})
    assert module_data(state)["records"][0]["review_status"] == "needs_review"
