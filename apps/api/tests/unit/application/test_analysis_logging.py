"""用真实路由与 Agent 图验证诊断链路，避免日志存在但无法关联实际动作。"""

import asyncio
import json
import logging
from dataclasses import replace
from unittest.mock import Mock

import pytest
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs
from synthesis_fixtures import research_calls, submission, summary_record
from test_analysis_synthesis import execute
from test_deep_analysis import call
from test_llm_routing import _candidate, _ScriptedGateway

from tender.application.analysis import execution as deep_analysis
from tender.application.llm.routing import RoutingModel
from tender.core.logging import bind_context, get_context, get_logger
from tender.core.logging.formatters import make_formatter
from tender.domain.shared.errors import ModelUnavailable


@pytest.fixture
def executor():
    return deep_analysis.AnalysisExecutor(
        None, model_factory=Mock(), embedding_gateway=Mock(), rerank_gateway=Mock(),
        checkpoints=Mock(),
    )


@pytest.mark.parametrize("failover_limit", [1, 2])
def test_routing_logs_once_with_final_model_and_aggregated_usage(failover_limit):
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
        with bind_context(project_id=15, report_id=18):
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
    assert all(log["project_id"] == 15 and log["report_id"] == 18 for log in logs)
    assert len({log["invocation_id"] for log in logs}) == 1
    finished = [log for log in logs if log["event"] == "model.call"]
    assert len(finished) == 1
    assert len(records) == (2 if failover_limit == 1 else 3)
    assert finished[0]["status"] == ("error" if failover_limit == 1 else "ok")
    assert finished[0]["model_name"] == records[-1].model_key_snapshot
    assert finished[0]["duration_ms"] >= 0
    assert not any(
        log["event"].startswith("model.") and log["event"] != "model.call"
        for log in logs
    )
    if failover_limit == 1:
        assert finished[0]["input_tokens"] is None
        assert finished[0]["output_tokens"] is None
    else:
        assert finished[0]["input_tokens"] == 3
        assert finished[0]["output_tokens"] == 5
    assert "fixture-key" not in json.dumps(logs, ensure_ascii=False)
    assert "私密模型请求正文" not in json.dumps(logs, ensure_ascii=False)


def test_real_agent_logs_tool_parameters_once_with_research_synthesis_and_verification():
    async def check():
        with bind_context(project_id=15, report_id=18):
            return await execute([
                *research_calls(),
                call("submit_analysis", submission([summary_record()]), "finish"),
            ])

    with capture_logs(processors=[merge_contextvars]) as logs:
        state, _, _ = asyncio.run(check())
    assert state["draft"]["fields"]
    events = [log["event"] for log in logs]
    assert "skill.load" in events
    assert all(log["log_level"] == "info" for log in logs if log["event"] == "skill.load")
    assert events.count("review.result") == 1
    assert not any(event.endswith((".start", ".end", ".queued")) for event in events)
    phases = {log.get("agent_phase") for log in logs}
    assert {"research", "synthesis", "verification"} <= phases
    tools = [log for log in logs if log["event"] == "tool.call"]
    assert {"list_documents", "search_document", "complete_research", "submit_analysis"} <= {
        log["tool"] for log in tools
    }
    assert all(log["project_id"] == 15 and log["report_id"] == 18 for log in logs)
    assert all(log["duration_ms"] >= 0 for log in tools)
    assert all("tool_parameters" in log for log in tools)
    assert all("tool_call_id" not in log for log in tools)
    rounds = [log for log in logs if log["event"] == "agent.round"]
    assert rounds and all(log["log_level"] == "debug" for log in rounds)
    # 精简展示不能破坏工具消息与调用的绑定，恢复仍需按原 ID 重放。
    assert state["tool_results"]["call_finish"]["data"]["tool_call_id"] == "call_finish"
    assert any(
        log["tool"] == "search_document" and log["tool_parameters"] == {"query": "质保"}
        for log in tools
    )


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
    rejected = next(log for log in logs if log["event"] == "record.reject")
    assert rejected["item_id"] and rejected["correction_count"] == 1
    assert rejected["issues"] == "原文不支持该结论"
    assert rejected["log_level"] == "warning"


def test_parallel_modules_keep_context_in_child_tasks_and_threads(monkeypatch, executor):
    async def probe(report, module, sources):
        await asyncio.sleep(0)
        await asyncio.to_thread(
            get_logger(__name__).info, "thread_probe", expected_project=report["project_id"],
            expected_report=report["id"], expected_module=module["module_key"],
        )

    monkeypatch.setattr(executor, "_execute_module", probe)

    async def check():
        with bind_context(task_id="celery-parent"):
            await asyncio.gather(*(
                executor.execute_module(
                    {"id": project_id + 3, "project_id": project_id},
                    {"id": run_id, "module_key": module_key}, [],
                )
                for project_id in (15, 16)
                for run_id, module_key in ((99, "basic"), (100, "deposit"))
            ))
            assert get_context() == {"task_id": "celery-parent"}

    with capture_logs(processors=[merge_contextvars]) as logs:
        asyncio.run(check())
    assert len(logs) == 4
    assert all(log["project_id"] == log["expected_project"] for log in logs)
    assert all(log["report_id"] == log["expected_report"] for log in logs)
    assert all(log["module_key"] == log["expected_module"] for log in logs)
    assert all("run_id" not in log for log in logs)
    assert all(log["task_id"] == "celery-parent" for log in logs)


def test_handled_module_failure_logs_before_database_cleanup_without_raw_sdk_cause(
    monkeypatch, executor,
):
    # 多模型错误可能超过自动摘要的500字符，尾部的后备失败原因仍需在普通日志可见。
    reason = "上游断连（已脱敏）：" + "连接错误详情；" * 90 + "后备模型余额不足（HTTP 403）"

    class Runtime:
        def __init__(self, *args):
            self.run = {}

        def check_access(self):
            pass

        def claim(self):
            cause = RuntimeError("raw-sdk-secret")
            raise ModelUnavailable(reason) from cause

        def abandon(self, status, error):
            assert status == "failed"

        def release(self):
            pass

    monkeypatch.setattr(deep_analysis, "AgentRuntime", Runtime)
    with capture_logs(processors=[merge_contextvars]) as logs:
        asyncio.run(executor.execute_module({"id": 18, "project_id": 15}, {"id": 99}, []))
    failure = next(log for log in logs if log["event"] == "module.fail")
    assert failure["project_id"] == 15 and failure["report_id"] == 18
    assert "reason" not in failure
    assert failure["error"] == reason
    assert "run_id" not in failure and "ModelUnavailable" in failure["exception"]
    assert "上游断连" in failure["exception"] and "claim" in failure["exception"]
    assert "raw-sdk-secret" not in json.dumps(logs, ensure_ascii=False)
    entry = logging.makeLogRecord(failure | {
        "msg": failure["event"], "levelno": logging.ERROR, "levelname": "ERROR",
    })
    payload = json.loads(make_formatter(json_output=True, include_exception=False).format(entry))
    assert payload["error"] == reason and "reason" not in payload
    assert "exception" not in payload
