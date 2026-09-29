"""内网 OpenAI Chat Completions 兼容适配器。"""

from __future__ import annotations

from typing import Any

import httpx

from tender.domain.errors import ExtractionFailed, ExtractionUnavailable
from tender.ports.llm import Completion

# 错误信息只截前 300 字符：网关的错误页可能很长，入库与日志都不需要整页。
_ERROR_EXCERPT = 300


def _int_or_none(value: Any) -> int | None:
    """兼容网关的 usage 字段类型不统一；非整数一律当作"没给"。"""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class OpenAIChatModel:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 90,
        temperature: float | None = None,
        max_tokens: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip():
            raise ValueError("LLM_BASE_URL 和 LLM_MODEL 必须配置")
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/", timeout=timeout
        )
        self._owns_client = client is None
        self._model = model
        self._api_key = api_key
        # 抽取要求稳定输出，默认温度 0；模型行没配时不要退化成网关默认值。
        self._temperature = 0 if temperature is None else temperature
        self._max_tokens = max_tokens

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    async def complete(self, prompt: str) -> Completion:
        body: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "只返回符合请求约束的 JSON 对象。"},
                {"role": "user", "content": prompt},
            ],
        }
        if self._max_tokens is not None:
            body["max_tokens"] = self._max_tokens
        try:
            response = await self._client.post(
                "chat/completions", headers=self._headers(), json=body
            )
        except httpx.HTTPError as exc:
            raise ExtractionUnavailable(f"LLM 网关请求失败：{exc}") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise ExtractionUnavailable(
                f"LLM 网关暂不可用：HTTP {response.status_code} {response.text[:_ERROR_EXCERPT]}",
                http_status=response.status_code,
            )
        if not response.is_success:
            raise ExtractionFailed(
                f"LLM 网关拒绝请求：HTTP {response.status_code} {response.text[:_ERROR_EXCERPT]}",
                http_status=response.status_code,
            )
        try:
            payload: Any = response.json()
            content = payload["choices"][0]["message"]["content"]
            model = payload.get("model", self._model)
            usage = payload.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ExtractionFailed("LLM 网关响应缺少 choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ExtractionFailed("LLM 网关返回空文本")
        return Completion(
            content=content,
            model=model if isinstance(model, str) else self._model,
            prompt_tokens=_int_or_none(usage.get("prompt_tokens")),
            completion_tokens=_int_or_none(usage.get("completion_tokens")),
        )

    async def list_models(self) -> list[str]:
        """读供应商的 /v1/models。

        返回空列表也算成功：部分兼容网关不实现该接口，页面表现为"没有可导入的模型"，
        而不是让人以为供应商连不上。
        """
        try:
            response = await self._client.get("models", headers=self._headers())
        except httpx.HTTPError as exc:
            raise ExtractionUnavailable(f"LLM 网关请求失败：{exc}") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise ExtractionUnavailable(
                f"LLM 网关暂不可用：HTTP {response.status_code} {response.text[:_ERROR_EXCERPT]}",
                http_status=response.status_code,
            )
        if not response.is_success:
            raise ExtractionFailed(
                f"LLM 网关拒绝请求：HTTP {response.status_code} {response.text[:_ERROR_EXCERPT]}",
                http_status=response.status_code,
            )
        try:
            payload: Any = response.json()
            data = payload["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ExtractionFailed("LLM 网关 /models 响应缺少 data 数组") from exc
        if not isinstance(data, list):
            raise ExtractionFailed("LLM 网关 /models 的 data 不是数组")
        return [
            item["id"]
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
