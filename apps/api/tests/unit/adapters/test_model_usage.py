"""完整请求只记录一次用量，坏JSON和缺失推理分项同样可诊断。"""

import asyncio
import json

import httpx
import pytest
from langchain_core.messages import HumanMessage, message_to_dict
from structlog.testing import capture_logs
from test_agent_chat import TOOL, agent, response, stream_response
from test_openai_stream import complete, event
from test_response_timeout import MODES, events

from tender.adapters.llm.openai_chat import OpenAIChatModel
from tender.domain.shared.errors import InvalidModelOutput


@pytest.mark.parametrize("protocol,mode", MODES)
@pytest.mark.parametrize("stream", [False, True])
def test_four_protocols_log_one_complete_usage_even_for_bad_json(protocol, mode, stream):
    async def run():
        usage = ({"prompt_tokens": 11, "completion_tokens": 22,
                  "completion_tokens_details": {"reasoning_tokens": 17}}
                 if mode == "chat_completions" else
                 {"input_tokens": 11, "output_tokens": 22,
                  "output_tokens_details": {"reasoning_tokens": 17}}
                 if mode == "responses" else
                 {"input_tokens": 11, "output_tokens": 22}
                 if mode == "messages" else
                 {"promptTokenCount": 11, "candidatesTokenCount": 22, "thoughtsTokenCount": 17})
        payload = {
            "chat_completions": {"choices": [{"message": {"content": "bad-json"}}], "usage": usage},
            "responses": {"output": [{"content": [{"type": "output_text", "text": "bad-json"}]}],
                          "usage": usage},
            "messages": {"content": [{"type": "text", "text": "bad-json"}], "usage": usage},
            "generate_content": {"candidates": [{"content": {"parts": [{"text": "bad-json"}]}}],
                                 "usageMetadata": usage},
        }[mode]
        chunks = events(mode)
        if mode == "chat_completions":
            chunks.insert(-1, event_usage({"choices": [], "usage": usage}))
        elif mode == "responses":
            chunks[-1] = event_usage({"type": "response.completed", "response": payload})
        elif mode == "messages":
            chunks.insert(-1, event_usage({"type": "message_delta", "usage": usage,
                                          "delta": {"stop_reason": "end_turn"}}))
        else:
            chunks[-1] = event_usage({"candidates": [{"finishReason": "STOP"}],
                                     "usageMetadata": usage})
        upstream = (httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  text="".join(chunks)) if stream
                    else httpx.Response(200, json=payload))
        async with httpx.AsyncClient(base_url="http://test/v1/", transport=httpx.MockTransport(
                lambda _: upstream)) as client:
            model = OpenAIChatModel("http://test/v1", "fixture", client=client,
                                    protocol=protocol, api_mode=mode)
            with capture_logs() as logs:
                if stream and mode != "responses":
                    await model.complete("secret-prompt")
                else:
                    with pytest.raises(InvalidModelOutput):
                        await model.complete("secret-prompt")
            entries = [entry for entry in logs if entry["event"] == "model.usage"]
            assert len(entries) == 1
            entry = entries[0]
            assert entry["log_level"] == "debug"
            assert (entry["prompt_tokens"], entry["completion_tokens"]) == (11, 22)
            assert entry["reasoning_tokens"] == (None if mode == "messages" else 17)
            assert "secret-prompt" not in json.dumps(entries)

    asyncio.run(run())


def event_usage(payload):
    return "data: " + json.dumps(payload) + "\n\n"


def test_stream_cumulative_usage_is_not_summed_or_logged_per_increment():
    with capture_logs() as logs:
        complete([event({"content": "{}"}, "stop"),
                  {"choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 4}},
                  {"choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 7}}])
    entries = [entry for entry in logs if entry["event"] == "model.usage"]
    assert len(entries) == 1 and entries[0]["completion_tokens"] == 7
    assert entries[0]["reasoning_tokens"] is None


def test_agent_invalid_tool_arguments_still_log_complete_usage():
    async def run():
        payload = response({"content": None, "tool_calls": [{"id": "call_1", "type": "function",
            "function": {"name": "search_document", "arguments": "bad-json"}}]})
        payload["usage"]["completion_tokens_details"] = {"reasoning_tokens": 5}
        model = agent(httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: stream_response(payload))))
        try:
            with capture_logs() as logs:
                with pytest.raises(InvalidModelOutput):
                    await model.chat([message_to_dict(HumanMessage(content="secret-prompt"))],
                                     [TOOL])
            entries = [entry for entry in logs if entry["event"] == "model.usage"]
            assert len(entries) == 1
            assert (entries[0]["prompt_tokens"], entries[0]["completion_tokens"]) == (12, 7)
            assert entries[0]["reasoning_tokens"] == 5
            assert "bad-json" not in json.dumps(entries)
        finally:
            await model.aclose()

    asyncio.run(run())
