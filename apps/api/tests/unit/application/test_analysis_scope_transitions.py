"""范围确认及修订必须能收敛，同时保留未解决事项和真实并存范围。"""

import asyncio
import copy

import pytest
from synthesis_fixtures import COMMON, accept, submission, summary_record
from test_analysis_research import block, session
from test_analysis_topic_flow import execute, prepared_flow, search, update
from test_deep_analysis import KEY, call

from tender.application.analysis.data import CoverageInput, prepare_coverage
from tender.application.analysis.state import published_items
from tender.application.analysis.topic_flow import TopicFlow, TopicUpdate

UNKNOWN = {"kind": "unknown", "lot_refs": []}
LOT_A = {"kind": "lots", "lot_refs": ["A标段"]}
LOT_B = {"kind": "lots", "lot_refs": ["B标段"]}


def test_unknown_scope_confirmation_preserves_and_resolves_tasks_and_references_in_graph():
    async def run():
        trace = {"topic": "a", "from_block_id": "s1r1c0", "target": "质保细则",
                 "status": "missing", "evidence_ids": []}
        state, saved, router, audited = await execute([
            search("a"),
            call("submit_analysis", submission(final=False) | {"topic_updates": [update(
                "a", scope=UNKNOWN, status="researching", checked=[],
                tasks=[{"detail": "核对起算条件", "status": "pending"}], references=[trace],
            )]}, "unknown"),
            call("submit_analysis", submission([summary_record()]) | {"topic_updates": [update(
                "a", ["warranty"], tasks=[{"detail": "核对起算条件", "status": "resolved",
                                           "record_keys": ["warranty"]}],
                references=[trace | {"status": "resolved", "evidence_ids": ["s1r1c0"]}],
            )]}, "confirmed"),
        ], keys=("a",))
        assert any(any(e["scope"] == UNKNOWN and e["tasks"]
                       for e in s["topic_flow"]["entries"].values()) for s in saved)
        restored = TopicFlow(copy.deepcopy(state), session([block()]))
        assert len(restored.entries) == 1 and restored.entries[0]["scope"] == COMMON
        assert len(restored.entries[0]["tasks"]) == len(restored.entries[0]["references"]) == 1
        assert len(router.requests) == 3 and len(audited) == 1
        assert len(state["draft"]["fields"]) == 1

    asyncio.run(run())


def test_confirming_scope_does_not_drop_pending_work_or_reuse_unknown_checks():
    flow, state, research = prepared_flow()
    state["topic_flow"]["entries"] = {}
    flow = TopicFlow(state, research)
    flow.apply([TopicUpdate.model_validate(update(
        "a", scope=UNKNOWN, status="researching", tasks=[{"detail": "核对例外"}],
        references=[{"topic": "a", "from_block_id": "s1r1c0", "target": "附件二",
                     "status": "missing"}],
    ))], {"warranty"})
    flow.apply([TopicUpdate.model_validate(update("a", ["warranty"], checked=[]))], {"warranty"})
    assert len(flow.entries) == 1 and flow.entries[0]["scope"] == COMMON
    assert flow.entries[0]["checked"] == [] and flow.pending()
    assert next(iter(flow.entries[0]["tasks"].values()))["status"] == "pending"
    assert flow.entries[0]["references"][0]["status"] == "missing"


def test_scope_revision_is_reverified_and_finishes_without_old_scope_in_graph():
    async def run():
        research = session([block()])
        retrieve = research.retrieve
        reviewed = []

        async def amendment(sources, query):
            if query == "适用范围":
                return [block() | {"block_id": "s1r1c1", "offset": 1,
                                   "content": "仅适用A标段，质保三年"}], {}
            return await retrieve(sources, query)

        async def review(items):
            reviewed.append(copy.deepcopy(items))
            await accept(items)

        research.retrieve = amendment
        revised = summary_record(scope=LOT_A, citations=[{
            "block_id": "s1r1c1", "quote": "仅适用A标段，质保三年",
        }])
        state, _, router, _ = await execute([
            search("a"),
            call("submit_analysis", submission([summary_record()], final=False) | {
                "topic_updates": [update("a", ["warranty"], checked=[])]}, "initial"),
            search("a", "适用范围", "amendment"),
            call("submit_analysis", submission([revised]) | {"topic_updates": [update(
                "a", ["warranty"], scope=LOT_A, replaces_scopes=[COMMON],
                evidence_ids=["s1r1c1"],
            )]}, "revision"),
        ], keys=("a",), research=research, review=review)
        entries = list(state["topic_flow"]["entries"].values())
        assert len(entries) == 1 and entries[0]["scope"] == LOT_A
        assert set(entries[0]["evidence_ids"]) == {"s1r1c0", "s1r1c1"}
        assert len(reviewed) == 2 and reviewed[0][0]["id"] == reviewed[1][0]["id"]
        assert len(router.requests) == 4
        assert state["draft"]["fields"][0]["business"]["scope"] == LOT_A

    asyncio.run(run())


