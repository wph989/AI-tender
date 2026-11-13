"""稳定性以业务行为验收：坏条目隔离、问题身份与合法草稿的自动审查。"""

import asyncio
import copy
import json

import pytest
from langchain_core.messages import AIMessage
from test_analysis_compact_protocol import ledger
from test_analysis_research import block, session
from test_analysis_v3 import batch, build, finish, raw
from test_deep_analysis import call

from tender.application.analysis.agent import invoke_module
from tender.application.analysis.data import module_data
from tender.application.analysis.research import AgentLimits
from tender.application.analysis.topic_flow import TopicFlow
from tender.application.analysis.validation import ToolIssue, record_issues, resolve_issues


@pytest.mark.parametrize("kind", ["unsupported", "scope", "conflict"])
def test_review_cannot_reject_record_only_present_in_cross_packet_navigation(kind):
    from tender.application.analysis.review import validate
    from tender.domain.shared.errors import InvalidModelOutput

    packet = {"topic": "budget", "records": [], "context_records": [],
              "record_index": [{"record_id": "budget-in-other-packet"}],
              "evidence": [{"id": "opening-time"}], "context_evidence": []}
    issue = {"topic": "budget", "kind": kind, "record_ids": ["budget-in-other-packet"],
             "evidence_ids": ["opening-time"], "target": "预算事项",
             "detail": "本包未见其它包的预算原文，无法支持预算事项"}
    with pytest.raises(InvalidModelOutput, match="完整正文"):
        validate({"reviews": {}, "issues": [issue]}, packet)

    # 必要依赖的完整正文已交付时，真实矛盾仍须进入定向修复。
    packet["context_records"] = [{"record_id": "budget-in-other-packet"}]
    validate({"reviews": {}, "issues": [issue]}, packet)


def test_issue_identity_survives_bad_values_reordering_and_checkpoint_replay():
    state = {}
    issue = ToolIssue("unread_evidence", "updates.0.evidence_ids", "选实际已读ID", ("w1",))
    first = record_issues(state, "update_research", [issue], "c1", 2)[0]
    restored = json.loads(json.dumps(state))
    assert record_issues(restored, "update_research", [issue], "c1", 2)[0] == first
    changed = ToolIssue(issue.code, "updates.7.evidence_ids", "另一个非法值", ("w1",))
    second = record_issues(restored, "update_research", [changed], "c2", 2)[0]
    assert second["key"] == first["key"] and second["remaining_attempts"] == 0
    other = ToolIssue("invalid_work", "updates.0.work_ids", "选当前工作", ("w1",))
    record_issues(restored, "update_research", [other], "c3", 2)
    resolve_issues(restored, "update_research", ["w1"], paths=("updates.*.work_ids",))
    assert restored["tool_issue_ledger"]["issues"][first["key"]]["active"]
    resolve_issues(restored, "update_research", ["w2"], paths=("updates.*.evidence_ids",))
    assert restored["tool_issue_ledger"]["issues"][first["key"]]["active"]
    resolve_issues(restored, "update_research", ["w1"], paths=("updates.*.evidence_ids",))
    assert not restored["tool_issue_ledger"]["issues"][first["key"]]["active"]
    assert record_issues(restored, "update_research", [issue], "c4", 2)[0][
        "remaining_attempts"] == 0


def test_new_record_issue_keeps_work_budget_and_requires_its_receipt_id_to_resolve():
    state = {}
    first = ToolIssue("schema_literal_error", "records.0.kind", "修正kind", ("w1",), ("r1",))
    second = ToolIssue(first.code, "records.3.kind", "改名重交仍非法", ("w1",), ("r2",))
    tracked = record_issues(state, "submit_analysis", [first], "c1", 2)[0]
    retried = record_issues(state, "submit_analysis", [second], "c2", 2)[0]
    assert tracked["key"] == retried["key"] and retried["remaining_attempts"] == 0

    state = json.loads(json.dumps(state))
    resolve_issues(state, "submit_analysis", ["w1"], paths=("records.*",), record_ids=("other",))
    entry = state["tool_issue_ledger"]["issues"][tracked["key"]]
    assert entry["active"]
    resolve_issues(state, "submit_analysis", ["w1"], paths=("records.*",), record_ids=("r1",))
    assert entry["active"]
    resolve_issues(state, "submit_analysis", ["w1"], paths=("records.*",), record_ids=("r2",))
    assert not entry["active"]

    state["staged_items"] = [{"id": "r1"}]
    after_acceptance = record_issues(state, "submit_analysis", [first], "c3", 2)[0]
    assert after_acceptance["key"] == tracked["key"]
    assert after_acceptance["remaining_attempts"] == 0


