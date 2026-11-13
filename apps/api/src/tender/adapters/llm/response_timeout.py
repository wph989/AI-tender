"""按模型进展计时，避免网络心跳延长模型等待，也避免持续输出被总时限截断。"""

from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager
from typing import Any

import structlog

from tender.domain.shared.errors import ModelUnavailable

logger = structlog.get_logger(__name__)


class ResponseTimeout:
    def __init__(self, interval: float, total: float | None = None) -> None:
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("响应间隔超时必须为有限正数")
        if total is not None and (not math.isfinite(total) or total <= 0):
            raise ValueError("单次请求总时限必须为有限正数或为空")
        self.interval, self.total = interval, total
        self.started = asyncio.get_running_loop().time()
        self.last = self.started
        self.first: float | None = None
        self.max_gap = 0.0
        self.kind: str | None = None
        self.timer = asyncio.timeout_at(self.deadline)

    @property
    def deadline(self) -> float:
        return min(self.last + self.interval,
                   self.started + self.total if self.total is not None else math.inf)

    def failure(self) -> ModelUnavailable:
        total_deadline = self.started + self.total if self.total is not None else math.inf
        self.kind = ("total" if total_deadline <= self.last + self.interval else
                     "first_increment" if self.first is None else "response_interval")
        label = {"total": "单次模型请求总时限", "first_increment": "首个有效模型增量等待",
                 "response_interval": "模型有效增量响应间隔"}[self.kind]
        seconds = self.total if self.kind == "total" else self.interval
        error = ModelUnavailable(f"{label}超时（{seconds:g}秒），供应商执行结果未知")
        error.timeout_kind = self.kind
        return error

    def observe(self, effective: bool) -> None:
        now = asyncio.get_running_loop().time()
        # 缓冲流也可能连续同步返回；先核对截止，防止迟到增量把已到期的计时续上。
        if now >= self.deadline:
            raise self.failure()
        if effective:
            self.max_gap = max(self.max_gap, now - self.last)
            self.first = self.first if self.first is not None else now
            self.last = now
            self.timer.reschedule(self.deadline)


@asynccontextmanager
async def response_timeout(interval: float, total: float | None = None):
    progress = ResponseTimeout(interval, total)
    try:
        async with progress.timer:
            yield progress
    except TimeoutError as exc:
        if progress.timer.expired():
            raise progress.failure() from exc
        raise
    finally:
        logger.info("model.response_timing", timeout_kind=progress.kind,
                    first_increment_ms=(round((progress.first - progress.started) * 1000)
                                        if progress.first is not None else None),
                    max_increment_gap_ms=round(max(
                        progress.max_gap, asyncio.get_running_loop().time() - progress.last,
                    ) * 1000))


def message_has_increment(message: Any) -> bool:
    """只观察当前消息块的内容和参数；角色、用量、签名和工具身份不能作为进展。"""
    content = message.content
    if isinstance(content, str) and content:
        return True
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str) and part:
                return True
            if isinstance(part, dict) and any(
                isinstance(part.get(key), str) and bool(part[key])
                for key in ("text", "thinking", "reasoning", "refusal")
            ):
                return True
            if isinstance(part, dict) and part.get("type") == "reasoning" and any(
                isinstance(summary, dict) and bool(summary.get("text"))
                for summary in part.get("summary", [])
            ):
                return True
    if any(call.get("args") for call in getattr(message, "tool_call_chunks", [])):
        return True
    # 完整JSON消息的参数已解析成对象；增量块则只能观察原始参数，避免工具身份续期。
    if not hasattr(message, "tool_call_chunks") and any(
        isinstance(call.get("args"), dict) for call in getattr(message, "tool_calls", [])
    ):
        return True
    extra = getattr(message, "additional_kwargs", {})
    return any(isinstance(extra.get(key), str) and bool(extra[key])
               for key in ("reasoning_content", "reasoning", "refusal"))


def chat_has_increment(data: dict) -> bool:
    for choice in data.get("choices") or []:
        if choice.get("index", 0) != 0:
            continue
        delta = choice.get("delta") or {}
        if any(isinstance(delta.get(key), str) and bool(delta[key])
               for key in ("content", "reasoning_content", "reasoning", "refusal")):
            return True
        if any(call.get("function", {}).get("arguments")
               for call in delta.get("tool_calls") or []):
            return True
    return False


def responses_has_increment(data: dict) -> bool:
    return data.get("type") in {
        "response.output_text.delta", "response.reasoning_text.delta",
        "response.reasoning_summary_text.delta", "response.function_call_arguments.delta",
        "response.refusal.delta",
    } and isinstance(data.get("delta"), str) and bool(data["delta"])
