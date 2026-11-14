"""校验不可用时降级为 partial：只发布已核实成果，未验证条目绝不冒充通过。"""

import asyncio
import copy
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import accept, noop, research_calls, submission, summary_record
from test_analysis_research import block, session
from test_deep_analysis import KEY, SKILL, ScriptedRouter, call, submitted_field

from tender.application.analysis import execution as deep_analysis
from tender.application.analysis.agent import (
    RoutedAgentModel,
    VerificationUnavailable,
    build_module_agent,
    invoke_module,
)
from tender.application.analysis.contract import RUNTIME_VERSION
from tender.application.analysis.research import AgentLimits
from tender.application.analysis.runtime import AgentRuntime
from tender.application.analysis.service import AnalysisService
from tender.application.analysis.skills import MODULES
from tender.application.knowledge.content import validate_items
from tender.domain.shared.errors import InvalidModelOutput, ModelOutputTruncated, ModelUnavailable


class _Store:
    """AgentRunStore 的最小替身：只验证发布投影与终态，不依赖数据库。"""

    def __init__(self):
        self.guarded = 0
        self.finished: list[tuple[str, str | None, dict | None]] = []

    def guard(self):
        self.guarded += 1

    def finish(self, status, error, publish=None):
        self.finished.append((status, error, publish))


class _DB:
    def __init__(self, store):
        self.store = store

    def accessible_report_status(self, report_id):
        return "running"

    def collections_for_project(self, project_id):
        return set()

    def sources(self, allowed):
        return []

    def agent_run_store(self, report, run):
        return self.store


def run_partial_finish(state):
    store = _Store()
    runtime = AgentRuntime(_DB(store), {"id": 1, "project_id": 1}, {"id": 2}, [])
    runtime.finish("partial", "校验服务不可用", state=state)
    assert store.guarded == 1
    assert len(store.finished) == 1
    return store.finished[0]


async def run_graph(review, script):
    """跑真实 Agent 图；校验降级后 VerificationUnavailable 必须向上冒泡给执行器。"""
    state, saved = {}, []

    async def save(value):
        saved.append(copy.deepcopy(value))

    router = ScriptedRouter(script)
    graph, files = build_module_agent(
        key=KEY,
        model=RoutedAgentModel(router=router),
        research=session([block()]),
        state=state,
        snapshot=SKILL,
        checkpointer=InMemorySaver(),
        reserve_tool=noop,
        save=save,
        review_support=review,
    )
    with pytest.raises(VerificationUnavailable):
        await invoke_module(graph, files, thread_id="degraded", task="分析")
    assert not router.calls
    return state, saved


def test_verification_model_unavailable_publishes_supported_items_as_partial():
    async def run():
        reviews = []

        async def review(items):
            reviews.append(copy.deepcopy(items))
            if len(reviews) > 1:
                raise ModelUnavailable("校验网关不可用")
            await accept(items)

        state, saved = await run_graph(
            review,
            [
                *research_calls(),
                call(
                    "submit_analysis",
                    submission([summary_record(key="warranty")], final=False),
                    1,
                ),
                call(
                    "submit_analysis",
                    submission(
                        [summary_record(key="delivery", text="交货期为30日")], final=True
                    ),
                    2,
                ),
            ],
        )
        pending_ids = {item["id"] for item in reviews[1]}
        assert state["verification_degraded"]["pending_count"] == 1
        assert "校验网关不可用" in state["verification_degraded"]["reason"]
        # 未验证条目被丢弃，已核实条目原样保留；没有通过校验就不能生成 draft。
        assert [entry["verification"] for entry in state["staged_items"]] == ["supported"]
        assert not pending_ids & {entry["id"] for entry in state["staged_items"]}
        assert "draft" not in state
        assert {gap["key"] for gap in state["business_gaps"]} == {
            "record:" + item_id for item_id in pending_ids
        }
        assert "verification_degraded" in saved[-1]

        status, error, publish = run_partial_finish(state)
        assert status == "partial" and error
        assert publish is not None
        assert [item["field"] for item in publish["items"]] == ["质保期限"]
        assert [record["key"] for record in publish["business"]["records"]] == ["warranty"]
        assert not any(
            record["verification"] == "pending"
            for record in publish["business"]["records"]
        )

    asyncio.run(run())


