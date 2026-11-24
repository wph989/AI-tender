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

from tender.core.error_details import error_detail
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
        max_total_requests: int = 6,
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
        self._failover_limit, self._max_total = failover_limit, max_total_requests
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
        # 冻结非密钥执行策略；恢复时仍重查启用状态和凭证，但不能换取新的重试额度。
        window.setdefault("policy", {
            "failover_limit": self._failover_limit, "max_total": self._max_total,
            "rate_max_wait": self._rate_max_wait, "rate_backoff": self._rate_backoff,
            "candidates": {str(c.registry_model_id or c.model): {
                "extra_retries": c.extra_retries, "timeout": c.timeout,
                "total_timeout": c.total_timeout,
            } for c in self._candidates},
        })

        async def persist():
            if self._invocation_store:
                writing = asyncio.create_task(asyncio.to_thread(
                    self._invocation_store.save_invocation, key, window,
                ))
                try:
                    await asyncio.shield(writing)
                except asyncio.CancelledError:
                    # 不能让旧写入在恢复后的新窗口之后落库。
                    while not writing.done():
                        with suppress(asyncio.CancelledError):
                            await asyncio.shield(writing)
                    writing.result()
                    raise

        await persist()
        records: list[CallRecord] = []
        started = time.monotonic()
        status = "error"
        failure: BaseException | None = None
        # 上下文随协程和 to_thread 传播，重试与备用请求共享一次调用身份，退出后恢复。
        with bind_context(invocation_id=invocation_id):
            try:
                completion = await self._invoke(
                    prompt, chat_request, invocation_id, records, window, persist,
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
        window: dict, persist,
    ) -> Completion:
        if not self._candidates:
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
        unavailable_only = True
        policy = window["policy"]
        failover_limit, max_total = policy["failover_limit"], policy["max_total"]
        candidates = tuple(replace(c, **policy["candidates"][str(c.registry_model_id or c.model)])
                           for c in self._candidates
                           if str(c.registry_model_id or c.model) in policy["candidates"])
        if failover_limit == 1:
            # 禁止降级时先固定最高优先级的启用模型；限流排序和429重试不能偷换成后备模型。
            # 管理员停用的候选仍可跳过，但选定后只等待/重试该模型。
            selected = []
            for candidate in candidates:
                if self._recheck is None or await asyncio.to_thread(self._recheck, candidate):
                    selected.append(candidate)
                    break
            candidates = tuple(selected)
        # 允许降级时先用可用供应商；全在冷却时等待最早恢复者，等待不占请求预算。
        delays = {candidate: await self._remaining(candidate) for candidate in candidates}
        candidates = sorted(candidates, key=delays.__getitem__)
        # 首次选定的候选顺序随调用保存，恢复不能因冷却排序变化重新获得候选额度。
        order = window.setdefault("candidate_order", [c.registry_model_id or c.model
                                                      for c in candidates])
        candidates = sorted(candidates, key=lambda c: order.index(c.registry_model_id or c.model))
        await persist()
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
            rate_state = window.setdefault("rate_state", {}).setdefault(
                str(model_key), {"waited": 0.0, "round": 0, "until": 0.0},
            )
            rate_waited, rate_round = rate_state["waited"], rate_state["round"]
            retry = sum(r["model"] == model_key for r in window["requests"])
            while retry <= snapshot.extra_retries:
                if request_count >= max_total or time.monotonic() >= deadline:
                    raise budget_error("模型调用已达到总请求次数或模块时间上限，请查看调用记录")
                delay = max(await self._remaining(snapshot), rate_state["until"] - time.time())
                if delay and await self._has_available(candidates[position + 1 :]):
                    break
                while delay > 0:
                    if time.monotonic() + delay >= deadline:
                        raise budget_error("模型调用时间预算不足以等待供应商限流恢复")
                    # 短等待便于取消；跨worker新收到的429可以继续延长当前等待。
                    await asyncio.sleep(min(delay, 1))
                    delay = max(await self._remaining(snapshot), rate_state["until"] - time.time())
                # 每次发送重新检查启用和凭证；配置读取失败会停止，不能绕过管理页面。
                candidate = (
                    await asyncio.to_thread(self._recheck, snapshot) if self._recheck else snapshot
                )
                if candidate is None:
                    break
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
                    await self._record_call(
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
                        ), records,
                    )
                    first_error = first_error or exc
                    if exc.http_status == 429:
                        # 等待不增加尝试；每次真实429仍使用原窗口的请求及候选重试额度。
                        hint = float(getattr(exc, "retry_after", 0) or 0)
                        # 首次信任供应商给的恢复时间；重复限流说明它偏小，按倍数递增。
                        escalated = min(
                            policy["rate_backoff"] * 2**min(rate_round, 5), policy["rate_max_wait"]
                        )
                        delay = hint if rate_round == 0 and hint else max(hint, escalated)
                        remaining_wait = policy["rate_max_wait"] - rate_waited
                        if remaining_wait <= 0:
                            # 等待额度用完就停止重发，落回原有不可用收尾以保留上游详情；
                            # 调用方按「可补跑」处理，不会把已核实成果丢掉。
                            break
                        if time.monotonic() + min(delay, remaining_wait) >= deadline:
                            if await self._has_available(candidates[position + 1 :]):
                                break
                            raise budget_error(
                                "模型调用时间预算不足以等待供应商限流恢复"
                            ) from exc
                        delay = min(delay, remaining_wait)
                        rate_waited += delay
                        rate_round += 1
                        rate_state.update(waited=rate_waited, round=rate_round,
                                          until=time.time() + delay)
                        await persist()
                        key = (
                            candidate.provider_id
                            if candidate.provider_id is not None
                            else candidate.base_url
                        )
                        self._rate_limited_until[key] = time.monotonic() + delay
                        if self._defer_provider:
                            await asyncio.to_thread(self._defer_provider, candidate, delay)
                        if await self._has_available(candidates[position + 1 :]):
                            break
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
                        and request_count < max_total
                    ):
                        # 在换候选前纠正已收到的坏格式，避免主模型的可修正问题被后备网络故障掩盖。
                        # 纠正也计入原有总次数和时间预算，不重发未知结果或明确拒绝。
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
                        and request_count < max_total
                    ):
                        delay = max(
                            random.uniform(0, min(30, self._retry_base * 2**retry)),
                            getattr(exc, "retry_after", 0),
                        )
                        if time.monotonic() + delay >= deadline:
                            if await self._has_available(candidates[position + 1 :]):
                                break
                            raise budget_error("模型调用时间预算不足以再次请求") from exc
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
        failures = list(dict.fromkeys(
            (record.model_name_snapshot, record.error_message)
            for record in records if record.error_message
        ))
        if len({name for name, _ in failures}) > 1:
            message = "所有已尝试模型均未完成请求：\n" + "\n".join(
                f"{name}：{detail}" for name, detail in failures
            )
        else:
            message = (failures[-1][1] if failures else
                       "当前模型均已停用或不可调用")
        message = error_detail(message) or "当前模型均不可调用"
        if unavailable_only and first_error:
            raise ModelUnavailable(message)
        raise ModelCallFailed(message)

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
