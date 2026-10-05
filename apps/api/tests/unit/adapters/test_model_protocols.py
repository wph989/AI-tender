"""模拟已实现协议的请求和返回；不依赖真实供应商或私有凭证。"""

import asyncio
import json

import httpx
import pytest

from tender.adapters.openai_chat import OpenAIChatModel
from tender.adapters.rerank_http import HttpRerankModel
from tender.domain.errors import ExtractionFailed, ExtractionUnavailable, ModelRefused


@pytest.mark.parametrize(
    "protocol,mode,path,payload",
    [
        (
            "openai",
            "responses",
            "responses",
            {
                "output": [{"content": [{"type": "output_text", "text": '{"ok":true}'}]}],
                "usage": {"input_tokens": 4, "output_tokens": 2},
            },
        ),
        (
            "anthropic",
            "messages",
            "messages",
            {
                "content": [{"type": "text", "text": '{"ok":true}'}],
                "usage": {"input_tokens": 4, "output_tokens": 2},
            },
        ),
        (
            "gemini",
            "generate_content",
            "models/fixture:generateContent",
            {
                "candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}],
                "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
            },
        ),
        (
            "openai_compatible",
            "chat_completions",
            "chat/completions",
            {
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            },
        ),
    ],
)
def test_native_request_paths_headers_and_usage(protocol, mode, path, payload):
    def handle(request):
        assert request.url.path == "/v1/" + path
        body = json.loads(request.content)
        assert "temperature" not in body
        if protocol == "anthropic":
            assert request.headers["x-api-key"] == "fixture-key"
            assert body["max_tokens"] == 128
        elif protocol == "gemini":
            assert request.headers["x-goog-api-key"] == "fixture-key"
            assert body["generationConfig"]["maxOutputTokens"] == 128
        else:
            assert request.headers["Authorization"] == "Bearer fixture-key"
        return httpx.Response(200, json=payload)

    async def run():
        async with httpx.AsyncClient(
            base_url="http://test/v1/", transport=httpx.MockTransport(handle)
        ) as client:
            model = OpenAIChatModel(
                "http://test/v1",
                "fixture",
                api_key="fixture-key",
                protocol=protocol,
                api_mode=mode,
                max_tokens=128,
                client=client,
            )
            completion = await model.complete("测试")
            assert completion.prompt_tokens == 4
            assert completion.completion_tokens == 2

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload,error",
    [
        ({"choices": [{"message": {"refusal": "private text", "content": None}}]}, ModelRefused),
        ({"choices": [{"message": {"content": "[]"}}]}, ExtractionFailed),
        ({"choices": [{"message": {"content": "invalid"}}]}, ExtractionFailed),
        (None, ExtractionFailed),
    ],
)
def test_invalid_or_refused_output_has_safe_error(payload, error):
    async def run():
        async with httpx.AsyncClient(
            base_url="http://test/",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
        ) as client:
            with pytest.raises(error) as caught:
                await OpenAIChatModel("http://test", "fixture", client=client).complete("测试")
            assert "private text" not in str(caught.value)

    asyncio.run(run())


def test_rate_limit_preserves_retry_after_without_echoing_body():
    async def run():
        async with httpx.AsyncClient(
            base_url="http://test/",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, headers={"Retry-After": "2"}, text="secret-key")
            ),
        ) as client:
            with pytest.raises(ExtractionUnavailable) as caught:
                await OpenAIChatModel("http://test", "fixture", client=client).complete("测试")
            assert caught.value.retry_after == 2
            assert "secret-key" not in str(caught.value)

    asyncio.run(run())


@pytest.mark.parametrize(
    "rows",
    [
        [{"index": 0, "relevance_score": 1}, {"index": 0, "relevance_score": 2}],
        [{"index": True, "relevance_score": 1}, {"index": 1, "relevance_score": 2}],
        [{"index": 3, "relevance_score": 1}, {"index": 1, "relevance_score": 2}],
        [{"index": 0, "relevance_score": "1"}, {"index": 1, "relevance_score": 2}],
        [],
    ],
)
def test_rerank_rejects_wrong_identity_and_scores(rows):
    async def run():
        async with httpx.AsyncClient(
            base_url="http://test/",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"results": rows})),
        ) as client:
            with pytest.raises(ExtractionFailed):
                await HttpRerankModel("http://test", "fixture", client=client).rerank(
                    "测试", ["甲", "乙"], 2
                )

    asyncio.run(run())
