"""内网 OpenAI Chat Completions 兼容适配器。"""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import httpx

from tender.core.error_details import upstream_error
from tender.domain.errors import (
    InvalidModelOutput,
    ModelCallFailed,
    ModelOutputTruncated,
    ModelRefused,
    ModelUnavailable,
)
from tender.ports.llm import Completion
from tender.ports.model_media import ModelImage


def _retry_after(response: httpx.Response) -> float:
    """仅采纳合法秒数或 HTTP 日期；不把供应商正文或凭证写进异常。"""
    value = response.headers.get("Retry-After", "")
    try:
        seconds = float(value)
    except ValueError:
        try:
            until = parsedate_to_datetime(value)
            now = (
                parsedate_to_datetime(response.headers["Date"])
                if "Date" in response.headers
                else datetime.now(UTC)
            )
            seconds = (until - now).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return 0
    return seconds if math.isfinite(seconds) and seconds > 0 else 0


def _int_or_none(value: Any) -> int | None:
    """兼容网关的 usage 字段类型不统一；非整数一律当作"没给"。"""
    return value if type(value) is int and value >= 0 else None


def _reject_constant(_: str) -> None:
    # Python 默认接受 NaN/Infinity，但它们不是合法 JSON，不能作为业务输出通过。
    raise ValueError("模型返回非有限 JSON 数值")


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
        protocol: str = "openai_compatible",
        api_mode: str = "chat_completions",
        parameters: dict | None = None,
        capabilities: list[str] | None = None,
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
        # 留空表示使用供应商默认值，避免给不接受 temperature 的模型强塞参数。
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._protocol = protocol
        self._api_mode = api_mode
        self._agent_settings = {
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
            "timeout": timeout,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "protocol": protocol,
            "api_mode": api_mode,
            "parameters": parameters or {},
        }
        self._agent_client = None
        self._parameters = parameters or {}
        self._capabilities = (
            capabilities if capabilities is not None else ["text_input", "json_output"]
        )

    def _headers(self) -> dict[str, str]:
        if self._protocol == "anthropic":
            return {"x-api-key": self._api_key or "", "anthropic-version": "2023-06-01"}
        if self._protocol == "gemini":
            return {"x-goog-api-key": self._api_key} if self._api_key else {}
        return {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}

    async def _post_completion(self, path: str, body: dict) -> httpx.Response:
        if self._api_mode != "chat_completions":
            return await self._client.post(path, headers=self._headers(), json=body)
        # 长推理的非流式响应会被部分网关在约60秒无数据时断开；接收增量保持连接，
        # 但业务层仍只拿完整正文，reasoning_content 和未结束的片段绝不能作为校验结论。
        body = body | {"stream": True, "stream_options": {"include_usage": True}}
        async with self._client.stream(
            "POST", path, headers=self._headers(), json=body
        ) as response:
            if not response.is_success or "text/event-stream" not in response.headers.get(
                "content-type", ""
            ):
                # 某些兼容服务忽略 stream 并返回完整JSON；沿用原结构与状态码校验。
                await response.aread()
                return response
            content: list[str] = []
            refusal: list[str] = []
            usage, model, finish = {}, self._model, None
            done = False
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    done = True
                    break
                try:
                    chunk = json.loads(data)
                    if not isinstance(chunk, dict) or chunk.get("error"):
                        raise ValueError("流式服务错误")
                    model = chunk.get("model") or model
                    usage = chunk.get("usage") or usage
                    for choice in chunk.get("choices", []):
                        if choice.get("index", 0) != 0:
                            continue
                        delta = choice.get("delta") or {}
                        for field, parts in (("content", content), ("refusal", refusal)):
                            value = delta.get(field)
                            if value is not None:
                                if not isinstance(value, str):
                                    raise ValueError("流式正文类型无效")
                                parts.append(value)
                        finish = choice.get("finish_reason") or finish
                except (ValueError, TypeError, AttributeError) as exc:
                    raise ModelUnavailable("LLM 流式响应无效或中断", http_status=200) from exc
            if not done or finish is None:
                raise ModelUnavailable("LLM 流式响应未完整结束", http_status=200)
            if finish == "length":
                error = ModelOutputTruncated(
                    "模型输出达到token上限，流式正文不完整", http_status=200
                )
                if isinstance(usage, dict):
                    error.prompt_tokens = _int_or_none(usage.get("prompt_tokens"))
                    error.completion_tokens = _int_or_none(usage.get("completion_tokens"))
                raise error
            return httpx.Response(
                response.status_code,
                json={
                    "model": model,
                    "usage": usage,
                    "choices": [
                        {
                            "finish_reason": finish,
                            "message": {"content": "".join(content), "refusal": "".join(refusal)},
                        }
                    ],
                },
            )

    async def complete(
        self, prompt: str, *, images: tuple[ModelImage, ...] = (), json_mode: bool = True
    ) -> Completion:
        if images and "image_input" not in self._capabilities:
            raise ValueError("模型未声明视觉能力，不能静默丢弃图片")
        if json_mode and "json_output" not in self._capabilities:
            raise ValueError("当前调用要求 JSON 输出，模型未声明此能力")
        body: dict[str, Any] = {
            "model": self._model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "只返回符合请求约束的 JSON 对象。"},
                {"role": "user", "content": prompt},
            ],
        }
        if self._temperature is not None:
            body["temperature"] = self._temperature
        if self._max_tokens is not None:
            body["max_tokens"] = self._max_tokens
        path = "chat/completions"
        if self._api_mode == "responses":
            path = "responses"
            body = {
                "model": self._model,
                "input": prompt,
                "instructions": "只返回符合请求约束的 JSON 对象。",
                "text": {"format": {"type": "json_object"}},
            }
            if self._max_tokens is not None:
                body["max_output_tokens"] = self._max_tokens
            if self._temperature is not None:
                body["temperature"] = self._temperature
        elif self._api_mode == "messages":
            path = "messages"
            body = {
                "model": self._model,
                "max_tokens": self._max_tokens or 4096,
                "system": "只返回符合请求约束的 JSON 对象。",
                "messages": [{"role": "user", "content": prompt}],
            }
            if self._temperature is not None:
                body["temperature"] = self._temperature
        elif self._api_mode == "generate_content":
            path = (
                "models/" + quote(self._model.removeprefix("models/"), safe="") + ":generateContent"
            )
            config: dict[str, Any] = {"responseMimeType": "application/json"}
            if self._temperature is not None:
                config["temperature"] = self._temperature
            if self._max_tokens is not None:
                config["maxOutputTokens"] = self._max_tokens
            body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}
        # 不同协议有不同的图片结构，必须实际发送图片字节而不是仅在提示词中提及图片。
        if self._api_mode == "responses":
            if not json_mode:
                body.pop("text", None)
                body.pop("instructions", None)
            if images:
                body["input"] = [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}]
                        + [{"type": "input_image", "image_url": img.data_url} for img in images],
                    }
                ]
            for key, value in self._parameters.items():
                if key == "reasoning_effort":
                    body["reasoning"] = {"effort": value}
                else:
                    body[key] = value
        elif self._api_mode == "messages":
            if not json_mode:
                body.pop("system", None)
            if images:
                body["messages"][0]["content"] = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.mime_type,
                            "data": img.base64,
                        },
                    }
                    for img in images
                ] + [{"type": "text", "text": prompt}]
            body.update(
                {"stop_sequences" if k == "stop" else k: v for k, v in self._parameters.items()}
            )
        elif self._api_mode == "generate_content":
            if not json_mode:
                body["generationConfig"].pop("responseMimeType", None)
            body["contents"][0]["parts"].extend(
                [{"inlineData": {"mimeType": img.mime_type, "data": img.base64}} for img in images]
            )
            names = {"top_p": "topP", "top_k": "topK", "stop": "stopSequences", "seed": "seed"}
            body["generationConfig"].update({names[k]: v for k, v in self._parameters.items()})
        else:
            if not json_mode:
                body.pop("response_format", None)
                body["messages"] = [{"role": "user", "content": prompt}]
            if images:
                body["messages"][-1]["content"] = [{"type": "text", "text": prompt}] + [
                    {"type": "image_url", "image_url": {"url": img.data_url}} for img in images
                ]
            body.update({k: v for k, v in self._parameters.items() if k != "token_limit_field"})
            if (
                self._parameters.get("token_limit_field") == "max_completion_tokens"
                and "max_tokens" in body
            ):
                body["max_completion_tokens"] = body.pop("max_tokens")
        try:
            response = await self._post_completion(path, body)
        except httpx.HTTPError as exc:
            # 仅保留异常类型，区分应用超时和上游断连；原异常文本可能含密钥或请求正文。
            raise ModelUnavailable(f"模型连接失败或请求超时（{type(exc).__name__}）") from exc
        # 网关可能在供应商超时后返回非标准 5xx（如 Cloudflare 524）；一律按可重试处理。
        if response.status_code in {408, 429} or response.status_code >= 500:
            error = ModelUnavailable(
                upstream_error(
                    f"LLM 网关暂不可用：HTTP {response.status_code}",
                    response.text,
                    api_key=self._api_key,
                ),
                http_status=response.status_code,
            )
            error.retry_after = _retry_after(response)
            raise error
        if not response.is_success:
            raise ModelCallFailed(
                upstream_error(
                    f"LLM 网关拒绝请求：HTTP {response.status_code}",
                    response.text,
                    api_key=self._api_key,
                ),
                http_status=response.status_code,
            )
        try:
            payload: Any = response.json()
            if self._api_mode == "responses":
                if any(
                    part.get("type") == "refusal"
                    for item in payload["output"]
                    for part in item.get("content", [])
                ):
                    raise ModelRefused("模型拒绝了该请求")
                content = "".join(
                    part["text"]
                    for item in payload["output"]
                    for part in item.get("content", [])
                    if part.get("type") == "output_text"
                )
            elif self._api_mode == "messages":
                if payload.get("stop_reason") == "refusal":
                    raise ModelRefused("模型拒绝了该请求")
                content = "".join(
                    item["text"] for item in payload["content"] if item.get("type") == "text"
                )
            elif self._api_mode == "generate_content":
                if payload.get("promptFeedback", {}).get("blockReason") or any(
                    candidate.get("finishReason") in {"SAFETY", "RECITATION", "PROHIBITED_CONTENT"}
                    for candidate in payload.get("candidates", [])
                ):
                    raise ModelRefused("模型拒绝了该请求")
                content = "".join(
                    item.get("text", "") for item in payload["candidates"][0]["content"]["parts"]
                )
            else:
                if (
                    payload["choices"][0]["message"].get("refusal")
                    or payload["choices"][0].get("finish_reason") == "content_filter"
                ):
                    raise ModelRefused("模型拒绝了该请求")
                content = payload["choices"][0]["message"]["content"]
            model = payload.get("model", self._model)
            usage = payload.get("usage") or payload.get("usageMetadata") or {}
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ModelCallFailed("模型响应不符合所选接口的文本结构") from exc
        if not isinstance(content, str) or not content.strip():
            # 子 Agent 实测：慢请求被网关在约110秒后截成 200+空正文，重发同一请求仍可能成功。
            # 空正文不是模型能自行纠正的格式问题，按暂不可用重试同一模型，既不降级也不误判为拒绝。
            # 不读取或拼接 reasoning_content，它不能替代模型正式提交的报告。
            raise ModelUnavailable("LLM 网关返回空文本", http_status=200)
        if json_mode:
            # 部分兼容服务仍给完整 JSON 加 Markdown 围栏；只移除完整外包装，绝不猜测正文中的 JSON。
            fenced = re.fullmatch(
                r"\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\s*", content, re.S | re.I
            )
            if fenced:
                content = fenced.group(1).strip()
        # 结构错误交给路由有限纠正；仍不合法才按既有策略换候选。
        try:
            parsed = json.loads(content, parse_constant=_reject_constant) if json_mode else {}
            if not isinstance(parsed, dict):
                raise ValueError("需要 JSON 对象")
        except ValueError as exc:
            raise InvalidModelOutput("模型输出不是合法 JSON 对象") from exc
        if not isinstance(usage, dict):
            usage = {}
        return Completion(
            content=content,
            model=model if isinstance(model, str) else self._model,
            prompt_tokens=_int_or_none(
                usage.get("prompt_tokens", usage.get("input_tokens", usage.get("promptTokenCount")))
            ),
            completion_tokens=_int_or_none(
                usage.get(
                    "completion_tokens",
                    usage.get("output_tokens", usage.get("candidatesTokenCount")),
                )
            ),
        )

    async def chat(self, messages: list[dict], tools: list[dict]) -> Completion:
        from tender.adapters.agent_chat import AgentChat

        if self._agent_client is None:
            self._agent_client = AgentChat(**self._agent_settings)
        return await self._agent_client.chat(messages, tools)

    async def list_models(self) -> list[str]:
        """读供应商的 /v1/models。

        返回空列表也算成功：部分兼容网关不实现该接口，页面表现为"没有可导入的模型"，
        而不是让人以为供应商连不上。
        """
        try:
            response = await self._client.get("models", headers=self._headers())
        except httpx.HTTPError as exc:
            raise ModelUnavailable("模型目录连接失败或请求超时") from exc
        if response.status_code == 429 or response.status_code >= 500:
            raise ModelUnavailable(
                upstream_error(
                    f"LLM 网关暂不可用：HTTP {response.status_code}",
                    response.text,
                    api_key=self._api_key,
                ),
                http_status=response.status_code,
            )
        if not response.is_success:
            raise ModelCallFailed(
                upstream_error(
                    f"LLM 网关拒绝请求：HTTP {response.status_code}",
                    response.text,
                    api_key=self._api_key,
                ),
                http_status=response.status_code,
            )
        try:
            payload: Any = response.json()
            data = payload["models"] if self._protocol == "gemini" else payload["data"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelCallFailed("LLM 网关 /models 响应缺少 data 数组") from exc
        if not isinstance(data, list):
            raise ModelCallFailed("LLM 网关 /models 的 data 不是数组")
        return [
            item.get("id", item.get("name"))
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id", item.get("name")), str)
        ]

    async def aclose(self) -> None:
        try:
            if self._agent_client is not None:
                await self._agent_client.aclose()
        finally:
            if self._owns_client:
                await self._client.aclose()
