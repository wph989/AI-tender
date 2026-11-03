"""模型不可用时的同线程有界恢复：不换 attempt、不重置预算、耗尽后部分发布。"""

import json
import os

import pytest
import test_deepagents_runtime
from test_deepagents_runtime import (
    NativeRouter,
    prepared_runtime,
    publishable_state,
)

from tender.adapters.pg.analysis.checkpoints import run_async
from tender.application.analysis import execution as worker
from tender.domain.shared.errors import ModelUnavailable

# pytest 只在定义模块或 conftest 中发现 fixture，这里显式复用隔离 schema 环境。
env = test_deepagents_runtime.env

pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库集成验证"
)


def module_run(env, runtime):
    return env.db.rows(
        """SELECT a.*,m.module_key FROM agent_module_run a
        JOIN analysis_module m ON m.id=a.module_id WHERE a.id=:id""",
        {"id": runtime.run["id"]},
    )[0]


def install_flaky_router(monkeypatch, env, failures):
    """前 ``failures`` 次模型请求失败，其余走正常脚本；恢复等待缩到零便于测试。"""

    class FlakyRouter(NativeRouter):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.remaining = failures

        async def chat(self, messages, tools):
            if self.remaining:
                self.remaining -= 1
                await self.reserve()
                raise ModelUnavailable("网关不可用")
            return await super().chat(messages, tools)

    def factory(feature_key, purpose, **kwargs):
        return FlakyRouter(purpose=purpose, **kwargs)

    monkeypatch.setattr(env.executor, "model_factory", factory)
    monkeypatch.setattr(worker, "model_recovery_delay", lambda attempt, remaining: 0)


def test_model_unavailable_resumes_same_thread_with_bounded_attempts(env, monkeypatch):
    runtime = prepared_runtime(env)
    run = module_run(env, runtime)
    original_thread = run["thread_id"]
    install_flaky_router(monkeypatch, env, failures=2)

    run_async(env.executor.execute_module(runtime.report, run, runtime.sources))

    row = env.db.rows(
        "SELECT * FROM agent_module_run WHERE module_id=:id ORDER BY attempt",
        {"id": runtime.run["module_id"]},
    )
    assert len(row) == 1 and row[0]["attempt"] == 1
    assert row[0]["thread_id"] == original_thread
    assert row[0]["status"] == "completed"
    assert row[0]["state"]["model_unavailable_retries"] == 2
    module = env.db.rows(
        "SELECT status FROM analysis_module WHERE id=:id", {"id": runtime.run["module_id"]}
    )[0]
    assert module["status"] == "completed"
    events = env.db.rows(
        "SELECT detail FROM agent_run_event WHERE run_id=:id"
        " AND kind='model_unavailable_recovery' ORDER BY id",
        {"id": runtime.run["id"]},
    )
    assert [event["detail"]["attempt"] for event in events] == [1, 2]
    # 两次失败恢复同样占用模型预算，不能通过恢复获得额外请求次数。
    assert row[0]["model_calls"] == 6


def test_model_unavailable_exhaustion_finishes_partial_with_supported_items(env, monkeypatch):
    runtime = prepared_runtime(env)
    run = module_run(env, runtime)
    # 预置一条已核实成果：恢复耗尽后只能发布它，不能把模块记成 completed。
    seeded = publishable_state(run["module_key"])
    seeded["staged_items"] = [
        item for item in seeded["staged_items"] if item["verification"] == "supported"
    ]
    env.db.execute(
        "UPDATE agent_module_run SET state=CAST(:state AS JSONB) WHERE id=:id",
        {"id": run["id"], "state": json.dumps(seeded)},
    )
    run = module_run(env, runtime)
    install_flaky_router(monkeypatch, env, failures=10)

    run_async(env.executor.execute_module(runtime.report, run, runtime.sources))

    row = env.db.rows(
        "SELECT * FROM agent_module_run WHERE module_id=:id", {"id": runtime.run["module_id"]}
    )
    assert len(row) == 1 and row[0]["status"] == "partial"
    assert row[0]["state"]["model_unavailable_retries"] == 2
    module = env.db.rows(
        "SELECT * FROM analysis_module WHERE id=:id", {"id": runtime.run["module_id"]}
    )[0]
    assert module["status"] == "partial"
    assert [item["record_id"] for item in module["items"]] == ["keep"]
    assert [record["id"] for record in module["business_data"]["records"]] == ["keep"]


def test_model_unavailable_does_not_create_new_attempt_or_reset_budget(env, monkeypatch):
    runtime = prepared_runtime(env)
    run = module_run(env, runtime)
    env.db.execute(
        "UPDATE agent_module_run SET model_calls=5, tool_calls=7, prompt_tokens=100,"
        " completion_tokens=50 WHERE id=:id",
        {"id": run["id"]},
    )
    run = module_run(env, runtime)
    install_flaky_router(monkeypatch, env, failures=2)

    run_async(env.executor.execute_module(runtime.report, run, runtime.sources))

    rows = env.db.rows(
        "SELECT * FROM agent_module_run WHERE module_id=:id ORDER BY attempt",
        {"id": runtime.run["module_id"]},
    )
    # 恢复沿用同一次运行账，不创建新 attempt，也不清空已消耗预算（7 次工具 + Skill 与四个工具）。
    assert len(rows) == 1
    assert rows[0]["model_calls"] == 11
    assert rows[0]["tool_calls"] == 12
    assert rows[0]["prompt_tokens"] >= 100
    assert rows[0]["completion_tokens"] >= 50
