"""检索收敛审查反例：工作隔离、可信分页及新增原文的保守复核。"""

import copy

import pytest
from test_analysis_research import block
from test_analysis_topic_flow import prepared_flow, update

from tender.application.analysis.research import ToolArgumentError
from tender.application.analysis.search_control import TopicSearch
from tender.application.analysis.state import published_items
from tender.application.analysis.topic_flow import TopicFlow, TopicUpdate


def exhaust(control, detail):
    for index in range(3):
        target = control.begin("search_document", {
            "topic_keys": ["a"], "work": detail, "query": str(index),
        })
        control.end(target, {"blocks": []}, set(control.flow.research.seen))
    with pytest.raises(ToolArgumentError):
        control.begin("search_document", {"topic_keys": ["a"], "work": detail, "query": "再找"})


def test_task_selection_cannot_hide_contradicting_evidence_for_another_record():
    flow, state, research = prepared_flow()
    count = copy.deepcopy(state["staged_items"][0])
    count.update(id="count")
    count["business"].update(key="count", content={"字段": "采购数量", "内容": "采购交换机10台"})
    state["staged_items"].append(count)
    task = {"detail": "核对质保起算点", "record_keys": ["warranty"]}
    flow.apply([TopicUpdate.model_validate(update(
        "a", ["warranty", "count"], status="researching", tasks=[task],
    ))], {"warranty", "count"})
    TopicSearch(flow).begin("search_document", {"topic_keys": ["a"], "work": task["detail"]})
    research.seen["new"] = block() | {"content": "采购交换机20台。质保自验收合格日起三年。"}
    flow.evidence({"s1r1c0"}, ["a"], {"blocks": [{"id": "new"}]})
    assert all(item["review_status"] == "needs_review" for item in state["staged_items"])
    assert published_items(state, final=True) == []


@pytest.mark.parametrize("kind", ["check", "reference"])
def test_exhausted_work_keeps_other_checks_available_across_restore(kind):
    flow, state, research = prepared_flow()
    entry = flow.entries[0]
    entry.update(checks=["期限", "采购数量"], checked=[], requested_status="researching")
    if kind == "reference":
        entry["references"] = [{"topic": "a", "from_block_id": "s1r1c0", "target": "附件一",
                                "status": "missing", "evidence_ids": []}]
    flow.sync()
    control = TopicSearch(flow)
    exhaust(control, "期限" if kind == "check" else "附件一")
    restored = TopicFlow(copy.deepcopy(state), research)
    control = TopicSearch(restored)
    assert control.begin("search_document", {"topic_keys": ["a"], "work": "采购数量"})
    assert restored.entries[0]["status"] != "blocked"
    exhaust(control, "采购数量")
    if kind == "reference":
        exhaust(control, "期限")
    assert restored.entries[0]["status"] == "blocked"
    assert not restored.pending()


@pytest.mark.parametrize("record_keys", [[], ["warranty"]])
def test_independent_tasks_have_separate_budgets_even_with_same_record_links(record_keys):
    flow, state, research = prepared_flow()
    tasks = [{"detail": "查附件一规定", "record_keys": record_keys},
             {"detail": "查递交截止时间", "record_keys": record_keys}]
    flow.apply([TopicUpdate.model_validate(update(
        "a", ["warranty"], status="researching", tasks=tasks,
    ))], {"warranty"})
    control = TopicSearch(flow)
    assert len({choice["id"] for choice in control.choices(["a"])}) == 2
    exhaust(control, tasks[0]["detail"])
    assert control.begin("search_document", {"topic_keys": ["a"], "work": tasks[1]["detail"]})
    assert [t["status"] for t in flow.entries[0]["tasks"].values()] == ["blocked", "pending"]


def test_task_rename_keeps_server_identity_and_exhaustion_across_restore():
    flow, state, research = prepared_flow()
    task = {"detail": "查截止时间", "record_keys": []}
    flow.apply([TopicUpdate.model_validate(update(
        "a", ["warranty"], status="researching", tasks=[task],
    ))], {"warranty"})
    task_id = next(iter(flow.entries[0]["tasks"]))
    control = TopicSearch(flow)
    exhaust(control, task["detail"])
    restored = TopicFlow(copy.deepcopy(state), research)
    renamed = {"task_id": task_id, "detail": "截止日期是哪一天", "status": "pending"}
    restored.apply([TopicUpdate.model_validate(update(
        "a", ["warranty"], status="researching", tasks=[renamed],
    ))], {"warranty"})
    assert len(restored.entries[0]["tasks"]) == 1
    with pytest.raises(ToolArgumentError):
        TopicSearch(restored).begin("search_document", {"topic_keys": ["a"],
                                                       "work": renamed["detail"]})
    assert TopicSearch.summary(restored.state)["exhausted_work"] == 1


def test_unknown_task_id_does_not_create_a_new_identity_or_mutate_progress():
    flow, state, _ = prepared_flow()
    previous = copy.deepcopy(flow.data["entries"])
    with pytest.raises(ValueError, match="task_id"):
        flow.apply([TopicUpdate.model_validate(update("a", ["warranty"], tasks=[{
            "task_id": "invented", "detail": "改名重开", "record_keys": ["warranty"],
        }]))], {"warranty"})
    assert flow.data["entries"] == previous


def test_two_references_from_the_same_block_have_separate_progress():
    flow, state, _ = prepared_flow()
    flow.entries[0].update(requested_status="researching", references=[
        {"topic": "a", "from_block_id": "s1r1c0", "target": target, "status": "missing",
         "evidence_ids": []} for target in ("附件一", "附件二")
    ])
    flow.sync()
    control = TopicSearch(flow)
    assert len({work["id"] for work in control.choices(["a"])}) == 2
    exhaust(control, "附件一")
    assert control.begin("search_document", {"topic_keys": ["a"], "work": "附件二"})


@pytest.mark.parametrize("offset", [1, 6, 30, 36, 60])
def test_empty_terminal_page_does_not_authorize_larger_offsets(offset):
    flow, _, research = prepared_flow()
    flow.entries[0].update(checked=[], requested_status="researching")
    flow.sync()
    control = TopicSearch(flow)
    target = control.begin("search_document", {"topic_keys": ["a"], "query": "空结果"})
    control.end(target, {"blocks": [], "page": {"offset": 0, "has_more": False,
                                               "next_offset": None}}, set(research.seen))
    with pytest.raises(ToolArgumentError):
        control.begin("search_document", {"topic_keys": ["a"], "query": "空结果",
                                           "offset": offset})
    assert control.summary(flow.state)["research_calls"] == 1


def test_valid_search_cursor_survives_restore_but_an_empty_page_counts_as_idle():
    flow, state, research = prepared_flow()
    flow.entries[0].update(checked=[], requested_status="researching")
    flow.sync()
    control = TopicSearch(flow)
    work = control.begin("search_document", {"topic_keys": ["a"], "query": "清单"})
    control.end(work, {"already_read": ["s1r1c0"], "blocks": [],
                       "page": {"offset": 0, "has_more": True, "next_offset": 6}},
                set(research.seen))
    restored = TopicFlow(copy.deepcopy(state), research)
    control = TopicSearch(restored)
    work = control.begin("search_document", {"topic_keys": ["a"], "query": "清单", "offset": 6})
    control.end(work, {"blocks": [], "page": {"offset": 6, "has_more": False,
                                             "next_offset": None}}, set(research.seen))
    assert control.ledger[work[0]["id"]]["idle"] == 2
    with pytest.raises(ToolArgumentError, match="分页"):
        control.begin("search_document", {"topic_keys": ["a"], "query": "清单", "offset": 12})
