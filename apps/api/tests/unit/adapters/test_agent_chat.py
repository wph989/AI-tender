"""直接检查供应商 HTTP 工具协议，防止文本适配器假装完成原生工具调用。"""

import asyncio
import json

import httpx
import pytest
from langchain_core.messages import HumanMessage, ToolMessage, message_to_dict
from structlog.testing import capture_logs

from tender.adapters.llm.agent_chat import AgentChat
from tender.application.llm.routing import ModelCandidate, RoutingModel
from tender.domain.shared.errors import (
    InvalidModelOutput,
    ModelCallFailed,
    ModelOutputTruncated,
    ModelRefused,
    ModelUnavailable,
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



def stream_response(body):
    """模拟供应商完整 SSE，工具参数按增量协议聚合后才能交给业务层。"""
    choice = body["choices"][0]
    delta = dict(choice["message"])
    if "tool_calls" in delta:
        delta["tool_calls"] = [dict(call, index=i) for i, call in enumerate(delta["tool_calls"])]
    chunks = [
        {"id": "fixture", "object": "chat.completion.chunk", "model": "fixture",
         "choices": [{"index": 0, "delta": delta, "finish_reason": choice["finish_reason"]}]},
        {"id": "fixture", "object": "chat.completion.chunk", "model": "fixture",
         "choices": [], "usage": body["usage"]},
    ]
    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                          text="".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                          + "data: [DONE]\n\n")


def test_native_tool_call_round_trip():
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["tools"] == [TOOL]
        if len(requests) == 1:
            return stream_response(response(
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
                ))
        assert body["messages"][-2]["tool_calls"][0]["id"] == "call_123"
        assert body["messages"][-1] == {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": "预算80万",
        }
        return stream_response(response({"role": "assistant", "content": "完成"}))

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


def test_streaming_tool_arguments_split_across_chunks_are_reassembled():
    """真实网关会把工具参数拆成多个增量：必须聚合完整后才能交给业务层。"""
    requests = []

    def split_stream():
        first = {
            "id": "fixture", "object": "chat.completion.chunk", "model": "fixture",
            "choices": [{"index": 0, "finish_reason": None, "delta": {
                "role": "assistant", "content": None,
                "tool_calls": [{"index": 0, "id": "call_7", "type": "function",
                                "function": {"name": "search_document", "arguments": '{"query":'}}],
            }}],
        }
        second = {
            "id": "fixture", "object": "chat.completion.chunk", "model": "fixture",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "delta": {
                "tool_calls": [{"index": 0, "function": {"arguments": '"预算"}'}}],
            }}],
        }
        usage = {
            "id": "fixture", "object": "chat.completion.chunk", "model": "fixture",
            "choices": [],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
        }
        return "".join(
            "data: " + json.dumps(chunk) + "\n\n" for chunk in (first, second, usage)
        ) + "data: [DONE]\n\n"

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, text=split_stream()
        )

    async def run():
        model = agent(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        try:
            reply = await model.chat([message_to_dict(HumanMessage(content="分析预算"))], [TOOL])
        finally:
            await model.aclose()
        assert reply.agent_message["data"]["tool_calls"][0]["args"] == {"query": "预算"}
        assert (reply.prompt_tokens, reply.completion_tokens) == (12, 7)

    asyncio.run(run())
    assert len(requests) == 1


def test_stream_without_finish_reason_is_not_delivered_as_submission():
    """流在收到 [DONE] 前断开时没有 finish_reason，半截工具参数绝不能进入提交工具。"""
    body = response(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function",
                 "function": {"name": "search_document", "arguments": '{"query":"预算"'}}
            ],
        }
    )
    body["choices"][0]["finish_reason"] = None
    model = agent(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: stream_response(body)))
    )

    async def run():
        try:
            with pytest.raises(ModelUnavailable, match="未完整结束"):
                await model.chat([message_to_dict(HumanMessage(content="检索"))], [TOOL])
        finally:
            await model.aclose()

    asyncio.run(run())

@pytest.mark.parametrize(
    "status,expected",
    [
        *[(status, ModelUnavailable) for status in (408, 429, 500, 502, 503, 504, 524, 599)],
        (401, ModelCallFailed),
    ],
)
def test_no_hidden_retries_and_upstream_error_is_preserved(status, expected):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            status,
            headers={"Retry-After": "2"},
            json={"error": {"message": "供应商额度不足，fixture-key", "code": "quota_exceeded"}},
        )

    async def run():
        model = agent(httpx.AsyncClient(transport=httpx.MockTransport(handle)))
        try:
            with pytest.raises(expected) as error:
                await model.chat([message_to_dict(HumanMessage(content="分析"))], [TOOL])
            assert "供应商额度不足" in str(error.value)
            assert "quota_exceeded" in str(error.value)
            assert f"HTTP {status}" in str(error.value)
            assert error.value.http_status == status
            assert "fixture-key" not in str(error.value)
            if status == 429:
                assert error.value.retry_after == 2
        finally:
            await model.aclose()

    asyncio.run(run())
    assert len(requests) == 1


