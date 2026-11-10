"""协议失败与恢复不能重新获得请求窗口；业务否决仍是成功调用。"""

import asyncio
import copy
import json
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from test_llm_routing import _candidate, _ScriptedGateway

from tender.application.llm.routing import RoutingModel
from tender.domain.shared.errors import (
    InvalidModelOutput,
    ModelBudgetExhausted,
    ModelCallFailed,
    ModelUnavailable,
)


class InvocationStore:
    def __init__(self):
        self.rows = {}

    def load_invocation(self, key):
        return copy.deepcopy(self.rows.get(key, {}))

    def save_invocation(self, key, value):
        self.rows[key] = copy.deepcopy(value)


def test_protocol_validation_runs_before_success_and_shares_configured_retries():
    records, validations = [], []
    gateway = _ScriptedGateway({"a": [None, None], "b": [None]})
    model = RoutingModel(
        "analysis", "fixture", [replace(_candidate("a", 1), extra_retries=1)],
        gateway, records.append,
    )

    def validate(completion):
        validations.append(completion.content)
        if len(validations) == 1:
            raise InvalidModelOutput("reviews 缺少本包ID")

    asyncio.run(model.complete_validated("审查", validate=validate, call_key="packet"))
    assert [r.status for r in records] == ["error", "ok"]
    assert [r.request_ordinal for r in records] == [1, 2]
    assert len({r.invocation_id for r in records}) == 1
    assert "reviews 缺少本包ID" in gateway.prompts[1]


def test_zero_extra_retries_does_not_secretly_add_format_corrections():
    records = []
    model = RoutingModel(
        "analysis", "fixture", [_candidate("a", 1)],
        _ScriptedGateway({"a": [InvalidModelOutput("格式错误"), None]}), records.append,
    )
    with pytest.raises(ModelCallFailed):
        asyncio.run(model.complete("审查"))
    assert len(records) == 1


def test_exhausted_invocation_is_not_reopened_by_new_router():
    store, records = InvocationStore(), []
    for _ in range(2):
        gateway = _ScriptedGateway({"a": [ModelUnavailable("504", http_status=504)] * 3})
        model = RoutingModel(
            "analysis", "fixture", [replace(_candidate("a", 1), extra_retries=2)],
            gateway, records.append, max_total_requests=2, retry_base_seconds=0,
            invocation_store=store,
        )
        with pytest.raises((ModelCallFailed, ModelUnavailable)):
            asyncio.run(model.complete_validated("审查", call_key="same-packet"))
    assert len(records) == 2
    assert [r.request_ordinal for r in records] == [1, 2]


def test_validated_business_rejection_is_cached_across_router_recreation():
    store, records = InvocationStore(), []
    for _ in range(2):
        gateway = _ScriptedGateway({"a": [None]})
        model = RoutingModel(
            "analysis", "fixture", [_candidate("a", 1)], gateway, records.append,
            invocation_store=store,
        )
        result = asyncio.run(model.complete_validated(
            "审查", call_key="same-packet", validate=lambda c: json.loads(c.content),
        ))
        assert json.loads(result.content) == {"ok": True}
    assert len({(r.invocation_id, r.request_ordinal) for r in records}) == 1


def test_rate_limited_sends_have_unique_ordinals_and_obey_total_request_limit():
    records = []
    model = RoutingModel(
        "analysis", "fixture", [replace(_candidate("a", 1), extra_retries=4)],
        _ScriptedGateway({"a": [ModelUnavailable("限流", http_status=429)] * 5}),
        records.append, max_total_requests=2,
        rate_limit_backoff_seconds=0, rate_limit_max_wait_seconds=1,
    )
    with pytest.raises((ModelCallFailed, ModelUnavailable)):
        asyncio.run(model.complete("审查"))
    assert [r.request_ordinal for r in records] == [1, 2]


def test_cancel_during_reservation_preserves_identity_and_frozen_retry_policy():
    async def run():
        store, records, reservations = InvocationStore(), [], []
        entered, release = asyncio.Event(), asyncio.Event()

        async def before(record):
            reservations.append(record.request_ordinal)
            entered.set()
            await release.wait()

        gateway = _ScriptedGateway({"a": [None]})
        first = RoutingModel(
            "analysis", "fixture", [replace(_candidate("a", 1), extra_retries=1)],
            gateway, records.append, invocation_store=store, before_call=before,
            max_total_requests=2,
        )
        task = asyncio.create_task(first.complete_validated("审查", call_key="packet"))
        await entered.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not gateway.prompts
        assert records[0].request_ordinal == 1 and records[0].status == "error"
        second = RoutingModel(
            "analysis", "fixture", [replace(_candidate("a", 1), extra_retries=0)],
            gateway, records.append, invocation_store=store, max_total_requests=1,
        )
        await second.complete_validated("审查", call_key="packet")
        assert [r.request_ordinal for r in records] == [1, 2]
        assert len({r.invocation_id for r in records}) == 1

    asyncio.run(run())


def test_protocol_error_then_timeout_share_one_window_and_token_ledger():
    records, validations = [], []
    model = RoutingModel(
        "analysis", "fixture", [replace(_candidate("a", 1), extra_retries=3)],
        _ScriptedGateway({"a": [None, ModelUnavailable("504", http_status=504), None]}),
        records.append, max_total_requests=2, retry_base_seconds=0,
    )

    def reject(completion):
        validations.append(completion)
        raise InvalidModelOutput("缺少判定ID")

    with pytest.raises(ModelCallFailed):
        asyncio.run(model.complete_validated("审查", validate=reject))
    assert [r.request_ordinal for r in records] == [1, 2]
    assert [r.status for r in records] == ["error", "error"]
    assert len(validations) == 1
    assert len({r.invocation_id for r in records}) == 1


