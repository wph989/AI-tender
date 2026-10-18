"""重排只改变已有候选顺序，不创建新的证据来源。"""

from typing import Protocol


class RerankModel(Protocol):
    async def rerank(
        self, query: str, documents: list[str], top_n: int
    ) -> list[tuple[int, float]]: ...

    async def aclose(self) -> None: ...
