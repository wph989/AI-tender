"""失败转移：按优先级降级、记录每次调用、候选耗尽后的错误分类。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest

from tender.application.llm_routing import CallRecord, ModelCandidate, RoutingModel
from tender.domain.errors import ExtractionFailed, ExtractionUnavailable
from tender.ports.llm import ChatGateway, Completion


class _ScriptedClient:
    """按脚本执行：脚本项是异常就抛出，否则返回成功补全。"""

    def __init__(self, model: str, script: list[Any]) -> None:
        self.model = model
        self.script = script
        self.closed = False

    async def complete(self, prompt: str) -> Completion:
        action = self.script.pop(0) if self.script else ExtractionFailed("脚本用尽")
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
        return _ScriptedClient(model, list(self._scripts.get(model, [])))


def _candidate(model: str, registry_id: int) -> ModelCandidate:
    return ModelCandidate(
        registry_model_id=registry_id,
        provider_id=1,
        display_name=model,
        model=model,
        base_url="http://gateway",
        api_key=None,
        timeout=1,
        temperature=None,
        max_tokens=None,
    )


def _run(
    candidates: Sequence[ModelCandidate],
    scripts: dict[str, list[Any]],
    feature: str = "extract",
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
            "bad": [ExtractionUnavailable("网关 503", http_status=503)],
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
    with pytest.raises(ExtractionUnavailable):
        _run(
            [_candidate("a", 1), _candidate("b", 2)],
            {
                "a": [ExtractionUnavailable("超时", http_status=504)],
                "b": [ExtractionUnavailable("限流", http_status=503)],
            },
        )


def test_mixed_failure_raises_failed_so_field_goes_to_review() -> None:
    """只要有一次是明确拒绝，重试没有意义，按字段失败处理。"""
    with pytest.raises(ExtractionFailed, match="拒绝"):
        _run(
            [_candidate("a", 1), _candidate("b", 2)],
            {
                "a": [ExtractionFailed("拒绝", http_status=401)],
                "b": [ExtractionUnavailable("限流")],
            },
        )


def test_without_candidates_reports_feature_name() -> None:
    gateway = _ScriptedGateway({})
    model = RoutingModel("extract", "extract", [], gateway, lambda record: None)

    with pytest.raises(ExtractionFailed, match="extract"):
        asyncio.run(model.complete("prompt"))


def test_client_is_created_once_and_reused_across_calls() -> None:
    gateway = _ScriptedGateway({"m": [None, None]})
    records: list[CallRecord] = []
    model = RoutingModel("extract", "extract", [_candidate("m", 1)], gateway, records.append)

    asyncio.run(model.complete("p1"))
    asyncio.run(model.complete("p2"))

    assert gateway.created == ["m"]
    assert len(records) == 2
