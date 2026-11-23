"""验证冷启动、业务质量及稳定问题身份，避免只修改前端标签掩盖执行错误。"""

from unittest.mock import Mock

import pytest
from test_analysis_verification_degradation import _RetryStore, _RetryTx

from tender.application.analysis.quality import refresh_input
from tender.application.analysis.service import AnalysisService
from tender.application.knowledge.content import source_signature, validate_items
from tender.application.shared.errors import Conflict


@pytest.mark.parametrize("status", ["completed", "failed", "partial", "canceled"])
@pytest.mark.parametrize("mode", [None, "restart"])
def test_restart_discards_all_analysis_state_for_every_terminal_status(status, mode):
    previous = {"staged_items": [{"id": "old"}],
                "research": {"seen": {"old": {}}, "tool_calls": 100}, "draft": {"fields": []}}
    tx = _RetryTx([{"id": 9, "status": status}], previous)
    service = AnalysisService(_RetryStore(tx), 1, Mock(), Mock())
    service.retry_report(3, module_keys=["project_basic_info_parsing"],
                         max_output_tokens=None, timeout_seconds=None, mode=mode)
    assert tx.pending == [9]
    assert tx.inserted[0]["state"] == {"execution_mode": "restart"}
    assert previous["research"]["tool_calls"] == 100


def test_confirmed_missing_input_does_not_restart_on_the_same_materials():
    tx = _RetryTx([{"id": 9, "status": "completed", "business_data": {
        "quality_status": "needs_input", "quality_input_signature": source_signature([]),
    }}], {})
    service = AnalysisService(_RetryStore(tx), 1, Mock(), Mock())
    original = service.report_row(3) | {"source_snapshot": []}
    service.report_row = Mock(return_value=original)
    service.analysis_status = Mock(return_value={"sources": []})
    service.store.sources = Mock(return_value=[])
    service.store.collections_for_project = Mock(return_value=[])
    with pytest.raises(Conflict):
        service.retry_report(3, module_keys=[], max_output_tokens=None,
                             timeout_seconds=None, mode="resume")
    assert not tx.inserted


@pytest.mark.parametrize("status", ["partial", "failed", "canceled"])
@pytest.mark.parametrize(("latest_quality", "formal_quality", "can_resume"), [
    ("needs_review", "needs_input", True),
    (None, "needs_input", True),
    ("needs_input", "needs_review", False),
])
def test_new_materials_interrupted_attempt_uses_its_own_quality(
    status, latest_quality, formal_quality, can_resume,
):
    from test_analysis_agent_workspace import approve, saved, workspace

    old = [{"source_id": 1, "project_id": 1, "version_id": 1, "parse_run_id": 1}]
    current = old + [{"source_id": 2, "project_id": 1, "version_id": 2, "parse_run_id": 2}]
    book = workspace()
    approve(book, saved(book))
    previous = book.state
    previous["quality_input_signature"] = source_signature(current)
    previous["agent_workspace"]["finalized"] = latest_quality == "needs_input"
    if latest_quality is not None:
        previous["quality_status"] = latest_quality
    business = {"quality_status": formal_quality, "quality_input_signature": source_signature(old)}
    # 补件后的中断轮只保存工作区，正式正文仍属于上一轮；二者不能混用来决定续跑。
    tx = _RetryTx([{"id": 9, "status": status, "business_data": business}], previous)
    store = _RetryStore(tx)
    store.report = Mock(return_value=store.report(3) | {
        "source_snapshot": current, "reference_snapshot": [],
    })
    store.sources = Mock(return_value=current)
    store.collections_for_project = Mock(return_value=[1])
    service = AnalysisService(store, 1, Mock(), Mock())
    service.analysis_status = Mock(return_value={"sources": current})

    if not can_resume:
        with pytest.raises(Conflict) as error:
            service.retry_report(3, module_keys=[], mode="resume",
                                 max_output_tokens=None, timeout_seconds=None)
        assert error.value.code == "nothing_to_retry"
        assert not tx.inserted and tx.pending is None
        return

    result = service.retry_report(3, module_keys=[], mode="resume",
                                  max_output_tokens=None, timeout_seconds=None)
    assert result["status"] == "pending" and tx.pending == [9]
    carried = tx.inserted[0]["state"]
    assert carried["execution_mode"] == "resume"
    assert carried["quality_input_signature"] == source_signature(current)
    assert carried["staged_items"] == previous["staged_items"]
    assert carried["agent_workspace"]["reviews"] == previous["agent_workspace"]["reviews"]
    assert not carried["agent_workspace"]["finalized"]
    assert tx.rows[0]["business_data"] == business




