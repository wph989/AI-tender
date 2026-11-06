"""真实Agent图验证子主题增量产出、关联失效、覆盖门禁和有界查漏。"""

import asyncio
import copy
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import COMMON, accept, noop, submission, summary_record
from test_analysis_research import block, session
from test_deep_analysis import KEY, SKILL, ScriptedRouter, call

from tender.application.analysis.agent import RoutedAgentModel, build_module_agent, invoke_module
from tender.application.analysis.data import assemble_dataset, module_data
from tender.application.analysis.state import published_items
from tender.application.analysis.topic_flow import (
    FLOW_KEY,
    FLOW_VERSION,
    TopicFlow,
    TopicIncomplete,
    TopicUpdate,
)


def snapshot(keys=("a", "b")):
    return SKILL | {FLOW_KEY: FLOW_VERSION, KEY + "/references/coverage.json": json.dumps([
        {"key": key, "title": key, "checks": ["核对独立事项及全部条件"]} for key in keys
    ], ensure_ascii=False)}


def update(key, records=(), **kwargs):
    return {"topic": key, "scope": COMMON, "status": "ready",
            "checked": ["核对独立事项及全部条件"], "evidence_ids": ["s1r1c0"],
            "record_keys": list(records), "detail": "已核对完整条款", **kwargs}


def search(key, query="质保", number="search"):
    return call("search_document", {"query": query, "topic_keys": [key]}, number)


async def execute(script, *, keys=("a", "b"), review=accept, audit=None, research=None):
    saved, audited, state = [], [], {}

    async def save(value):
        saved.append(copy.deepcopy(value))

    async def coverage(payload):
        audited.append(copy.deepcopy(payload))
        return await audit(payload) if audit else {"issues": []}

    router = ScriptedRouter(script)
    graph, files = build_module_agent(
        key=KEY, model=RoutedAgentModel(router=router), research=research or session([block()]),
        state=state, snapshot=snapshot(keys), checkpointer=InMemorySaver(),
        reserve_tool=noop, save=save, review_support=review, review_coverage=coverage,
        budget_status=lambda: {"seconds_remaining": 1, "model_calls_remaining": 1,
                               "tool_calls_remaining": 1, "finish_reserve_seconds": 300},
    )
    await invoke_module(graph, files, thread_id="topics", task="增量分析")
    assert not router.calls
    return state, saved, router, audited


def test_topic_result_is_published_early_and_finishes_without_empty_call():
    async def run():
        reviewed = []

        async def review(items):
            reviewed.append([i["business"]["key"] for i in items])
            await accept(items)

        state, saved, router, audited = await execute([
            call("list_documents", {}, "docs"), search("a"),
            call("submit_analysis", submission([summary_record(key="one")]) | {
                "topic_updates": [update("a", ["one"])]}, "a"),
            search("b", "期限", "search-b"),
            call("submit_analysis", submission([summary_record(key="two", title="另一事项")]) | {
                "topic_updates": [update("b", ["two"])]}, "b"),
        ], review=review)
        early = next(s for s in saved if any(i.get("verification") == "supported"
                                            for i in s.get("staged_items", [])))
        assert len(module_data(early)["records"]) == 1
        assert any(e["topic"] == "b" and e["status"] == "pending"
                   for e in early["topic_flow"]["entries"].values())
        assert reviewed == [["one"], ["two"]]
        assert len(router.requests) == 5 and len(audited) == 2
        assert len(state["draft"]["fields"]) == 2
        assert "complete_research" not in [t["function"]["name"] for t in router.requests[0][1]]

    asyncio.run(run())


def test_partial_topic_update_cannot_finish_without_all_required_checks():
    async def run():
        state, _, router, _ = await execute([
            search("a"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"], checked=[])]}, "early"),
            call("submit_analysis", submission() | {
                "topic_updates": [update("a", ["warranty"])]}, "checked"),
        ], keys=("a",))
        assert "尚未完成" in str(router.requests[-1][0])
        assert state["topic_flow"]["audit"]["done"]

    asyncio.run(run())


def test_completeness_repairs_only_once_and_does_not_request_extra_empty_submission():
    async def run():
        calls = []
        issue = {"topic": "a", "detail": "缺少质保起算条件", "evidence_ids": ["s1r1c0"],
                 "record_keys": ["warranty"], "target": ""}

        async def audit(payload):
            calls.append(payload)
            return {"issues": [issue]} if len(calls) == 1 else {"issues": []}

        state, _, router, _ = await execute([
            search("a"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"])]}, "first"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"],
                 tasks=[{"detail": issue["detail"], "status": "resolved",
                         "evidence_ids": ["s1r1c0"]}])]}, "repair"),
        ], keys=("a",), audit=audit)
        assert len(calls) == 2 and calls[-1]["audit_issues"] == [issue]
        assert len(router.requests) == 3 and "draft" in state

    asyncio.run(run())


