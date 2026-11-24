"""使用真实异步 HTTP 流核对有效增量计时，网络心跳不能替模型续期。"""

import asyncio
import json

import httpx
import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, message_to_dict
from structlog.testing import capture_logs

from tender.adapters.llm.agent_chat import AgentChat
from tender.adapters.llm.openai_chat import OpenAIChatModel
from tender.adapters.llm.response_timeout import message_has_increment
from tender.domain.shared.errors import ModelOutputTruncated, ModelUnavailable

MODES = [
    ("openai_compatible", "chat_completions"), ("openai", "responses"),
    ("anthropic", "messages"), ("gemini", "generate_content"),
]

TOOL = {"type": "function", "function": {"name": "probe", "description": "测试工具",
        "parameters": {"type": "object", "properties": {}}}}


class TimedStream(httpx.AsyncByteStream):
    def __init__(self, parts, delay=0.08):
        self.parts, self.delay = parts, delay
        self.closed = False

    async def __aiter__(self):
        for part in self.parts:
            await asyncio.sleep(self.delay)
            yield part if isinstance(part, bytes) else part.encode("utf-8")

    async def aclose(self):
        self.closed = True


def event(data):
    return "data: " + json.dumps(data) + "\n\n"


def events(mode, *, finish=True):
    text = ['{"', 'ok', '":', 'true', '}']
    if mode == "chat_completions":
        result = [event({"choices": [{"delta": {"reasoning_content": "先检查"}}]})]
        result += [event({"choices": [{"delta": {"content": t}}]}) for t in text]
        if finish:
            result += [event({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
                       "data: [DONE]\n\n"]
    elif mode == "responses":
        result = [event({"type": "response.reasoning_summary_text.delta", "delta": "先检查"})]
        result += [event({"type": "response.output_text.delta", "delta": t}) for t in text]
        if finish:
            result += [event({"type": "response.completed", "response": {
                "status": "completed", "output": [{"content": [{"type": "output_text",
                                                                      "text": "".join(text)}]}],
            }})]
    elif mode == "messages":
        result = [event({"type": "message_start", "message": {"content": [], "usage": {}}}),
                  event({"type": "content_block_start", "index": 0,
                         "content_block": {"type": "text", "text": ""}})]
        result += [event({"type": "content_block_delta", "index": 0,
                          "delta": {"type": "text_delta", "text": t}}) for t in text]
        if finish:
            result += [event({"type": "message_delta", "delta": {"stop_reason": "end_turn"}}),
                       event({"type": "message_stop"})]
    else:
        result = [
            event({"candidates": [{"content": {"parts": [{"text": "先检查", "thought": True}]}}]})
        ]
        result += [event({"candidates": [{"content": {"parts": [{"text": t}]}}]}) for t in text]
        if finish:
            result += [event({"candidates": [{"finishReason": "STOP"}]})]
    return result


@pytest.mark.parametrize("protocol,mode", MODES)
def test_effective_stream_can_exceed_interval(protocol, mode):
    async def run():
        stream = TimedStream(events(mode))
        def handle(request):
            assert request.extensions["timeout"]["read"] is None
            body = json.loads(request.content)
            assert body.get("stream") is True or ":streamGenerateContent?alt=sse" in str(
                request.url
            )
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

        async with httpx.AsyncClient(
            base_url="http://test/v1/", transport=httpx.MockTransport(handle)
        ) as client:
            model = OpenAIChatModel("http://test/v1", "fixture", client=client,
                                    timeout=0.5, protocol=protocol, api_mode=mode)
            with capture_logs() as logs:
                result = await model.complete("测试")
            assert json.loads(result.content) == {"ok": True}
            timing = next(log for log in logs if log["event"] == "model.response_timing")
            assert timing["first_increment_ms"] is not None
            assert timing["timeout_kind"] is None
            assert stream.closed
    asyncio.run(run())


@pytest.mark.parametrize("protocol,mode", MODES)
@pytest.mark.parametrize("metadata", [False, True, "empty"])
def test_heartbeats_and_metadata_do_not_extend_first_increment(protocol, mode, metadata):
    async def run():
        value = (
            {"choices": [{"delta": {"role": "assistant"}}]}
            if mode == "chat_completions"
            else {"type": "ping"}
        )
        stream = TimedStream([
            "data: \n\n" if metadata == "empty" else
            event(value) if metadata else ": heartbeat\n\n"
        ] * 15)
        async with httpx.AsyncClient(
            base_url="http://test/v1/",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=stream,
                )
            ),
        ) as client:
            model = OpenAIChatModel("http://test/v1", "fixture", client=client, timeout=0.5,
                                    protocol=protocol, api_mode=mode)
            with pytest.raises(ModelUnavailable, match="首个有效模型增量等待") as failure:
                await model.complete("测试")
            assert failure.value.timeout_kind == "first_increment"
            assert stream.closed
    asyncio.run(run())


