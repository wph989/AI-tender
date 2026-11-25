"""分析与问答共用的模型适配和上下文预算。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

from deepagents import GeneralPurposeSubagentProfile, HarnessProfile, register_harness_profile
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain_core.exceptions import ContextOverflowError
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    MessageLikeRepresentation,
    convert_to_messages,
    message_to_dict,
    messages_from_dict,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from tender.domain.shared.errors import ModelBudgetExhausted

# 当前单Agent运行不启用通用递归子Agent及默认摘要，统一由本模块的预算中间件处理。
register_harness_profile(
    "tender:analysis",
    HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        excluded_middleware={"SummarizationMiddleware"},
    ),
)


def _model_messages(messages: Sequence[BaseMessage]) -> list[dict]:
    # 估算和发送使用同一份消息视图，避免上下文预算与实际请求不一致。
    return [message_to_dict(message) for message in messages]


class RoutedAgentModel(BaseChatModel):
    """将 LangChain 原生工具调用消息桥接到现有模型路由。"""

    model_name: str = "tender:analysis"
    router: Any = Field(exclude=True)

    @property
    def _llm_type(self) -> str:
        return "tender_routed_agent"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):
        return self.bind(tools=[convert_to_openai_tool(tool) for tool in tools])

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise RuntimeError("标书 Agent 必须异步运行，以支持超时与取消")

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        result = await self.router.chat(_model_messages(messages), kwargs.get("tools", []))
        if result.agent_message is None:
            raise ValueError("模型没有返回原生 Agent 消息")
        message = messages_from_dict([result.agent_message])[0]
        if not isinstance(message, AIMessage):
            raise ValueError("供应商必须返回 assistant 消息")
        return ChatResult(generations=[ChatGeneration(message=message)])


def context_size(messages: Iterable[MessageLikeRepresentation], *, tools=None) -> int:
    """按同一消息视图估算请求体，工具定义也计入上下文预算。"""
    # SDK允许消息生成器和简写格式，先归一化再按实际发送的消息视图计量。
    prepared = convert_to_messages(messages)
    serialized = json.dumps(_model_messages(prepared), ensure_ascii=False)
    if tools:
        definitions = [convert_to_openai_tool(tool) for tool in tools]
        serialized += json.dumps(definitions, ensure_ascii=False)
    ascii_count = sum(ord(char) < 128 for char in serialized)
    return len(serialized) - ascii_count + (ascii_count + 2) // 3 + 8 * len(prepared)


class BudgetedSummarization(SummarizationMiddleware):
    """在请求构造完成后执行压缩，并将超限转为可结算的预算错误。"""

    def __init__(
        self,
        *args,
        context_tokens: int | None,
        output_tokens: int,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.input_limit = (
            None if context_tokens is None else max(0, context_tokens * 95 // 100 - output_tokens)
        )

    def _input_budget(self, request):
        provider_limit = super()._input_budget(request)
        if self.input_limit is None:
            return provider_limit
        return self.input_limit if provider_limit is None else min(self.input_limit, provider_limit)

    async def awrap_model_call(self, request, handler):
        try:
            return await super().awrap_model_call(request, handler)
        except ContextOverflowError as exc:
            raise ModelBudgetExhausted("完整模型请求超过上下文预算") from exc