def test_degraded_verification_drops_pending_items_and_records_gap():
    async def run():
        reviews = []

        async def review(items):
            reviews.append(copy.deepcopy(items))
            raise InvalidModelOutput("校验输出格式不可解析")

        state, _ = await run_graph(
            review,
            [
                *research_calls(),
                call(
                    "submit_analysis",
                    submission([summary_record(key="warranty")], final=True),
                    1,
                ),
            ],
        )
        pending_ids = {item["id"] for item in reviews[0]}
        assert not state.get("staged_items")
        assert state["verification_degraded"]["pending_count"] == len(pending_ids)
        gaps = {gap["key"]: gap for gap in state["business_gaps"]}
        assert set(gaps) == {"record:" + item_id for item_id in pending_ids}
        assert all(gap["code"] == "unknown_condition" for gap in gaps.values())
        assert "格式纠正" in state["verification_degraded"]["reason"]

    asyncio.run(run())


def test_invalid_verification_output_keeps_previous_verified_version():
    async def run():
        reviews = []

        async def review(items):
            reviews.append(copy.deepcopy(items))
            if len(reviews) > 1:
                raise InvalidModelOutput("校验输出格式不可解析")
            await accept(items)

        state, _ = await run_graph(
            review,
            [
                *research_calls(),
                call(
                    "submit_analysis",
                    submission([summary_record(key="warranty")], final=False),
                    1,
                ),
                call(
                    "submit_analysis",
                    submission(
                        [summary_record(key="warranty", text="质保期限为五年")], final=True
                    ),
                    2,
                ),
            ],
        )
        # 本次改写未通过校验时恢复上一版已核实内容，不能借降级删掉正确结论。
        assert len(state["staged_items"]) == 1
        entry = state["staged_items"][0]
        assert entry["verification"] == "supported"
        assert "质保期限为三年" in entry["values"][0]["value"]
        assert not state.get("business_gaps")
        assert "格式纠正" in state["verification_degraded"]["reason"]
        assert "draft" not in state

    asyncio.run(run())


def test_truncated_verification_degrades_after_three_smaller_batch_attempts():
    async def run():
        async def review(items):
            raise ModelOutputTruncated("校验输出达到token上限")

        state, _ = await run_graph(
            review,
            [
                *research_calls(),
                call(
                    "submit_analysis",
                    submission([summary_record(key="warranty")], final=False),
                    1,
                ),
                call(
                    "submit_analysis",
                    submission([summary_record(key="warranty")], final=False),
                    2,
                ),
                call(
                    "submit_analysis",
                    submission([summary_record(key="warranty")], final=True),
                    3,
                ),
            ],
        )
        assert state["unavailable_submissions"] == 3
        assert "token上限" in state["verification_degraded"]["reason"]
        assert not state.get("staged_items")
        assert state["business_gaps"][0]["code"] == "unknown_condition"

    asyncio.run(run())


def test_partial_finish_publishes_items_but_never_pending_items():
    async def run():
        research = session([block()])
        await research.search("质保", "project")
        supported, pending = validate_items(
            [submitted_field("已核实", "质保三年"), submitted_field("未核实", "质保三年")],
            research.seen,
        )
        supported["verification"] = "supported"
        pending["verification"] = "pending"
        state = {
            "staged_items": [supported, pending],
            "staged_items_verified": True,
            "staged_relations": [],
        }

        status, _, publish = run_partial_finish(state)
        assert status == "partial"
        assert [item["field"] for item in publish["items"]] == ["已核实"]
        assert pending["id"] not in str(publish)

    asyncio.run(run())