@pytest.mark.parametrize("protocol,mode", MODES)
def test_total_timeout_and_incomplete_stream(protocol, mode):
    async def run(total, finish):
        async with httpx.AsyncClient(
            base_url="http://test/v1/",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=TimedStream(events(mode, finish=finish), delay=0.08 if total else 0),
                )
            ),
        ) as client:
            model = OpenAIChatModel("http://test/v1", "fixture", client=client, timeout=0.5,
                                    total_timeout=total, protocol=protocol, api_mode=mode)
            with pytest.raises(ModelUnavailable, match="总时限" if total else "未完整结束"):
                await model.complete("测试")
    asyncio.run(run(0.35, True))
    asyncio.run(run(None, False))


def test_wait_for_headers_and_nonstream_json_is_first_increment_wait():
    async def run():
        async def slow_headers(_):
            await asyncio.sleep(0.8)
            return httpx.Response(200, json={})

        async with httpx.AsyncClient(
            base_url="http://test/v1/", transport=httpx.MockTransport(slow_headers)
        ) as client:
            model = OpenAIChatModel("http://test/v1", "fixture", client=client, timeout=0.5)
            with pytest.raises(ModelUnavailable, match="首个有效模型增量等待"):
                await model.complete("测试")
        body = json.dumps({"choices": [{"message": {"content": '{"ok":true}'}}]})
        stream = TimedStream([body[:10], body[10:]], delay=0.3)
        async with httpx.AsyncClient(
            base_url="http://test/v1/",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    headers={"content-type": "application/json"},
                    stream=stream,
                )
            ),
        ) as client:
            model = OpenAIChatModel("http://test/v1", "fixture", client=client, timeout=0.5)
            with pytest.raises(ModelUnavailable, match="首个有效模型增量等待"):
                await model.complete("测试")
    asyncio.run(run())


def test_body_then_only_heartbeats_times_out_between_increments():
    async def run():
        stream = TimedStream([event({"choices": [{"delta": {"content": "{"}}]})]
                             + [": heartbeat\n\n"] * 15)
        async with httpx.AsyncClient(
            base_url="http://test/v1/",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=stream,
                )
            ),
        ) as client:
            model = OpenAIChatModel("http://test/v1", "fixture", client=client, timeout=0.5)
            with pytest.raises(ModelUnavailable, match="有效增量响应间隔") as failure:
                await model.complete("测试")
            assert failure.value.timeout_kind == "response_interval"
    asyncio.run(run())


def test_agent_chunk_progress_excludes_identity_and_includes_reasoning_and_arguments():
    from langchain_core.messages import AIMessage

    assert not message_has_increment(
        AIMessageChunk(content="", additional_kwargs={"role": "assistant"})
    )
    assert not message_has_increment(
        AIMessageChunk(content=[{"type": "thinking", "signature": "签名"}])
    )
    assert message_has_increment(AIMessageChunk(content=[{"type": "thinking", "thinking": "推理"}]))
    assert message_has_increment(
        AIMessageChunk(content=[{"type": "reasoning", "reasoning": "推理"}])
    )
    assert message_has_increment(AIMessageChunk(content="", tool_call_chunks=[{
        "name": None, "args": '{"query":', "id": None, "index": 0,
    }]))
    assert not message_has_increment(AIMessageChunk(content="", tool_call_chunks=[{
        "name": "probe", "args": "", "id": "call_1", "index": 0,
    }]))
    assert message_has_increment(AIMessage(content="", tool_calls=[{
        "name": "probe", "args": {}, "id": "call_1",
    }]))



def test_responses_incomplete_is_not_success():
    async def run():
        async with httpx.AsyncClient(
            base_url="http://test/v1/",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    text=event(
                        {
                            "type": "response.incomplete",
                            "response": {"status": "incomplete", "output": []},
                        }
                    ),
                )
            ),
        ) as client:
            model = OpenAIChatModel(
                "http://test/v1", "fixture", client=client, api_mode="responses"
            )
            with pytest.raises(ModelOutputTruncated):
                await model.complete("测试")
    asyncio.run(run())