def test_new_evidence_marks_only_related_results_for_review_and_final_projection_excludes_them():
    async def run():
        research = session([block()])
        from tender.application.analysis.output import output_schema

        state = {"business_topics": [{"key": key, "title": key} for key in ("a", "b")],
                 "output_schema": output_schema(snapshot(), KEY)}
        flow = TopicFlow(state, research)
        await research.search("质保", "project")
        flow.evidence(set(), ["a", "b"])
        from tender.application.analysis.data import SynthesisRecord, prepare_records

        state["staged_items"] = prepare_records([
            SynthesisRecord.model_validate(summary_record(key="one")),
            SynthesisRecord.model_validate(summary_record(key="two")),
        ], state, research.seen, KEY)
        await accept(state["staged_items"])
        for key, record in (("a", "one"), ("b", "two")):
            flow.apply([TopicUpdate.model_validate(update(key, [record], checked=[key]))],
                       {"one", "two"})
        research.seen["new"] = block() | {"block_id": "new", "content": "但易损件保修一年"}
        flow.evidence({"s1r1c0"}, ["a"])
        assert len(published_items(state)) == 2
        assert [i["business"]["key"] for i in published_items(state, final=True)] == ["two"]
        assert state["staged_items"][0]["review_evidence_ids"] == ["new"]
        projected = module_data(state)
        assert projected["records"][0]["review_status"] == "needs_review"
        data = assemble_dataset([{"module_key": KEY, "title": "概况", "status": "partial",
                                  "business_data": projected}], [])
        assert len(data["requirements"]) == 1

    asyncio.run(run())


def test_failed_targeted_audit_preserves_verified_results_and_stops():
    async def run():
        async def audit(payload):
            return {"issues": [{"topic": "a", "detail": "缺少例外",
                                "evidence_ids": ["s1r1c0"], "record_keys": [], "target": ""}]}

        with pytest.raises(TopicIncomplete):
            await execute([
                search("a"),
                call("submit_analysis", submission([summary_record()]) | {
                    "topic_updates": [update("a", ["warranty"])]}, "first"),
                call("submit_analysis", submission() | {"topic_updates": [update("a", ["warranty"],
                     tasks=[{"detail": "缺少例外", "status": "blocked"}])]}, "blocked"),
            ], keys=("a",), audit=audit)

    asyncio.run(run())


def prepared_flow(keys=("a",)):
    from tender.application.analysis.data import SynthesisRecord, prepare_records
    from tender.application.analysis.output import output_schema

    research = session([block()])
    research.seen["s1r1c0"] = block()
    state = {"business_topics": json.loads(snapshot(keys)[KEY + "/references/coverage.json"]),
             "output_schema": output_schema(snapshot(keys), KEY)}
    flow = TopicFlow(state, research)
    state["staged_items"] = prepare_records(
        [SynthesisRecord.model_validate(summary_record())], state, research.seen, KEY)
    state["staged_items"][0]["verification"] = "supported"
    flow.evidence(set(), [keys[0]])
    flow.apply([TopicUpdate.model_validate(update(keys[0], ["warranty"]))], {"warranty"})
    return flow, state, research


def test_reused_evidence_has_multiple_owners_without_invalidating_current_result():
    flow, state, _ = prepared_flow(("a", "b"))
    flow.evidence({"s1r1c0"}, ["b"], {"already_read": ["s1r1c0"]})
    assert flow.data["evidence_topics"]["s1r1c0"] == ["a", "b"]
    assert state["staged_items"][0]["verification"] == "supported"
    assert state["staged_items"][0].get("review_status") != "needs_review"