def test_scope_replacement_preserves_coexisting_lot_and_replay_budget():
    flow, state, research = prepared_flow()
    other = copy.deepcopy(state["staged_items"][0])
    other.update(id="other-lot")
    other["business"].update(key="other-lot", scope=LOT_B)
    state["staged_items"].append(other)
    flow.apply([TopicUpdate.model_validate(update("a", ["other-lot"], scope=LOT_B))],
               {"warranty", "other-lot"})
    state["model_calls"] = 12
    state["correction_failures"] = {"record:test": 2}
    state["staged_items"][0]["business"]["scope"] = LOT_A
    revision = TopicUpdate.model_validate(update(
        "a", ["warranty"], scope=LOT_A, replaces_scopes=[COMMON],
    ))
    flow.apply([revision], {"warranty", "other-lot"})
    assert flow.pending() and not any(i["business"]["key"] == "warranty"
                                      for i in published_items(state, final=True))
    state["staged_items"][0]["review_status"] = "current"
    restored = TopicFlow(copy.deepcopy(state), research)
    restored.apply([revision], {"warranty", "other-lot"})
    assert {e["scope"]["lot_refs"][0] for e in restored.entries} == {"A标段", "B标段"}
    assert all(e["status"] == "ready" for e in restored.entries) and not restored.pending()
    assert restored.state["model_calls"] == 12
    assert restored.state["correction_failures"] == {"record:test": 2}


def test_replacing_scope_can_split_records_while_retaining_common_requirements():
    flow, state, _ = prepared_flow()
    spare = copy.deepcopy(state["staged_items"][0])
    spare.update(id="spare")
    spare["business"]["key"] = "spare"
    state["staged_items"].append(spare)
    flow.apply([TopicUpdate.model_validate(update("a", ["warranty", "spare"]))],
               {"warranty", "spare"})
    state["staged_items"][0]["business"]["scope"] = LOT_A
    flow.apply([
        TopicUpdate.model_validate(update(
            "a", ["warranty"], scope=LOT_A, replaces_scopes=[COMMON],
        )),
        TopicUpdate.model_validate(update("a", ["spare"])),
    ], {"warranty", "spare"})
    common = next(e for e in flow.entries if e["scope"] == COMMON)
    assert common["record_keys"] == ["spare"] and common["status"] == "ready"
    assert state["staged_items"][1].get("review_status") != "needs_review"
    state["staged_items"][0]["review_status"] = "current"
    assert not flow.pending()


def test_one_scope_can_split_into_two_lots_without_losing_unresolved_work():
    flow, state, _ = prepared_flow()
    second = copy.deepcopy(state["staged_items"][0])
    second.update(id="lot-b")
    second["business"].update(key="lot-b", scope=LOT_B)
    state["staged_items"].append(second)
    flow.apply([TopicUpdate.model_validate(update("a", ["warranty", "lot-b"],
                                                 tasks=[{"detail": "核对例外"}]))],
               {"warranty", "lot-b"})
    state["staged_items"][0]["business"]["scope"] = LOT_A
    flow.apply([TopicUpdate.model_validate(update(
        "a", [key], scope=scope, replaces_scopes=[COMMON],
    )) for key, scope in (("warranty", LOT_A), ("lot-b", LOT_B))], {"warranty", "lot-b"})
    assert len(flow.entries) == 2 and flow.pending()
    assert {tuple(e["record_keys"]) for e in flow.entries} == {("warranty",), ("lot-b",)}
    assert all(next(iter(e["tasks"].values()))["status"] == "pending" for e in flow.entries)
    assert all(e["evidence_ids"] == ["s1r1c0"] for e in flow.entries)


