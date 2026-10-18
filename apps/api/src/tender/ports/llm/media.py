"""图片按内存内容传递，避免模型网关替调用者抓取任意远程地址。"""

import base64
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ModelImage:
    data: bytes
    mime_type: str = "image/png"

    @property
    def base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    @property
    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{self.base64}"


@dataclass(frozen=True, slots=True)
class EmbeddingInput:
    text: str
    images: tuple[ModelImage, ...] = ()


class ImageGenerationModel(Protocol):
    async def generate(self, prompt: str, images: tuple[ModelImage, ...] = ()) -> ModelImage: ...

    async def aclose(self) -> None: ...
