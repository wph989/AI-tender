"""功能级有界重试与故障转移；每个实际请求均带调用身份。"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from uuid import uuid4

from tender.core.error_details import MAX_ERROR_LENGTH, error_detail, model_error_details
from tender.core.logging import bind_context, get_logger
from tender.domain.shared.errors import (
    InvalidModelOutput,
    ModelBudgetExhausted,
    ModelCallFailed,
    ModelOutputTruncated,
    ModelRefused,
    ModelUnavailable,
    TenderError,
)
from tender.ports.llm.chat import ChatGateway, Completion, ModelGateway, ModelInvocationStore

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
    total_timeout: float | None = None
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
        load_route: Callable[[], tuple[Sequence[ModelCandidate], int]] | None = None,
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
        invocation_store: ModelInvocationStore | None = None,
        before_call: Callable[[CallRecord], Awaitable[None]] | None = None,
    ):
        self._feature_key, self._purpose = feature_key, purpose
        self._candidates = tuple(candidates)
        self._gateway, self._on_call = gateway, on_call
        self._failover_limit = failover_limit
        self._load_route = load_route
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
        self._rate_waited = 0.0
        self._invocation_store = invocation_store
        self._before_call = before_call

    async def _remaining(self, candidate: ModelCandidate) -> float:
        key = candidate.provider_id if candidate.provider_id is not None else candidate.base_url
        local = self._rate_limited_until.get(key, 0) - time.monotonic()
        shared = (
            await asyncio.to_thread(self._cooldown_remaining, candidate)
            if self._cooldown_remaining else 0
        )
        return max(0, local, shared)

    async def _has_available(self, candidates: Sequence[ModelCandidate]) -> bool:
        for candidate in candidates:
            if await self._remaining(candidate) == 0:
                return True
        return False

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
                **(
                    {"total_timeout": candidate.total_timeout}
                    if candidate.total_timeout is not None
                    else {}
                ),
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
        # 图检查点里的消息ID固定；恢复时动态预算提示变化不能生成一套新调用额度。
        checkpoint = [m for m in messages if m.get("data", {}).get("id")
                      and m.get("type") != "system"]
        call_key = ("agent:" + hashlib.sha256(json.dumps(
            checkpoint, ensure_ascii=False, sort_keys=True,
        ).encode("utf-8")).hexdigest()) if checkpoint else None
        return await self._complete("", chat_request={"messages": messages, "tools": tools},
                                    call_key=call_key)

    async def _complete(self, prompt: str, chat_request: dict | None = None,
                        *, call_key: str | None = None) -> Completion:
        key = call_key or hashlib.sha256(json.dumps(
            [prompt, chat_request], ensure_ascii=False, sort_keys=True,
        ).encode("utf-8")).hexdigest()
        window = (await asyncio.to_thread(self._invocation_store.load_invocation, key)
                  if self._invocation_store else {})
        if window.get("result"):
            if window.get("success_record"):
                await asyncio.to_thread(self._on_call, CallRecord(**window["success_record"]))
            return Completion(**window["result"])
        if window.get("exhausted"):
            # 恢复必须保留可部分收尾的错误类型，不能把网络故障改成业务失败。
            failure_type = {
                "ModelUnavailable": ModelUnavailable,
                "ModelBudgetExhausted": ModelBudgetExhausted,
                "ModelCallFailed": ModelCallFailed,
                "InvalidModelOutput": InvalidModelOutput,
                "ModelOutputTruncated": ModelOutputTruncated,
                "ModelRefused": ModelRefused,
            }.get(window.get("error_type"), ModelBudgetExhausted)
            failure = failure_type(window.get("error") or "原模型请求窗口已耗尽，请补跑继续",
                                   http_status=window.get("http_status"))
            if isinstance(failure, ModelUnavailable):
                failure.invocation_exhausted = True
            raise failure
        invocation_id = window.setdefault("invocation_id", str(uuid4()))
        window.setdefault("requests", [])
        original_input = window.setdefault("input", {
            "prompt": prompt, "chat_request": chat_request,
        })
        prompt, chat_request = original_input["prompt"], original_input["chat_request"]
        # 同一专题复用路由器，每个新窗口仍从已保存的功能绑定创建候选。
        candidates, failover_limit = (
            await asyncio.to_thread(self._load_route) if self._load_route
            else (self._candidates, self._failover_limit)
        )
        # 冻结非密钥执行策略；恢复时仍重查启用状态和凭证，但不能换取新的重试额度。
        window.setdefault("policy", {
            "failover_limit": failover_limit,
            "rate_max_wait": self._rate_max_wait, "rate_backoff": self._rate_backoff,
            "candidates": {str(c.registry_model_id or c.model): {
                "extra_retries": c.extra_retries, "timeout": c.timeout,
                "total_timeout": c.total_timeout,
            } for c in candidates},
        })

        async def persist():
            if self._invocation_store:
                await self._finish_write(asyncio.to_thread(
                    self._invocation_store.save_invocation, key, window,
                ))

        async def settle_failure(
            record: CallRecord, failure: dict, cooldown: tuple[ModelCandidate, float] | None,
        ) -> None:
            # 先结算真实回执，再保存摘要；取消不能停在两次写入之间。
            await self._record_call(record, records)
            window.setdefault("failures", []).append(failure)
            await persist()
            if cooldown is not None and self._defer_provider:
                await asyncio.to_thread(self._defer_provider, *cooldown)

        if self._invocation_store:
            # 跨窗口累计等待经运行账读取，Worker 重新领取运行后也沿用已用额度。
            self._rate_waited = await asyncio.to_thread(
                self._invocation_store.other_invocation_wait, key,
            ) + window.get("rate_waited", sum(
                state.get("waited", 0.0) for state in window.get("rate_state", {}).values()
            ))
        records: list[CallRecord] = []
        started = time.monotonic()
        status = "error"
        failure: BaseException | None = None
        # 上下文随协程和 to_thread 传播，重试与备用请求共享一次调用身份，退出后恢复。
        with bind_context(invocation_id=invocation_id):
            try:
                completion = await self._invoke(
                    prompt, chat_request, invocation_id, records,
                    window, persist, candidates, settle_failure,
                )
                status = "ok"
                return completion
            except asyncio.CancelledError as exc:
                status = "cancelled"
                failure = exc
                raise
            except Exception as exc:
                status = "error"
                failure = exc
                if isinstance(exc, (ModelCallFailed, ModelUnavailable)):
                    window.update(exhausted=True, error=error_detail(str(exc)),
                                  error_type=type(exc).__name__, http_status=exc.http_status)
                    await persist()
                    if isinstance(exc, ModelUnavailable):
                        exc.invocation_exhausted = True
                raise
            finally:
                last = records[-1] if records else None
                input_tokens = [record.prompt_tokens for record in records
                                if record.prompt_tokens is not None]
                output_tokens = [record.completion_tokens for record in records
                                 if record.completion_tokens is not None]
                log = logger.info if status == "ok" else logger.warning
                log(
                    "model.call",
                    model_name=last.model_key_snapshot if last else None,
                    status=status,
                    input_tokens=sum(input_tokens) if input_tokens else None,
                    output_tokens=sum(output_tokens) if output_tokens else None,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    error_type=type(failure).__name__ if failure else None,
                    error=(
                        last.error_message if last and last.error_message
                        else error_detail(str(failure)) if failure else None
                    ),
                )

    async def _record_call(self, record: CallRecord, records: list[CallRecord]) -> None:
        # 逐次请求继续写调用账本；运行日志由外层在整次路由调用结束时汇总一次。
        records.append(record)
        await asyncio.to_thread(self._on_call, record)

    @staticmethod
    async def _finish_write(operation: Awaitable[None]) -> None:
        writing = asyncio.ensure_future(operation)
        try:
            await asyncio.shield(writing)
        except asyncio.CancelledError:
            # 已开始的写入必须先落定，避免旧执行者释放所有权后仍在写账。
            while not writing.done():
                with suppress(asyncio.CancelledError):
                    await asyncio.shield(writing)
            writing.result()
            raise

    async def _reserve_call(self, record: CallRecord, records: list[CallRecord]) -> None:
        if self._reserve is None and self._before_call is None:
            return

        async def reserve():
            if self._before_call:
                await self._before_call(record)
            if self._reserve:
                await asyncio.to_thread(self._reserve, record)

        reservation = asyncio.create_task(reserve())
        try:
            await asyncio.shield(reservation)
        except asyncio.CancelledError:
            async def finish_cancellation() -> None:
                # 预占可能在提交后才报错；无论结果如何，都要等写入落定再补终态。
                with suppress(Exception):
                    await reservation
                await self._record_call(replace(
                    record, status="error",
                    error_message="本地任务在发送前已取消，未向供应商发送请求",
                ), records)

            cleanup = asyncio.create_task(finish_cancellation())
            # 重复取消也不能打断收尾，否则迟到的 running 写入可能覆盖终态。
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    continue
            cleanup.result()
            raise

    async def _invoke(
        self, prompt: str, chat_request: dict | None, invocation_id: str,
        records: list[CallRecord],
        window: dict, persist, candidates: Sequence[ModelCandidate], settle_failure,
    ) -> Completion:
        if not candidates and not window.get("candidate_order"):
            raise ModelCallFailed(
                f"功能 {self._feature_key} 没有可用模型，请在模型管理中配置并绑定"
            )
        # 只有模块拥有整个运行的时间预算，功能绑定不再另加截止。
        duration = self._remaining_seconds() if self._remaining_seconds else float("inf")
        deadline = time.monotonic() + duration
        budget_error = ModelBudgetExhausted if self._remaining_seconds else ModelCallFailed
        request_count = len(window["requests"])
        attempted_models = {r["model"] for r in window["requests"]}
        candidate_count = len(attempted_models)
        first_error: TenderError | None = None
        unavailable_only = all(f.get("unavailable", True) for f in window.get("failures", []))
        policy = window["policy"]
        failover_limit = policy["failover_limit"]
        candidates = tuple(replace(c, **policy["candidates"][str(c.registry_model_id or c.model)])
                           for c in candidates
                           if str(c.registry_model_id or c.model) in policy["candidates"])
        if failover_limit == 1 and "candidate_order" not in window:
            # 禁止降级时先固定最高优先级的启用模型；限流排序和429重试不能偷换成后备模型。
            # 管理员停用的候选仍可跳过，但选定后只等待/重试该模型。
            selected = []
            for candidate in candidates:
                if self._recheck is None or await asyncio.to_thread(self._recheck, candidate):
                    selected.append(candidate)
                    break
            candidates = tuple(selected)
        # 仓储已按用户保存的优先级排序；冷却只影响能否发送，不重排候选。
        # 顺序随调用保存，恢复不能换取新的候选或重试额度。
        order = window.setdefault("candidate_order", [c.registry_model_id or c.model
                                                      for c in candidates])
        by_key = {c.registry_model_id or c.model: c for c in candidates}
        candidates = tuple(by_key[model_key] for model_key in order if model_key in by_key)
        await persist()
        rate_waited = window.get("rate_waited", sum(
            state.get("waited", 0.0) for state in window.get("rate_state", {}).values()
        ))
        blocked_by_time = False
        for position, snapshot in enumerate(candidates):
            model_key = snapshot.registry_model_id or snapshot.model
            if model_key in window.get("finished_candidates", []):
                continue
            if candidate_count >= failover_limit and model_key not in attempted_models:
                break
            attempted = model_key in attempted_models
            feedback = window.get("feedback", {}).get(str(model_key), {})
            request_prompt = feedback.get("prompt", prompt)
            native_request = feedback.get("chat_request", chat_request)
            rate_state = window.setdefault("rate_state", {}).setdefault(str(model_key), {})
            retry = sum(r["model"] == model_key for r in window["requests"])
            while retry <= snapshot.extra_retries:
                if time.monotonic() >= deadline:
                    raise budget_error(self._failure_message(
                        window, "模块总时限已到，不能继续请求模型",
                    ))
                delay = max(
                    await self._remaining(snapshot), rate_state.get("until", 0.0) - time.time(),
                )
                if (delay and not attempted
                        and await self._has_available(candidates[position + 1 :])):
                    window.setdefault("skipped", {})[str(model_key)] = (
                        f"{snapshot.display_name}：供应商仍在限流冷却，剩余{delay:.1f}秒"
                    )
                    await persist()
                    break
                while delay > 0:
                    module_remaining = max(0, deadline - time.monotonic())
                    remaining_wait = max(0, policy["rate_max_wait"] - self._rate_waited)
                    if delay > remaining_wait or delay >= module_remaining:
                        blocked_by_time |= delay >= module_remaining
                        window.setdefault("skipped", {})[str(model_key)] = (
                            f"{snapshot.display_name}：上游限流需等待{delay:.1f}秒，"
                            f"模块剩余{module_remaining:.1f}秒，"
                            f"限流等待额度剩余{remaining_wait:.1f}秒"
                        )
                        break
                    # 短等待便于取消；跨worker新收到的429可以继续延长当前等待。
                    pause = min(delay, 1)
                    rate_waited += pause
                    self._rate_waited += pause
                    if self._invocation_store:
                        window["rate_waited"] = rate_waited
                        await persist()
                    await asyncio.sleep(pause)
                    delay = max(
                        await self._remaining(snapshot), rate_state.get("until", 0.0) - time.time(),
                    )
                if delay > 0:
                    break
                # 每次发送重新检查启用和凭证；配置读取失败会停止，不能绕过管理页面。
                candidate = (
                    await asyncio.to_thread(self._recheck, snapshot) if self._recheck else snapshot
                )
                if candidate is None:
                    break
                # 启用状态和凭证实时核验，执行参数仍使用本次调用冻结的模型配置。
                candidate = replace(candidate, timeout=snapshot.timeout,
                                    total_timeout=snapshot.total_timeout,
                                    extra_retries=snapshot.extra_retries)
                # 每个实际请求（含换源、格式纠正、摘要）都先预占模块持久预算。
                if self._before_request:
                    await self._before_request()
                if not attempted:
                    candidate_count += 1
                    attempted = True
                    attempted_models.add(model_key)
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
                    candidate.display_name,
                    candidate.provider_name,
                    candidate.model,
                )
                # 先持久化单调请求序号，再预占额度；预占期间中断也不能复用旧请求身份。
                window["requests"].append({"model": model_key, "ordinal": request_count})
                await persist()
                # 先登记实际请求身份，数据库失败时不发送收费请求。
                await self._reserve_call(record, records)
                started = time.monotonic()
                try:
                    with bind_context(
                        request_ordinal=request_count, model_id=candidate.registry_model_id,
                    ):
                        completion = await asyncio.wait_for(
                            self._client(candidate).chat(**native_request)
                            if native_request is not None
                            else self._client(candidate).complete(request_prompt),
                            timeout=max(0, deadline - time.monotonic())
                            if self._remaining_seconds
                            else None,
                        )
                except asyncio.CancelledError:
                    await self._record_call(
                        replace(
                            record,
                            status="unknown",
                            latency_ms=int((time.monotonic() - started) * 1000),
                            error_message="本地任务已取消，供应商执行结果未知",
                        ), records,
                    )
                    raise
                except (TenderError, TimeoutError) as exc:
                    if isinstance(exc, TimeoutError):
                        exc = ModelUnavailable("模块总时间预算已耗尽，供应商执行结果未知")
                    unavailable = isinstance(exc, ModelUnavailable)
                    unavailable_only = unavailable_only and unavailable
                    # 同一调用恢复后仍能展示此前每个模型的真实失败，避免被最后一次错误覆盖。
                    failure = {
                        "model_key": str(model_key), "model": candidate.display_name,
                        "provider": candidate.provider_name, "ordinal": request_count,
                        "unavailable": unavailable,
                        "message": error_detail(str(exc), api_key=candidate.api_key),
                    }
                    failed_record = replace(
                        record,
                        status="unknown" if exc.http_status is None and unavailable else "error",
                        http_status=exc.http_status,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        prompt_tokens=getattr(exc, "prompt_tokens", None),
                        completion_tokens=getattr(exc, "completion_tokens", None),
                        error_message=failure["message"],
                    )

                    cooldown = None
                    if exc.http_status == 429:
                        # 等待不增加尝试；每次真实429仍使用原窗口的请求及候选重试额度。
                        hint = float(getattr(exc, "retry_after", 0) or 0)
                        # 首次信任供应商给的恢复时间；重复限流说明它偏小，按倍数递增。
                        rate_round = rate_state.get("round", 0)
                        escalated = min(
                            policy["rate_backoff"] * 2**min(rate_round, 5), policy["rate_max_wait"]
                        )
                        delay = hint if rate_round == 0 and hint else max(hint, escalated)
                        key = (
                            candidate.provider_id
                            if candidate.provider_id is not None
                            else candidate.base_url
                        )
                        # 最后一次失败也登记供应商冷却，切换同供应商模型不能绕过429。
                        self._rate_limited_until[key] = max(
                            self._rate_limited_until.get(key, 0.0), time.monotonic() + delay,
                        )
                        rate_state.update(round=rate_round + 1, until=time.time() + delay)
                        cooldown = (candidate, delay)

                    await self._finish_write(settle_failure(failed_record, failure, cooldown))
                    first_error = first_error or exc
                    if exc.http_status == 429:
                        # 每次真实发送占一个尝试和候选重试；等待本身不占次数。
                        retry += 1
                        continue
                    if isinstance(exc, ModelRefused) or not isinstance(
                        exc, (ModelCallFailed, ModelUnavailable)
                    ):
                        # 本地权限或业务约束错误不允许通过切换模型绕过。
                        raise exc
                    if (
                        isinstance(exc, InvalidModelOutput)
                        and not isinstance(exc, ModelOutputTruncated)
                        and retry < snapshot.extra_retries
                    ):
                        # 在换候选前纠正已收到的坏格式，避免主模型的可修正问题被后备网络故障掩盖。
                        # 纠正也计入该模型重试次数和模块预算，不重发未知结果或明确拒绝。
                        detail = (error_detail(str(exc), api_key=candidate.api_key)
                                  or "模型响应不符合当前协议")[:1800]
                        request_prompt = prompt + (
                            "\n上次响应不符合 JSON 协议：" + detail
                            + "。请重新返回一个完整 JSON 对象，遵守本次请求的字段和结构；"
                            "不要返回Markdown或计划。"
                        )
                        if chat_request is not None:
                            native_request = chat_request | {
                                "messages": [
                                    *chat_request["messages"],
                                    {
                                        "type": "human",
                                        "data": {
                                            "content": (
                                                # 原生工具纠正保留具体缺项，避免相同坏响应循环。
                                                "上次协议校验失败：" + detail
                                                + "。请使用本次已提供的工具，"
                                                "工具参数必须完整符合其 JSON Schema；"
                                                "完成后返回正式结论。"
                                            )
                                        },
                                    },
                                ]
                            }
                        window.setdefault("feedback", {})[str(model_key)] = {
                            "prompt": request_prompt, "chat_request": native_request,
                        }
                        await persist()
                        retry += 1
                        continue
                    if (
                        unavailable
                        and retry < snapshot.extra_retries
                    ):
                        delay = max(
                            random.uniform(0, min(30, self._retry_base * 2**retry)),
                            getattr(exc, "retry_after", 0),
                        )
                        if time.monotonic() + delay >= deadline:
                            if await self._has_available(candidates[position + 1 :]):
                                break
                            raise budget_error(
                                self._failure_message(
                                    window,
                                    f"{candidate.display_name}：重试需等待{delay:.1f}秒，模块剩余"
                                    f"{max(0, deadline - time.monotonic()):.1f}秒",
                                )
                            ) from exc
                        await asyncio.sleep(delay)
                        retry += 1
                        continue
                    break
                completion = replace(completion, registry_model_id=candidate.registry_model_id)
                success_record = replace(
                        record,
                        status="ok",
                        http_status=200,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        prompt_tokens=completion.prompt_tokens,
                        completion_tokens=completion.completion_tokens,
                    )
                if completion.agent_message is not None:
                    message = copy.deepcopy(completion.agent_message)
                    message["data"].setdefault("response_metadata", {})[
                        "request_latency_ms"] = success_record.latency_ms
                    completion = replace(completion, agent_message=message)
                # 先保存有效返回，Worker在结算前中断时可恢复回执，无须再次向供应商发送。
                window.update(result=asdict(completion), success_record=asdict(success_record))
                await persist()
                await self._record_call(success_record, records)
                return completion
            window.setdefault("finished_candidates", []).append(model_key)
            await persist()
        # 首候选的渠道故障不能掩盖后备的余额／权限错误；只使用已脱敏的调用账摘要。
        # 同模型多次重试按原因去重，避免前端堆积相同堆栈或回显凭证。
        message = self._failure_message(window) or "配置的模型在请求前已停用或不再可调用"
        message = error_detail(message) or "当前模型均不可调用"
        if blocked_by_time and unavailable_only:
            raise budget_error(message)
        if unavailable_only and (first_error or window.get("failures") or window.get("skipped")):
            raise ModelUnavailable(message)
        raise ModelCallFailed(message)

    @staticmethod
    def _failure_message(window: dict, reason: str = "") -> str:
        notes = [*window.get("skipped", {}).values(), reason]
        notes = [note for note in notes if note]
        reserved = sum(len(note) + 2 for note in notes)
        failures = model_error_details(
            window.get("failures", []), limit=MAX_ERROR_LENGTH - reserved,
        )
        details = [failures, *notes]
        return "\n\n".join(detail for detail in details if detail)

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
