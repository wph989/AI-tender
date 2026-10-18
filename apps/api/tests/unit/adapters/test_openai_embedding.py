import asyncio

import httpx
import pytest

from tender.adapters.llm.openai_embedding import OpenAIEmbeddingModel
from tender.domain.shared.errors import ModelCallFailed


def test_embedding_uses_ordered_float_vectors_and_correct_endpoint():
    def handle(request):
        assert request.url.path == "/v1/embeddings"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(
            base_url="http://test/v1/", transport=httpx.MockTransport(handle)
        ) as client:
            model = OpenAIEmbeddingModel("http://test/v1", "embedding-test", client=client)
            assert await model.embed(["甲", "乙"]) == [[1.0, 0.0], [0.0, 1.0]]

    asyncio.run(run())


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 0, "embedding": []}],
        [{"index": 0, "embedding": [0, 0]}],
        [{"index": 1, "embedding": [1, 0]}],
    ],
)
def test_malformed_vectors_fail_instead_of_corrupting_index(data):
    async def run():
        async with httpx.AsyncClient(
            base_url="http://test/",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": data})),
        ) as client:
            model = OpenAIEmbeddingModel("http://test", "model", client=client)
            with pytest.raises(ModelCallFailed):
                await model.embed(["甲"])

    asyncio.run(run())
