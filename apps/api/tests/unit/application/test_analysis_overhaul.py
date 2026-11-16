"""验证冷启动、业务质量及稳定问题身份，避免只修改前端标签掩盖执行错误。"""

import asyncio
from unittest.mock import Mock

import pytest
from test_analysis_verification_degradation import _RetryStore, _RetryTx

from tender.application.analysis.evidence import display_citation
from tender.application.analysis.quality import merge_issues, refresh_input
from tender.application.analysis.service import AnalysisService
from tender.application.knowledge.content import source_signature, validate_items
from tender.application.shared.errors import Conflict


@pytest.mark.parametrize("status", ["completed", "failed", "partial", "canceled"])
@pytest.mark.parametrize("mode", [None, "restart"])
def test_restart_discards_all_analysis_state_for_every_terminal_status(status, mode):
    previous = {"staged_items": [{"id": "old"}], "topic_flow": {"audit": {"done": True}},
                "research": {"seen": {"old": {}}, "tool_calls": 100}, "draft": {"fields": []}}
    tx = _RetryTx([{"id": 9, "status": status}], previous)
    service = AnalysisService(_RetryStore(tx), 1, Mock(), Mock(), Mock())
    service.retry_report(3, module_keys=["project_basic_info_parsing"],
                         max_output_tokens=None, timeout_seconds=None, mode=mode)
    assert tx.reset is None and tx.pending == [9]
    assert tx.inserted[0]["state"] == {"execution_mode": "restart"}
    assert previous["research"]["tool_calls"] == 100


def test_confirmed_missing_input_does_not_restart_on_the_same_materials():
    tx = _RetryTx([{"id": 9, "status": "completed", "business_data": {
        "quality_status": "needs_input"}}], {})
    service = AnalysisService(_RetryStore(tx), 1, Mock(), Mock(), Mock())
    original = service.report_row(3) | {"source_snapshot": []}
    service.report_row = Mock(return_value=original)
    service.analysis_status = Mock(return_value={"sources": []})
    service.store.sources = Mock(return_value=[])
    service.store.collections_for_project = Mock(return_value=[])
    with pytest.raises(Conflict):
        service.retry_report(3, module_keys=[], max_output_tokens=None,
                             timeout_seconds=None, mode="resume")
    assert not tx.inserted


@pytest.mark.parametrize("confirmed_first", [False, True])
def test_cross_topic_missing_attachment_keeps_confirmed_details_and_proof(confirmed_first):
    from tender.application.analysis.quality import settle_quality

    pending = {"topic": "payment", "kind": "reference", "action": "read",
               "target": "附件2商务规范书", "detail": "需补读商务规范书",
               "record_keys": [], "evidence_ids": ["c208"]}
    confirmed = pending | {
        "topic": "acceptance", "action": "provide_input",
        "detail": "已核对全部项目资料，附件2商务规范书未提供，请补充该附件。",
        "missing_input": {"file_name": "商务规范书", "reference_ids": ["c208"],
                          "checked_source_ids": [14]},
    }
    state = {}
    settle_quality(state, [confirmed, pending] if confirmed_first else [pending, confirmed])
    issue, = state["quality_issues"]
    # 跨主题合并不能只改为等待资料却丢掉实际缺件依据，或继续展示旧的补读指令。
    assert state["quality_status"] == "needs_input"
    assert issue["missing_input"] == confirmed["missing_input"]
    assert issue["detail"] == confirmed["detail"]
    assert issue["topics"] == ["acceptance", "payment"]
    assert state["business_gaps"][0]["detail"] == confirmed["detail"]
    assert "missing_input" not in pending


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
    service = AnalysisService(store, 1, Mock(), Mock(), Mock())
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
    assert "topic_flow" not in carried
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
    service = AnalysisService(store, 1, Mock(), Mock(), Mock())
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
    service = AnalysisService(_RetryStore(tx), 1, Mock(), Mock(), Mock())
    service.retry_report(3, module_keys=[], max_output_tokens=None,
                         timeout_seconds=None, mode="resume")
    carried = tx.inserted[0]["state"]
    assert "topic_flow" not in carried
    assert carried["agent_workspace"]["issues"][receipt["issues"][0]["id"]]["status"] == "open"


@pytest.mark.parametrize("kind,action,quality", [
    ("omission", "read", "needs_review"), ("omission", "provide_input", "needs_input"),
    ("reference", "provide_input", "needs_input"),
])
def test_independent_gap_preserves_supported_result_and_finishes_normally(kind, action, quality):
    from synthesis_fixtures import summary_record
    from test_analysis_combined_review import approve, execute
    from test_analysis_research import block

    from tender.application.analysis.research import AgentLimits

    async def run():
        async def review(payload):
            result = approve(payload)
            result["issues"] = [{"topic": "a", "kind": kind, "action": action,
                                 "target": "附件甲具体日期", "detail": "具体日期仍需核对",
                                 "record_ids": list(result["reviews"]), "evidence_ids": []}]
            if action == "provide_input":
                result["issues"][0]["missing_input"] = {
                    "file_name": "附件甲", "reference_ids": [
                        (payload["evidence"] + payload["context_evidence"])[0]["id"]],
                    "checked_source_ids": [s["source_id"] for s in payload["documents"]
                                           if s["project_id"] == payload["project_id"]],
                }
            return result

        state, _, _, calls = await execute([summary_record()], review=review,
                                          limits=AgentLimits(max_review_repairs=0),
                                          evidence_rows=[block() | {
                                              "content": "质保三年。具体日期详见附件甲。"}])
        assert state["quality_status"] == quality
        assert len(state["draft"]["fields"]) == 1
        assert state["draft"]["fields"][0]["verification"] == "supported"
        assert len(calls) == 1
        assert state["topic_flow"]["phase"] == "completed"

    asyncio.run(run())