@pytest.mark.parametrize("registration", ["search", "update"])
def test_existing_evidence_new_to_topic_requires_review(registration):
    flow, state, research = prepared_flow(("a", "b"))
    research.seen["exception"] = block() | {"content": "但易损件仅保修一年"}
    flow.associate("exception", ["b"])
    if registration == "search":
        flow.evidence(set(research.seen), ["a"], {"already_read": ["exception"]})
    else:
        flow.apply([TopicUpdate.model_validate(update(
            "a", ["warranty"], evidence_ids=["s1r1c0", "exception"],
        ))], {"warranty"})
    assert published_items(state)[0]["review_status"] == "needs_review"
    assert published_items(state, final=True) == []
    assert state["staged_items"][0]["review_evidence_ids"] == ["exception"]


def test_unowned_or_wrong_scope_record_cannot_be_submitted():
    flow, state, _ = prepared_flow()
    item = copy.deepcopy(state["staged_items"][0])
    item["business"]["key"] = "orphan"
    with pytest.raises(ValueError, match="topic_updates"):
        flow.validate_records([item], [])
    item["business"]["scope"] = {"kind": "lots", "lot_refs": ["A标段"]}
    with pytest.raises(ValueError, match="适用范围"):
        flow.validate_records([item], [TopicUpdate.model_validate(update("a", ["orphan"]))])


def test_unknown_scope_and_missing_lot_prevent_complete():
    flow, state, _ = prepared_flow()
    state["topic_lots"] = ["A标段", "B标段"]
    entry = flow.entries[0]
    entry["scope"] = {"kind": "lots", "lot_refs": ["A标段"]}
    assert any("B标段" in text for text in flow.pending())
    entry["scope"] = {"kind": "unknown", "lot_refs": []}
    assert flow.pending() and entry["status"] != "ready"


def test_lot_topic_uses_unresolved_refs_and_rejects_different_lot():
    flow, state, _ = prepared_flow()
    scope = {"kind": "lots", "lot_refs": ["A标段"]}
    item = state["staged_items"][0]
    item["business"]["scope"] = scope
    flow.entries[0]["scope"] = scope
    flow.validate_records([item], [])
    assert not flow.pending() and flow.entries[0]["status"] == "ready"
    item["business"]["scope"] = {"kind": "lots", "lot_refs": ["B标段"]}
    with pytest.raises(ValueError, match="适用范围"):
        flow.validate_records([item], [])
    assert flow.pending()


def test_revision_invalidates_previous_display_version_during_pending_update():
    flow, state, research = prepared_flow()
    old = copy.deepcopy(state["staged_items"][0])
    state["business_previous"] = {old["id"]: old}
    state["staged_items"][0]["verification"] = "pending"
    research.seen["revision"] = block() | {"file_name": "补遗一.pdf", "content": "质保改为五年"}
    flow.evidence({"s1r1c0"}, ["a"])
    assert published_items(state)[0]["review_status"] == "needs_review"
    assert published_items(state, final=True) == []


def test_audit_replay_reuses_saved_batch_and_detects_changed_data():
    async def run():
        flow, state, research = prepared_flow()
        calls = []

        async def review(payload):
            calls.append(payload)
            return {"issues": []}

        async def interrupted_save(state):
            raise ConnectionError("模拟检查点中断")

        with pytest.raises(ConnectionError):
            await flow.audit(review, interrupted_save)
        restored = TopicFlow(copy.deepcopy(state), research)
        assert await restored.audit(review, noop)
        assert len(calls) == 1
        assert await restored.audit(review, noop)
        assert len(calls) == 1
        research.seen["s1r1c0"]["content"] += "另有例外"
        with pytest.raises(TopicIncomplete, match="发生变化"):
            await restored.audit(review, noop)

    asyncio.run(run())


def test_not_applicable_proof_is_verified_and_new_evidence_revokes_completion():
    from tender.application.analysis.data import CoverageInput, prepare_coverage

    flow, state, research = prepared_flow()
    state["staged_items"] = []
    for entry in flow.entries:
        entry["record_keys"] = []
    coverage, proofs = prepare_coverage([CoverageInput.model_validate({
        "topic": "a", "scope": COMMON, "status": "not_applicable", "detail": "该条款不适用",
        "citations": [{"block_id": "s1r1c0", "quote": "质保三年"}],
    })], state, research.seen, state["business_topics"], KEY)
    state.update(business_coverage=coverage, staged_items=proofs)
    flow.sync()
    assert flow.pending()
    proofs[0]["verification"] = "supported"
    assert flow.pending() == []
    assert flow.audit_batches([])[0]["records"][0]["kind"] == "coverage"
    research.seen["new"] = block() | {"content": "本条仍适用"}
    flow.evidence({"s1r1c0"}, ["a"])
    assert flow.pending() and published_items(state, final=True) == []


