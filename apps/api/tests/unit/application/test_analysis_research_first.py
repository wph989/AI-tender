"""真实Agent图验证先研究后综合、跨字段复用及未命中结论的依据。"""

import asyncio
import copy
import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import COMMON, accept, noop, submission, summary_record
from test_analysis_research import block, session
from test_analysis_topic_flow import search, snapshot, update
from test_deep_analysis import KEY, ScriptedRouter, call

from tender.application.analysis.agent import RoutedAgentModel, build_module_agent, invoke_module
from tender.application.analysis.data import module_data
from tender.application.analysis.topic_flow import (
    OUTPUT_MODE,
    OUTPUT_MODE_KEY,
    TopicFlow,
    TopicIncomplete,
    TopicUpdate,
)

CHECK = "核对独立事项及全部条件"


def note(topic, **kwargs):
    return {"topic": topic, "scope": COMMON,
            "findings": [{"check": CHECK, "detail": "质保三年，已核对完整条件",
                          "evidence_ids": ["s1r1c0"]}], **kwargs}


def research_update(*topics, **kwargs):
    return call("update_research", {"topic_updates": [note(key) for key in topics], **kwargs},
                "notes-" + "-".join(topics))


async def execute(script, *, keys=("a", "b"), research=None, audit=None, review=None):
    state, saved, audited, reviewed = {}, [], [], []

    async def save(value):
        saved.append(copy.deepcopy(value))

    async def coverage(payload):
        audited.append(copy.deepcopy(payload))
        return await audit(payload) if audit else {"issues": []}

    async def support(items):
        reviewed.append([i["business"]["key"] for i in items])
        await (review or accept)(items)

    router = ScriptedRouter(script)
    graph, files = build_module_agent(
        key=KEY, model=RoutedAgentModel(router=router), research=research or session([block()]),
        state=state, snapshot=snapshot(keys) | {OUTPUT_MODE_KEY: OUTPUT_MODE},
        checkpointer=InMemorySaver(), reserve_tool=noop, save=save,
        review_support=support, review_coverage=coverage,
    )
    await invoke_module(graph, files, thread_id="research-first", task="先研究后统一综合")
    assert not router.calls
    return state, saved, router, audited, reviewed


def test_one_search_answers_two_topics_and_all_results_are_released_together():
    async def run():
        state, saved, router, audited, reviewed = await execute([
            call("list_documents", {}, "docs"),
            call("search_document", {"query": "质保", "topic_keys": ["a", "b"]}, "shared"),
            research_update("a", "b"),
            call("submit_analysis", submission([summary_record(key="one")], final=False) | {
                "topic_updates": [update("a", ["one"])]}, "one"),
            call("submit_analysis", submission([summary_record(key="two")]) | {
                "topic_updates": [update("b", ["two"])]}, "two"),
        ])
        assert reviewed == [["one"], ["two"]] and len(audited) == 2
        assert len(router.requests) == 5
        assert all(not module_data(s)["records"] for s in saved if "draft" not in s)
        assert len(module_data(state)["records"]) == 2
        assert state["topic_flow"]["phase"] == "completed"
        assert all(e["findings"] for e in state["topic_flow"]["entries"].values())
        assert "先检索研究" in str(router.requests[0][0])

    asyncio.run(run())


