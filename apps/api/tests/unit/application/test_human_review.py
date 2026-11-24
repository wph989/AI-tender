"""核对人工裁定投影能阻断未确认事项和其依赖。"""

import pytest

from tender.application.analysis.data import ContextInput, build_context
from tender.application.analysis.human_review import RecordReviewInput, reviewed_compilation


def record(record_id: str, kind: str = "requirement", **values):
    return {
        "id": record_id, "module_key": "module-a", "kind": kind, "title": record_id,
        "text": "机器抽取正文", "scope": {"kind": "common", "lot_refs": []},
        "citations": [{"block_id": "block-a"}], "review_status": "current",
        "human_review_status": "pending", "content": {"原字段": "原值"}, **values,
    }


def test_pending_records_are_withheld():
    target = record("requirement-a")
    data = {
        "gaps": [],
        "lots": [], "facts": [], "requirements": [target], "format_nodes": [], "relations": [],
    }
    result = reviewed_compilation(data)
    assert result["requirements"] == []
    assert {gap["code"] for gap in result["gaps"]} == {"human_review_required"}


def test_machine_self_check_does_not_confirm_a_human_review():
    target = record("requirement-a", human_review_status="pending")
    data = {
        "quality_status": "self_check_passed", "gaps": [], "lots": [],
        "facts": [], "requirements": [target], "format_nodes": [], "relations": [],
    }

    result = reviewed_compilation(data)

    assert result["requirements"] == []
    assert result["gaps"][0]["code"] == "human_review_required"


def test_corrected_record_retains_original_citation_but_drops_machine_structure():
    target = record("requirement-a", human_review_status="corrected", human_review={
        "decision": "corrected", "corrected_text": "人工修正正文",
    })
    data = {"gaps": [], "lots": [], "facts": [], "requirements": [target],
            "format_nodes": [], "relations": []}
    result = reviewed_compilation(data)
    assert result["requirements"][0]["text"] == "人工修正正文"
    assert result["requirements"][0]["citations"] == target["citations"]
    assert result["requirements"][0]["structuring"] == "partial"
    assert result["requirements"][0]["content"] == {}


def test_unconfirmed_parent_and_relation_endpoints_do_not_reach_compilation():
    parent = record("parent-a", "format_node")
    child = record("child-a", "format_node", parent_id="parent-a")
    relation = record("relation-a", "relation", subject_id="child-a", object_id="fact-a")
    data = {"gaps": [], "lots": [], "facts": [record("fact-a")],
            "requirements": [], "format_nodes": [parent, child], "relations": [relation]}
    result = reviewed_compilation(data)
    assert result["format_nodes"] == []
    assert result["relations"] == []
    assert any(gap["detail"] == "事项尚未获人工确认" for gap in result["gaps"])


def test_review_input_requires_reason_for_correction_and_rejection():
    values = {"snapshot_id": 1, "record_id": "r1", "previous_review_id": None,
              "decision": "rejected"}
    try:
        RecordReviewInput(**values)
    except ValueError as exc:
        assert "理由" in str(exc)
    else:
        raise AssertionError("驳回没有理由必须失败")


@pytest.mark.parametrize("decision", ["pending", "rejected", "confirmed"])
@pytest.mark.parametrize("predicate", ["supersedes", "conflicts"])
def test_only_confirmed_relations_change_the_requirement_manifest(decision, predicate):
    subject = record("new", human_review_status="confirmed")
    scope = subject["scope"]
    flag = "superseded_in" if predicate == "supersedes" else "conflicts_in"
    target = record("old", human_review_status="confirmed", **{flag: [scope]})
    if predicate == "conflicts":
        subject[flag] = [scope]
    relation = record("rel", "relation", human_review_status=decision, predicate=predicate,
                      subject_id=subject["id"], object_id=target["id"])
    data = {"gaps": [{"code": "conflict", "scope": scope, "record_id": "rel"}]
            if predicate == "conflicts" else [], "lots": [], "facts": [],
            "requirements": [subject, target], "format_nodes": [], "relations": [relation]}
    context = build_context(
        reviewed_compilation(data), ContextInput(snapshot_id=1, purpose="check"),
    )
    expected = (["new", "old"] if decision != "confirmed"
                else ["new"] if predicate == "supersedes" else [])
    assert context["requirement_manifest"] == expected
    assert any(g["code"] == "conflict" for g in context["gaps"]) == (
        decision == "confirmed" and predicate == "conflicts"
    )
    assert target[flag] == [scope]


def test_corrected_endpoint_invalidates_confirmed_relation():
    target = record("old", human_review_status="corrected",
                    human_review={"corrected_text": "已核实的正文"})
    subject = record("new", human_review_status="confirmed")
    relation = record("rel", "relation", human_review_status="confirmed", predicate="supersedes",
                      subject_id="new", object_id="old", object_text=target["text"])
    data = {"gaps": [], "lots": [], "facts": [], "format_nodes": [],
            "requirements": [subject, target], "relations": [relation]}
    result = reviewed_compilation(data)
    assert result["relations"] == []
    assert "superseded_in" not in result["requirements"][1]
    assert result["gaps"][0]["code"] == "unresolved_relation"