def test_submission_business_errors_keep_field_paths_for_independent_recovery():
    async def run():
        graph, files, state, _, _, _ = build([
            batch(["质保"]),
            call("submit_analysis", {"records": [
                raw(work_ids=["obsolete"]), raw(scope={"kind": "lots", "lot_refs": ["虚构标段"]}),
                raw(),
            ], "final": False}, "field-errors"),
            call("complete_research", {"research_summary": "已核对有效事项"}, "done"),
        ])
        await invoke_module(graph, files, thread_id="business-field-errors", task="按具体字段纠正")
        receipt = json.loads(state["tool_results"]["call_field-errors"]["data"]["content"])
        paths = {issue["path"] for issue in receipt["details"]["issues"]}
        assert paths == {"records.0.work_ids", "records.1.scope.lot_refs[0]"}
        assert [r["status"] for r in receipt["records"]] == ["rejected", "rejected", "accepted"]

    asyncio.run(run())


@pytest.mark.parametrize("invalid", [False, {"work_ids": ["missing"], "detail": "非法工作"}])
def test_research_batch_isolates_independent_groups_and_preserves_original_indices(invalid):
    book, flow, state, _ = ledger()
    flow.data["protocol"] = "research-v3"
    result = book.update_batch([
        {"work_ids": ["w1"], "status": "examined", "detail": "已分析条款",
         "examined_ids": ["s1r1c0"]}, invalid,
    ])
    assert result["updates"] == [{"index": 0, "status": "accepted"},
                                 {"index": 1, "status": "rejected"}]
    assert result["issues"] and state["topic_flow"]["entries"]
    assert "已分析条款" in str(book.context(["w1"]))


def test_same_topic_research_updates_roll_back_as_one_group():
    book, flow, state, _ = ledger()
    flow.data["protocol"] = "research-v3"
    book.works()
    before = copy.deepcopy(state)
    result = book.update_batch([
        {"work_ids": ["w1"], "detail": "有效发现", "evidence_ids": ["s1r1c0"]},
        {"work_ids": ["w1"], "detail": "非法证据", "evidence_ids": ["invented"]},
    ])
    assert all(r["status"] == "rejected" for r in result["updates"])
    assert state == before


@pytest.mark.parametrize("invalid_first", [True, False])
def test_long_task_note_keeps_independent_update_receipts_and_can_be_corrected(invalid_first):
    async def run():
        valid_detail = "研究" * 1000
        valid = {"work_ids": ["w1"], "status": "examined", "detail": valid_detail,
                 "examined_ids": ["s1r1c0"]}
        invalid = {"work_ids": ["w3"], "status": "examined", "detail": "待" * 1001,
                   "examined_ids": ["s1r1c0"]}
        updates = [invalid, valid] if invalid_first else [valid, invalid]
        # 长文本边界专项留足上下文，让预设工具回合完整执行，不被摘要调用消耗。
        research = session([block()], limits=AgentLimits(context_tokens=96000))
        graph, files, state, saved, reviewed, _ = build([
            call("search_document_batch", {"queries": [
                {"query": "质保", "work_ids": ["w1", "w2"]},
            ]}, "both"),
            call("update_research", {"updates": [{"work_ids": ["w2"], "status": "examined",
                "detail": "核对起算条件", "examined_ids": ["s1r1c0"],
                "followups": [{"detail": "核对待办"}]}]}, "followup"),
            call("update_research", {"updates": updates}, "mixed-notes"),
            call("update_research", {"updates": [{"work_ids": ["w3"], "status": "found",
                "detail": "待" * 1000, "evidence_ids": ["s1r1c0"]}]}, "fixed-note"),
            call("submit_analysis", {"records": [raw(), raw(work_ids=["w2"],
                content={"字段": "质保起算", "内容": "三年"})], "final": False}, "drafts"),
            call("complete_research", {"research_summary": "已核对两个主题及待办"}, "done"),
        ], research, keys=("a", "b"))
        await invoke_module(graph, files, thread_id=f"long-task-{invalid_first}", task="逐组纠正")

        receipt = json.loads(state["tool_results"]["call_mixed-notes"]["data"]["content"])
        bad_index = 0 if invalid_first else 1
        assert receipt["updates"] == [{"index": i, "status": (
            "rejected" if i == bad_index else "accepted")} for i in range(2)]
        issue, = receipt["details"]["issues"]
        assert issue["path"] == f"updates.{bad_index}.detail"
        assert issue["work_ids"] == ["w3"]
        assert "待" * 1001 not in receipt["message"]
        # 两种顺序都必须先保存合法研究及逐组回执，不能依赖后续修正补回丢失的更新。
        persisted = next(s for s in saved
                         if "call_mixed-notes" in s.get("research_update_receipts", {}))
        assert persisted["research_update_receipts"]["call_mixed-notes"]["updates"] == (
            receipt["updates"])
        assert valid_detail in str(persisted["topic_flow"])
        fixed = json.loads(state["tool_results"]["call_fixed-note"]["data"]["content"])
        assert fixed["updates"] == [{"index": 0, "status": "accepted"}]
        assert not state["tool_issue_ledger"]["issues"][issue["key"]]["active"]
        assert reviewed and len(module_data(state)["records"]) == 2

    asyncio.run(run())


