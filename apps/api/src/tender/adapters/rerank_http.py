"""固定 /rerank 契约；只返回原候选位置，不接纳供应商替换来源。"""

import math

import httpx

from tender.domain.errors import ModelCallFailed, ModelUnavailable


class HttpRerankModel:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 90,
        top_n_limit: int | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/", timeout=timeout
        )
        self._owns_client = client is None
        self._model = model
        self._api_key = api_key
        self._top_n_limit = top_n_limit

    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
        top_n = min(top_n, self._top_n_limit or top_n, len(documents))
        try:
            response = await self._client.post(
                "rerank",
                headers={"Authorization": f"Bearer {self._api_key}"} if self._api_key else {},
                json={"model": self._model, "query": query, "documents": documents, "top_n": top_n},
            )
        except httpx.HTTPError as exc:
            raise ModelUnavailable("重排服务连接失败或超时") from exc
        if not response.is_success:
            raise ModelCallFailed(
                f"重排服务返回 HTTP {response.status_code}", http_status=response.status_code
            )
        try:
            rows = response.json()["results"]
            if not isinstance(rows, list) or len(rows) != min(top_n, len(documents)):
                raise ValueError("返回数量错误")
            result = []
            seen = set()
            for row in rows:
                index, score = row["index"], row["relevance_score"]
                if (
                    type(index) is not int
                    or not 0 <= index < len(documents)
                    or index in seen
                    or type(score) not in (int, float)
                    or not math.isfinite(score)
                ):
                    raise ValueError("索引或分数无效")
                seen.add(index)
                result.append((index, float(score)))
            return sorted(result, key=lambda item: item[1], reverse=True)
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelCallFailed("重排服务返回的候选索引、分数或数量无效") from exc

    async def aclose(self):
        if self._owns_client:
            await self._client.aclose()