def test_plain_text_gateway_error_preserves_multiline_body():
    async def run():
        body = "<html>\n网关超时\nrequest_id=upstream-123\n</html>"
        model = agent(httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(524, text=body),
        )))
        try:
            with pytest.raises(ModelUnavailable) as error:
                await model.chat([message_to_dict(HumanMessage(content="分析"))], [TOOL])
            assert body in str(error.value)
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.RemoteProtocolError])
def test_transport_failure_preserves_reason_without_serializing_request(error_type):
    async def run():
        def fail(request):
            raise error_type(
                "Server disconnected without sending a response. password=fixture-key",
                request=request,
            )

        model = agent(httpx.AsyncClient(transport=httpx.MockTransport(fail)))
        try:
            with pytest.raises(ModelUnavailable) as error:
                await model.chat([message_to_dict(HumanMessage(content="私密请求正文"))], [TOOL])
            assert error_type.__name__ in str(error.value)
            assert "Server disconnected without sending a response" in str(error.value)
            assert "未收到上游 HTTP 响应" in str(error.value)
            assert error.value.http_status is None
            assert "fixture-key" not in str(error.value)
            assert "私密请求正文" not in str(error.value)
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("chunks", [0, 1])
def test_interrupted_stream_preserves_response_metadata_without_partial_content(chunks):
    class InterruptedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            if chunks:
                yield b'data: {"choices":[{"index":0,"delta":{"content":"partial-secret"}}]}\n\n'
            raise httpx.RemoteProtocolError(
                "peer closed connection without sending complete message body "
                "(incomplete chunked read)"
            )

    async def run():
        model = agent(httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, stream=InterruptedStream(),
                headers={"content-type": "text/event-stream", "x-request-id": "upstream-123",
                         "set-cookie": "private-cookie"},
            ),
        )))
        try:
            with pytest.raises(ModelUnavailable) as error:
                await model.chat([message_to_dict(HumanMessage(content="私密请求正文"))], [TOOL])
            detail = str(error.value)
            assert "incomplete chunked read" in detail
            assert "HTTP 200 响应头" in detail
            assert f"已收到 {chunks} 个数据块" in detail
            assert "x-request-id：upstream-123" in detail
            assert "未收到上游 HTTP 响应" not in detail
            assert error.value.http_status is None, "流开始的 200 不能将未知完成状态改判为成功"
            for secret in ("fixture-key", "partial-secret", "private-cookie", "私密请求正文"):
                assert secret not in detail
        finally:
            await model.aclose()

    with capture_logs() as logs:
        asyncio.run(run())
    assert not any(log["event"].startswith("stream.") for log in logs)
    for secret in ("fixture-key", "partial-secret", "private-cookie", "私密请求正文"):
        assert secret not in json.dumps(logs, ensure_ascii=False)


@pytest.mark.parametrize(("temporary", "retries", "failover", "expected"), [
    (True, 1, 2, ["primary", "primary"]),
    (False, 1, 2, ["primary", "primary", "backup"]),
    (False, 1, 1, ["primary", "primary"]),
    (False, 0, 2, ["primary", "backup"]),
])
def test_remote_protocol_error_uses_configured_retries_and_failover(
    temporary, retries, failover, expected,
):
    requests = []
    records = []

    def handle(request):
        model = json.loads(request.content)["model"]
        requests.append(model)
        if model == "primary" and (not temporary or len(requests) == 1):
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return stream_response(response({"role": "assistant", "content": "恢复成功"}))

    def gateway(base_url, model, **kwargs):
        return AgentChat(
            base_url=base_url, model=model, **kwargs, protocol="openai_compatible",
            api_mode="chat_completions", parameters={},
            http_async_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
        )

    async def run():
        router = RoutingModel(
            "analysis", "analysis", [
                ModelCandidate(i, i, name, name, "http://test/v1", "fixture-key", 5, None, 128,
                               extra_retries=retries)
                for i, name in enumerate(("primary", "backup"), 1)
            ], gateway, records.append, failover_limit=failover, retry_base_seconds=0,
        )
        try:
            call = router.chat([message_to_dict(HumanMessage(content="分析"))], [TOOL])
            if not temporary and failover == 1:
                with pytest.raises(ModelUnavailable, match="Server disconnected"):
                    await call
            else:
                assert (await call).content == "恢复成功"
        finally:
            await router.aclose()

    asyncio.run(run())
    assert requests == expected
    assert len(records) == len(expected), "每个实际 HTTP 请求必须落账，SDK 不得隐式倍增重试"
    assert len({record.invocation_id for record in records}) == 1
    assert [record.request_ordinal for record in records] == list(range(1, len(expected) + 1))
    assert records[0].status == "unknown"
    assert "Server disconnected" in records[0].error_message
    assert records[1].retry_ordinal == (1 if retries else 0)


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
            with pytest.raises(ModelUnavailable) as error:
                await model.chat([message_to_dict(HumanMessage(content="检索"))], [TOOL])
            assert error.value.retry_after == 5
        finally:
            await model.aclose()

    asyncio.run(run())


def test_native_refusal_stops_processing():
    async def run():
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: stream_response(
                    response({"role": "assistant", "content": "", "refusal": "拒绝"})
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
                transport=httpx.MockTransport(lambda _: stream_response(body))
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
                transport=httpx.MockTransport(lambda _: stream_response(body))
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
                lambda _: stream_response(response({"role": "assistant", "content": ""}))
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