def test_partial_restart_does_not_consume_another_modules_input_change():
    from test_analysis_agent_workspace import workspace

    old = [{"source_id": 1, "project_id": 1, "version_id": 1, "parse_run_id": 1}]
    current = old + [{"source_id": 2, "project_id": 1, "version_id": 2, "parse_run_id": 2}]
    previous = workspace().state
    previous["quality_input_signature"] = source_signature(old)
    tx = _RetryTx([{"id": 9, "status": "completed"}], previous)
    store = _RetryStore(tx)
    report = store.report(3) | {"source_snapshot": old, "reference_snapshot": []}
    store.report = Mock(side_effect=lambda _: report)
    store.sources = Mock(return_value=current)
    store.collections_for_project = Mock(return_value=[1])
    service = AnalysisService(store, 1, Mock(), Mock())
    service.analysis_status = Mock(return_value={"sources": current})
    tx.update_report = lambda _, values: report.update(values)
    service.retry_report(3, module_keys=["project_basic_info_parsing"], mode="restart",
                         max_output_tokens=None, timeout_seconds=None)
    report["status"] = "completed"
    tx.rows = [{"id": 10, "status": "completed", "business_data": {
        "quality_status": "needs_input", "quality_input_signature": source_signature(old),
    }}]
    service.retry_report(3, module_keys=[], mode="resume",
                         max_output_tokens=None, timeout_seconds=None)
    carried = tx.inserted[-1]["state"]
    assert tx.pending == [10] and len(tx.inserted) == 2
    assert "agent_progress" not in carried
    assert not carried["agent_workspace"]["finalized"]


def test_unchanged_module_does_not_resume_only_because_report_snapshot_is_old():
    old = [{"source_id": 1, "project_id": 1}]
    current = old + [{"source_id": 2, "project_id": 1}]
    tx = _RetryTx([{"id": 9, "status": "completed", "business_data": {
        "quality_status": "needs_input", "quality_input_signature": source_signature(current),
    }}], {})
    store = _RetryStore(tx)
    store.report = Mock(return_value=store.report(3) | {
        "source_snapshot": old, "reference_snapshot": [],
    })
    store.sources = Mock(return_value=current)
    store.collections_for_project = Mock(return_value=[1])
    service = AnalysisService(store, 1, Mock(), Mock())
    service.analysis_status = Mock(return_value={"sources": current})
    with pytest.raises(Conflict, match="没有需要补跑"):
        service.retry_report(3, module_keys=[], mode="resume",
                             max_output_tokens=None, timeout_seconds=None)
    assert not tx.inserted


@pytest.mark.parametrize("quote,pages", [("若系统故障，应延后开标。", [2]),
                                         ("准时参加。若系统故障，应延后开标。", [1, 2])])
def test_qa_quote_uses_full_large_block_offsets_and_only_its_actual_pages(quote, pages):
    from tender.domain.knowledge.text import iter_retrieval_chunks

    texts = ["5. 开标要求", "招标人组织开标，所有投标人应准时参加。", "若系统故障，应延后开标。"]
    rows = [{"id": index + 1, "type": "text", "text": text,
             "page_no": 1 if index < 2 else 2, "anchor": f"p{index + 1}b1"}
            for index, text in enumerate(texts)]
    chunk = list(iter_retrieval_chunks(rows))[0][1] | {
        "block_id": "s1r1g2c0", "source_id": 1, "parse_run_id": 1,
    }
    result = validate_items([{"field": "开标", "values": [{"value": "故障时延后开标",
        "citations": [{"block_id": chunk["block_id"], "quote": quote}]}]}],
        {chunk["block_id"]: chunk}, align=False)
    refs = result[0]["values"][0]["citations"]
    assert [ref["page_no"] for ref in refs] == pages
    assert refs[-1]["quote"] == texts[-1]
    assert all(ref["quote"] and ref["quote"] in (
        "\n".join(texts[:2]) if ref["page_no"] == 1 else texts[-1]) for ref in refs)


def test_resume_retains_unresolved_issue_for_same_agent_without_stage_switch():
    from test_analysis_agent_workspace import workspace

    book = workspace()
    receipt = book.record_review([], [{"topic": "warranty", "target": "起算点",
        "detail": "需补读起算点", "action": "read"}], "issue")
    tx = _RetryTx([{"id": 9, "status": "completed", "business_data": {
        "quality_status": "needs_review"}}], book.state)
    service = AnalysisService(_RetryStore(tx), 1, Mock(), Mock())
    service.retry_report(3, module_keys=[], max_output_tokens=None,
                         timeout_seconds=None, mode="resume")
    carried = tx.inserted[0]["state"]
    assert "agent_progress" not in carried
    assert carried["agent_workspace"]["issues"][receipt["issues"][0]["id"]]["status"] == "open"






def test_new_input_invalidates_confirmed_missing_cache_and_old_version_evidence():
    from test_analysis_agent_workspace import workspace

    state = workspace().state
    state["research"] = {"seen": {
        "same": {"source_id": 1, "version_id": 1, "parse_run_id": 1},
        "old": {"source_id": 2, "version_id": 1, "parse_run_id": 1},
    }}
    state["agent_workspace"]["finalized"] = True
    refresh_input(state, [{"source_id": 1, "version_id": 1, "parse_run_id": 1},
                          {"source_id": 2, "version_id": 2, "parse_run_id": 2}])
    assert set(state["research"]["seen"]) == {"same"}
    assert state["agent_workspace"]["reviews"] == {}
    assert not state["agent_workspace"]["finalized"]