def test_issue_identity_ignores_wording_and_topic_but_preserves_scope_and_object():
    issue = {"topic": "a", "kind": "omission", "action": "read", "record_keys": ["r1"],
             "scope": {"kind": "lots", "lot_refs": ["标段一"]},
             "target": "公告/开标日期", "detail": "日期未读", "evidence_ids": []}
    merged = merge_issues([issue, issue | {"topic": "b", "detail": "具体时刻待查"},
                           issue | {"record_keys": ["r2"]},
                           issue | {"scope": {"kind": "lots", "lot_refs": ["标段二"]}}])
    assert len(merged) == 3
    assert merged[0]["topics"] == ["a", "b"]


def test_code_builds_relevant_excerpt_without_changing_evidence_identity():
    ref = {"block_id": "s1r1c1", "source_id": 1, "element_id": 2,
           "quote": "采用网上开标，投标人必须使用证书签名，异常时按原文流程办理。预算为500万元。"}
    selected = display_citation(ref, {"content": {"要求": "采用网上开标，投标人必须使用证书签名"}})
    assert selected["block_id"] == ref["block_id"]
    assert "异常时按原文流程办理" in selected["quote"]
    assert "预算" not in selected["quote"]
    fallback = display_citation(ref, {"content": {"要求": "摘要完全无法逐字匹配"}})
    assert fallback["excerpt_status"] == "block_only" and fallback["quote"] == ""


def test_excerpt_keeps_exception_and_separates_other_facts_and_wrong_numbers():
    ref = {"block_id": "b1", "quote": "采用网上开标方式。若系统故障，应延后开标。"
           "预算金额为500万元。服务期限为两年。"}
    selected = display_citation(ref, {"content": {"要求": "采用网上开标方式"}})
    assert selected["excerpts"] == ["采用网上开标方式。", "若系统故障，应延后开标。"]
    wrong = display_citation(ref, {"content": {"要求": "预算金额为600万元"}})
    assert wrong["excerpt_status"] == "block_only"


def test_capacity_failure_does_not_become_completed_or_a_business_issue():
    from synthesis_fixtures import summary_record
    from test_analysis_combined_review import execute

    from tender.application.analysis.research import AgentLimits
    from tender.application.analysis.topic_flow import TopicIncomplete

    async def run():
        state = {}
        with pytest.raises(TopicIncomplete, match="审查未完成"):
            await execute([summary_record()], state=state, limits=AgentLimits(
                review_max_input_tokens=1000, max_review_repairs=0,
            ))
        assert state["topic_flow"]["phase"] != "completed"
        assert state["topic_flow"]["audit"]["execution_errors"]
        assert not state.get("quality_status")
        assert not state["topic_flow"]["audit"]["remaining"]

    asyncio.run(run())


def test_new_input_invalidates_confirmed_missing_cache_and_old_version_evidence():
    from test_analysis_compact_protocol import ledger

    _, flow, state, research = ledger()
    state["research"] = {"seen": {
        "same": {"source_id": 1, "version_id": 1, "parse_run_id": 1},
        "old": {"source_id": 2, "version_id": 1, "parse_run_id": 1},
    }}
    flow.data["audit"] = {"done": True, "issues": [{"action": "provide_input"}]}
    refresh_input(state, [{"source_id": 1, "version_id": 1, "parse_run_id": 1},
                          {"source_id": 2, "version_id": 2, "parse_run_id": 2}])
    assert set(state["research"]["seen"]) == {"same"}
    assert flow.data["audit"] == {"round": 0, "results": {}}
    assert all(e["status"] == "researching" for e in flow.entries)


def test_same_packet_unrelated_evidence_and_unproven_missing_input_are_rejected():
    from tender.application.analysis.review import validate
    from tender.domain.shared.errors import InvalidModelOutput

    payload = {"topic": "a", "project_id": 1, "checks": [],
               "records": [{"record_id": "r1"}], "context_records": [],
               "evidence": [{"id": "b1"}, {"id": "unrelated"}], "context_evidence": [],
               "record_evidence_ids": {"r1": ["b1"]},
               "documents": [{"source_id": 1, "project_id": 1}]}
    result = {"reviews": {"r1": {"supported": True, "block_ids": ["unrelated"], "issues": []}},
              "issues": []}
    with pytest.raises(InvalidModelOutput, match="block_ids"):
        validate(result, payload)
    result["reviews"]["r1"]["block_ids"] = ["b1"]
    result["issues"] = [{"topic": "a", "kind": "omission", "action": "provide_input",
                         "detail": "本包没有公告", "target": "招标公告", "record_ids": [],
                         "evidence_ids": []}]
    with pytest.raises(InvalidModelOutput, match="missing_input"):
        validate(result, payload)
