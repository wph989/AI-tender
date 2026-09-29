"""按功能优先级调用模型并在失败时降级，同时产出调用记录（设计文档 12 第 4 节）。

这是抽取链路唯一认识"多个模型"的地方：上层 `extract_field` 仍然只依赖
`StructuredTextModel` 协议，降级、连接复用与调用记录都在这里发生。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from tender.domain.errors import ExtractionFailed, ExtractionUnavailable, TenderError
from tender.ports.llm import ChatGateway, Completion, ModelGateway

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    """一条可调用的候选：绑定行的模型 + 供应商连接信息 + 推理参数。"""

    # .env 回退的单模型没有注册表行，两个 id 允许为空。
    registry_model_id: int | None
    provider_id: int | None
    display_name: str
    model: str
    base_url: str
    api_key: str | None
    timeout: float
    temperature: float | None
    max_tokens: int | None


@dataclass(frozen=True, slots=True)
class CallRecord:
    """一次模型调用的结果；成功与失败都要落库，否则排查时只剩最后一跳。"""

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


class RoutingModel:
    """实现 StructuredTextModel：按优先级依次尝试候选模型。"""

    def __init__(
        self,
        feature_key: str,
        purpose: str,
        candidates: Sequence[ModelCandidate],
        gateway: ModelGateway,
        on_call: Callable[[CallRecord], None],
    ) -> None:
        self._feature_key = feature_key
        self._purpose = purpose
        self._candidates = tuple(candidates)
        self._gateway = gateway
        self._on_call = on_call
        # 只有真正用到的候选才建客户端：整任务复用连接池，避免每个字段一次握手。
        self._clients: dict[ModelCandidate, ChatGateway] = {}

    @property
    def candidate_count(self) -> int:
        return len(self._candidates)

    def _client(self, candidate: ModelCandidate) -> ChatGateway:
        client = self._clients.get(candidate)
        if client is None:
            client = self._gateway(
                candidate.base_url,
                candidate.model,
                api_key=candidate.api_key,
                timeout=candidate.timeout,
                temperature=candidate.temperature,
                max_tokens=candidate.max_tokens,
            )
            self._clients[candidate] = client
        return client

    async def complete(self, prompt: str) -> Completion:
        if not self._candidates:
            raise ExtractionFailed(
                f"功能 {self._feature_key} 没有可用模型："
                "请先在模型管理里绑定，或配置 LLM_BASE_URL / LLM_MODEL"
            )
        unavailable_only = True
        # 报错信息保留第一次失败（主模型）的原因：它才是排查的起点，
        # 全部尝试的细节在 llm_call_log 里，不需要靠一句异常传递。
        first_error: TenderError | None = None
        for candidate in self._candidates:
            started = time.monotonic()
            try:
                completion = await self._client(candidate).complete(prompt)
            except TenderError as exc:
                if not isinstance(exc, ExtractionUnavailable):
                    unavailable_only = False
                self._record(
                    candidate,
                    status="error",
                    http_status=exc.http_status,
                    latency_ms=_elapsed_ms(started),
                    prompt_tokens=None,
                    completion_tokens=None,
                    error_message=str(exc),
                )
                if first_error is None:
                    first_error = exc
                continue
            self._record(
                candidate,
                status="ok",
                http_status=200,
                latency_ms=_elapsed_ms(started),
                prompt_tokens=completion.prompt_tokens,
                completion_tokens=completion.completion_tokens,
                error_message=None,
            )
            return replace(completion, registry_model_id=candidate.registry_model_id)
        # 全是"暂时不可用"时向上抛可用性错误，让 worker 退避后整任务重试；
        # 只要有一个是明确拒绝，就按字段失败处理，重试没有意义。
        message = str(first_error) if first_error else "模型调用失败"
        if unavailable_only:
            raise ExtractionUnavailable(message)
        raise ExtractionFailed(message)

    def _record(
        self,
        candidate: ModelCandidate,
        *,
        status: str,
        http_status: int | None,
        latency_ms: int,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        error_message: str | None,
    ) -> None:
        record = CallRecord(
            provider_id=candidate.provider_id,
            model_id=candidate.registry_model_id,
            feature_key=self._feature_key,
            purpose=self._purpose,
            status=status,
            http_status=http_status,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error_message=error_message[:500] if error_message else None,
        )
        try:
            self._on_call(record)
        except Exception:
            # 记录失败不能连累抽取本身：调用记录是排查用的旁路，不是主链路的必要条件。
            logger.warning("调用记录写入失败", exc_info=True)

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