def test_research_status_renaming_and_unrelated_evidence_do_not_reset_progress():
    flow, state, research = prepared_flow()
    before = flow.signature()
    flow.entries[0]["status"] = "researching"
    flow.entries[0]["detail"] = "换一种说法"
    research.seen["unrelated"] = block() | {"content": "与当前待办无关"}
    assert flow.signature() == before
    flow.entries[0]["checked"] = []
    assert flow.signature() != before


def test_evidence_invalidation_alone_does_not_count_as_forward_progress():
    flow, state, research = prepared_flow()
    before = flow.signature()
    research.seen["new"] = block() | {"content": "没有补充实质条件的重复说明"}
    flow.evidence({"s1r1c0"}, ["a"])
    assert state["staged_items"][0]["review_status"] == "needs_review"
    assert flow.signature() == before


def test_completeness_response_defaults_are_normalized():
    from tender.application.analysis.completeness import review_completeness
    from tender.ports.llm.chat import Completion

    class Model:
        async def complete(self, prompt):
            return Completion(content=json.dumps({"issues": [{
                "topic": "a", "detail": "请核对附件二", "target": "附件二",
            }]}), model="offline")

    result = asyncio.run(review_completeness(Model(), {
        "topic": "a", "evidence_ids": [], "record_keys": [],
    }))
    assert result["issues"][0]["evidence_ids"] == []
    assert result["issues"][0]["record_keys"] == []


def test_deadline_settlement_still_checks_access_and_execution_ownership():
    from unittest.mock import Mock

    from tender.application.analysis.runtime import AgentRuntime
    from tender.ports.repository.analysis.reports import ReportRepository
    from tender.ports.repository.analysis.runtime import AgentRunStore

    _, state, _ = prepared_flow()
    state["staged_items_verified"] = False
    db = Mock(spec=ReportRepository)
    store = Mock(spec=AgentRunStore)
    db.agent_run_store.return_value = store
    db.accessible_report_status.return_value = "running"
    db.collections_for_project.return_value = set()
    db.sources.return_value = []
    runtime = AgentRuntime(db, {"id": 1, "project_id": 1}, {}, [])
    store.guard.side_effect = TimeoutError("已到期")
    runtime.finish("partial", "到期保留核实结果", state=state)
    store.guard.assert_not_called()
    store.guard_settlement.assert_called_once()
    assert len(store.finish.call_args.kwargs["publish"]["items"]) == 1
    assert store.finish.call_args.kwargs["state"] is state
    store.finish.reset_mock()
    db.accessible_report_status.return_value = "canceled"
    with pytest.raises(InterruptedError):
        runtime.finish("partial", state=state)
    store.finish.assert_not_called()
    db.accessible_report_status.return_value = "running"
    runtime.sources = [{"collection_id": 9}]
    with pytest.raises(PermissionError):
        runtime.finish("partial", state=state)
    runtime.sources = []
    store.guard_settlement.side_effect = InterruptedError("租约失效")
    with pytest.raises(InterruptedError, match="租约"):
        runtime.finish("partial", state=state)
    store.finish.assert_not_called()



def test_pending_scope_renames_and_duplicate_verified_keys_do_not_reset_progress():
    flow, state, _ = prepared_flow()
    before = flow.signature()
    duplicate = copy.deepcopy(state["staged_items"][0])
    duplicate["id"] = "another-id"
    duplicate["business"]["id"] = "another-id"
    duplicate["business"]["key"] = "another-key"
    duplicate["business"]["title"] = "改名"
    state["staged_items"].append(duplicate)
    assert flow.signature() == before
    entry = copy.deepcopy(flow.entries[0])
    entry["scope"] = {"kind": "lots", "lot_refs": ["虚构标段"]}
    flow.data["entries"]["renamed"] = entry
    assert flow.signature() == before


