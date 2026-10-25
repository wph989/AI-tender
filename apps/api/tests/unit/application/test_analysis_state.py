"""业务阶段转换在保存/恢复后保持一致，尤其不能借用旧 final 或重置预算。"""

import json

from tender.application.analysis.state import AnalysisTransitions


def test_evidence_change_invalidates_results_but_preserves_budget_and_replay():
    snapshot = {
        "research_completed": {"evidence_ids": ["one"]},
        "staged_items": [{"id": "fact", "verification": "supported"}],
        "draft": {"fields": ["old"]}, "pending_final": {"research_summary": "old"},
        "research": {"seen": {"one": {}, "two": {}}},
        "model_calls": 7, "tool_results": {"call": "cached"}, "subagent_retries": 2,
    }
    transitions = AnalysisTransitions(snapshot)
    transitions.evidence_changed()
    restored = AnalysisTransitions(json.loads(json.dumps(snapshot)))
    assert restored.phase == "research"
    assert not snapshot.get("draft") and not snapshot.get("pending_final")
    assert snapshot["staged_items"] == []
    assert snapshot["model_calls"] == 7 and snapshot["subagent_retries"] == 2
    assert snapshot["tool_results"] == {"call": "cached"}
    assert set(snapshot["research"]["seen"]) == {"one", "two"}


def test_submission_review_and_final_intent_survive_checkpoint_round_trip():
    snapshot = {}
    transitions = AnalysisTransitions(snapshot)
    transitions.research_completed({"evidence_ids": ["one"]})
    assert transitions.phase == "synthesis"
    transitions.replace_items([{"id": "fact", "verification": "pending"}])
    transitions.request_final("本轮完成", None)
    transitions = AnalysisTransitions(json.loads(json.dumps(snapshot)))
    assert transitions.phase == "verification"
    assert "business_gaps" not in transitions.take_final()
    assert transitions.take_final() is None
    transitions.replace_items([{"id": "fact", "verification": "supported"}])
    transitions.mark_verified()
    assert transitions.phase == "synthesis"
    transitions.request_final("重新确认", [])
    assert transitions.take_final()["business_gaps"] == []
    transitions.publish_draft({"fields": [{"id": "fact"}]})
    assert transitions.phase == "completed"


def test_abandoned_rewrite_restores_verified_item_without_endorsing_new_coverage():
    snapshot = {
        "staged_items": [{"id": "proof", "verification": "pending",
                          "business": {"kind": "coverage"}}],
        "business_previous": {"proof": {"id": "proof", "verification": "supported"}},
        "business_coverage": [{"review_id": "proof", "status": "not_applicable"}],
    }
    AnalysisTransitions(snapshot).drop_pending({"proof"})
    assert snapshot["staged_items"] == [snapshot["business_previous"]["proof"]]
    assert snapshot["business_coverage"][0]["status"] == "pending"
