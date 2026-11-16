"""草稿、自查与最终发布是数据契约，不依赖程序安排工作阶段。"""

import copy

import pytest
from test_analysis_research import block
from test_analysis_v3 import KEY, raw, schema

from tender.application.analysis.drafts import DraftWorkspace
from tender.application.analysis.state import published_items
from tender.application.shared.validation import InputError


def workspace(state=None):
    state = state if state is not None else {"output_schema": schema()}
    return DraftWorkspace(state, {"s1r1c0": block()}, KEY)


def saved(book, **changes):
    return book.save_records([raw(**changes)], "draft-1")["accepted"][0]


def approve(book, receipt):
    return book.record_review(
        [
            {
                "record_id": receipt["id"],
                "version": receipt["version"],
                "status": "passed",
                "reason": "已对照项目条款核对质保期限与适用范围",
                "block_ids": ["s1r1c0"],
            }
        ],
        [],
        f"review:{receipt['id']}:{receipt['version']}",
    )


def test_draft_and_review_never_publish_before_explicit_final():
    book = workspace()
    row = saved(book)
    assert published_items(book.state, final=True) == []
    approve(book, row)
    assert published_items(book.state, final=True) == []
    book.finalize([row["id"]], "已核对质保要求")
    assert len(published_items(book.state, final=True)) == 1
    assert book.state["draft"]["business_data"]["records"][0]["content"] == raw()["content"]


def test_missing_and_stale_review_rejected_then_same_agent_can_correct():
    book = workspace()
    row = saved(book)
    with pytest.raises(InputError, match="自查"):
        book.finalize([row["id"]], "完成")
    approve(book, row)
    changed = book.save_records(
        [raw(id=row["id"], version=1, content={"字段": "质保", "内容": "五年"})], "draft-2"
    )["accepted"][0]
    assert changed["version"] == 2
    with pytest.raises(InputError, match="自查"):
        book.finalize([row["id"]], "完成")
    approve(book, changed)
    book.finalize([row["id"]], "完成")


def test_restored_replay_and_identical_resubmission_keep_identity_and_version():
    book = workspace()
    row = saved(book)
    restored = workspace(copy.deepcopy(book.state))
    assert saved(restored) == row
    duplicate = restored.save_records([raw()], "another-call")["accepted"][0]
    assert duplicate["id"] == row["id"] and duplicate["version"] == 1
    approve(restored, row)
    restored.finalize([row["id"]], "完成")


def test_bad_record_does_not_erase_valid_record_or_publish_it():
    book = workspace()
    result = book.save_records([raw(block_ids=["unknown"]), raw()], "batch")
    assert len(result["accepted"]) == len(result["rejected"]) == 1
    assert result["rejected"][0]["index"] == 0
    assert published_items(book.state) == []


def test_open_record_error_blocks_final_until_explicit_resolution():
    book = workspace()
    row = saved(book)
    result = book.record_review(
        [],
        [
            {
                "topic": "a",
                "target": "质保期限",
                "detail": "起算点尚未核清",
                "record_ids": [row["id"]],
                "action": "repair",
                "block_ids": ["s1r1c0"],
            }
        ],
        "problem",
    )
    issue_id = result["issues"][0]["id"]
    approve(book, row)
    with pytest.raises(InputError, match="未解决"):
        book.finalize([row["id"]], "完成")
    book.record_review(
        [], [{"id": issue_id, "status": "resolved", "detail": "已对照原文确认起算条件"}], "resolved"
    )
    book.finalize([row["id"]], "完成")


def test_dependency_change_invalidates_review_but_unrelated_evidence_does_not():
    book = workspace()
    parent = saved(book, kind="requirement")
    child = book.save_records(
        [
            raw(
                kind="requirement",
                requirement_keys=[parent["id"]],
                content={"字段": "质保材料", "内容": "提交承诺函"},
            )
        ],
        "child",
    )["accepted"][0]
    approve(book, parent)
    approve(book, child)
    book.seen["s2r1c0"] = block(2)
    assert book.review_current(child["id"])
    book.save_records(
        [
            raw(
                id=parent["id"],
                version=1,
                kind="requirement",
                content={"字段": "质保", "内容": "五年"},
            )
        ],
        "edit-parent",
    )
    assert not book.review_current(child["id"])
    with pytest.raises(InputError, match="自查"):
        book.finalize([parent["id"], child["id"]], "完成")


