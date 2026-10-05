"""功能级有界重试与故障转移；每个实际请求均带调用身份。"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from uuid import uuid4

from tender.domain.errors import ExtractionFailed, ExtractionUnavailable, ModelRefused, TenderError
from tender.ports.llm import ChatGateway, Completion, ModelGateway


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    registry_model_id: int | None
    provider_id: int | None
    display_name: str
    model: str
    base_url: str
    api_key: str | None
    timeout: float
    temperature: float | None
    max_tokens: int | None
    extra_retries: int = 1
    protocol: str = "openai_compatible"
    api_mode: str = "chat_completions"
    provider_name: str = ""
    parameters_json: str = "{}"
    capabilities: tuple[str, ...] = ("text_input", "json_output")


@dataclass(frozen=True, slots=True)
class CallRecord:
    provider_id: int | None
    model_id: int | None
    feature_key: str | None
    purpose: str
    status: str
    http_status: int | None
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    error_message: str | None
    invocation_id: str | None = None
    candidate_ordinal: int | None = None
    retry_ordinal: int | None = None
    request_ordinal: int | None = None
    model_name_snapshot: str | None = None
    provider_name_snapshot: str | None = None
    model_key_snapshot: str | None = None


class RoutingModel:
    def __init__(
        self,
        feature_key: str,
        purpose: str,
        candidates: Sequence[ModelCandidate],
        gateway: ModelGateway,
        on_call: Callable[[CallRecord], None],
        *,
        failover_limit: int = 3,
        max_total_requests: int = 6,
        deadline_seconds: int = 600,
        recheck: Callable[[ModelCandidate], ModelCandidate | None] | None = None,
        reserve: Callable[[CallRecord], None] | None = None,
        retry_base_seconds: float = 1,
    ):
        self._feature_key, self._purpose = feature_key, purpose
        self._candidates = tuple(candidates)
        self._gateway, self._on_call = gateway, on_call
        self._failover_limit, self._max_total = failover_limit, max_total_requests
        self._deadline_seconds = deadline_seconds
        self._recheck, self._reserve = recheck, reserve
        self._retry_base = retry_base_seconds
        self._clients: dict[ModelCandidate, ChatGateway] = {}

    @property
    def candidate_count(self) -> int:
        return len(self._candidates)

    def _client(self, candidate: ModelCandidate) -> ChatGateway:
        client = self._clients.get(candidate)
        if client is None:
            kwargs = {}
            if (
                candidate.protocol != "openai_compatible"
                or candidate.api_mode != "chat_completions"
            ):
                kwargs = {"protocol": candidate.protocol, "api_mode": candidate.api_mode}
            if candidate.parameters_json != "{}":
                kwargs["parameters"] = json.loads(candidate.parameters_json)
            if candidate.capabilities != ("text_input", "json_output"):
                kwargs["capabilities"] = list(candidate.capabilities)
            client = self._gateway(
                candidate.base_url,
                candidate.model,
                api_key=candidate.api_key,
                timeout=candidate.timeout,
                temperature=candidate.temperature,
                max_tokens=candidate.max_tokens,
                **kwargs,
            )
            self._clients[candidate] = client
        return client

    async def complete(self, prompt: str) -> Completion:
        if not self._candidates:
            raise ExtractionFailed(
                f"功能 {self._feature_key} 没有可用模型，请在模型管理中配置并绑定"
            )
        invocation_id = str(uuid4())
        deadline = time.monotonic() + self._deadline_seconds
        request_count = candidate_count = 0
        first_error: TenderError | None = None
        unavailable_only = True
        for snapshot in self._candidates:
            if candidate_count >= self._failover_limit:
                break
            attempted = False
            for retry in range(snapshot.extra_retries + 1):
                if request_count >= self._max_total or time.monotonic() >= deadline:
                    raise ExtractionFailed("模型调用已达到总请求次数或时间上限，请查看调用记录")
                # 每次发送重新检查启用和凭证；配置读取失败会停止，不能绕过管理页面。
                candidate = self._recheck(snapshot) if self._recheck else snapshot
                if candidate is None:
                    break
                if not attempted:
                    candidate_count += 1
                    attempted = True
                request_count += 1
                record = CallRecord(
                    candidate.provider_id,
                    candidate.registry_model_id,
                    self._feature_key,
                    self._purpose,
                    "running",
                    None,
                    0,
                    None,
                    None,
                    None,
                    invocation_id,
                    candidate_count,
                    retry,
                    request_count,
                    snapshot.display_name,
                    snapshot.provider_name,
                    snapshot.model,
                )
                # 先登记实际请求身份，数据库失败时不发送收费请求。
                if self._reserve:
                    self._reserve(record)
                started = time.monotonic()
                try:
                    completion = await asyncio.wait_for(
                        self._client(candidate).complete(prompt),
                        timeout=min(snapshot.timeout, deadline - time.monotonic()),
                    )
                except (TenderError, TimeoutError) as exc:
                    if isinstance(exc, TimeoutError):
                        exc = ExtractionUnavailable("模型请求超时，供应商执行结果未知")
                    unavailable = isinstance(exc, ExtractionUnavailable)
                    unavailable_only = unavailable_only and unavailable
                    self._on_call(
                        replace(
                            record,
                            status="unknown"
                            if exc.http_status is None and unavailable
                            else "error",
                            http_status=exc.http_status,
                            latency_ms=int((time.monotonic() - started) * 1000),
                            error_message=str(exc)[:500],
                        )
                    )
                    first_error = first_error or exc
                    if isinstance(exc, ModelRefused) or not isinstance(
                        exc, (ExtractionFailed, ExtractionUnavailable)
                    ):
                        # 本地权限或业务约束错误不允许通过切换模型绕过。
                        raise exc
                    if (
                        unavailable
                        and retry < snapshot.extra_retries
                        and request_count < self._max_total
                    ):
                        delay = max(
                            random.uniform(0, min(30, self._retry_base * 2**retry)),
                            getattr(exc, "retry_after", 0),
                        )
                        if time.monotonic() + delay >= deadline:
                            raise ExtractionFailed("模型调用时间预算不足以再次请求") from exc
                        await asyncio.sleep(delay)
                        continue
                    break
                self._on_call(
                    replace(
                        record,
                        status="ok",
                        http_status=200,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        prompt_tokens=completion.prompt_tokens,
                        completion_tokens=completion.completion_tokens,
                    )
                )
                return replace(completion, registry_model_id=candidate.registry_model_id)
        message = str(first_error) if first_error else "当前模型均已停用或不可调用"
        if unavailable_only and first_error:
            raise ExtractionUnavailable(message)
        raise ExtractionFailed(message)

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
