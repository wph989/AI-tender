"""以真实请求和状态反例验证解析分析报告中的八类缺陷。"""

import asyncio

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from tender.application.shared.agent_model import (
    BudgetedSummarization as AnalysisSummarizationMiddleware,
)
from tender.application.shared.agent_model import RoutedAgentModel, context_size
from tender.domain.shared.errors import ModelBudgetExhausted


def test_context_count_accepts_sdk_message_forms_and_one_pass_iterables():
    canonical = [SystemMessage(content="规则"), HumanMessage(content="问题")]
    shorthand = [{"role": "system", "content": "规则"}, ("user", "问题")]
    assert context_size(iter(shorthand)) == context_size(canonical)


def test_tool_schema_is_counted_and_irreducible_request_stops_before_model_call():
    async def run():
        from deepagents.backends import StateBackend

        middleware = AnalysisSummarizationMiddleware(
            RoutedAgentModel(router=None), backend=StateBackend,
            context_tokens=1000, output_tokens=100, keep=("messages", 4),
            token_counter=context_size,
        )
        tools = [{"type": "function", "function": {"name": "large", "description": "规则" * 1000,
                  "parameters": {"type": "object", "properties": {}}}}]
        messages = [SystemMessage(content="固定规则")]
        assert context_size(messages, tools=tools) > context_size(messages)
        invoked = []

        async def handler(req):
            invoked.append(req)
            raise AssertionError("已知超限不能进入模型")

        req = ModelRequest(model=RoutedAgentModel(router=None), system_message=messages[0],
                           messages=[], tools=tools, state={}, runtime=None)
        with pytest.raises(ModelBudgetExhausted, match="上下文预算"):
            await middleware.awrap_model_call(req, handler)
        assert not invoked

    asyncio.run(run())
