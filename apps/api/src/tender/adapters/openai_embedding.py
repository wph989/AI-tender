"""OpenAI 文本和 Gemini 图文嵌入；一次端口调用只发送一次 HTTP 请求。"""

import math
from urllib.parse import quote

import httpx

from tender.core.error_details import raise_for_status
from tender.domain.errors import ModelCallFailed, ModelUnavailable
from tender.ports.model_media import EmbeddingInput


class OpenAIEmbeddingModel:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 90,
        protocol: str = "openai_compatible",
        parameters: dict | None = None,
        allow_images: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/", timeout=timeout
        )
        self._owns_client = client is None
        self._model = model
        self._api_key = api_key
        self._protocol = protocol
        self._parameters = parameters or {}
        self._allow_images = allow_images
        self._headers = (
            (
                {"x-goog-api-key": api_key}
                if protocol == "gemini"
                else {"Authorization": f"Bearer {api_key}"}
            )
            if api_key
            else {}
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self.embed_inputs([EmbeddingInput(text) for text in texts])

    async def embed_inputs(self, inputs: list[EmbeddingInput]) -> list[list[float]]:
        if not inputs:
            return []
        if any(item.images for item in inputs) and (
            self._protocol != "gemini" or not self._allow_images
        ):
            raise ValueError("当前模型未声明或适配图片嵌入，不能静默丢弃图片")
        if self._protocol == "gemini":
            model = "models/" + self._model.removeprefix("models/")
            path = (
                "models/"
                + quote(self._model.removeprefix("models/"), safe="")
                + ":batchEmbedContents"
            )
            requests = []
            for item in inputs:
                parts = ([{"text": item.text}] if item.text else []) + [
                    {"inlineData": {"mimeType": image.mime_type, "data": image.base64}}
                    for image in item.images
                ]
                entry = {"model": model, "content": {"parts": parts}}
                if "dimensions" in self._parameters:
                    entry["outputDimensionality"] = self._parameters["dimensions"]
                if "task_type" in self._parameters:
                    entry["taskType"] = self._parameters["task_type"]
                requests.append(entry)
            body = {"requests": requests}
        else:
            path = "embeddings"
            body = {
                "model": self._model,
                "input": [item.text for item in inputs],
                "encoding_format": "float",
            } | self._parameters
        try:
            response = await self._client.post(path, headers=self._headers, json=body)
        except httpx.HTTPError as exc:
            raise ModelUnavailable("向量服务连接失败或超时") from exc
        raise_for_status(
            response, name="向量服务", api_key=self._api_key,
            retry_statuses=frozenset({408, 429, 500, 502, 503, 504}),
        )
        try:
            if self._protocol == "gemini":
                raw = [row["values"] for row in response.json()["embeddings"]]
            else:
                rows = sorted(response.json()["data"], key=lambda row: row["index"])
                if any(type(row["index"]) is not int for row in rows) or [
                    row["index"] for row in rows
                ] != list(range(len(inputs))):
                    raise ValueError("向量序号不符")
                raw = [row["embedding"] for row in rows]
            if len(raw) != len(inputs) or any(
                not isinstance(v, list) or any(type(x) not in {int, float} for x in v) for v in raw
            ):
                raise ValueError("向量数量或类型不符")
            vectors = [[float(v) for v in row] for row in raw]
            dimension = len(vectors[0])
            if (
                not 0 < dimension <= 65536
                or (
                    self._parameters.get("dimensions") is not None
                    and dimension != self._parameters["dimensions"]
                )
                or any(
                    len(v) != dimension
                    or not all(math.isfinite(x) for x in v)
                    or not any(x != 0 for x in v)
                    for v in vectors
                )
            ):
                raise ValueError("向量为空、维度不一致或包含非法数值")
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
            raise ModelCallFailed("向量服务响应格式错误或维度与配置不符") from exc
        return vectors

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