@pytest.mark.parametrize("protocol,mode", MODES)
@pytest.mark.parametrize("code", [None, "server_error"])
def test_stream_error_without_http_code_rejects_prior_content(protocol, mode, code):
    async def run():
        error = {"message": "generation failed fixture-secret", "type": "server_error"}
        if code is not None:
            error["code"] = code
        data = events(mode)
        # 错误后仍给结束标记，才能证明失败事件不会被已有正文和正常结束掩盖。
        data.insert(-2 if mode in {"chat_completions", "messages"} else -1,
                    event({"error": error}))
        stream = TimedStream(data, delay=0)
        async with httpx.AsyncClient(
            base_url="http://test/v1/", transport=httpx.MockTransport(
                lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"},
                                         stream=stream),
            ),
        ) as client:
            model = OpenAIChatModel(
                "http://test/v1", "fixture", api_key="fixture-secret", client=client,
                timeout=2, protocol=protocol, api_mode=mode,
            )
            with pytest.raises(ModelUnavailable, match="流式响应报告错误") as failure:
                await model.complete("测试")
            assert "generation failed" not in str(failure.value)
            assert "fixture-secret" not in str(failure.value)
            assert stream.closed
    asyncio.run(run())


@pytest.mark.parametrize("terminal_error", [False, True])
def test_responses_error_events_without_http_code_are_not_ignored(terminal_error):
    async def run():
        error = {"code": "server_error", "message": "generation failed"}
        data = events("responses")
        if terminal_error:
            # 终态错误对象同样需要兜底，不能只依赖之后缺少结束标记才报错。
            data[-1] = event({"type": "response.failed", "response": {
                "status": "failed", "error": error, "output": [],
            }})
        else:
            data.insert(-1, event({"type": "error", **error}))
        async with httpx.AsyncClient(
            base_url="http://test/v1/", transport=httpx.MockTransport(
                lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"},
                                         text="".join(data)),
            ),
        ) as client:
            model = OpenAIChatModel("http://test/v1", "fixture", client=client,
                                    protocol="openai", api_mode="responses")
            with pytest.raises(ModelUnavailable, match="流式响应报告错误") as failure:
                await model.complete("测试")
            assert "generation failed" not in str(failure.value)
    asyncio.run(run())


@pytest.mark.parametrize("final_usage,expected_input", [
    ({"output_tokens": 7}, 174),
    ({"output_tokens": 7, "input_tokens": None, "cache_read_input_tokens": None}, 174),
    ({"output_tokens": 7, "input_tokens": 123, "cache_read_input_tokens": 45,
      "cache_creation_input_tokens": 6}, 174),
    ({"output_tokens": 7, "input_tokens": 0, "cache_read_input_tokens": 0,
      "cache_creation_input_tokens": 0}, 0),
    ({"output_tokens": 7, "input_tokens": 10, "cache_read_input_tokens": 5,
      "cache_creation_input_tokens": 0}, 15),
])
def test_anthropic_agent_merges_cumulative_usage_without_losing_initial_input(
    final_usage, expected_input,
):
    import httpx2
    from anthropic import AsyncAnthropic

    async def run():
        data = [
            {"type": "message_start", "message": {
                "id": "msg_1", "type": "message", "role": "assistant", "model": "fixture",
                "content": [], "usage": {"input_tokens": 123, "output_tokens": 1,
                                          "cache_read_input_tokens": 45,
                                          "cache_creation_input_tokens": 6},
            }},
            {"type": "content_block_start", "index": 0, "content_block": {
                "type": "tool_use", "id": "call_1", "name": "probe", "input": {},
            }},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "input_json_delta", "partial_json": "{"}},
            {"type": "content_block_delta", "index": 0,
             "delta": {"type": "input_json_delta", "partial_json": "}"}},
            {"type": "content_block_stop", "index": 0},
            # 用量是累计值；多次message_delta不能把4与7再次相加。
            {"type": "message_delta", "delta": {"stop_reason": None, "stop_sequence": None},
             "usage": {"output_tokens": 4}},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use",
                                                  "stop_sequence": None},
             "usage": final_usage},
            {"type": "message_stop"},
        ]
        body = "".join("event: " + item["type"] + "\n" + event(item) for item in data)
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(
            lambda _: httpx2.Response(200, headers={"content-type": "text/event-stream"},
                                      text=body),
        ))
        model = AgentChat(
            base_url="http://test/v1", model="fixture", api_key="fixture", timeout=2,
            temperature=None, max_tokens=128, protocol="anthropic", api_mode="messages",
            parameters={},
        )
        model.model._async_client = AsyncAnthropic(
            api_key="fixture", http_client=client, timeout=None, max_retries=0,
        )
        try:
            result = await model.chat([message_to_dict(HumanMessage(content="测试"))], [TOOL])
            assert result.agent_message["data"]["tool_calls"][0]["args"] == {}
            assert (result.prompt_tokens, result.completion_tokens) == (expected_input, 7)
            usage = result.agent_message["data"]["usage_metadata"]
            assert usage["total_tokens"] == expected_input + 7
            expected_cache = final_usage.get("cache_read_input_tokens")
            assert usage["input_token_details"]["cache_read"] == (
                45 if expected_cache is None else expected_cache
            )
        finally:
            await model.aclose()
    asyncio.run(run())