def test_internal_value_error_is_not_reported_as_model_argument_error(monkeypatch):
    book, _, _, _ = ledger()

    def broken(*args):
        raise ValueError("程序缺陷")

    monkeypatch.setattr(TopicFlow, "apply", broken)
    with pytest.raises(ValueError, match="程序缺陷"):
        book.update_batch([{"work_ids": ["w1"], "detail": "已分析",
                            "status": "examined", "examined_ids": ["s1r1c0"]}])


@pytest.mark.parametrize("ending", ["natural", "repeated", "evidence_budget"])
def test_valid_draft_reaches_review_through_recoverable_finish_paths(ending):
    async def run():
        script = [batch(["质保"]),
                  call("submit_analysis", {"records": [raw()], "final": False}, "draft")]
        research = session([block()], limits=AgentLimits(max_no_progress_rounds=8,
                                                         max_identical_tool_calls=2))
        if ending == "natural":
            script += [AIMessage(content="研究已完成", id=f"natural{i}") for i in range(3)]
        elif ending == "repeated":
            script += [call("get_research_context", {"work_ids": ["w1"]}, f"ctx{i}")
                       for i in range(3)]
        else:
            # 按真实边界模拟取证函数拒绝新增原文，不替换Agent节点或审查器。
            from tender.application.analysis.research import EvidenceBudgetError

            async def exhausted(*args, **kwargs):
                raise EvidenceBudgetError("已到原文额度")

            research.read_evidence = exhausted
            script.append(call("read_document", {"block_id": "s1r1c0",
                                                   "work_ids": ["w1"]}, "full"))
        graph, files, state, saved, reviewed, _ = build(script, research)
        await invoke_module(graph, files, thread_id="finish-" + ending, task="完成解析")
        assert len(reviewed) == 1 and len(module_data(state)["records"]) == 1
        assert state["topic_flow"]["phase"] == "completed"
        assert state["draft"]["business_data"]["records"] == module_data(state)["records"]
        assert state["draft"]["business_data"]["progress"]["phase"] == "completed"
        assert saved and not state.get("consecutive_tool_failures")

    asyncio.run(run())


def test_multiple_recoverable_problems_do_not_accumulate_terminal_tool_failures():
    async def run():
        script = [batch(["质保"])]
        for index in range(6):
            script.append(call("update_research", {"updates": [{"work_ids": ["w1"],
                "status": "examined", "detail": "仅核对线索",
                "examined_ids": ["fake" + str(index)]}]}, f"invalid{index}"))
        script += finish()
        research = session([block()], limits=AgentLimits(max_no_progress_rounds=10))
        graph, files, state, _, reviewed, _ = build(script, research)
        await invoke_module(graph, files, thread_id="many-errors", task="纠正工具参数")
        assert len(reviewed) == 1 and len(module_data(state)["records"]) == 1
        issues = list(state["tool_issue_ledger"]["issues"].values())
        assert len(issues) == 1 and issues[0]["attempts"] == 6
        assert not state.get("consecutive_tool_failures")

    asyncio.run(run())


