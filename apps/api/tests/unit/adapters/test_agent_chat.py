"""直接检查供应商 HTTP 工具协议，防止文本适配器假装完成原生工具调用。"""

import asyncio
import json

import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage, message_to_dict

from tender.adapters.agent_chat import AgentChat
from tender.domain.errors import (
    ExtractionFailed,
    ExtractionUnavailable,
    InvalidModelOutput,
    ModelOutputTruncated,
    ModelRefused,
)

TOOL = {
    "type": "function",
    "function": {
        "name": "search_document",
        "description": "检索",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}


def agent(client):
    return AgentChat(
        base_url="http://test/v1",
        model="fixture",
        api_key="fixture-key",
        timeout=5,
        temperature=None,
        max_tokens=128,
        protocol="openai_compatible",
        api_mode="chat_completions",
        parameters={},
        http_async_client=client,
    )


def response(message):
    return {
        "id": "fixture",
        "object": "chat.completion",
        "created": 1,
        "model": "fixture",
        "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
    }


def test_native_tool_call_round_trip():
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["tools"] == [TOOL]
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=response(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_123",
                                "type": "function",
                                "function": {
                                    "name": "search_document",
                                    "arguments": '{"query":"预算"}',
                                },
                            }
                        ],
                    }
                ),
            )
        assert body["messages"][-2]["tool_calls"][0]["id"] == "call_123"
        assert body["messages"][-1] == {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": "预算80万",
        }
        return httpx.Response(200, json=response({"role": "assistant", "content": "完成"}))

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        model = agent(client)
        try:
            messages = [message_to_dict(HumanMessage(content="分析预算"))]
            first = await model.chat(messages, [TOOL])
            assert first.agent_message["data"]["tool_calls"][0]["args"] == {"query": "预算"}
            messages += [
                first.agent_message,
                message_to_dict(ToolMessage(content="预算80万", tool_call_id="call_123")),
            ]
            final = await model.chat(messages, [TOOL])
            assert (final.content, final.prompt_tokens, final.completion_tokens) == ("完成", 12, 7)
        finally:
            await model.aclose()
        assert client.is_closed

    asyncio.run(run())


@pytest.mark.parametrize(
    "status,expected",
    [
        *[(status, ExtractionUnavailable) for status in (408, 429, 500, 502, 503, 504)],
        (401, ExtractionFailed),
    ],
)
def test_no_hidden_retries_or_sensitive_errors(status, expected):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            status, headers={"Retry-After": "2"}, json={"error": {"message": "密钥和标书机密正文"}}
        )

    async def run():
        model = agent(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        try:
            with pytest.raises(expected) as error:
                await model.chat([message_to_dict(HumanMessage(content="分析"))], [TOOL])
            assert "机密" not in str(error.value)
            if status == 429:
                assert error.value.retry_after == 2
        finally:
            await model.aclose()

    asyncio.run(run())
    assert len(requests) == 1


def test_429_http_date_uses_server_clock_for_retry_after():
    async def run():
        model = agent(
            httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        429,
                        headers={
                            "Date": "Wed, 07 Oct 2026 00:00:00 GMT",
                            "Retry-After": "Wed, 07 Oct 2026 00:00:05 GMT",
                        },
                        json={"error": {"message": "busy"}},
                    )
                )
            )
        )
        try:
            with pytest.raises(ExtractionUnavailable) as error:
                await model.chat([message_to_dict(HumanMessage(content="检索"))], [TOOL])
            assert error.value.retry_after == 5
        finally:
            await model.aclose()

    asyncio.run(run())


def test_native_refusal_stops_processing():
    async def run():
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json=response({"role": "assistant", "content": "", "refusal": "拒绝"})
                )
            )
        )
        model = agent(client)
        try:
            with pytest.raises(ModelRefused):
                await model.chat([message_to_dict(HumanMessage(content="分析"))], [TOOL])
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("tokens,expected", [(128, ModelOutputTruncated), (7, InvalidModelOutput)])
def test_incomplete_tool_arguments_are_not_delivered_as_business_submissions(tokens, expected):
    async def run():
        body = response(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search_document", "arguments": "{}"},
                    }
                ],
            }
        )
        body["choices"][0]["finish_reason"] = "tool_calls"
        body["usage"]["completion_tokens"] = tokens
        model = agent(
            httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
            )
        )
        try:
            with pytest.raises(expected) as error:
                await model.chat([message_to_dict(HumanMessage(content="检索"))], [TOOL])
            assert error.value.completion_tokens == tokens
        finally:
            await model.aclose()

    asyncio.run(run())


def test_malformed_tool_name_is_bounded_protocol_error_without_echoing_document():
    async def run():
        body = response(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "submit_analysis=机密标书正文" * 1000,
                            "arguments": "{}",
                        },
                    }
                ],
            }
        )
        model = agent(
            httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body))
            )
        )
        try:
            with pytest.raises(InvalidModelOutput) as error:
                await model.chat([message_to_dict(HumanMessage(content="检索"))], [TOOL])
            assert len(str(error.value)) < 100 and "机密" not in str(error.value)
        finally:
            await model.aclose()

    asyncio.run(run())


def test_invalid_response_keeps_usage_for_budget_accounting():
    async def run():
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json=response({"role": "assistant", "content": ""}))
            )
        )
        model = agent(client)
        try:
            with pytest.raises(InvalidModelOutput) as error:
                await model.chat([message_to_dict(HumanMessage(content="分析"))], [TOOL])
            assert (error.value.prompt_tokens, error.value.completion_tokens) == (12, 7)
            assert error.value.http_status == 200
        finally:
            await model.aclose()

    asyncio.run(run())


def test_each_module_owns_http_clients_so_closing_one_does_not_break_another():
    async def run():
        first, second = agent(None), agent(None)
        try:
            assert first._owned_http is not second._owned_http
            assert first._owned_sync_http is not second._owned_sync_http
            await first.aclose()
            assert first._owned_http.is_closed
            assert not second._owned_http.is_closed
            assert not second._owned_sync_http.is_closed
        finally:
            await second.aclose()

    asyncio.run(run())
