"""向量端口独立于文本生成，避免聊天模型故障转移混用嵌入空间。"""

from typing import Protocol

from tender.ports.model_media import EmbeddingInput


class EmbeddingModel(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_inputs(self, inputs: list[EmbeddingInput]) -> list[list[float]]: ...

    async def aclose(self) -> None: ...
