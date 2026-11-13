"""精简协议的行为边界：稳定身份、显式证据处理及按需读取。"""

import copy

import pytest
from test_analysis_research_first import researched_flow

from tender.application.analysis.protocol import ResearchDelta, ResearchLedger


def ledger():
    flow, state, research = researched_flow()
    flow.data["protocol"] = "research-v2"
    return ResearchLedger(flow), flow, state, research


def test_lightweight_discovery_uses_server_work_id_and_preserves_original():
    book, flow, _, research = ledger()
    work = book.works()[0]
    book.update(
        [
            ResearchDelta(
                work_ids=[work["id"]],
                detail="质保三年",
                evidence_ids=["s1r1c0"],
                scope={"kind": "common", "lot_refs": []},
            )
        ]
    )
    assert not flow.researching
    assert book.works()[0]["id"] == work["id"]
    assert research.seen["s1r1c0"]["content"]
    assert "质保三年" not in flow.prompt()
    assert "质保三年" in str(book.context([work["id"]]))


def test_invalid_batch_is_atomic_and_does_not_clear_unexamined_evidence():
    book, flow, state, _ = ledger()
    work = book.works()[0]
    before = copy.deepcopy(state)
    with pytest.raises(ValueError):
        book.update([ResearchDelta(work_ids=[work["id"]], detail="已核对", evidence_ids=["fake"])])
    assert state == before
    book.update(
        [
            ResearchDelta(
                work_ids=[work["id"]],
                detail="目前只看到标题",
                status="examined",
                evidence_ids=["s1r1c0"],
            )
        ]
    )
    assert flow.researching
    assert not flow.entries[0].get("findings")


@pytest.mark.parametrize("scope", [
    {"kind": "common", "lot_refs": []},
    {"kind": "lots", "lot_refs": ["A标段"]},
])
def test_known_scope_notes_preserve_coexisting_unknown_drafts_after_restore(scope):
    import json

    from synthesis_fixtures import summary_record

    from tender.application.analysis.data import BusinessRecord, prepare_records
    from tender.application.analysis.topic_flow import TopicFlow, TopicUpdate, identity

    book, flow, state, research = ledger()
    flow.data["protocol"] = "research-v3"
    research.seen["s1r1c0"]["content"] = "A标段质保三年"
    unknown = {"kind": "unknown", "lot_refs": []}
    state["staged_items"] = prepare_records([
        BusinessRecord.model_validate(summary_record(key=key, scope=value) | {"text": "质保三年"})
        for key, value in (("unconfirmed", unknown), ("confirmed", scope))
    ], state, research.seen, "project_basic_info_parsing")
    flow.apply([
        TopicUpdate(topic="a", scope=unknown, record_keys=["unconfirmed"]),
        TopicUpdate(topic="a", scope=scope, record_keys=["confirmed"]),
    ], {"unconfirmed", "confirmed"})
    book.works()
    state = json.loads(json.dumps(state))
    flow = TopicFlow(state, research)
    book = ResearchLedger(flow)
    work_id = next(w["id"] for w in book.works() if w["scope"] == scope)
    before = copy.deepcopy(flow.data["entries"][identity("a", unknown)])
    items = copy.deepcopy(state["staged_items"])
    book.update([ResearchDelta(work_ids=[work_id], detail="已核对当前范围的质保期限",
                               evidence_ids=["s1r1c0"])])
    assert flow.data["entries"][identity("a", unknown)] == before
    assert flow.data["entries"][identity("a", scope)]["record_keys"] == ["confirmed"]
    assert state["staged_items"] == items
    assert next(w for w in book.works() if w["id"] == work_id)["status"] == "found"
    assert flow.researching


def test_one_real_query_can_record_not_found_without_claiming_absence():
    book, flow, _, research = ledger()
    work = book.works()[0]
    flow.data["research_searches"] = {
        "a": {"q": {"query": "质保", "source_ids": [1], "has_more": False, "limited": False}}
    }
    book.update(
        [
            ResearchDelta(
                work_ids=[work["id"]],
                status="not_found",
                detail="本次已检索项目资料未找到",
                scope={"kind": "common", "lot_refs": []},
                evidence_ids=["s1r1c0"],
            )
        ]
    )
    assert not flow.researching
    assert flow.state["business_gaps"]
    assert not flow.state.get("staged_items")
    assert research.seen


def test_context_pagination_never_silently_drops_remaining_evidence():
    book, _, _, research = ledger()
    research.seen["s1r1c0"]["content"] = "长原文" * 5000
    result = book.context([book.works()[0]["id"]], limit=1000)
    assert result["has_more"] and result["next_offset"] > 0
    assert len(str(result)) < 6000


def test_reopening_a_finished_check_preserves_identity_and_execution_budget():
    book, flow, state, _ = ledger()
    work_id = book.works()[0]["id"]
    book.update(
        [
            ResearchDelta(
                work_ids=[work_id],
                detail="质保三年",
                evidence_ids=["s1r1c0"],
                scope={"kind": "common", "lot_refs": []},
            )
        ]
    )
    state["model_recovery_attempts"] = 2
    book.update([ResearchDelta(work_ids=[work_id], detail="核对补遗例外", status="reopen")])
    assert flow.researching
    assert book.works()[0]["id"] == work_id
    assert state["model_recovery_attempts"] == 2


