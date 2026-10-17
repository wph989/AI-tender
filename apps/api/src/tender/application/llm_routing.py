"""功能级有界重试与故障转移；每个实际请求均带调用身份。"""

from __future__ import annotations

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, replace
from uuid import uuid4

from tender.core.error_details import error_detail
from tender.core.logging import bind_context, get_logger
from tender.domain.errors import (
    InvalidModelOutput,
    ModelCallFailed,
    ModelOutputTruncated,
    ModelRefused,
    ModelUnavailable,
    TenderError,
)
from tender.ports.llm import ChatGateway, Completion, ModelGateway

logger = get_logger(__name__)


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
        before_request: Callable[[], Awaitable[None]] | None = None,
        output_limit: int | None = None,
        cooldown_remaining: Callable[[ModelCandidate], float] | None = None,
        defer_provider: Callable[[ModelCandidate, float], None] | None = None,
        remaining_seconds: Callable[[], float] | None = None,
        rate_limit_backoff_seconds: float = 30,
        rate_limit_max_wait_seconds: float = 600,
    ):
        self._feature_key, self._purpose = feature_key, purpose
        self._candidates = tuple(candidates)
        self._gateway, self._on_call = gateway, on_call
        self._failover_limit, self._max_total = failover_limit, max_total_requests
        self._deadline_seconds = deadline_seconds
        self._recheck, self._reserve = recheck, reserve
        self._retry_base = retry_base_seconds
        self._before_request = before_request
        self._output_limit = output_limit
        self._clients: dict[ModelCandidate, ChatGateway] = {}
        self._rate_limited_until: dict[int | str, float] = {}
        self._cooldown_remaining, self._defer_provider = cooldown_remaining, defer_provider
        self._remaining_seconds = remaining_seconds
        self._rate_backoff = rate_limit_backoff_seconds
        self._rate_max_wait = rate_limit_max_wait_seconds

    def _remaining(self, candidate: ModelCandidate) -> float:
        key = candidate.provider_id if candidate.provider_id is not None else candidate.base_url
        local = self._rate_limited_until.get(key, 0) - time.monotonic()
        shared = self._cooldown_remaining(candidate) if self._cooldown_remaining else 0
        return max(0, local, shared)

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
                max_tokens=(
                    min(candidate.max_tokens or self._output_limit, self._output_limit)
                    if self._output_limit
                    else candidate.max_tokens
                ),
                **kwargs,
            )
            self._clients[candidate] = client
        return client

    async def complete(self, prompt: str) -> Completion:
        return await self._complete(prompt)

    async def chat(self, messages: list[dict], tools: list[dict]) -> Completion:
        return await self._complete("", chat_request={"messages": messages, "tools": tools})

    async def _complete(self, prompt: str, chat_request: dict | None = None) -> Completion:
        invocation_id = str(uuid4())
        # 上下文随协程和 to_thread 传播，重试与备用请求共享一次调用身份，退出后恢复。
        with bind_context(
            feature_key=self._feature_key, purpose=self._purpose, invocation_id=invocation_id,
        ):
            logger.info(
                "model_invocation_started", candidate_count=len(self._candidates),
                failover_limit=self._failover_limit, max_total_requests=self._max_total,
                deadline_seconds=self._deadline_seconds,
            )
            return await self._invoke(prompt, chat_request, invocation_id)

    def _record_call(self, record: CallRecord) -> None:
        # 先记文件再落账，数据库写入失败时仍能查到已经发生的请求；正文已按候选密钥脱敏。
        log = logger.info if record.status == "ok" else logger.warning
        log("model_request_finished", **asdict(record))
        self._on_call(record)

    async def _invoke(
        self, prompt: str, chat_request: dict | None, invocation_id: str,
    ) -> Completion:
        if not self._candidates:
            logger.warning("model_invocation_stopped", reason="no_candidates")
            raise ModelCallFailed(
                f"功能 {self._feature_key} 没有可用模型，请在模型管理中配置并绑定"
            )
        duration = self._deadline_seconds
        if self._remaining_seconds:
            duration = min(duration, self._remaining_seconds())
        deadline = time.monotonic() + duration
        request_count = candidate_count = 0
        first_error: TenderError | None = None
        unavailable_only = True
        last_candidate = None
        candidates = self._candidates
        if self._failover_limit == 1:
            # 禁止降级时先固定最高优先级的启用模型；限流排序和429重试不能偷换成后备模型。
            # 管理员停用的候选仍可跳过，但选定后只等待/重试该模型。
            candidates = tuple(
                c for c in candidates if self._recheck is None or self._recheck(c) is not None
            )[:1]
        # 允许降级时先用可用供应商；全在冷却时等待最早恢复者，等待不占请求预算。
        candidates = sorted(candidates, key=lambda c: self._remaining(c))
        for position, snapshot in enumerate(candidates):
            if candidate_count >= self._failover_limit:
                break
            attempted = False
            request_prompt = prompt
            native_request = chat_request
            rate_waited = 0.0
            rate_round = 0
            retry = 0
            while retry <= max(snapshot.extra_retries, 2):
                if request_count >= self._max_total or time.monotonic() >= deadline:
                    logger.warning(
                        "model_invocation_stopped", reason="request_or_time_budget_exhausted",
                        request_count=request_count, candidate_count=candidate_count,
                    )
                    raise ModelCallFailed("模型调用已达到总请求次数或时间上限，请查看调用记录")
                delay = self._remaining(snapshot)
                if delay and any(self._remaining(c) == 0 for c in candidates[position + 1 :]):
                    break
                if delay > 0:
                    # 冷却检查每秒执行，等待日志只在进入循环时输出一次。
                    logger.info("model_provider_wait", provider_id=snapshot.provider_id,
                                wait_seconds=round(delay, 3))
                while delay > 0:
                    if time.monotonic() + delay >= deadline:
                        raise ModelCallFailed("模型调用时间预算不足以等待供应商限流恢复")
                    # 短等待便于取消；跨worker新收到的429可以继续延长当前等待。
                    await asyncio.sleep(min(delay, 1))
                    delay = self._remaining(snapshot)
                # 每次发送重新检查启用和凭证；配置读取失败会停止，不能绕过管理页面。
                candidate = self._recheck(snapshot) if self._recheck else snapshot
                if candidate is None:
                    logger.info("model_candidate_skipped", model_id=snapshot.registry_model_id,
                                reason="disabled_or_changed")
                    break
                # 每个实际请求（含换源、格式纠正、摘要）都先预占模块持久预算。
                if self._before_request:
                    await self._before_request()
                if not attempted:
                    if last_candidate is not None:
                        logger.warning(
                            "model_failover", from_model_id=last_candidate.registry_model_id,
                            from_provider_id=last_candidate.provider_id,
                            to_model_id=candidate.registry_model_id,
                            to_provider_id=candidate.provider_id,
                        )
                    candidate_count += 1
                    attempted = True
                    last_candidate = candidate
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
                future = candidates[
                    position + 1 : position + 1 + self._failover_limit - candidate_count
                ]
                planned_requests = min(
                    self._max_total - request_count + 1,
                    max(1, snapshot.extra_retries - retry + 1)
                    + sum(c.extra_retries + 1 for c in future),
                )
                # Agent 多轮运行已有模块总时限，给当前请求连续窗口；不能把末尾60秒
                # 切成四次15秒并反复打断正常生成。其它功能保留候选之间的时间分配。
                request_timeout = min(
                    snapshot.timeout,
                    max(0, deadline - time.monotonic())
                    / (1 if self._remaining_seconds else planned_requests),
                )
                logger.info(
                    "model_request_started", model_id=candidate.registry_model_id,
                    provider_id=candidate.provider_id, model=candidate.model,
                    candidate_ordinal=candidate_count, retry_ordinal=retry,
                    request_ordinal=request_count, extra_retries=snapshot.extra_retries,
                    timeout_seconds=round(request_timeout, 3),
                )
                try:
                    with bind_context(
                        request_ordinal=request_count, model_id=candidate.registry_model_id,
                    ):
                        completion = await asyncio.wait_for(
                            self._client(candidate).chat(**native_request)
                            if native_request is not None
                            else self._client(candidate).complete(request_prompt),
                            timeout=request_timeout,
                        )
                except asyncio.CancelledError:
                    self._record_call(
                        replace(
                            record,
                            status="unknown",
                            latency_ms=int((time.monotonic() - started) * 1000),
                            error_message="本地任务已取消，供应商执行结果未知",
                        )
                    )
                    raise
                except (TenderError, TimeoutError) as exc:
                    if isinstance(exc, TimeoutError):
                        exc = ModelUnavailable("模型请求超时，供应商执行结果未知")
                    unavailable = isinstance(exc, ModelUnavailable)
                    unavailable_only = unavailable_only and unavailable
                    self._record_call(
                        replace(
                            record,
                            status="unknown"
                            if exc.http_status is None and unavailable
                            else "error",
                            http_status=exc.http_status,
                            latency_ms=int((time.monotonic() - started) * 1000),
                            prompt_tokens=getattr(exc, "prompt_tokens", None),
                            completion_tokens=getattr(exc, "completion_tokens", None),
                            error_message=error_detail(str(exc), api_key=candidate.api_key),
                        )
                    )
                    first_error = first_error or exc
                    if exc.http_status == 429:
                        # 限流是「暂时没有配额」，不是「这次请求失败」：等待不消耗重试次数，
                        # 否则三四十秒的默认冷却永远撑不过供应商分钟级窗口，整模块白跑。
                        hint = float(getattr(exc, "retry_after", 0) or 0)
                        # 首次信任供应商给的恢复时间；重复限流说明它偏小，按倍数递增。
                        escalated = min(
                            self._rate_backoff * 2**min(rate_round, 5), self._rate_max_wait
                        )
                        delay = hint if rate_round == 0 and hint else max(hint, escalated)
                        remaining_wait = self._rate_max_wait - rate_waited
                        if remaining_wait <= 0:
                            logger.warning("model_provider_wait_exhausted",
                                           provider_id=candidate.provider_id)
                            # 等待额度用完就停止重发，落回原有不可用收尾以保留上游详情；
                            # 调用方按「可补跑」处理，不会把已核实成果丢掉。
                            break
                        if time.monotonic() + min(delay, remaining_wait) >= deadline:
                            if any(self._remaining(c) == 0 for c in candidates[position + 1 :]):
                                break
                            raise ModelCallFailed(
                                "模型调用时间预算不足以等待供应商限流恢复"
                            ) from exc
                        delay = min(delay, remaining_wait)
                        logger.warning(
                            "model_provider_cooldown", provider_id=candidate.provider_id,
                            wait_seconds=round(delay, 3), reason="http_429",
                        )
                        rate_waited += delay
                        rate_round += 1
                        key = (
                            candidate.provider_id
                            if candidate.provider_id is not None
                            else candidate.base_url
                        )
                        self._rate_limited_until[key] = time.monotonic() + delay
                        if self._defer_provider:
                            self._defer_provider(candidate, delay)
                        if any(self._remaining(c) == 0 for c in candidates[position + 1 :]):
                            break
                        # 429 不计入总请求预算：本次没有产生模型输出。
                        request_count -= 1
                        continue
                    if isinstance(exc, ModelRefused) or not isinstance(
                        exc, (ModelCallFailed, ModelUnavailable)
                    ):
                        # 本地权限或业务约束错误不允许通过切换模型绕过。
                        raise exc
                    if (
                        isinstance(exc, InvalidModelOutput)
                        and not isinstance(exc, ModelOutputTruncated)
                        and retry < 2
                        and request_count < self._max_total
                    ):
                        # 在换候选前纠正已收到的坏格式，避免主模型的可修正问题被后备网络故障掩盖。
                        # 纠正也计入原有总次数和时间预算，不重发未知结果或明确拒绝。
                        request_prompt = prompt + (
                            "\n上次响应不符合 JSON 协议。请重新返回一个完整 JSON 对象，"
                            "遵守当前阶段的字段要求；工具动作也必须用 action 对象表达，"
                            "不能只说明计划。"
                        )
                        if chat_request is not None:
                            native_request = chat_request | {
                                "messages": [
                                    *chat_request["messages"],
                                    {
                                        "type": "human",
                                        "data": {
                                            "content": (
                                                "上次未返回合法工具调用或正文。请使用已提供的工具，"
                                                "工具参数必须完整符合其 JSON Schema；"
                                                "完成后返回正式结论。"
                                            )
                                        },
                                    },
                                ]
                            }
                        retry += 1
                        logger.warning(
                            "model_retry_scheduled", model_id=candidate.registry_model_id,
                            retry_ordinal=retry, wait_seconds=0, reason="invalid_output",
                        )
                        continue
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
                            if any(self._remaining(c) == 0 for c in candidates[position + 1 :]):
                                break
                            raise ModelCallFailed("模型调用时间预算不足以再次请求") from exc
                        logger.warning(
                            "model_retry_scheduled", model_id=candidate.registry_model_id,
                            retry_ordinal=retry + 1, wait_seconds=round(delay, 3),
                            reason="model_unavailable",
                        )
                        await asyncio.sleep(delay)
                        retry += 1
                        continue
                    break
                self._record_call(
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
        logger.warning(
            "model_invocation_stopped",
            reason="candidate_limit_reached" if candidate_count >= self._failover_limit
            else "candidates_exhausted",
            candidate_count=candidate_count, failover_limit=self._failover_limit,
            request_count=request_count,
        )
        if unavailable_only and first_error:
            raise ModelUnavailable(message)
        raise ModelCallFailed(message)

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
