"""单Agent同线程恢复：不换attempt、不重置预算、中断不发布草稿。"""

import json
import os

import pytest
import test_deepagents_runtime
from test_deepagents_runtime import (
    NativeRouter,
    draft_state,
    prepared_runtime,
)

from tender.adapters.pg.analysis.checkpoints import run_async
from tender.application.analysis import execution as worker
from tender.application.analysis.runtime import AgentRuntime
from tender.domain.shared.errors import ModelUnavailable

# pytest 只在定义模块或 conftest 中发现 fixture，这里显式复用隔离 schema 环境。
env = test_deepagents_runtime.env


def compact_runtime(env):
    """恢复专项使用当前协议，避免以旧工具替身掩盖真实装配变化。"""
    return prepared_runtime(env)


def verified_state(key):
    from tender.application.analysis.drafts import AGENT_PROTOCOL

    state = draft_state(key)
    state["agent_workspace"] = {"protocol": AGENT_PROTOCOL, "reviews": {}, "issues": {},
        "notes": {}, "history": [], "finalized": False, "final_ids": []}
    for item in state["staged_items"]:
        item["draft_version"] = 1
    return state


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
    runtime = compact_runtime(env)
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
    assert row[0]["model_calls"] == 6  # 两次失败和四次主模型，无独立审查。


def test_model_unavailable_exhaustion_finishes_partial_with_supported_items(env, monkeypatch):
    runtime = compact_runtime(env)
    run = module_run(env, runtime)
    # 预置草稿：恢复耗尽后保留检查点，正式结果仍为空。
    seeded = verified_state(run["module_key"])
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
    assert not module["business_data"].get("records")
    assert row[0]["state"]["staged_items"][0]["id"] == "keep"


def test_model_unavailable_does_not_create_new_attempt_or_reset_budget(env, monkeypatch):
    runtime = compact_runtime(env)
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
    assert rows[0]["model_calls"] == 11  # 旧预算五次加本轮六次。
    assert rows[0]["tool_calls"] == 11
    assert rows[0]["prompt_tokens"] >= 100
    assert rows[0]["completion_tokens"] >= 50


@pytest.mark.parametrize("used", [1, 2])
def test_worker_restart_keeps_persisted_model_recovery_limit(env, monkeypatch, used):
    runtime = compact_runtime(env)
    run = module_run(env, runtime)
    state = verified_state(run["module_key"])
    state["staged_items"] = [i for i in state["staged_items"] if i["verification"] == "supported"]
    state["model_unavailable_retries"] = used
    # 模拟原Worker已持久化恢复次数，后续执行者接管同一个attempt。
    env.db.execute(
        "UPDATE agent_module_run SET state=CAST(:state AS JSONB),model_calls=5 WHERE id=:id",
        {"id": run["id"], "state": json.dumps(state)},
    )
    run = module_run(env, runtime)
    install_flaky_router(monkeypatch, env, failures=10)
    run_async(env.executor.execute_module(runtime.report, run, runtime.sources))
    row = module_run(env, runtime)
    assert row["status"] == "partial" and row["attempt"] == 1
    assert row["state"]["model_unavailable_retries"] == 2
    assert row["model_calls"] == 5 + (3 - used)
    events = env.db.rows(
        "SELECT detail FROM agent_run_event WHERE run_id=:id "
        "AND kind='model_unavailable_recovery' ORDER BY id",
        {"id": run["id"]},
    )
    assert [event["detail"]["attempt"] for event in events] == list(range(used + 1, 3))


@pytest.mark.parametrize("boundary", ["research_update", "draft", "review", "edit", "final"])
def test_saved_business_update_resumes_graph_without_reapplying_or_resettling(
    env, monkeypatch, boundary,
):
    """真实工具事务成功但图未收到回执；恢复复用回执并保持版本及账本。"""
    from langchain_core.messages import AIMessage, message_to_dict

    from tender.ports.llm.chat import Completion

    runtime = compact_runtime(env)
    run = module_run(env, runtime)
    original_save = AgentRuntime.save
    interrupted, deadlines = [], []
    target = {"research_update": 3, "draft": 4, "review": 5, "edit": 6, "final": 8}[boundary]

    def save(active, state):
        original_save(active, state)
        deadlines.append(active.run["deadline_at"])
        if not interrupted and f"call{target}" in state.get("tool_results", {}):
            interrupted.append(True)
            raise ConnectionError("故障注入：工具事务提交后响应中断")

    class DraftRouter(NativeRouter):
        async def chat(self, messages, tools):
            if self.calls < 3:
                return await super().chat(messages, tools)
            await self.reserve()
            self.calls += 1
            bid = next(block["id"] for m in messages if m["type"] == "tool"
                       and m["data"].get("name") == "search_document"
                       for block in json.loads(m["data"]["content"])["blocks"])
            row = {"kind": "fact", "group": "项目基本信息",
                   "content": {"字段": "质保", "内容": "三年"},
                   "scope": {"kind": "common"}, "block_ids": [bid]}
            if self.calls == 4:
                name, args = "submit_analysis", {"records": [row]}
            else:
                receipt = next(json.loads(m["data"]["content"])["accepted"][0]
                    for m in reversed(messages) if m["type"] == "tool"
                    and m["data"].get("name") == "submit_analysis")
                if self.calls == 6:
                    name, args = "submit_analysis", {"records": [row | {
                        "id": receipt["id"], "version": receipt["version"],
                        "content": {"字段": "质保期限", "内容": "三年"},
                    }]}
                elif self.calls in {5, 7}:
                    name, args = "record_review", {"records": [{
                        "record_id": receipt["id"], "version": receipt["version"],
                        "status": "passed", "reason": "对照原文核对期限", "block_ids": [bid],
                    }]}
                else:
                    name, args = "submit_analysis", {"final": True,
                        "record_ids": [receipt["id"]], "summary": "已完成质保核对"}
            return self.respond(Completion(content="", model="fixture",
                agent_message=message_to_dict(AIMessage(content="", tool_calls=[{
                    "name": name, "id": f"call{self.calls}", "args": args,
                }]))))

        async def complete(self, prompt):
            raise AssertionError("不得调用独立审查模型")

    monkeypatch.setattr(AgentRuntime, "save", save)
    monkeypatch.setattr(env.executor, "model_factory",
                        lambda feature, purpose, **kw: DraftRouter(purpose=purpose, **kw))
    run_async(env.executor.execute_module(runtime.report, run, runtime.sources))
    row = module_run(env, runtime)
    assert row["status"] == "completed", row["error_message"]
    assert interrupted
    assert row["attempt"] == 1 and row["thread_id"] == run["thread_id"]
    assert len(set(deadlines)) == 1
    assert len(row["state"]["staged_items"]) == 1
    assert row["state"]["staged_items"][0]["draft_version"] == 2
    assert [e["event"] for e in row["state"]["agent_workspace"]["history"]] == [
        "draft", "review", "draft", "review",
    ]
    assert row["state"]["subagent_retries"] == 1
    attempts = env.db.rows("SELECT * FROM agent_call_attempt WHERE run_id=:id",
                           {"id": run["id"]})
    assert not any(r["status"] == "pending" for r in attempts)
    assert row["successful_tool_calls"] == 8
    assert row["successful_tool_calls"] == sum(
        r["kind"] == "tool" and r["status"] == "ok" for r in attempts)
    module = env.db.rows("SELECT business_data FROM analysis_module WHERE id=:id",
                         {"id": run["module_id"]})[0]
    assert module["business_data"]["records"][0]["content"] == {"字段": "质保期限", "内容": "三年"}