@pytest.mark.parametrize("status", ["blocked", "missing_source"])
def test_blocked_check_revokes_old_finding_and_published_review(status):
    book, flow, state, _ = ledger()
    work_id = book.works()[0]["id"]
    book.update(
        [
            ResearchDelta(
                work_ids=[work_id],
                detail="质保三年",
                evidence_ids=["s1r1c0"],
                scope={"kind": "common", "lot_refs": []},
            )
        ]
    )
    state["staged_items"] = [
        {
            "id": "old",
            "business": {"key": "old", "scope": {"kind": "common", "lot_refs": []}},
            "verification": "supported",
            "review_status": "current",
        }
    ]
    flow.entries[0]["record_keys"] = ["old"]
    flow.data["audit"]["record_topics"] = {"old": ["a"]}
    book.update([ResearchDelta(work_ids=[work_id], detail="补遗附件缺失", status=status)])
    assert not flow.entries[0]["findings"]
    assert flow.entries[0]["status"] == "blocked"
    assert book.works()[0]["status"] == "blocked"
    assert state["staged_items"][0]["review_status"] == "needs_review"
    assert "old" not in flow.data["audit"]["record_topics"]


def test_explicit_scope_replacement_preserves_work_identity_without_retired_gap():
    book, flow, _, _ = ledger()
    work_id = book.works()[0]["id"]
    old = {"kind": "common", "lot_refs": []}
    book.update(
        [ResearchDelta(work_ids=[work_id], detail="质保三年", evidence_ids=["s1r1c0"], scope=old)]
    )
    new = {"kind": "lots", "lot_refs": ["A标段"]}
    book.update(
        [
            ResearchDelta(
                work_ids=[work_id],
                detail="补遗明确仅适用A标段",
                evidence_ids=["s1r1c0"],
                scope=new,
                replaces_scopes=[old],
            )
        ]
    )
    assert len(flow.entries) == 1 and flow.entries[0]["scope"] == new
    assert book.works()[0]["id"] == work_id
    assert not flow.researching


def test_record_cannot_use_another_scopes_work_even_when_both_scopes_exist():
    book, _, _, _ = ledger()
    work_id = book.works()[0]["id"]
    for scope in ({"kind": "common", "lot_refs": []}, {"kind": "lots", "lot_refs": ["A标段"]}):
        book.update([ResearchDelta(work_ids=[work_id], detail="核对范围内质保",
                                  evidence_ids=["s1r1c0"], scope=scope)])
    record = {"business": {"key": "a-only", "scope": {"kind": "lots", "lot_refs": ["A标段"]}}}
    with pytest.raises(ValueError, match="相同已确认范围"):
        book.record_updates([record], [work_id])


def test_explicit_research_scope_confirmation_revokes_initial_synthesis_origin():
    book, _, _, _ = ledger()
    book.finish("已有依据充分，先综合未知范围内的内容")
    work_id = next(iter(book.submission_works()))
    book.update([ResearchDelta(
        work_ids=[work_id], detail="重新核对后明确仅适用A标段", evidence_ids=["s1r1c0"],
        scope={"kind": "lots", "lot_refs": ["A标段"]},
    )])
    record = {"business": {"key": "b-only", "scope": {"kind": "lots", "lot_refs": ["B标段"]}}}
    with pytest.raises(ValueError, match="相同已确认范围"):
        book.record_updates([record], [work_id])


def test_pending_drafts_advance_only_synthesis_and_duplicate_claims_do_not_renew_budget():
    from synthesis_fixtures import summary_record

    from tender.application.analysis.data import BusinessRecord, prepare_records

    book, flow, state, research = ledger()
    book.update([ResearchDelta(
        work_ids=[book.works()[0]["id"]], detail="质保三年", evidence_ids=["s1r1c0"],
        scope={"kind": "common", "lot_refs": []},
    )])
    before = flow.signature()
    prepared = prepare_records([
        BusinessRecord.model_validate(summary_record() | {"text": "质保三年"}),
    ], state, research.seen, "project_basic_info_parsing")
    prepared[0]["verification"] = "pending"
    state["staged_items"] = prepared
    progress = flow.signature()
    assert progress != before
    duplicate = copy.deepcopy(prepared[0])
    duplicate["business"].update(key="renamed", title="新的展示名称")
    state["staged_items"].append(duplicate)
    research.seen["unrelated"] = {"content": "无关原文"}
    assert flow.signature() == progress
    prepared[0]["review_status"] = "needs_review"
    assert flow.signature() == progress
    prepared[0]["business"]["conditions"] = {"expression": "自验收合格起"}
    assert flow.signature() != progress
    flow.data["phase"] = "research"
    assert flow.signature() == before