def test_submission_during_research_is_rejected_without_saving_business_data():
    async def run():
        state, saved, _, _, reviewed = await execute([
            search("a"),
            call("submit_analysis", submission([summary_record()]), "early"),
            research_update("a"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"])]}, "final"),
        ], keys=("a",))
        assert "研究阶段" in state["tool_results"]["call_early"]["data"]["content"]
        assert reviewed == [["warranty"]]
        early = next(s for s in saved if "call_early" in s.get("tool_results", {}))
        assert not early.get("staged_items")

    asyncio.run(run())


def test_complete_request_returns_specific_missing_checks_then_research_continues():
    async def run():
        state, _, _, _, _ = await execute([
            search("a"),
            call("update_research", {"topic_updates": [{"topic": "a", "detail": "只找到标题"}],
                                     "complete": True}, "premature"),
            research_update("a"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"])]}, "final"),
        ], keys=("a",))
        result = json.loads(state["tool_results"]["call_premature"]["data"]["content"])
        assert result["phase"] == "research" and not result["complete"]
        assert CHECK in str(result["pending"])

    asyncio.run(run())


def test_a_single_empty_search_cannot_certify_that_documents_have_no_requirement():
    async def run():
        research = session([block()])
        retrieve = research.retrieve

        async def selective(sources, query):
            return await retrieve(sources, query) if query == "质保" else ([], {})

        research.retrieve = selective
        absent = note("b", findings=[{"check": CHECK, "detail": "已核对项目资料，未找到相关约定",
                                     "status": "not_found"}])
        state, _, _, _, _ = await execute([
            search("a"), research_update("a"), search("b", "例外", "first"),
            call("update_research", {"topic_updates": [absent]}, "single-miss"),
            search("b", "售后条件", "second"),
            call("update_research", {"topic_updates": [absent]}, "checked-miss"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"])]}, "final"),
        ], research=research)
        assert "至少两种查询" in state["tool_results"]["call_single-miss"]["data"]["content"]
        assert len(module_data(state)["records"]) == 1
        assert any(c["status"] == "searched_not_found" for c in state["business_coverage"])
        assert state["business_gaps"]

    asyncio.run(run())


def researched_flow():
    research = session([block()])
    asyncio.run(research.search("质保", "project"))
    state = {"business_topics": [{"key": "a", "title": "质保", "checks": [CHECK]}]}
    flow = TopicFlow(state, research)
    flow.data.update(output_mode=OUTPUT_MODE, phase="research")
    flow.evidence(set(), ["a"])
    return flow, state, research


def test_research_notes_survive_recovery_and_new_evidence_requires_analysis():
    flow, state, research = researched_flow()
    assert not flow.record_research([TopicUpdate.model_validate(note("a"))])
    restored = TopicFlow(copy.deepcopy(state), research)
    assert not restored.researching
    assert CHECK in restored.prompt() and "s1r1c0" in restored.prompt()
    research.seen["new"] = block() | {"block_id": "new", "content": "易损件例外为一年"}
    restored.evidence({"s1r1c0"}, ["a"])
    assert restored.researching and "新增原文尚未分析" in str(restored.research_pending())
    assert restored.entries[0]["findings"][CHECK]["detail"]
    restored.record_research([TopicUpdate.model_validate({"topic": "a"})])
    assert restored.researching
    restored.record_research([TopicUpdate.model_validate(note("a", detail="已核对易损件例外"))])
    assert not restored.researching


@pytest.mark.parametrize("bad", [
    {"checked": [CHECK], "findings": []},
    {"findings": [{"check": CHECK, "detail": "无证据"}]},
    {"findings": [{"check": CHECK, "detail": "未知证据", "evidence_ids": ["missing"]}]},
])
def test_invalid_research_update_is_atomic(bad):
    flow, state, _ = researched_flow()
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        flow.record_research([TopicUpdate.model_validate(note("a", **bad))])
    assert state == before


@pytest.mark.parametrize("limited", ["has_more", "limited"])
def test_unread_search_results_cannot_be_used_as_absence_proof(limited):
    flow, _, _ = researched_flow()
    flow.data["research_searches"] = {"a": {
        str(i): {"query": str(i), "source_ids": [1], "has_more": False, "limited": False,
                 **({limited: True} if i == 0 else {})} for i in range(2)}}
    with pytest.raises(ValueError, match="未读分页或截断"):
        flow.record_research([TopicUpdate.model_validate(note("a", findings=[{
            "check": CHECK, "detail": "未找到", "status": "not_found"}]))])


def test_unchanged_research_notes_do_not_renew_work_budget():
    from tender.application.analysis.search_control import TopicSearch

    flow, _, _ = researched_flow()
    flow.record_research([TopicUpdate.model_validate(note("a", tasks=[{"detail": "查找例外"}]))])
    control = TopicSearch(flow)
    for i in range(3):
        work = control.begin("search_document", {"topic_keys": ["a"], "query": str(i),
                                                "work": "查找例外"})
        control.end(work, {"blocks": []}, {"s1r1c0"})
        flow.record_research([TopicUpdate.model_validate(note("a", detail="改写进展说明"))])
    from tender.application.analysis.research import WorkClosed

    with pytest.raises(WorkClosed):
        control.begin("search_document", {"topic_keys": ["a"], "query": "继续换词",
                                          "work": "查找例外"})


def test_audit_repair_research_can_finish_before_old_records_are_reverified():
    async def run():
        issue = {"topic": "a", "detail": "核对质保起算条件", "target": "合同条款",
                 "evidence_ids": ["s1r1c0"], "record_keys": ["warranty"]}
        count = 0

        async def audit(payload):
            nonlocal count
            count += 1
            return {"issues": [issue] if count == 1 else []}

        state, _, _, audited, reviewed = await execute([
            search("a"), research_update("a"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"])]}, "first"),
            call("update_research", {"topic_updates": [note("a", tasks=[{
                "detail": issue["detail"], "status": "resolved", "evidence_ids": ["s1r1c0"],
                "record_keys": ["warranty"]}])]}, "repaired-notes"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"])]}, "repaired-record"),
        ], keys=("a",), audit=audit)
        assert len(audited) == 2 and reviewed == [["warranty"], ["warranty"]]
        assert module_data(state)["records"][0]["review_status"] == "current"

    asyncio.run(run())


def test_synthesis_is_not_finished_merely_because_one_topic_has_a_record():
    async def run():
        state, saved, _, audited, reviewed = await execute([
            search("a"), research_update("a"),
            call("submit_analysis", submission([summary_record(key="first")], final=False) | {
                "topic_updates": [update("a", ["first"])]}, "first"),
            call("submit_analysis", submission([summary_record(key="second")]) | {
                "topic_updates": [update("a", ["second"])]}, "second"),
        ], keys=("a",))
        assert reviewed == [["first"], ["second"]] and len(audited) == 1
        assert len(state["draft"]["fields"]) == 2
        assert not any(s.get("topic_flow", {}).get("audit", {}).get("done")
                       for s in saved if "call_second" not in s.get("tool_results", {}))

    asyncio.run(run())


def test_failed_targeted_review_stops_after_two_audits():
    async def run():
        count = 0
        issue = {"topic": "a", "detail": "缺少例外", "target": "附件",
                 "evidence_ids": ["s1r1c0"], "record_keys": ["warranty"]}

        async def audit(payload):
            nonlocal count
            count += 1
            return {"issues": [issue]}

        with pytest.raises(TopicIncomplete):
            await execute([
                search("a"), research_update("a"),
                call("submit_analysis", submission([summary_record()]) | {
                    "topic_updates": [update("a", ["warranty"])]}, "first"),
                call("update_research", {"topic_updates": [note("a", tasks=[{
                    "detail": issue["detail"], "status": "resolved", "evidence_ids": ["s1r1c0"],
                    "record_keys": ["warranty"]}])]}, "repair"),
                call("submit_analysis", submission([summary_record()]) | {
                    "topic_updates": [update("a", ["warranty"])]}, "second"),
            ], keys=("a",), audit=audit)
        assert count == 2

    asyncio.run(run())


def test_missing_check_is_preserved_when_other_checks_in_same_topic_have_evidence():
    flow, state, _ = researched_flow()
    state["business_topics"][0]["checks"].append("例外")
    flow.data["research_searches"] = {"a": {
        str(i): {"query": str(i), "source_ids": [1], "has_more": False, "limited": False}
        for i in range(2)}}
    finding = {"check": "例外", "detail": "核对附件及条款后仍未找到", "status": "not_found"}
    flow.record_research([TopicUpdate.model_validate(note("a", findings=[
        *note("a")["findings"], finding]))])
    assert any(g["key"].startswith("finding:") and "例外" in g["detail"]
               for g in state["business_gaps"])
    flow.record_research([TopicUpdate.model_validate(note("a", findings=[{
        **finding, "status": "found", "evidence_ids": ["s1r1c0"]}]))])
    assert not any(g["key"].startswith("finding:") for g in state["business_gaps"])


def test_natural_language_during_research_redirects_to_research_notes():
    async def run():
        _, _, router, _, _ = await execute([
            search("a"), AIMessage(content="已经分析完成"), research_update("a"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"])]}, "final"),
        ], keys=("a",))
        feedback = router.requests[2][0][-1]["data"]["content"]
        assert "请用update_research" in feedback and "进入synthesis后" in feedback

    asyncio.run(run())


def test_a_later_nonfinal_batch_revokes_previous_completion_intent():
    async def run():
        state, _, router, _, reviewed = await execute([
            call("search_document", {"query": "质保", "topic_keys": ["a", "b"]}, "shared"),
            research_update("a", "b"),
            call("submit_analysis", submission([summary_record(key="first")]) | {
                "topic_updates": [update("a", ["first"])]}, "premature-final"),
            call("submit_analysis", submission([summary_record(key="second")], final=False) | {
                "topic_updates": [update("b", ["second"])]}, "nonfinal"),
            call("submit_analysis", submission([summary_record(key="third")]) | {
                "topic_updates": [update("b", ["third"])]}, "final"),
        ])
        assert len(router.requests) == 5 and reviewed == [["first"], ["second"], ["third"]]
        assert len(state["draft"]["fields"]) == 3

    asyncio.run(run())