@pytest.mark.parametrize("problem", [
    "missing_record", "unknown_source", "invalid_evidence", "self", "cycle",
])
def test_invalid_scope_replacement_preserves_original_state(problem):
    flow, state, _ = prepared_flow()
    args = update("a", ["warranty"], scope=LOT_A, replaces_scopes=[COMMON])
    if problem == "missing_record":
        args["record_keys"] = []
    elif problem == "unknown_source":
        args["replaces_scopes"] = [LOT_B]
    elif problem == "invalid_evidence":
        args["evidence_ids"] = ["unread"]
    elif problem == "self":
        args["scope"] = COMMON
    elif problem == "cycle":
        flow.apply([TopicUpdate.model_validate(update("a", scope=LOT_A, checked=[]))],
                   {"warranty"})
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        updates = [TopicUpdate.model_validate(args)]
        if problem == "cycle":
            updates.append(TopicUpdate.model_validate(update(
                "a", ["warranty"], replaces_scopes=[LOT_A],
            )))
        flow.apply(updates, {"warranty"})
    assert state == before


def test_retired_scope_proof_does_not_prove_new_scope_or_block_its_new_proof():
    flow, state, research = prepared_flow()
    proofs, items = prepare_coverage([CoverageInput.model_validate({
        "topic": "a", "scope": COMMON, "status": "not_applicable", "detail": "该条不适用",
        "citations": [{"block_id": "s1r1c0", "quote": "质保三年"}],
    })], state, research.seen, state["business_topics"], KEY)
    items[0]["verification"] = "supported"
    state.update(staged_items=items, business_coverage=proofs)
    flow.entries[0]["record_keys"] = []
    flow.sync()
    old_id = items[0]["id"]
    flow.apply([TopicUpdate.model_validate(update(
        "a", scope=LOT_A, replaces_scopes=[COMMON],
    ))], set())
    assert flow.pending() and not published_items(state, final=True)
    assert all(c["scope"] != COMMON for c in state["business_coverage"])
    assert old_id not in state.get("business_previous", {})
    coverage, pending = prepare_coverage([CoverageInput.model_validate({
        **{k: v for k, v in proofs[0].items() if k != "review_id"}, "scope": LOT_A,
    } | {"citations": [{"block_id": "s1r1c0", "quote": "质保三年"}]})],
        state, research.seen, state["business_topics"], KEY)
    state.update(staged_items=pending, business_coverage=coverage)
    assert flow.pending()
    pending[0]["verification"] = "supported"
    assert not flow.pending()


def test_scope_replacement_with_bad_record_keeps_valid_items_and_waits_for_correction():
    async def run():
        bad = summary_record(scope=LOT_A, quote="不存在的引文")
        state, saved, _, _ = await execute([
            search("a"),
            call("submit_analysis", submission([summary_record()], final=False) | {
                "topic_updates": [update("a", ["warranty"], checked=[])]}, "initial"),
            call("submit_analysis", submission([
                bad, summary_record(key="other"),
            ], final=False) | {"topic_updates": [
                update("a", ["warranty"], scope=LOT_A, replaces_scopes=[COMMON]),
                update("a", ["other"], checked=[]),
            ]}, "mixed"),
            call("submit_analysis", submission([summary_record(scope=LOT_A)]) | {
                "topic_updates": [update(
                    "a", ["warranty"], scope=LOT_A, replaces_scopes=[COMMON], tasks=[{
                        "detail": "修正未通过预校验的事项：warranty", "status": "resolved",
                        "record_keys": ["warranty"],
                    }],
                ), update("a", ["other"])]}, "corrected"),
        ], keys=("a",))
        assert any({i["business"]["key"] for i in published_items(s)} == {"warranty", "other"}
                   and any(e["scope"] == COMMON for e in s["topic_flow"]["entries"].values())
                   for s in saved)
        assert len(state["draft"]["fields"]) == 2

    asyncio.run(run())
