"""补跑保留成果，但新 attempt 的调用预算不能被历史研究计数占用。"""

import asyncio
import copy
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from tender.application.analysis.contract import RUNTIME_VERSION
from tender.application.analysis.research import AgentLimits, ResearchSession
from tender.application.analysis.service import AnalysisService
from tender.ports.repository.analysis.reports import ReportRepository, ReportTransaction


@pytest.mark.parametrize("staged", [False, True])
@pytest.mark.parametrize("previous_tool_calls", [76, 100])
@pytest.mark.parametrize("topic_flow", [False, True])
def test_retry_preserves_evidence_and_results_with_fresh_tool_budget(
    monkeypatch, staged, previous_tool_calls, topic_flow
):
    source = {
        "source_id": 1, "collection_id": 1, "project_id": 10, "file_name": "采购.pdf",
        "purpose": "tender", "parse_run_id": 1, "version_id": 1,
    }
    evidence = source | {
        "block_id": "s1r1c0", "element_id": 1, "content": "质保三年", "offset": 0,
        "chapter": "质保",
    }
    field = {
        "id": "warranty", "field": "质保", "verification": "supported",
        "values": [{"value": "质保三年", "citations": [{
            "block_id": "s1r1c0", "source_id": 1, "project_id": 10, "quote": "质保三年",
        }]}],
    }
    saved_state = {
        "research": {
            "seen": {"s1r1c0": evidence},
            "events": [{"action": "search_result", "scope": "project"}],
            "tool_calls": previous_tool_calls,
        },
        "research_completed": True,
        "research_summary": "已核对质保要求",
    }
    if topic_flow:
        saved_state.update(topic_research_round="old-round", topic_flow={
            "entries": {"a": {"status": "blocked", "requested_status": "blocked", "tasks": {
                "task": {"status": "blocked"},
            }, "blocked_checks": ["截止时点"], "references": [{"status": "budget_exhausted"}]}},
            "audit": {"round": 1, "results": {"old": {"issues": []}}},
            "search_work": {"old-work": {"exhausted": True, "attempts": 3}},
            "efficiency": {"research_calls": 3},
            "active_work": [{"work": "旧待办"}], "active_topics": ["a"],
        })
    if staged:
        saved_state.update(staged_items=[field], staged_items_verified=True)
    else:
        saved_state["draft"] = {"fields": [field], "relations": []}
    repository = MagicMock(spec=ReportRepository)
    transaction = Mock(spec=ReportTransaction)
    repository.transaction.return_value.__enter__.return_value = transaction
    repository.resolved_config.return_value = {"analysis.max_tool_calls": 100}
    transaction.report_status.return_value = "partial"
    transaction.execution_active.return_value = False
    transaction.try_lock_execution.return_value = True
    transaction.other_active_report.return_value = None
    transaction.modules_for_retry.return_value = [{"id": 20, "status": "partial"}]
    transaction.report_has_modules.return_value = True
    transaction.module_attempt.return_value = 3
    # 仓储返回反序列化状态；新运行不能回写旧 attempt 的审计记录。
    transaction.previous_run_state.return_value = copy.deepcopy(saved_state)
    service = AnalysisService(repository, 1, Mock(), Mock(), Mock())
    monkeypatch.setattr(service, "report_row", lambda _: {
        "id": 27, "project_id": 10, "status": "partial", "runtime_version": RUNTIME_VERSION,
        "skill_snapshot": {"__analysis_flow_version__": "research-v3"},
        "coverage": {"mode": "agent_research"},
    })

    result = service.retry_report(
        27, module_keys=["project_basic_info_parsing"], max_output_tokens=None,
        timeout_seconds=None,
    )

    assert result == {"id": 27, "status": "pending"}
    arguments = transaction.insert_module_run.call_args.kwargs
    assert arguments["attempt"] == 3
    assert arguments["thread_id"] == "analysis:27:20:3"
    carried = arguments["state"]
    assert carried["staged_items"] == [field]
    assert carried["staged_items_verified"] is True
    assert "draft" not in carried
    assert carried["research_completed"] is True
    assert carried["research_summary"] == saved_state["research_summary"]
    assert carried["research"]["seen"] == saved_state["research"]["seen"]
    assert carried["research"]["events"] == saved_state["research"]["events"]
    assert carried["research"]["tool_calls"] == 0
    assert saved_state["research"]["tool_calls"] == previous_tool_calls
    if topic_flow:
        assert carried["topic_flow"]["entries"]["a"]["status"] == "researching"
        assert carried["topic_flow"]["entries"]["a"]["tasks"]["task"]["status"] == "pending"
        assert carried["topic_flow"]["entries"]["a"]["blocked_checks"] == []
        assert carried["topic_flow"]["entries"]["a"]["references"][0]["status"] == "missing"
        assert carried["topic_flow"]["audit"] == {"round": 0, "results": {}}
        assert not set(carried["topic_flow"]) & {
            "search_work", "efficiency", "active_work", "active_topics",
        }
        assert "topic_research_round" not in carried
        assert saved_state["topic_flow"]["search_work"]["old-work"]["exhausted"]

    async def run():
        research = ResearchSession(
            [source], 10, AsyncMock(), AsyncMock(), AsyncMock(),
            limits=AgentLimits(**arguments["limits"]), **carried["research"],
        )
        # 实际执行完整研究预算，验证不会在第 26 次或首次调用时提前失败。
        for _ in range(100):
            await research.documents()
        with pytest.raises(ValueError, match="工具调用预算"):
            await research.documents()
        assert research.tool_calls == 100

    asyncio.run(run())