def test_agent_responses_observes_raw_reasoning_before_sdk_conversion():
    async def run():
        terminal = {"id": "resp_1", "object": "response", "created_at": 1,
                    "model": "fixture", "status": "completed", "error": None,
                    "output": [{"id": "msg_1", "type": "message", "role": "assistant",
                                "status": "completed", "content": [{"type": "output_text",
                                "text": "完成", "annotations": []}]}],
                    "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}}
        parts = [event({"type": "response.reasoning_text.delta", "delta": "推理",
                        "output_index": 0, "content_index": 0, "item_id": "think_1"})] * 12
        parts += [event({"type": "response.output_text.delta", "delta": "完成",
                         "output_index": 1, "content_index": 0, "item_id": "msg_1"}),
                  event({"type": "response.completed", "response": terminal})]
        stream = TimedStream(parts, delay=0.5)
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=stream,
        )))
        model = AgentChat(base_url="http://test/v1", model="fixture", api_key="fixture",
                          timeout=5, temperature=None, max_tokens=128, protocol="openai",
                          api_mode="responses", parameters={}, http_async_client=client)
        model.model.root_async_client._platform = "test"
        # 本例衡量增量续期；先初始化 SDK 流资源，避免首次模块加载占用首包时限。
        _ = model.model.root_async_client.responses.with_streaming_response
        try:
            result = await model.chat([message_to_dict(HumanMessage(content="测试"))], [])
            assert result.content == "完成"
            assert (result.prompt_tokens, result.completion_tokens) == (2, 3)
            assert stream.closed
        finally:
            await model.aclose()
    asyncio.run(run())


@pytest.mark.parametrize("finish", [True, False])
def test_agent_anthropic_requires_message_stop_with_real_sdk(finish):
    import httpx2
    from anthropic import AsyncAnthropic

    async def run():
        data = events("messages", finish=finish)
        # 使用正式 SDK 验证事件解析与 stop_reason 聚合，不以普通文本模拟工具协议。
        data[0] = event(
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": "fixture",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 2, "output_tokens": 0},
                },
            }
        )
        if finish:
            data[-2] = event({"type": "message_delta", "delta": {"stop_reason": "end_turn"},
                              "usage": {"output_tokens": 3}})
        # Anthropic SDK按SSE event字段选择事件，正式Messages协议须同时携带event和data。
        data = ["event: " + json.loads(part[6:])["type"] + "\n" + part for part in data]

        class AnthropicStream(httpx2.AsyncByteStream):
            async def __aiter__(self):
                for part in data:
                    await asyncio.sleep(0.02)
                    yield part.encode("utf-8")

        def handle(request):
            # bind_tools必须保留供应商原生工具结构，不能把OpenAI wrapper直传Messages。
            assert json.loads(request.content)["tools"][0]["name"] == "probe"
            return httpx2.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=AnthropicStream(),
            )
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
        model = AgentChat(
            base_url="http://test/v1",
            model="fixture",
            api_key="fixture",
            timeout=2,
            temperature=None,
            max_tokens=128,
            protocol="anthropic",
            api_mode="messages",
            parameters={},
        )
        model.model._async_client = AsyncAnthropic(
            api_key="fixture",
            base_url="http://test/v1",
            http_client=client,
            timeout=None,
            max_retries=0,
        )
        try:
            if finish:
                result = await model.chat([message_to_dict(HumanMessage(content="测试"))], [TOOL])
                assert json.loads(result.content) == {"ok": True}
                assert (result.prompt_tokens, result.completion_tokens) == (2, 3)
            else:
                with pytest.raises(ModelUnavailable, match="未完整结束"):
                    await model.chat([message_to_dict(HumanMessage(content="测试"))], [TOOL])
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("finish", [True, False])
def test_agent_gemini_uses_sdk_conversion_and_requires_finish(finish):
    import httpx2

    async def run():
        def handle(request):
            assert request.url.path.endswith(":streamGenerateContent")
            body = json.loads(request.content)
            assert body["contents"][0]["parts"][0]["text"] == "测试"
            assert body["tools"][0]["functionDeclarations"][0]["name"] == "probe"
            return httpx2.Response(
                200,
                headers={"content-type": "text/event-stream"},
                text=": heartbeat\n\n"
                + "".join(
                    events("generate_content", finish=finish),
                ),
            )

        model = AgentChat(
            base_url="http://test/v1",
            model="fixture",
            api_key="fixture",
            timeout=2,
            temperature=None,
            max_tokens=128,
            protocol="gemini",
            api_mode="generate_content",
            parameters={},
        )
        api = model.model.client._api_client
        await api._async_httpx_client.aclose()
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(handle))
        api._async_httpx_client = client
        try:
            if finish:
                result = await model.chat([message_to_dict(HumanMessage(content="测试"))], [TOOL])
                assert json.loads(result.content) == {"ok": True}
            else:
                with pytest.raises(ModelUnavailable, match="未完整结束"):
                    await model.chat([message_to_dict(HumanMessage(content="测试"))], [TOOL])
        finally:
            await model.aclose()
        assert client.is_closed

    asyncio.run(run())