def test_mixed_submission_preserves_good_record_and_only_retries_rejected_part():
    async def run():
        script = [batch(["质保"]),
            call("submit_analysis", {"records": [raw(), {"work_ids": ["w1"], "kind": False}],
                                      "final": True}, "mixed"),
            call("submit_analysis", {"records": [raw(content={"字段": "服务", "内容": "三年"})],
                                      "final": False}, "fixed"),
            call("complete_research", {"research_summary": "已核对全部事项"}, "end")]
        graph, files, state, _, reviewed, _ = build(script)
        await invoke_module(graph, files, thread_id="mixed-fix", task="逐项修正")
        receipt = json.loads(state["tool_results"]["call_mixed"]["data"]["content"])
        assert [r["status"] for r in receipt["records"]] == ["accepted", "rejected"]
        assert receipt["recoverable"] and not receipt["final"]
        assert len(reviewed) == 1 and len(module_data(state)["records"]) == 2

    asyncio.run(run())


def test_public_tool_schema_retains_item_fields_while_execution_isolates_bad_types():
    from pydantic import create_model

    from tender.application.analysis.protocol import ResearchDelta, SubmissionRecord, batch_field

    for name, model in (("updates", ResearchDelta), ("records", SubmissionRecord)):
        container = create_model("Batch", **{name: (list, batch_field(model))})
        schema = container.model_json_schema()["properties"][name]["items"]
        assert "work_ids" in schema["required"]
        assert schema["additionalProperties"] is False
        assert "$ref" not in json.dumps(schema)
        assert container.model_validate({name: [False]})


def test_budget_handoff_gives_synthesis_its_first_submission_opportunity():
    async def run():
        state = {}

        def budget():
            return {"model_calls_remaining": (
                0 if "call_ctx2" in state.get("tool_results", {}) else 80)}

        graph, files, _, _, reviewed, _ = build([
            batch(["质保"]),
            *(call("get_research_context", {"work_ids": ["w1"]}, f"ctx{i}") for i in range(3)),
            call("submit_analysis", {"records": [raw()], "final": True}, "synthesize"),
        ], state=state, budget=budget)
        await invoke_module(graph, files, thread_id="handoff-idle", task="综合并审查")
        assert len(reviewed) == 1 and len(module_data(state)["records"]) == 1
        assert state["topic_flow"]["research_stop_reason"] == "budget_reserve"

    asyncio.run(run())


def test_finish_reserve_uses_successful_request_duration_after_model_failover(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from test_analysis_argument_failures import middleware

    _, flow, state, research = ledger()

    async def run():
        flow.data["protocol"] = "research-v3"
        wraps = middleware(research, state)
        wraps.topic_flow = flow
        wraps.topic_model_call = AsyncMock(return_value=SimpleNamespace(result=[
            AIMessage(content="", response_metadata={"request_latency_ms": 70000}),
        ]))
        ticks = iter([0, 432])
        monkeypatch.setattr("tender.application.analysis.agent.time",
                            SimpleNamespace(monotonic=lambda: next(ticks)))
        await wraps.awrap_model_call(None, None)
        assert state["model_round_seconds"] == 70

    asyncio.run(run())


def test_submission_program_error_is_not_isolated_as_a_bad_record(monkeypatch):
    from tender.application.analysis import data
    from tender.application.analysis.protocol import SubmissionRecord, submission_records

    book, _, state, research = ledger()
    state["output_schema"] = {"sections": []}
    records, _ = submission_records([SubmissionRecord.model_validate(raw(title="质保"))], state,
                                     book.works(), "program-error")

    def broken(*args):
        raise ValueError("输出程序缺陷")

    monkeypatch.setattr(data, "record_output", broken)
    with pytest.raises(ValueError, match="输出程序缺陷"):
        data.prepare_record_batch([record for _, record in records], state, research.seen,
                                   "project_basic_info_parsing")