def test_lot_code_and_name_refer_to_same_required_scope():
    flow, state, _ = prepared_flow()
    state["topic_lots"] = [{"code": "A", "name": "第一标段"}]
    flow.entries[0]["scope"] = {"kind": "lots", "lot_refs": ["第一标段"]}
    assert not flow.pending()


def test_resolved_task_with_unverified_record_still_prevents_completion():
    flow, state, _ = prepared_flow()
    unverified = copy.deepcopy(state["staged_items"][0])
    unverified["id"] = "unverified"
    unverified["business"]["key"] = "unverified"
    unverified["verification"] = "unsupported"
    state["staged_items"].append(unverified)
    flow.apply([TopicUpdate.model_validate(update("a", ["warranty"], tasks=[{
        "detail": "核对例外", "status": "resolved", "record_keys": ["unverified"],
    }]))], {"warranty", "unverified"})
    assert flow.entries[0]["status"] != "ready" and flow.pending()



def test_audit_batches_keep_full_continuation_exceptions_and_scope_with_bounded_inputs():
    from tender.application.analysis.research import AgentLimits

    flow, state, research = prepared_flow()
    research.limits = AgentLimits(context_tokens=6000)
    text = "质保三年。" + "前文说明。" * 1000 + "清单续段：A标段易损件除外；B标段另按附件二。"
    research.seen["s1r1c0"]["content"] = text
    batches = flow.audit_batches([])
    pieces = [e["text"] for batch in batches for e in batch["evidence"]]
    assert len(batches) > 1 and "".join(pieces) == text
    assert "A标段易损件除外" in pieces[-1] and "附件二" in pieces[-1]
    assert all(len(json.dumps(batch, ensure_ascii=False)) <= 2400 for batch in batches)


def test_evidence_budget_exhaustion_stops_new_model_calls_and_retains_prior_result():
    from tender.application.analysis.agent import ResearchMiddleware

    async def run():
        flow, state, research = prepared_flow()
        flow.evidence({"s1r1c0"}, ["a"], {"budget_exhausted": True})
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)
        with pytest.raises(TopicIncomplete, match="证据额度"):
            await middleware.abefore_model({"messages": []}, None)
        assert len(published_items(state, final=True)) == 1

    asyncio.run(run())