def test_missing_attachment_survives_final_with_independent_correct_record():
    book = workspace()
    row = saved(book)
    approve(book, row)
    book.record_review(
        [],
        [
            {
                "topic": "a",
                "target": "商务规范书",
                "detail": "目录和转引已核清，附件未提供",
                "record_ids": [],
                "block_ids": ["s1r1c0"],
                "action": "provide_input",
                "missing_input": {
                    "file_name": "商务规范书",
                    "reference_ids": ["s1r1c0"],
                    "checked_source_ids": [1],
                },
            }
        ],
        "missing",
    )
    book.finalize([row["id"]], "质保有依据，附件待补")
    assert book.state["quality_status"] == "needs_input"
    assert (
        book.state["draft"]["business_data"]["quality_issues"][0]["missing_input"]["file_name"]
        == "商务规范书"
    )


def test_deleted_mistake_can_be_closed_and_does_not_return_in_final():
    book = workspace()
    row = saved(book)
    issue = book.record_review(
        [],
        [
            {
                "topic": "a",
                "target": "旧模板",
                "detail": "误用旧模板",
                "record_ids": [row["id"]],
                "action": "repair",
            }
        ],
        "bad",
    )["issues"][0]
    book.save_records([], "delete", [row["id"]])
    book.record_review(
        [], [{"id": issue["id"], "status": "resolved", "detail": "已删除误用条目"}], "close"
    )
    book.finalize([], "当前材料未规定质保要求")
    assert book.state["draft"]["fields"] == []
    assert any(event["event"] == "delete" for event in book.book["history"])


def test_runtime_does_not_project_drafts_even_after_final_tool_before_commit():
    from tender.application.analysis.runtime import AgentRuntime

    book = workspace()
    row = saved(book)
    approve(book, row)
    assert AgentRuntime._staged_payload(book.state, include_relations=True) is None

    book.finalize([row["id"]], "完成")
    assert AgentRuntime._staged_payload(book.state, include_relations=True) is None


def test_new_attempt_call_ids_cannot_overwrite_previous_drafts():
    from tender.application.analysis.drafts import resume_workspace

    book = workspace()
    first = saved(book)
    restored = workspace(resume_workspace(book.state))
    second = saved(restored, content={"字段": "交货", "内容": "十日内"})
    assert first["id"] != second["id"]
    assert len(restored.items()) == 2


def test_review_issue_reference_blocks_final_even_without_reverse_record_link():
    book = workspace()
    row = saved(book)
    issue = book.record_review([], [{"topic": "a", "target": "起算点",
        "detail": "条款不完整", "action": "repair"}], "issue")["issues"][0]
    book.record_review([{"record_id": row["id"], "version": 1, "status": "passed",
        "reason": "期限正确，起算点仍待修正", "block_ids": ["s1r1c0"],
        "issue_ids": [issue["id"]]}], [], "review")
    with pytest.raises(InputError, match="未解决"):
        book.finalize([row["id"]], "完成")


def test_review_replay_keeps_history_and_rejects_changed_arguments():
    book = workspace()
    row = saved(book)
    approve(book, row)
    original = copy.deepcopy(book.state)
    assert approve(book, row)["reviews"][0]["status"] == "passed"
    assert book.state == original
    with pytest.raises(InputError, match="同一工具调用"):
        book.record_review([], [], f"review:{row['id']}:{row['version']}")


def test_renamed_parent_requires_resaving_child_path_even_after_new_review():
    book = workspace({"output_schema": {"version": "1", "sections": [
        {"title": "*", "layout": "tree", "columns": ["编制要求"]}]}})
    book.module_key = "bid_format_outline_parsing"

    def node(title, **changes):
        return raw(kind="format_node", title=title, node_type="section",
                   content={"编制要求": "按原文编制"}, **changes)

    parent = book.save_records([node("商务部分")], "parent")["accepted"][0]
    child = book.save_records([node("承诺函", parent_key=parent["id"])], "child")["accepted"][0]
    parent = book.save_records(
        [node("资格部分", id=parent["id"], version=1)], "rename")["accepted"][0]
    approve(book, parent)
    approve(book, child)
    with pytest.raises(InputError, match="祖先路径"):
        book.finalize([parent["id"], child["id"]], "完成")
    child = book.save_records([node("承诺函", parent_key=parent["id"], id=child["id"], version=1)],
                              "move")["accepted"][0]
    assert child["version"] == 2
    approve(book, child)
    book.finalize([parent["id"], child["id"]], "完成")


