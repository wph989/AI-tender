"""网关长请求会断连；流式传输只有完整结束后才能进入原有业务校验。"""

import asyncio
import json

import httpx
import pytest

from tender.adapters.openai_chat import OpenAIChatModel
from tender.domain.errors import ExtractionUnavailable, ModelOutputTruncated, ModelRefused


class FragmentedStream(httpx.AsyncByteStream):
    def __init__(self, content):
        self.content = content

    async def __aiter__(self):
        # 网络分片可落在中文UTF-8字符内部，不能假设一个网络块就是一个JSON事件。
        for offset in range(0, len(self.content), 7):
            yield self.content[offset : offset + 7]


def event(delta=None, finish=None):
    return {"choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}]}


def complete(chunks, *, done=True):
    data = ": keep-alive\n\n" + "".join(
        "data: " + json.dumps(chunk, ensure_ascii=False) + "\n\n" for chunk in chunks
    )
    if done:
        data += "data: [DONE]\n\n"

    def handle(request):
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            stream=FragmentedStream(data.encode("utf-8")),
        )

    async def run():
        async with httpx.AsyncClient(
            base_url="http://test/v1/", transport=httpx.MockTransport(handle)
        ) as client:
            return await OpenAIChatModel("http://test/v1", "fixture", client=client).complete(
                "校验"
            )

    return asyncio.run(run())


def test_stream_joins_only_final_content_and_preserves_trailing_usage():
    result = complete(
        [
            event({"reasoning_content": '{"错误":true}'}),
            event({"content": '{"结果":'}),
            event({"content": '"通过"}'}),
            event(finish="stop"),
            {
                "choices": [],
                "model": "actual",
                "usage": {"prompt_tokens": 11, "completion_tokens": 22},
            },
        ]
    )
    assert json.loads(result.content) == {"结果": "通过"}
    assert (result.model, result.prompt_tokens, result.completion_tokens) == ("actual", 11, 22)


@pytest.mark.parametrize("done,finish", [(False, "stop"), (True, None)])
def test_stream_cannot_accept_json_without_both_completion_markers(done, finish):
    with pytest.raises(ExtractionUnavailable, match="未完整结束"):
        complete([event({"content": '{"supported":true}'}, finish)], done=done)


def test_stream_refusal_is_not_retried_as_transport_failure():
    with pytest.raises(ModelRefused):
        complete([event({"refusal": "拒绝"}, "stop")])


def test_stream_token_limit_preserves_usage_even_if_prefix_is_valid_json():
    with pytest.raises(ModelOutputTruncated) as caught:
        complete(
            [
                event({"content": '{"supported":true}'}, "length"),
                {"choices": [], "usage": {"prompt_tokens": 11, "completion_tokens": 12000}},
            ]
        )
    assert caught.value.completion_tokens == 12000


def test_stream_error_does_not_expose_provider_payload():
    with pytest.raises(ExtractionUnavailable) as caught:
        complete([{"error": {"message": "secret-provider-body"}}])
    assert "secret-provider-body" not in str(caught.value)