@pytest.mark.parametrize("tool,args", [
    ("search_document", {"query": "质保"}),
    ("search_document", {"query": "质保", "topic_keys": ["不存在"]}),
    ("search_knowledge", {"query": "质保"}),
    ("search_knowledge", {"query": "质保", "topic_keys": ["不存在"]}),
    ("read_document", {"block_id": "s1r1c0"}),
    ("read_document", {"block_id": "s1r1c0", "topic_keys": ["不存在"]}),
])
def test_invalid_topic_arguments_are_corrected_without_aborting_module(tool, args):
    async def run():
        research = session([block()])
        state, _, router, _ = await execute([
            call(tool, args, "invalid"), search("a"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"])]}, "finish"),
        ], keys=("a",), research=research)
        feedback = [m["data"] for m in router.requests[1][0] if m["type"] == "tool"][-1]
        assert "tool_argument_invalid" in feedback["content"]
        assert "topic_keys" in feedback["content"]
        assert state["argument_failures"] == 1
        assert research.tool_calls == 1 and "draft" in state
        assert state.get("consecutive_tool_failures", 0) == 0

    asyncio.run(run())


@pytest.mark.parametrize("reference_only", [False, True])
def test_new_related_evidence_reopens_rejected_record_without_resetting_failure_budget(
    reference_only,
):
    async def run():
        research = session([block()])
        retrieve = research.retrieve
        reviewed = []

        async def additional_evidence(sources, query):
            if query == "补充依据":
                return [block() | {"block_id": "s1r1c1", "offset": 1,
                                   "content": "质保三年，含易损件"}], {"mode": "keyword"}
            return await retrieve(sources, query)

        async def review(items):
            reviewed.append(copy.deepcopy(items))
            if len(reviewed) <= 3:
                for item in items:
                    item.update(verification="unsupported", verification_issues=["依据不足"])
                    if reference_only:
                        item["verification_references"] = ["请补齐原文"]
            else:
                await accept(items)

        research.retrieve = additional_evidence
        rejected = submission([summary_record()], final=False) | {
            "topic_updates": [update("a", ["warranty"])]}
        corrected = summary_record(citations=[{"block_id": "s1r1c1", "quote": "质保三年"}])
        state, saved, _, _ = await execute([
            search("a"),
            *[call("submit_analysis", rejected, f"reject-{i}") for i in range(3)],
            search("a", "补充依据", "new-evidence"),
            call("submit_analysis", submission([corrected]) | {
                "topic_updates": [update("a", ["warranty"], evidence_ids=["s1r1c1"])]},
                 "corrected"),
        ], keys=("a",), research=research, review=review)
        item_id = reviewed[0][0]["id"]
        assert any(s.get("rejected_records", {}).get(item_id) for s in saved)
        assert len(reviewed) == 4 and item_id not in state["rejected_records"]
        assert all(batch[0]["id"] == item_id for batch in reviewed)
        ledger = state["reference_failures"] if reference_only else state["correction_failures"]
        assert ledger[item_id if reference_only else "record:" + item_id] == 3
        assert len(published_items(state, final=True)) == 1 and "draft" in state
        assert not any(g["key"] == "record:" + item_id for g in state["business_gaps"])
        assert not state.get("gap_notes")

    asyncio.run(run())


def test_only_new_related_evidence_reopens_rejections_including_absent_records_and_proofs():
    from tender.application.analysis.data import record_identity
    from tender.application.knowledge.content import fingerprint

    flow, state, research = prepared_flow(keys=("a", "b"))
    flow.apply([TopicUpdate.model_validate(update("b", status="researching"))], {"warranty"})
    item_id = state["staged_items"][0]["id"]
    proof_id = record_identity(state, "coverage:" + fingerprint(["b", COMMON]))
    state.update(staged_items=[], rejected_records={item_id: True, proof_id: True},
                 business_coverage=[{"topic": "b", "scope": COMMON, "status": "pending",
                                     "review_id": proof_id}])
    flow.evidence(set(research.seen), ["a"], {"already_read": ["s1r1c0"]})
    assert state["rejected_records"] == {item_id: True, proof_id: True}
    research.seen["new-a"] = block() | {"content": "补充质保要求"}
    flow.evidence({"s1r1c0"}, ["a"])
    assert state["rejected_records"] == {proof_id: True}
    # 同一原文首次归属另一主题也改变该主题的校验依据，但普通回读不能重开纠错。
    flow.evidence(set(research.seen), ["b"], {"already_read": ["new-a"]})
    assert state["rejected_records"] == {}


@pytest.mark.parametrize("final", [False, True])
def test_prevalidation_failure_preserves_valid_batch_items_and_tracks_failed_item(final):
    async def run():
        reviewed = []

        async def review(items):
            reviewed.append([i["business"]["key"] for i in items])
            await accept(items)

        task = "修正未通过预校验的事项：bad"
        state, saved, router, _ = await execute([
            search("a"),
            call("submit_analysis", submission([
                summary_record(key="bad", quote="原文中不存在的引文"),
                summary_record(key="good"),
            ], final=final) | {"topic_updates": [update("a", ["bad", "good"], tasks=[{
                "detail": "核对失败事项", "status": "resolved", "record_keys": ["bad"],
            }])]}, "mixed"),
            call("submit_analysis", submission([summary_record(key="bad")]) | {
                "topic_updates": [update("a", ["bad", "good"], tasks=[
                    {"detail": task, "status": "resolved", "record_keys": ["bad"]},
                    {"detail": "核对失败事项", "status": "resolved", "record_keys": ["bad"]},
                ])]}, "corrected"),
        ], keys=("a",), review=review)
        early = next(s for s in saved if published_items(s))
        assert [i["business"]["key"] for i in published_items(early)] == ["good"]
        progress = next(iter(early["topic_flow"]["entries"].values()))
        assert progress["status"] != "ready"
        assert {t["detail"] for t in progress["tasks"].values()
                if t["status"] == "pending"} == {task, "核对失败事项"}
        assert reviewed == [["good"], ["bad"]]
        feedback = [m["data"] for m in router.requests[2][0] if m["type"] == "tool"][-1]
        assert "bad" in feedback["content"]
        assert len(state["draft"]["fields"]) == 2

    asyncio.run(run())
