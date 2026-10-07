"""借助供应商适配器保留原生工具消息；重试统一交给项目模型路由。"""

from __future__ import annotations

import inspect
from typing import Any

import httpx
from langchain_core.messages import message_to_dict, messages_from_dict
from langsmith import tracing_context

from tender.domain.errors import (
    ExtractionFailed,
    ExtractionUnavailable,
    InvalidModelOutput,
    ModelOutputTruncated,
    ModelRefused,
)
from tender.ports.llm import Completion


class AgentChat:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout: float,
        temperature: float | None,
        max_tokens: int | None,
        protocol: str,
        api_mode: str,
        parameters: dict,
        http_async_client: Any = None,
    ) -> None:
        self._max_tokens = max_tokens
        # SDK 默认重试会与项目路由相乘；所有供应商必须关掉自己的隐式重试。
        common: dict[str, Any] = {"model": model, "max_retries": 0, "timeout": timeout}
        if temperature is not None:
            common["temperature"] = temperature
        if max_tokens is not None:
            common["max_tokens"] = max_tokens
        params = {k: v for k, v in parameters.items() if k != "token_limit_field"}
        if protocol in {"openai", "openai_compatible"}:
            from langchain_openai import ChatOpenAI

            # LangChain 默认缓存 httpx 客户端。模块独立关闭/跨 Celery 事件循环恢复时，
            # 共享缓存会让其它模块复用已关闭客户端，因此显式为每个适配器创建连接池。
            self._owned_http = http_async_client or httpx.AsyncClient(timeout=timeout)
            self._owned_sync_http = httpx.Client(timeout=timeout)
            self.model = ChatOpenAI(
                **common,
                **params,
                base_url=base_url,
                api_key=api_key or "local-anonymous",
                use_responses_api=api_mode == "responses",
                stream_usage=False,
                http_async_client=self._owned_http,
                http_client=self._owned_sync_http,
            )
            self._client_names = ("root_async_client", "root_client")
        elif protocol == "anthropic":
            from langchain_anthropic import ChatAnthropic

            if "stop" in params:
                params["stop_sequences"] = params.pop("stop")
            self.model = ChatAnthropic(
                **common,
                **params,
                base_url=base_url,
                api_key=api_key or "local-anonymous",
            )
            self._client_names = ("_async_client", "_client")
        elif protocol == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            self.model = ChatGoogleGenerativeAI(
                **common,
                **params,
                base_url=base_url,
                api_key=api_key or "local-anonymous",
            )
            self._client_names = ("client",)
        else:
            raise ValueError("该协议暂不支持 Agent 原生工具调用")

    async def chat(self, messages: list[dict], tools: list[dict]) -> Completion:
        try:
            runnable = self.model.bind_tools(tools) if tools else self.model
            # 业务调用记录保存在本项目，不能因终端残留 tracing 配置外发标书正文。
            with tracing_context(enabled=False):
                result = await runnable.ainvoke(messages_from_dict(messages))
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status in {408, 429, 500, 502, 503, 504} or any(
                token in type(exc).__name__ for token in ("Timeout", "Connection")
            ):
                error = ExtractionUnavailable("Agent 模型连接失败或暂不可用", http_status=status)
                response = getattr(exc, "response", None)
                if response is not None:
                    from tender.adapters.openai_chat import _retry_after

                    error.retry_after = _retry_after(response)
                raise error from exc
            # SDK 异常可能含完整请求正文或密钥，不直接回显其文本。
            raise ExtractionFailed(
                f"Agent 模型调用失败（{type(exc).__name__}）",
                http_status=status,
            ) from exc
        usage = result.usage_metadata or {}

        def invalid(error_type, message):
            # 已收到的坏输出同样消耗token，不能只给成功响应记账。
            error = error_type(message, http_status=200)
            error.prompt_tokens = usage.get("input_tokens")
            error.completion_tokens = usage.get("output_tokens")
            return error

        if (
            result.additional_kwargs.get("refusal")
            or result.response_metadata.get("finish_reason") == "content_filter"
        ):
            raise invalid(ModelRefused, "模型拒绝了该请求")
        required = {
            tool["function"]["name"]: set(
                tool["function"].get("parameters", {}).get("required", [])
            )
            for tool in tools
        }
        missing = any(
            call["name"] not in required or required[call["name"]] - call["args"].keys()
            for call in result.tool_calls
        )
        finish = result.response_metadata.get("finish_reason") or result.response_metadata.get(
            "stop_reason"
        )
        if str(finish).lower() in {"length", "max_tokens"} or (
            (missing or result.invalid_tool_calls)
            and self._max_tokens
            and usage.get("output_tokens", 0) >= self._max_tokens
        ):
            # 部分兼容网关在额度耗尽时仍标tool_calls并返回{}，不能当作完整业务提交。
            raise invalid(ModelOutputTruncated, "模型输出达到token上限，工具参数或正文不完整")
        if result.invalid_tool_calls:
            raise invalid(InvalidModelOutput, "模型工具调用参数不是合法 JSON")
        if missing:
            raise invalid(InvalidModelOutput, "模型工具名称或必填参数无效，请按JSON Schema完整返回")
        if not result.content and not result.tool_calls:
            raise invalid(InvalidModelOutput, "模型既未返回正文，也未返回工具调用")
        return Completion(
            content=result.text,
            model=result.response_metadata.get("model_name", str(getattr(self.model, "model", ""))),
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            agent_message=message_to_dict(result),
        )

    async def aclose(self) -> None:
        for name in self._client_names:
            client = getattr(self.model, name, None)
            if client is not None and hasattr(client, "close"):
                result = client.close()
                if inspect.isawaitable(result):
                    await result