def test_checkpoint_resume_does_not_reopen_window_when_budget_hint_changes():
    from types import SimpleNamespace

    async def chat(**kwargs):
        raise ModelUnavailable("504", http_status=504)

    store, records = InvocationStore(), []
    for seconds in (100, 50):
        model = RoutingModel(
            "analysis", "fixture", [_candidate("a", 1)],
            lambda *args, **kwargs: SimpleNamespace(chat=chat),
            records.append, invocation_store=store,
        )
        with pytest.raises((ModelCallFailed, ModelUnavailable)):
            asyncio.run(model.chat([
                {"type": "system", "data": {"content": f"剩余{seconds}秒"}},
                {"type": "human", "data": {"id": "checkpoint-1", "content": "研究原文"}},
            ], []))
    assert len(records) == 1


@pytest.mark.parametrize("budget_error", [False, True])
def test_exhausted_window_preserves_failure_class_and_deadline_after_router_recreation(
    budget_error,
):
    async def run():
        store, records = InvocationStore(), []
        error_type = ModelBudgetExhausted if budget_error else ModelUnavailable
        first = RoutingModel(
            "analysis", "fixture", [_candidate("a", 1)],
            _ScriptedGateway({"a": [ModelUnavailable("上游504", http_status=504)]}),
            records.append, invocation_store=store,
            remaining_seconds=(lambda: 0) if budget_error else None,
        )
        with pytest.raises(error_type):
            await first.complete_validated("审查", call_key="packet")
        original = copy.deepcopy(store.rows)
        second = RoutingModel(
            "analysis", "fixture", [_candidate("a", 1)],
            _ScriptedGateway({"a": [None]}), records.append, invocation_store=store,
        )
        with pytest.raises(error_type):
            await second.complete_validated("审查", call_key="packet")
        assert store.rows == original
        assert len(records) == (0 if budget_error else 1)

    asyncio.run(run())


def test_legacy_exhausted_window_uses_incomplete_settlement_without_a_new_request():
    store, records = InvocationStore(), []
    store.rows["packet"] = {"exhausted": True, "error": "上游504", "deadline_at": 12345,
                            "requests": [{"ordinal": 1}]}
    original = copy.deepcopy(store.rows)
    model = RoutingModel(
        "analysis", "fixture", [_candidate("a", 1)], _ScriptedGateway({"a": [None]}),
        records.append, invocation_store=store,
    )
    with pytest.raises(ModelBudgetExhausted, match="上游504"):
        asyncio.run(model.complete_validated("审查", call_key="packet"))
    assert not records and store.rows == original


@pytest.mark.parametrize("has_results", [False, True])
def test_executor_settles_restored_unavailable_window_without_losing_verified_results(
    monkeypatch, has_results,
):
    from synthesis_fixtures import summary_record
    from test_analysis_combined_review import execute

    from tender.application.analysis import execution
    from tender.application.analysis.research import AgentLimits
    from tender.application.analysis.skills import skill_snapshot
    from tender.application.analysis.state import published_items

    async def run():
        state, _, _, _ = await execute([summary_record()])
        state.pop("draft", None)
        if not has_results:
            state["staged_items"] = []
        records, store = [], InvocationStore()
        gateway = _ScriptedGateway({"a": [ModelUnavailable("上游504", http_status=504)]})
        router = RoutingModel("analysis", "fixture", [_candidate("a", 1)], gateway,
                              records.append, invocation_store=store)
        with pytest.raises(ModelUnavailable):
            await router.complete_validated("研究下一事项", call_key="checkpoint")
        original = copy.deepcopy(store.rows)
        runtime = Mock()
        runtime.run = {"state": state, "limits": asdict(AgentLimits()), "thread_id": "same",
                       "deadline_at": datetime.now(UTC) + timedelta(seconds=300)}
        runtime.store = store

        @asynccontextmanager
        async def checkpoints():
            yield None

        async def invoke(*args, **kwargs):
            await router.complete_validated("研究下一事项", call_key="checkpoint")

        async def claimed(*args):
            pass

        monkeypatch.setattr(execution, "AgentRuntime", lambda *args: runtime)
        monkeypatch.setattr(execution, "wait_for_claim", claimed)
        monkeypatch.setattr(execution, "build_module_agent", lambda **kwargs: (None, None))
        monkeypatch.setattr(execution, "invoke_module", invoke)
        monkeypatch.setattr(execution, "model_recovery_delay", lambda *args: 0)
        executor = execution.AnalysisExecutor(
            None, model_factory=lambda *args, **kwargs: router,
            embedding_gateway=Mock(), rerank_gateway=Mock(), checkpoints=checkpoints,
        )
        report = {"id": 1, "project_id": 1, "category": "engineering", "topics": [],
                  "lot_settings": [], "skill_snapshot": skill_snapshot()
                  | {"__analysis_flow_version__": "research-v3"}}
        await executor.execute_module(report, {"module_key": "project_basic_info_parsing",
                                               "attempt": 1}, [])
        runtime.abandon.assert_not_called()
        runtime.finish.assert_called_once_with(
            "partial" if has_results else "failed", "上游504", state=state,
        )
        assert len(published_items(state, final=True)) == int(has_results)
        assert len(records) == 1 and store.rows == original
        assert not any(call.args[0] == "model_unavailable_recovery"
                       for call in runtime.event.call_args_list)

    asyncio.run(run())