def test_changed_relation_endpoint_requires_resaving_derived_text():
    book = workspace()
    first = saved(book)
    second = book.save_records(
        [raw(content={"字段": "新质保", "内容": "五年"})], "second")["accepted"][0]
    relation = raw(kind="relation", predicate="supersedes", subject_key=second["id"],
                   object_key=first["id"], content={"字段": "替代", "内容": "新要求替代原要求"})
    link = book.save_records([relation], "link")["accepted"][0]
    second = book.save_records([raw(id=second["id"], version=1,
        content={"字段": "新质保", "内容": "六年"})], "edit")["accepted"][0]
    for receipt in (first, second, link):
        approve(book, receipt)
    with pytest.raises(InputError, match="端点正文"):
        book.finalize([first["id"], second["id"], link["id"]], "完成")
    link = book.save_records(
        [relation | {"id": link["id"], "version": 1}], "refresh")["accepted"][0]
    approve(book, link)
    book.finalize([first["id"], second["id"], link["id"]], "完成")


def test_relation_cannot_expand_endpoint_scope_when_publishing():
    book = workspace()
    book.seen["s1r1c0"]["content"] += "，标段一适用"
    book.state["topic_lots"] = [{"lot_id": 1, "code": "标段一", "title": "标段一", "aliases": []}]
    first = saved(book, scope={"kind": "lots", "lot_refs": ["标段一"]})
    second = book.save_records(
        [raw(content={"字段": "新质保", "内容": "五年"})], "second")["accepted"][0]
    link = book.save_records([raw(kind="relation", predicate="supersedes",
        subject_key=second["id"], object_key=first["id"],
        content={"字段": "替代", "内容": "新要求替代原要求"})], "link")["accepted"][0]
    for receipt in (first, second, link):
        approve(book, receipt)
    with pytest.raises(InputError, match="范围"):
        book.finalize([first["id"], second["id"], link["id"]], "完成")
    assert not book.book["finalized"]


@pytest.mark.parametrize("lot", [
    {"id": 1, "code": "A包", "name": "标段一", "aliases": ["设备包"]},
    {"lot_id": 1, "code": "A包", "title": "标段一", "aliases": ["设备包"]},
])
def test_parent_scope_accepts_known_lot_name_code_and_alias(lot):
    book = workspace({"output_schema": {"version": "1", "sections": [
        {"title": "*", "layout": "tree", "columns": ["编制要求"]}]}, "topic_lots": [lot]})
    book.module_key = "bid_format_outline_parsing"
    book.seen["s1r1c0"]["content"] += " 标段一（A包，设备包）"

    def node(title, ref, **changes):
        return raw(kind="format_node", title=title, node_type="section",
                   content={"编制要求": "按原文编制"},
                   scope={"kind": "lots", "lot_refs": [ref]}, **changes)

    parent = book.save_records([node("商务部分", "标段一")], "parent")["accepted"][0]
    children = book.save_records([
        node("承诺函", "A包", parent_key=parent["id"]),
        node("报价函", "设备包", parent_key=parent["id"]),
    ], "children")["accepted"]
    for receipt in [parent, *children]:
        approve(book, receipt)
    book.finalize([r["id"] for r in [parent, *children]], "完成")
    assert len(book.state["draft"]["fields"]) == 3


@pytest.mark.parametrize("target_ref,allowed", [
    ("设备包", True), ("B包", False), ("共同简称", False),
])
def test_relation_scope_resolves_aliases_without_merging_distinct_lots(target_ref, allowed):
    book = workspace()
    book.state["topic_lots"] = [
        {"id": 1, "code": "A包", "name": "标段一", "aliases": ["设备包", "共同简称"]},
        {"id": 2, "code": "B包", "name": "标段二", "aliases": ["共同简称"]},
    ]
    book.seen["s1r1c0"]["content"] += " 标段一 A包 设备包 B包 共同简称 新标段"
    # 目录可能不完整；已知别名归一，尚未进入目录的同名标段仍可比较。
    first = saved(book, scope={"kind": "lots", "lot_refs": ["标段一", "新标段"]})
    second = book.save_records([raw(content={"字段": "新质保", "内容": "五年"})],
                               "second")["accepted"][0]
    link = book.save_records([raw(kind="relation", predicate="supersedes",
        subject_key=second["id"], object_key=first["id"],
        scope={"kind": "lots", "lot_refs": [target_ref, "新标段"]},
        content={"字段": "替代", "内容": "新要求替代原要求"})], "link")["accepted"][0]
    for receipt in (first, second, link):
        approve(book, receipt)
    if allowed:
        book.finalize([first["id"], second["id"], link["id"]], "完成")
    else:
        with pytest.raises(InputError, match="范围"):
            book.finalize([first["id"], second["id"], link["id"]], "完成")
        assert not book.book["finalized"]