def test_no_supported_items_keeps_module_failed(monkeypatch):
    finished = []

    class Runtime:
        def __init__(self, db, report, module, sources):
            self.run = {
                "state": {},
                "limits": asdict(AgentLimits()),
                "thread_id": "thread",
                "deadline_at": datetime.now(UTC) + timedelta(seconds=60),
                "model_calls": 0,
                "tool_calls": 0,
            }

        def claim(self):
            return True

        def guard(self):
            pass

        def reserve(self, kind):
            pass

        def save(self, state):
            pass

        def event(self, kind, detail=None):
            pass

        def heartbeat(self):
            pass

        def finish(self, status, error=None, draft=None, *, state=None):
            finished.append(("finish", status))

        def abandon(self, status, error=None):
            finished.append(("abandon", status))

        def release(self):
            pass

    async def invoke(graph, files, *, state=None, **kwargs):
        state.update(
            staged_items=[{"id": "pending-1", "verification": "pending"}],
            verification_degraded={"pending_count": 1},
        )
        raise VerificationUnavailable("证据校验请求失败")

    @asynccontextmanager
    async def saver():
        yield None

    monkeypatch.setattr(deep_analysis, "AgentRuntime", Runtime)
    monkeypatch.setattr(deep_analysis, "build_module_agent", lambda **kwargs: (object(), {}))
    monkeypatch.setattr(deep_analysis, "invoke_module", invoke)
    executor = deep_analysis.AnalysisExecutor(
        db=Mock(),
        model_factory=Mock(return_value=AsyncMock()),
        embedding_gateway=Mock(),
        rerank_gateway=Mock(),
        checkpoints=saver,
    )
    asyncio.run(
        executor.execute_module(
            {
                "id": 5, "project_id": 1, "category": "goods",
                "source_snapshot": [], "reference_snapshot": [],
                "lot_settings": [], "topics": [], "skill_snapshot": {},
            },
            {"id": 7, "module_key": next(iter(MODULES)), "attempt": 1},
            [],
        )
    )
    # 一条可发布成果都没有时只能是 failed；“partial”必须有已核实内容。
    assert finished == [("abandon", "failed")]


class _RetryTx:
    def __init__(self, rows, previous):
        self.rows, self.previous = rows, previous
        self.retry_call = None
        self.reset = None
        self.pending = None
        self.inserted = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def lock_project(self, project_id):
        pass

    def report_status(self, report_id, lock=False):
        return "partial"

    def execution_active(self, report_id):
        return False

    def try_lock_execution(self, report_id):
        return True

    def other_active_report(self, project_id, report_id):
        return None

    def modules_for_retry(self, report_id, keys, *, explicit):
        self.retry_call = (report_id, keys, explicit)
        return self.rows

    def report_has_modules(self, report_id):
        return True

    def reset_modules(self, module_ids):
        self.reset = module_ids

    def mark_modules_pending(self, module_ids):
        self.pending = module_ids

    def module_attempt(self, module_id):
        return 2

    def previous_run_state(self, module_id):
        return copy.deepcopy(self.previous)

    def insert_module_run(self, **kwargs):
        self.inserted.append(kwargs)

    def update_report(self, report_id, values):
        self.report_update = values


class _RetryStore:
    def __init__(self, tx):
        self.tx = tx

    def report(self, report_id):
        return {
            "id": report_id, "project_id": 1, "status": "partial",
            "runtime_version": RUNTIME_VERSION,
            "skill_snapshot": {"__analysis_flow_version__": "research-v3"},
            "coverage": {"mode": "agent_research"},
        }

    def transaction(self):
        return self.tx

    def resolved_config(self):
        return {}


def test_partial_report_retry_selects_partial_modules():
    verified = {
        "id": "rec1", "field": "质保期限", "group": "",
        "values": [{
            "value": "质保三年",
            "citations": [{
                "block_id": "s1r1c0", "quote": "质保三年",
                "source_id": 1, "project_id": 1,
            }],
        }],
        "verification": "supported",
    }
    previous = {
        "staged_items": [verified],
        "staged_items_verified": True,
        "verification_degraded": {"reason": "旧降级", "pending_count": 1},
        "argument_failures": 4,
        "argument_failure_rounds": {"round": "r1", "tools": ["read_document"]},
        "evidence_budget_failures": 2,
        "failure_policy_version": 2,
        "model_unavailable_retries": 2,
    }
    tx = _RetryTx([{"id": 9, "status": "partial"}], previous)
    service = AnalysisService(
        _RetryStore(tx), 1, Mock(), Mock(), Mock(),
    )
    result = service.retry_report(
        3, module_keys=[], max_output_tokens=None, timeout_seconds=None
    )
    assert result["status"] == "pending"
    assert tx.retry_call == (3, list(MODULES), False)
    assert tx.reset == [] and tx.pending == [9]
    carried = tx.inserted[0]["state"]
    assert carried["staged_items"] == [verified]
    assert carried["staged_items_verified"] is True
    for key in (
        "verification_degraded",
        "argument_failures",
        "argument_failure_rounds",
        "evidence_budget_failures",
        "failure_policy_version",
        "model_unavailable_retries",
    ):
        assert key not in carried
