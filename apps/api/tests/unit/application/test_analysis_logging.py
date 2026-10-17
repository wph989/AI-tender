"""用真实路由与 Agent 图验证诊断链路，避免日志存在但无法关联实际动作。"""

import asyncio
import json
from dataclasses import replace

import pytest
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs
from synthesis_fixtures import research_calls, submission, summary_record
from test_analysis_synthesis import execute
from test_deep_analysis import call
from test_llm_routing import _candidate, _ScriptedGateway

from tender.application.llm_routing import RoutingModel
from tender.core.logging import bind_context, get_context, get_logger
from tender.domain.errors import ModelUnavailable
from tender.worker import deep_analysis


@pytest.mark.parametrize("failover_limit", [1, 2])
def test_routing_logs_explain_retry_failover_and_disabled_fallback(failover_limit):
    records = []
    router = RoutingModel(
        "analysis", "analysis:18:personnel:4",
        [replace(_candidate("primary", 1), extra_retries=1, api_key="fixture-key"),
         _candidate("backup", 2)],
        _ScriptedGateway({"primary": [ModelUnavailable("disconnect fixture-key")] * 2,
                          "backup": [None]}),
        records.append, failover_limit=failover_limit, retry_base_seconds=0,
    )

    async def check():
        with bind_context(report_id=18, run_id=99):
            try:
                if failover_limit == 1:
                    with pytest.raises(ModelUnavailable):
                        await router.complete("私密模型请求正文")
                else:
                    assert (await router.complete("私密模型请求正文")).model == "backup"
            finally:
                await router.aclose()
        assert get_context() == {}

    with capture_logs(processors=[merge_contextvars]) as logs:
        asyncio.run(check())
    assert all(log["run_id"] == 99 and log["report_id"] == 18 for log in logs)
    assert len({log["invocation_id"] for log in logs}) == 1
    finished = [log for log in logs if log["event"] == "model_request_finished"]
    assert len(finished) == len(records) == (2 if failover_limit == 1 else 3)
    assert [log["request_ordinal"] for log in finished] == list(range(1, len(records) + 1))
    assert len([log for log in logs if log["event"] == "model_retry_scheduled"]) == 1
    failovers = [log for log in logs if log["event"] == "model_failover"]
    if failover_limit == 1:
        assert not failovers
        assert logs[-1]["reason"] == "candidate_limit_reached"
        assert logs[-1]["failover_limit"] == 1
    else:
        assert failovers[0]["from_model_id"] == 1 and failovers[0]["to_model_id"] == 2
    assert "fixture-key" not in json.dumps(logs, ensure_ascii=False)
    assert "私密模型请求正文" not in json.dumps(logs, ensure_ascii=False)


def test_real_agent_logs_tools_research_synthesis_and_verification_without_document_text():
    async def check():
        with bind_context(report_id=18, run_id=99):
            return await execute([
                *research_calls(),
                call("submit_analysis", submission([summary_record()]), "finish"),
            ])

    with capture_logs(processors=[merge_contextvars]) as logs:
        state, _, _ = asyncio.run(check())
    assert state["draft"]["fields"]
    events = [log["event"] for log in logs]
    assert "analysis_skill_loaded" in events
    assert "analysis_review_started" in events and "analysis_review_finished" in events
    phases = {log.get("agent_phase") for log in logs}
    assert {"research", "synthesis", "verification"} <= phases
    tools = [log for log in logs if log["event"] == "analysis_tool_finished"]
    assert {"list_documents", "search_document", "complete_research", "submit_analysis"} <= {
        log["tool"] for log in tools
    }
    assert any(log["new_evidence_count"] > 0 for log in tools)
    assert all(log["run_id"] == 99 and log["report_id"] == 18 for log in logs)
    assert all(log["duration_ms"] >= 0 for log in tools)
    assert "质保三年" not in json.dumps(logs, ensure_ascii=False)


def test_validation_rejection_logs_item_reason_and_correction_count():
    async def reject(items):
        for item in items:
            item.update(verification="unsupported", verification_issues=["原文不支持该结论"])

    with capture_logs(processors=[merge_contextvars]) as logs:
        asyncio.run(execute([
            *research_calls(),
            call("submit_analysis", submission([summary_record()], final=False), "bad"),
            call("submit_analysis", submission(), "finish"),
        ], review=reject))
    rejected = next(log for log in logs if log["event"] == "analysis_record_rejected")
    assert rejected["item_id"] and rejected["correction_count"] == 1
    assert rejected["issues"] == "原文不支持该结论"
    assert rejected["log_level"] == "warning"


def test_parallel_modules_keep_context_in_child_tasks_and_threads(monkeypatch):
    async def probe(db, report, module, sources):
        await asyncio.sleep(0)
        await asyncio.to_thread(get_logger(__name__).info, "thread_probe", expected=module["id"])

    monkeypatch.setattr(deep_analysis, "_execute_module", probe)

    async def check():
        with bind_context(task_id="celery-parent"):
            await asyncio.gather(*(
                deep_analysis.execute_module(None, {"id": 18}, {"id": run_id}, [])
                for run_id in (99, 100)
            ))
            assert get_context() == {"task_id": "celery-parent"}

    with capture_logs(processors=[merge_contextvars]) as logs:
        asyncio.run(check())
    assert len(logs) == 2
    assert all(log["run_id"] == log["expected"] for log in logs)
    assert all(log["task_id"] == "celery-parent" for log in logs)


def test_handled_module_failure_logs_before_database_cleanup_without_raw_sdk_cause(monkeypatch):
    class Runtime:
        def __init__(self, *args):
            pass

        def claim(self):
            cause = RuntimeError("raw-sdk-secret")
            raise ModelUnavailable("上游断连（已脱敏）") from cause

        def abandon(self, status, error):
            assert status == "failed"

        def release(self):
            pass

    monkeypatch.setattr(deep_analysis, "AgentRuntime", Runtime)
    with capture_logs(processors=[merge_contextvars]) as logs:
        asyncio.run(deep_analysis.execute_module(None, {"id": 18}, {"id": 99}, []))
    failure = next(log for log in logs if log["event"] == "analysis_module_failed")
    assert failure["run_id"] == 99 and failure["error_type"] == "ModelUnavailable"
    assert "上游断连" in failure["error"] and "claim" in failure["exception"]
    assert "raw-sdk-secret" not in json.dumps(logs, ensure_ascii=False)
