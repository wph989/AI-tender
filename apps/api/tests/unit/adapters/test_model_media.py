"""冻结真实协议载荷；测试通过必须证明图片字节和配置参数确实出站。"""

import asyncio
import json

import httpx
import pytest

from tender.adapters.openai_chat import OpenAIChatModel
from tender.adapters.openai_embedding import OpenAIEmbeddingModel
from tender.adapters.provider_image import ProviderImageModel
from tender.application.model_probes import PROBE_IMAGE
from tender.application.model_profiles import validate_model
from tender.domain.errors import ExtractionFailed
from tender.ports.model_media import EmbeddingInput


@pytest.mark.parametrize(
    "protocol,mode,path,output",
    [
        (
            "openai",
            "chat_completions",
            "/v1/chat/completions",
            {"choices": [{"message": {"content": "红蓝"}}]},
        ),
        (
            "openai",
            "responses",
            "/v1/responses",
            {"output": [{"content": [{"type": "output_text", "text": "红蓝"}]}]},
        ),
        ("anthropic", "messages", "/v1/messages", {"content": [{"type": "text", "text": "红蓝"}]}),
        (
            "gemini",
            "generate_content",
            "/v1/models/fixture:generateContent",
            {"candidates": [{"content": {"parts": [{"text": "红蓝"}]}}]},
        ),
    ],
)
def test_vision_sends_inline_image_and_uses_native_parameters(protocol, mode, path, output):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        assert request.url.path == path
        assert PROBE_IMAGE.base64 in request.content.decode()
        assert "response_format" not in body and "text" not in body
        if protocol == "gemini":
            assert body["generationConfig"]["topP"] == 0.7
        else:
            assert body["top_p"] == 0.7
        return httpx.Response(200, json=output)

    async def run():
        async with httpx.AsyncClient(
            base_url="http://fixture/v1/", transport=httpx.MockTransport(handler)
        ) as client:
            model = OpenAIChatModel(
                "http://fixture/v1",
                "fixture",
                client=client,
                protocol=protocol,
                api_mode=mode,
                capabilities=["text_input", "image_input"],
                parameters={"top_p": 0.7},
            )
            result = await model.complete("描述颜色", images=(PROBE_IMAGE,), json_mode=False)
            assert result.content == "红蓝"

    asyncio.run(run())
    assert len(requests) == 1


def test_gemini_multimodal_embedding_aggregates_text_and_image_in_one_content():
    def handler(request):
        assert request.url.path == "/v1beta/models/fixture:batchEmbedContents"
        entry = json.loads(request.content)["requests"][0]
        assert entry["content"]["parts"][0] == {"text": "红蓝"}
        assert entry["content"]["parts"][1]["inlineData"]["data"] == PROBE_IMAGE.base64
        assert entry["outputDimensionality"] == 3
        return httpx.Response(200, json={"embeddings": [{"values": [0.1, 0.2, 0.3]}]})

    async def run():
        async with httpx.AsyncClient(
            base_url="http://fixture/v1beta/", transport=httpx.MockTransport(handler)
        ) as client:
            model = OpenAIEmbeddingModel(
                "http://fixture",
                "fixture",
                protocol="gemini",
                client=client,
                parameters={"dimensions": 3},
                allow_images=True,
            )
            assert await model.embed_inputs([EmbeddingInput("红蓝", (PROBE_IMAGE,))]) == [
                [0.1, 0.2, 0.3]
            ]

    asyncio.run(run())


def test_standard_embedding_never_discards_image_or_accepts_wrong_dimensions():
    requests = []

    def handler(request):
        requests.append(request)
        assert json.loads(request.content)["dimensions"] == 2
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 2, 3]}]})

    async def run():
        async with httpx.AsyncClient(
            base_url="http://fixture/", transport=httpx.MockTransport(handler)
        ) as client:
            model = OpenAIEmbeddingModel(
                "http://fixture", "fixture", client=client, parameters={"dimensions": 2}
            )
            with pytest.raises(ValueError, match="不能静默丢弃"):
                await model.embed_inputs([EmbeddingInput("图片", (PROBE_IMAGE,))])
            assert requests == []
            with pytest.raises(ExtractionFailed, match="维度"):
                await model.embed(["文本"])

    asyncio.run(run())
    assert len(requests) == 1


@pytest.mark.parametrize("protocol", ["openai", "openai_compatible", "gemini"])
def test_image_generation_single_request_and_decodable_result(protocol):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if protocol == "gemini":
            assert body["generationConfig"] == {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": "1:1"},
            }
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "inlineData": {
                                            "mimeType": "image/png",
                                            "data": PROBE_IMAGE.base64,
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        assert body == {"model": "fixture", "prompt": "蓝色圆形", "n": 1, "quality": "low"}
        return httpx.Response(200, json={"data": [{"b64_json": PROBE_IMAGE.base64}]})

    async def run():
        async with httpx.AsyncClient(
            base_url="http://fixture/", transport=httpx.MockTransport(handler)
        ) as client:
            model = ProviderImageModel(
                "http://fixture",
                "fixture",
                client=client,
                protocol=protocol,
                parameters={"aspect_ratio": "1:1"} if protocol == "gemini" else {"quality": "low"},
            )
            result = await model.generate("蓝色圆形")
            assert result.mime_type == "image/png" and result.data == PROBE_IMAGE.data

    asyncio.run(run())
    assert len(requests) == 1


@pytest.mark.parametrize(
    "data", [{"b64_json": "bm90LWFuLWltYWdl"}, {"url": "http://169.254.169.254/credentials"}]
)
def test_image_payload_must_decode_and_never_fetches_returned_url(data):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [data]})

    async def run():
        async with httpx.AsyncClient(
            base_url="http://fixture/", transport=httpx.MockTransport(handler)
        ) as client:
            with pytest.raises(ExtractionFailed):
                await ProviderImageModel("http://fixture", "fixture", client=client).generate(
                    "蓝色圆形"
                )

    asyncio.run(run())
    assert len(requests) == 1


def test_model_parameter_rules_can_narrow_but_cannot_override_request_identity():
    model = {
        "kind": "language",
        "api_mode": "chat_completions",
        "capabilities": ["text_input"],
        "supported_parameters": ["top_p"],
        "parameters": {"top_p": 0.7},
    }
    validate_model("openai", model)
    for changes in (
        {"temperature": 0.5},
        {"parameters": {"model": "other"}},
        {"parameters": {"top_p": True}},
        {"supported_parameters": ["unknown"]},
    ):
        with pytest.raises(ValueError):
            validate_model("openai", model | changes)
