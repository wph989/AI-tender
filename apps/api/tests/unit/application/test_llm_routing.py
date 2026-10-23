"""失败转移：按优先级降级、记录每次调用、候选耗尽后的错误分类。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import pytest

from tender.application.llm.routing import CallRecord, ModelCandidate, RoutingModel
from tender.domain.shared.errors import (
    InvalidModelOutput,
    ModelCallFailed,
    ModelOutputTruncated,
    ModelRefused,
    ModelUnavailable,
    TenderError,
)
from tender.ports.llm.chat import ChatGateway, Completion


class _ScriptedClient:
    """按脚本执行：脚本项是异常就抛出，否则返回成功补全。"""

    def __init__(self, model: str, script: list[Any], prompts: list[str]) -> None:
        self.model = model
        self.script = script
        self.prompts = prompts
        self.closed = False

    async def complete(self, prompt: str) -> Completion:
        self.prompts.append(prompt)
        action = self.script.pop(0) if self.script else ModelCallFailed("脚本用尽")
        if isinstance(action, Exception):
            raise action
        return Completion(
            content='{"ok": true}',
            model=self.model,
            prompt_tokens=3,
            completion_tokens=5,
        )

    async def list_models(self) -> list[str]:
        return []

    async def aclose(self) -> None:
        self.closed = True


class _ScriptedGateway:
    """按模型名分派脚本，并记录建了几次客户端（验证连接复用）。"""

    def __init__(self, scripts: dict[str, list[Any]]) -> None:
        self._scripts = scripts
        self.created: list[str] = []
        self.prompts: list[str] = []

    def __call__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 90,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatGateway:
        self.created.append(model)
        return _ScriptedClient(model, list(self._scripts.get(model, [])), self.prompts)


def _candidate(model: str, registry_id: int) -> ModelCandidate:
    return ModelCandidate(
        registry_model_id=registry_id,
        provider_id=registry_id,
        display_name=model,
        model=model,
        base_url="http://gateway",
        api_key=None,
        timeout=1,
        temperature=None,
        max_tokens=None,
        extra_retries=0,
    )


def _run(
    candidates: Sequence[ModelCandidate],
    scripts: dict[str, list[Any]],
    feature: str = "analysis",
) -> tuple[Completion, list[CallRecord], _ScriptedGateway]:
    records: list[CallRecord] = []
    gateway = _ScriptedGateway(scripts)
    model = RoutingModel(feature, feature, candidates, gateway, records.append)
    completion = asyncio.run(model.complete("prompt"))
    asyncio.run(model.aclose())
    return completion, records, gateway


def test_failover_moves_to_next_priority_and_records_both_attempts() -> None:
    completion, records, _ = _run(
        [_candidate("bad", 1), _candidate("good", 2)],
        {
            "bad": [ModelUnavailable("网关 503", http_status=503)],
            "good": [None],
        },
    )

    assert completion.registry_model_id == 2
    assert completion.model == "good"
    assert [(record.model_id, record.status) for record in records] == [(1, "error"), (2, "ok")]
    assert records[0].http_status == 503
    assert records[1].prompt_tokens == 3


def test_all_unavailable_raises_unavailable_for_job_level_retry() -> None:
    """全是暂时不可用时交给 worker 退避重试，而不是把字段判死。"""
    with pytest.raises(ModelUnavailable):
        _run(
            [_candidate("a", 1), _candidate("b", 2)],
            {
                "a": [ModelUnavailable("超时", http_status=504)],
                "b": [ModelUnavailable("限流", http_status=503)],
            },
        )


def test_final_error_includes_each_candidate_reason_without_exposing_credentials():
    candidates = [replace(_candidate("a", 1), api_key="fixture-key"), _candidate("b", 2)]
    gateway = _ScriptedGateway({
        "a": [ModelUnavailable("渠道失效 fixture-key", http_status=503)],
        "b": [ModelCallFailed("账户余额不足", http_status=403)],
    })
    model = RoutingModel("analysis", "analysis", candidates, gateway, lambda record: None)
    try:
        with pytest.raises(ModelCallFailed) as error:
            asyncio.run(model.complete("解析"))
        assert "渠道失效" in str(error.value) and "账户余额不足" in str(error.value)
        assert "fixture-key" not in str(error.value)
    finally:
        asyncio.run(model.aclose())


def test_call_record_preserves_long_upstream_details_and_hides_candidate_key():
    records: list[CallRecord] = []
    detail = "网关返回 HTTP 429\n" + "x" * 1000 + "\n额度不足 request_id=upstream-123"
    gateway = _ScriptedGateway({"a": [ModelUnavailable(detail + " fixture-key", http_status=429)]})
    model = RoutingModel(
        "analysis", "analysis", [replace(_candidate("a", 1), api_key="fixture-key")],
        gateway, records.append,
        # 本用例只核对落账正文；等待额度设为 0，不重发也不真等 30 秒。
        rate_limit_backoff_seconds=0, rate_limit_max_wait_seconds=0,
    )
    try:
        with pytest.raises(ModelUnavailable):
            asyncio.run(model.complete("分析"))
    finally:
        asyncio.run(model.aclose())
    assert len(records) == 1
    assert records[0].http_status == 429
    assert detail in records[0].error_message
    assert "fixture-key" not in records[0].error_message


def test_invalid_json_is_corrected_before_trying_an_unavailable_fallback():
    completion, records, gateway = _run(
        [_candidate("a", 1), _candidate("b", 2)],
        {"a": [InvalidModelOutput("非法 JSON"), None], "b": [ModelUnavailable("超时")]},
    )
    assert completion.model == "a"
    assert gateway.created == ["a"]
    assert [record.status for record in records] == ["error", "ok"]
    assert gateway.prompts[0] == "prompt"
    assert "上次响应不符合 JSON 协议" in gateway.prompts[1]
    assert "非法 JSON" in gateway.prompts[1]
    assert "action" not in gateway.prompts[1]


def test_invalid_json_exhausts_two_corrections_then_fails_over():
    completion, records, _ = _run(
        [_candidate("a", 1), _candidate("b", 2)],
        {"a": [InvalidModelOutput("非法 JSON")] * 3, "b": [None]},
    )
    assert completion.model == "b"
    assert [record.model_id for record in records] == [1, 1, 1, 2]


def test_output_truncation_fails_over_without_repeating_same_output_budget():
    completion, records, _ = _run(
        [_candidate("a", 1), _candidate("b", 2)],
        {"a": [ModelOutputTruncated("输出额度耗尽")], "b": [None]},
    )
    assert completion.model == "b"
    assert [record.model_id for record in records] == [1, 2]


def test_format_correction_does_not_reset_total_request_budget():
    records = []
    router = RoutingModel(
        "analysis",
        "analysis",
        [_candidate("a", 1), _candidate("b", 2)],
        _ScriptedGateway({name: [InvalidModelOutput("非法 JSON")] * 3 for name in "ab"}),
        records.append,
    )
    from tender.application.analysis.skills import json_completion

    with pytest.raises(ModelCallFailed):
        asyncio.run(json_completion(router, "分析"))
    assert len(records) == 6
    assert len({record.invocation_id for record in records}) == 1


def test_mixed_failure_raises_failed_so_field_goes_to_review() -> None:
    """只要有一次是明确拒绝，重试没有意义，按字段失败处理。"""
    with pytest.raises(ModelCallFailed, match="拒绝"):
        _run(
            [_candidate("a", 1), _candidate("b", 2)],
            {
                "a": [ModelCallFailed("拒绝", http_status=401)],
                "b": [ModelUnavailable("限流")],
            },
        )


def test_without_candidates_reports_feature_name() -> None:
    gateway = _ScriptedGateway({})
    model = RoutingModel("analysis", "analysis", [], gateway, lambda record: None)

    with pytest.raises(ModelCallFailed, match="analysis"):
        asyncio.run(model.complete("prompt"))


def test_client_is_created_once_and_reused_across_calls() -> None:
    gateway = _ScriptedGateway({"m": [None, None]})
    records: list[CallRecord] = []
    model = RoutingModel("analysis", "analysis", [_candidate("m", 1)], gateway, records.append)

    asyncio.run(model.complete("p1"))
    asyncio.run(model.complete("p2"))

    assert gateway.created == ["m"]
    assert len(records) == 2


def test_default_retries_try_a_a_b_b_c_c():
    records = []
    candidates = [replace(_candidate(name, i), extra_retries=1) for i, name in enumerate("abc", 1)]
    gateway = _ScriptedGateway(
        {name: [ModelUnavailable("忙", http_status=503)] * 2 for name in "abc"}
    )
    router = RoutingModel(
        "analysis", "analysis", candidates, gateway, records.append, retry_base_seconds=0
    )
    with pytest.raises(ModelUnavailable):
        asyncio.run(router.complete("测试"))
    assert [r.model_key_snapshot for r in records] == list("aabbcc")
    assert [r.request_ordinal for r in records] == list(range(1, 7))
    assert [r.retry_ordinal for r in records] == [0, 1, 0, 1, 0, 1]
    assert len({r.invocation_id for r in records}) == 1


def test_total_budget_prevents_starting_next_candidate():
    records = []
    gateway = _ScriptedGateway(
        {"a": [ModelUnavailable("忙", http_status=503)] * 11, "b": [None]}
    )
    router = RoutingModel(
        "analysis",
        "analysis",
        [replace(_candidate("a", 1), extra_retries=10), _candidate("b", 2)],
        gateway,
        records.append,
        retry_base_seconds=0,
    )
    with pytest.raises(ModelCallFailed, match="上限"):
        asyncio.run(router.complete("测试"))
    assert len(records) == 6
    assert gateway.created == ["a"]


def test_skipped_candidate_does_not_consume_failover_limit():
    records = []
    router = RoutingModel(
        "analysis",
        "analysis",
        [_candidate("a", 1), _candidate("b", 2)],
        _ScriptedGateway({"b": [None]}),
        records.append,
        failover_limit=1,
        recheck=lambda c: c if c.model == "b" else None,
    )
    assert asyncio.run(router.complete("测试")).model == "b"
    assert records[0].candidate_ordinal == 1


@pytest.mark.parametrize("error", [ModelRefused("拒绝"), TenderError("权限失效")])
def test_refusal_and_local_errors_do_not_failover(error):
    gateway = _ScriptedGateway({"a": [error], "b": [None]})
    router = RoutingModel(
        "analysis", "analysis", [_candidate("a", 1), _candidate("b", 2)], gateway, lambda _: None
    )
    with pytest.raises(type(error)):
        asyncio.run(router.complete("测试"))
    assert gateway.created == ["a"]


def test_database_reservation_failure_sends_no_request():
    gateway = _ScriptedGateway({"a": [None]})

    def reserve(_):
        raise RuntimeError("数据库断开")

    router = RoutingModel(
        "analysis", "analysis", [_candidate("a", 1)], gateway, lambda _: None, reserve=reserve
    )
    with pytest.raises(RuntimeError):
        asyncio.run(router.complete("测试"))
    assert gateway.created == []


def test_retry_after_larger_than_deadline_stops_without_retry():
    error = ModelUnavailable("限流", http_status=429)
    error.retry_after = 60
    records = []
    router = RoutingModel(
        "analysis",
        "analysis",
        [replace(_candidate("a", 1), extra_retries=1)],
        _ScriptedGateway({"a": [error, None]}),
        records.append,
        deadline_seconds=1,
    )
    with pytest.raises(ModelCallFailed, match="时间预算"):
        asyncio.run(router.complete("测试"))
    assert len(records) == 1


def test_rate_limit_wait_does_not_consume_retry_allowance():
    """限流是暂时没有配额，不是请求失败：等待后必须仍然可以重试。"""

    async def run():
        records: list[CallRecord] = []
        limit = ModelUnavailable("限流", http_status=429)
        limit.retry_after = 0.01
        gateway = _ScriptedGateway({"a": [limit, True]})
        model = RoutingModel(
            "analysis", "analysis", [replace(_candidate("a", 1), extra_retries=0)],
            gateway, records.append,
            rate_limit_backoff_seconds=0.01, rate_limit_max_wait_seconds=0.05,
        )
        try:
            # extra_retries=0 时旧实现只允许一次请求，这里必须能在等待后成功。
            completion = await model.complete("分析")
        finally:
            await model.aclose()
        assert completion.model == "a"
        assert [record.http_status for record in records] == [429, 200]

    asyncio.run(run())


def test_rate_limit_wait_stops_after_the_configured_budget():
    """等待额度用尽时按不可用收尾，保留上游详情供补跑定位。"""

    async def run():
        records: list[CallRecord] = []
        limit = ModelUnavailable("限流配额耗尽", http_status=429)
        limit.retry_after = 0.5
        model = RoutingModel(
            "analysis", "analysis", [replace(_candidate("a", 1), extra_retries=2)],
            _ScriptedGateway({"a": [limit] * 5}), records.append,
            rate_limit_backoff_seconds=0.01, rate_limit_max_wait_seconds=0.02,
        )
        try:
            with pytest.raises(ModelUnavailable, match="限流配额耗尽"):
                await model.complete("分析")
        finally:
            await model.aclose()
        # 额度用尽后不再重发；记录数等于实际发送次数减去被拒的那次之外的重试。
        assert len(records) <= 2

    asyncio.run(run())


def test_rate_limit_backoff_grows_when_the_supplier_gives_no_reset_time():
    """没有 Retry-After 时按倍数递增，避免 30 秒固定冷却反复撞同一窗口。"""

    async def run():
        records: list[CallRecord] = []
        first = ModelUnavailable("限流", http_status=429)
        second = ModelUnavailable("限流", http_status=429)
        gateway = _ScriptedGateway({"a": [first, second, True]})
        model = RoutingModel(
            "analysis", "analysis", [replace(_candidate("a", 1), extra_retries=0)],
            gateway, records.append,
            rate_limit_backoff_seconds=0.01, rate_limit_max_wait_seconds=5,
        )
        try:
            await model.complete("分析")
        finally:
            await model.aclose()
        assert [record.http_status for record in records] == [429, 429, 200]

    asyncio.run(run())


def test_rate_limit_cooldown_avoids_repeated_requests_and_invalid_usage_is_recorded():
    async def run():
        records = []
        invalid = InvalidModelOutput("无效输出", http_status=200)
        invalid.prompt_tokens, invalid.completion_tokens = 7, 11
        gateway = _ScriptedGateway(
            {
                "limited": [ModelUnavailable("限流", http_status=429)],
                "fallback": [invalid, True, True],
            }
        )
        model = RoutingModel(
            "analysis",
            "analysis",
            [_candidate("limited", 1), _candidate("fallback", 2)],
            gateway,
            records.append,
        )
        try:
            await model.complete("第一轮")
            await model.complete("第二轮")
        finally:
            await model.aclose()
        assert [r.model_id for r in records] == [1, 2, 2, 2]
        assert (records[1].prompt_tokens, records[1].completion_tokens) == (7, 11)

    asyncio.run(run())


def test_transient_503_recovers_within_same_candidate_and_counts_each_request():
    records, reservations = [], []
    router = RoutingModel(
        "analysis",
        "analysis",
        [replace(_candidate("a", 1), extra_retries=1)],
        _ScriptedGateway({"a": [ModelUnavailable("繁忙", http_status=503), None]}),
        records.append,
        reserve=reservations.append,
        retry_base_seconds=0,
    )
    assert asyncio.run(router.complete("测试")).model == "a"
    assert [r.status for r in records] == ["error", "ok"]
    assert len(reservations) == 2


def test_provider_cooldown_is_shared_between_independent_routers():
    deadlines = {}

    def remaining(c):
        return deadlines.get(c.provider_id, 0)

    def defer(c, seconds):
        deadlines[c.provider_id] = seconds

    async def run():
        all_records = []
        for _ in range(2):
            gateway = _ScriptedGateway(
                {
                    "primary": [ModelUnavailable("限流", http_status=429)],
                    "backup": [None],
                }
            )
            router = RoutingModel(
                "analysis",
                "analysis",
                [_candidate("primary", 1), _candidate("backup", 2)],
                gateway,
                all_records.append,
                cooldown_remaining=remaining,
                defer_provider=defer,
            )
            assert (await router.complete("测试")).model == "backup"
            await router.aclose()
        assert [r.model_id for r in all_records] == [1, 2, 2]
        assert deadlines[1] == 30

    asyncio.run(run())


def test_switching_models_of_same_provider_cannot_bypass_429():
    records = []
    router = RoutingModel(
        "analysis",
        "analysis",
        [_candidate("a", 1), replace(_candidate("b", 2), provider_id=1), _candidate("c", 3)],
        _ScriptedGateway({"a": [ModelUnavailable("限流", http_status=429)], "c": [None]}),
        records.append,
    )
    assert asyncio.run(router.complete("测试")).model == "c"
    assert [r.model_id for r in records] == [1, 3]


def test_retry_after_waits_without_burning_requests(monkeypatch):
    from tender.application.llm import routing as llm_routing

    now, sleeps, records = [100.0], [], []
    monkeypatch.setattr(llm_routing.time, "monotonic", lambda: now[0])

    async def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(llm_routing.asyncio, "sleep", sleep)
    error = ModelUnavailable("限流", http_status=429)
    error.retry_after = 2
    router = RoutingModel(
        "analysis",
        "analysis",
        [replace(_candidate("a", 1), extra_retries=1)],
        _ScriptedGateway({"a": [error, None]}),
        records.append,
        retry_base_seconds=0,
    )
    assert asyncio.run(router.complete("测试")).model == "a"
    assert sum(sleeps) >= 2
    assert len(records) == 2


@pytest.mark.parametrize("already_cooling", [False, True])
def test_disabled_failover_waits_for_primary_instead_of_using_a_lower_priority_model(
    monkeypatch, already_cooling
):
    from tender.application.llm import routing as llm_routing

    now, records = [100.0], []
    monkeypatch.setattr(llm_routing.time, "monotonic", lambda: now[0])

    async def sleep(seconds):
        now[0] += seconds

    monkeypatch.setattr(llm_routing.asyncio, "sleep", sleep)
    error = ModelUnavailable("限流", http_status=429)
    error.retry_after = 2
    gateway = _ScriptedGateway({"a": [None] if already_cooling else [error, None], "b": [None]})
    router = RoutingModel(
        "analysis",
        "analysis",
        [replace(_candidate("a", 1), extra_retries=1), _candidate("b", 2)],
        gateway,
        records.append,
        failover_limit=1,
        retry_base_seconds=0,
        cooldown_remaining=lambda c: (
            max(0, 102 - now[0]) if already_cooling and c.model == "a" else 0
        ),
    )
    assert asyncio.run(router.complete("测试")).model == "a"
    assert gateway.created == ["a"]
    assert now[0] >= 102
    assert len(records) == (1 if already_cooling else 2)


def test_cancel_during_shared_cooldown_sends_no_request():
    async def run():
        checked = asyncio.Event()
        records = []

        def remaining(_):
            checked.set()
            return 60

        gateway = _ScriptedGateway({"a": [None]})
        router = RoutingModel(
            "analysis",
            "analysis",
            [_candidate("a", 1)],
            gateway,
            records.append,
            cooldown_remaining=remaining,
        )
        task = asyncio.create_task(router.complete("测试"))
        await checked.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not records and not gateway.created

    asyncio.run(run())


def test_slow_candidates_leave_time_for_final_fallback_within_deadline(monkeypatch):
    """非 Agent 功能仍按计划请求切分剩余时间：慢候选不能吃光后备模型的窗口。"""
    from tender.application.llm import routing as llm_routing

    now, timeouts, records = [100.0], [], []
    monkeypatch.setattr(llm_routing.time, "monotonic", lambda: now[0])

    async def wait_for(request, timeout):
        timeouts.append(timeout)
        try:
            return await request
        except TimeoutError:
            now[0] += timeout
            raise

    monkeypatch.setattr(llm_routing.asyncio, "wait_for", wait_for)
    router = RoutingModel(
        "analysis",
        "analysis",
        [
            replace(_candidate(name, index), timeout=300, extra_retries=1)
            for index, name in enumerate("abc", 1)
        ],
        _ScriptedGateway(
            {
                "a": [TimeoutError(), TimeoutError()],
                "b": [TimeoutError(), TimeoutError()],
                "c": [None],
            }
        ),
        records.append,
        retry_base_seconds=0,
        deadline_seconds=600,
    )
    assert asyncio.run(router.complete("测试")).model == "c"
    assert [r.model_id for r in records] == [1, 1, 2, 2, 3]
    assert now[0] < 700 and all(timeout <= 100.01 for timeout in timeouts)


def test_agent_module_window_is_a_continuous_budget_for_the_current_request(monkeypatch):
    """Agent 多轮已有模块总时限：当前请求用连续窗口，不能切成小片反复打断生成。"""
    from tender.application.llm import routing as llm_routing

    now, timeouts, records = [100.0], [], []
    monkeypatch.setattr(llm_routing.time, "monotonic", lambda: now[0])

    async def wait_for(request, timeout):
        timeouts.append(timeout)
        try:
            return await request
        except TimeoutError:
            now[0] += timeout
            raise

    monkeypatch.setattr(llm_routing.asyncio, "wait_for", wait_for)
    router = RoutingModel(
        "analysis",
        "analysis",
        [
            replace(_candidate(name, index), timeout=300, extra_retries=1)
            for index, name in enumerate("abc", 1)
        ],
        _ScriptedGateway(
            {
                "a": [TimeoutError(), TimeoutError()],
                "b": [TimeoutError(), TimeoutError()],
                "c": [None],
            }
        ),
        records.append,
        retry_base_seconds=0,
        deadline_seconds=600,
        remaining_seconds=lambda: 60,
    )
    # 首次请求拿到完整的剩余 60 秒窗口；慢候选耗尽后按模块总时限结束，不再切片重发或换后备。
    with pytest.raises(ModelCallFailed, match="总请求次数或时间上限"):
        asyncio.run(router.complete("测试"))
    assert timeouts == [60.0]
    assert [r.model_id for r in records] == [1]