def test_retry_preserves_examined_notes_todos_and_evidence_without_complete_findings():
    from test_analysis_compact_protocol import ledger
    from test_analysis_verification_degradation import _RetryStore, _RetryTx

    from tender.application.analysis.protocol import ResearchDelta, ResearchLedger
    from tender.application.analysis.topic_flow import TopicFlow

    book, flow, previous, research = ledger()
    work_id = book.works()[0]["id"]
    book.update([ResearchDelta(
        work_ids=[work_id], status="examined", detail="已读质保条款，还需核对附件例外",
        examined_ids=["s1r1c0"],
        followups=[{"detail": "核对附件例外", "from_block_id": "s1r1c0"}],
    )])
    previous["research"] = research.checkpoint() | {"tool_calls": 20}
    original = copy.deepcopy(previous)
    assert not flow.entries[0].get("findings") and not previous.get("staged_items")
    tx = _RetryTx([{"id": 9, "status": "failed"}], previous)
    service = AnalysisService(_RetryStore(tx), 1, Mock(), Mock(), Mock())
    service.retry_report(3, module_keys=[], max_output_tokens=None, timeout_seconds=None)
    carried = tx.inserted[0]["state"]
    assert carried["research"]["seen"] == previous["research"]["seen"]
    assert carried["research"]["tool_calls"] == 0
    assert carried["topic_flow"]["work_registry"] == previous["topic_flow"]["work_registry"]
    restored = ResearchLedger(TopicFlow(carried, research))
    assert restored.flow.entries[0]["dispositions"] == flow.entries[0]["dispositions"]
    assert restored.flow.entries[0]["tasks"] == flow.entries[0]["tasks"]
    assert restored.works()[0]["id"] == work_id
    assert "还需核对附件例外" in str(restored.context([work_id]))
    assert previous == original


def test_v3_retry_keeps_valid_packets_and_completed_topics_instead_of_restarting_research():
    from test_analysis_verification_degradation import _RetryStore, _RetryTx

    previous = {"topic_flow": {
        "audit": {"version": "combined-v3", "round": 1, "done": True,
                  "results": {"packet": {"reviews": {}, "issues": []}},
                  "record_results": {"record-fingerprint": {"supported": True}},
                  "completed_topics": {"1:a": {"signature": "same", "issues": []}}},
        "entries": {}, "phase": "review", "synthesis_finished": True,
    }}
    tx = _RetryTx([{"id": 9, "status": "partial"}], previous)
    service = AnalysisService(_RetryStore(tx), 1, Mock(), Mock(), Mock())
    service.retry_report(3, module_keys=[], max_output_tokens=None, timeout_seconds=None)
    flow = tx.inserted[0]["state"]["topic_flow"]
    assert flow["phase"] == "review"
    assert flow["audit"]["round"] == 0 and not flow["audit"]["done"]
    assert flow["audit"]["results"] == previous["topic_flow"]["audit"]["results"]
    assert flow["audit"]["completed_topics"] == {"0:a": {"signature": "same", "issues": []}}
    assert flow["audit"]["record_results"]["record-fingerprint"]["supported"]