def test_agent_chat_requires_done_after_finish_reason():
    async def run():
        # 兼容网关只给finish_reason后断连，不能作为完整协议结束。
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    text="".join(events("chat_completions")[:-1]),
                )
            )
        )
        model = AgentChat(
            base_url="http://test/v1",
            model="fixture",
            api_key="fixture",
            timeout=2,
            temperature=None,
            max_tokens=128,
            protocol="openai",
            api_mode="chat_completions",
            parameters={},
            http_async_client=client,
        )
        try:
            with pytest.raises(ModelUnavailable, match="未完整结束"):
                await model.chat([message_to_dict(HumanMessage(content="测试"))], [])
        finally:
            await model.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("protocol,mode", MODES)
def test_agent_accepts_full_json_when_stream_parameter_is_ignored(protocol, mode):
    import httpx2
    from anthropic import AsyncAnthropic

    async def run():
        if mode == "chat_completions":
            data = {
                "model": "fixture",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "完成"},
                    }
                ],
            }
        elif mode == "responses":
            data = {
                "id": "resp_1",
                "object": "response",
                "created_at": 1,
                "model": "fixture",
                "status": "completed",
                "error": None,
                "output": [
                    {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "完成", "annotations": []}],
                    }
                ],
            }
        elif mode == "messages":
            data = {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "fixture",
                "content": [{"type": "text", "text": "完成"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 2, "output_tokens": 3},
            }
        else:
            data = {
                "candidates": [{"content": {"parts": [{"text": "完成"}]}, "finishReason": "STOP"}]
            }
        options = {}
        if protocol.startswith("openai"):
            client = httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, json=data),
                )
            )
            options["http_async_client"] = client
        else:
            client = httpx2.AsyncClient(
                transport=httpx2.MockTransport(
                    lambda _: httpx2.Response(200, json=data),
                )
            )
        model = AgentChat(
            base_url="http://test/v1",
            model="fixture",
            api_key="fixture",
            timeout=2,
            temperature=None,
            max_tokens=128,
            protocol=protocol,
            api_mode=mode,
            parameters={},
            **options,
        )
        if mode == "messages":
            model.model._async_client = AsyncAnthropic(
                api_key="fixture",
                http_client=client,
                timeout=None,
                max_retries=0,
            )
        elif mode == "generate_content":
            api = model.model.client._api_client
            await api._async_httpx_client.aclose()
            api._async_httpx_client = client
        try:
            with capture_logs() as logs:
                assert (
                    await model.chat([message_to_dict(HumanMessage(content="测试"))], [])
                ).content == "完成"
            entries = [e for e in logs if e["event"] == "model.usage"]
            assert len(entries) == 1 and entries[0]["log_level"] == "debug"
        finally:
            await model.aclose()

    asyncio.run(run())
