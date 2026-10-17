"""受控生图请求；仅接收可解码图片，不抓取供应商返回的任意 URL。"""

import base64
import binascii
import io
from urllib.parse import quote

import httpx
from PIL import Image, UnidentifiedImageError

from tender.core.error_details import upstream_error
from tender.domain.errors import ModelCallFailed, ModelRefused, ModelUnavailable
from tender.ports.model_media import ModelImage


class ProviderImageModel:
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
    ):
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/", timeout=timeout
        )
        self._owns_client = client is None
        self._model, self._protocol = model, protocol
        self._api_key = api_key
        self._parameters, self._allow_images = parameters or {}, allow_images
        self._headers = (
            (
                {"x-goog-api-key": api_key}
                if protocol == "gemini"
                else {"Authorization": f"Bearer {api_key}"}
            )
            if api_key
            else {}
        )

    async def generate(self, prompt: str, images: tuple[ModelImage, ...] = ()) -> ModelImage:
        if images and (not self._allow_images or self._protocol != "gemini"):
            raise ValueError("当前生图适配器或模型未允许图片输入")
        if self._protocol == "gemini":
            path = (
                "models/" + quote(self._model.removeprefix("models/"), safe="") + ":generateContent"
            )
            config = {"responseModalities": ["TEXT", "IMAGE"]}
            mapping = {"aspect_ratio": "aspectRatio", "image_size": "imageSize"}
            if self._parameters:
                config["imageConfig"] = {mapping[k]: v for k, v in self._parameters.items()}
            parts = [{"text": prompt}] + [
                {"inlineData": {"mimeType": img.mime_type, "data": img.base64}} for img in images
            ]
            body = {"contents": [{"parts": parts}], "generationConfig": config}
        else:
            path = "images/generations"
            # 测试和当前管理端口始终只生成一张，不接受任意 n 增加费用。
            body = {"model": self._model, "prompt": prompt, "n": 1} | self._parameters
        try:
            response = await self._client.post(path, headers=self._headers, json=body)
        except httpx.HTTPError as exc:
            raise ModelUnavailable("生图服务连接失败或超时") from exc
        if response.status_code in {408, 429, 500, 502, 503, 504}:
            raise ModelUnavailable(
                upstream_error(
                    f"生图服务暂不可用：HTTP {response.status_code}",
                    response.text,
                    api_key=self._api_key,
                ),
                http_status=response.status_code,
            )
        if not response.is_success:
            raise ModelCallFailed(
                upstream_error(
                    f"生图服务拒绝请求：HTTP {response.status_code}",
                    response.text,
                    api_key=self._api_key,
                ),
                http_status=response.status_code,
            )
        try:
            payload = response.json()
            if self._protocol == "gemini":
                if payload.get("promptFeedback", {}).get("blockReason"):
                    raise ModelRefused("生图请求被模型拒绝")
                candidate = payload["candidates"][0]
                if candidate.get("finishReason") in {
                    "SAFETY",
                    "PROHIBITED_CONTENT",
                    "IMAGE_SAFETY",
                }:
                    raise ModelRefused("生图请求被模型拒绝")
                parts = candidate["content"]["parts"]
                encoded = next(
                    p.get("inlineData", p.get("inline_data", {}))["data"]
                    for p in parts
                    if "inlineData" in p or "inline_data" in p
                )
            else:
                encoded = payload["data"][0]["b64_json"]
            if not isinstance(encoded, str) or len(encoded) > 28_000_000:
                raise ValueError("图片内容超出限制")
            data = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(data)) as image:
                if (
                    image.format not in {"PNG", "JPEG", "WEBP"}
                    or image.width * image.height > 25_000_000
                ):
                    raise ValueError("图片格式或像素数超出限制")
                mime = Image.MIME[image.format]
                image.verify()
            # verify 检查容器；load 进一步保证像素确实可读取。
            with Image.open(io.BytesIO(data)) as image:
                image.load()
            return ModelImage(data, mime)
        except (
            ValueError,
            KeyError,
            IndexError,
            TypeError,
            AttributeError,
            StopIteration,
            binascii.Error,
            OSError,
            UnidentifiedImageError,
            Image.DecompressionBombError,
        ) as exc:
            raise ModelCallFailed(
                "生图响应没有可读取的 PNG/JPEG/WebP；兼容服务需配置 base64 响应"
            ) from exc

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
