"""借助供应商适配器保留原生工具消息；重试统一交给项目模型路由。"""

from __future__ import annotations

import inspect
import json
from typing import Any

import httpx
from langchain_core.messages import message_chunk_to_message, message_to_dict, messages_from_dict
from langsmith import tracing_context

from tender.core.error_details import quota_window, retry_after, upstream_error
from tender.domain.errors import (
    InvalidModelOutput,
    ModelCallFailed,
    ModelOutputTruncated,
    ModelRefused,
    ModelUnavailable,
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
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._stream_chat = (
            protocol in {"openai", "openai_compatible"} and api_mode == "chat_completions"
        )
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
                stream_usage=True,
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
            # 业务调用记录保存在本项目，不能因终端残留 tracing 配置外发标书正文。
            with tracing_context(enabled=False):
                if self._stream_chat:
                    # 先聚合完整工具参数再交给 Agent；增量接收避免长生成被网关闲置超时断开。
                    merged = await self._aggregate_chat_stream(messages, tools)
                    result = message_chunk_to_message(merged) if merged is not None else None
                else:
                    runnable = self.model.bind_tools(tools) if tools else self.model
                    result = await runnable.ainvoke(messages_from_dict(messages))
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            stream_response = getattr(exc, "_tender_stream_response", None)
            response = getattr(exc, "response", None) or stream_response
            body = None
            if isinstance(response, httpx.Response) and stream_response is None:
                # SDK 的流式失败响应可能还未读取；只提取上游正文，不回显含请求的异常文本。
                try:
                    await response.aread()
                    body = response.text
                except (httpx.HTTPError, httpx.StreamError):
                    # 响应已关闭时仍保留原错误分类，继续尝试 SDK 已解析的错误正文。
                    pass
            if not body and (payload := getattr(exc, "body", None)) is not None:
                body = (
                    payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
                )
            transport_failure = isinstance(exc, httpx.TransportError) or any(
                token in type(exc).__name__ for token in ("Timeout", "Connection")
            )
            # 524 等非标准 5xx 同样是上游超时，必须可重试，不能直接判失败。
            if (
                status in {408, 429}
                or (status is not None and status >= 500)
                or transport_failure
            ):
                # SDK 会包装传输异常；保留最底层原因，HTTP 错误仍优先记录实际上游正文。
                cause = exc
                while cause.__cause__ is not None:
                    cause = cause.__cause__
                summary = (
                    f"Agent 模型连接失败或暂不可用（{type(cause).__name__}）"
                    + (f"：HTTP {status}" if status is not None else "")
                )
                if transport_failure:
                    # 只取底层传输异常的消息，不序列化 request、消息正文或鉴权头。
                    # 文本仍统一脱敏；只留异常类型会丢失断连、协议错误等关键诊断。
                    summary += "\n底层异常：" + (str(cause) or "未提供具体消息")
                    if stream_response is not None:
                        # 流开始的 200 不代表完整响应，不能把请求结果改判为成功。
                        summary += (
                            f"\n响应情况：已收到 HTTP {stream_response.status_code} 响应头，"
                            f"流式接收中断；已收到 {exc._tender_stream_chunks} 个数据块。"
                        )
                    elif response is None:
                        summary += "\n响应情况：未收到上游 HTTP 响应，无响应正文可记录。"
                if isinstance(response, httpx.Response):
                    # 只保留便于供应商排查的请求标识，避免整份响应头携带 Cookie 等凭证。
                    for header in ("x-request-id", "request-id", "x-amzn-requestid", "cf-ray"):
                        if value := response.headers.get(header):
                            summary += f"\n{header}：{value}"
                error = ModelUnavailable(
                    upstream_error(
                        summary, body, api_key=self._api_key,
                    ),
                    http_status=status,
                )
                # SDK 的 429 同样可能不带 Retry-After，按正文窗口估算恢复时间。
                error.retry_after = max(
                    retry_after(response) if response is not None else 0,
                    quota_window(body),
                )
                raise error from exc
            raise ModelCallFailed(
                upstream_error(
                    f"Agent 模型调用失败（{type(exc).__name__}）"
                    + (f"：HTTP {status}" if status is not None else ""),
                    body,
                    api_key=self._api_key,
                ),
                http_status=status,
            ) from exc
        if result is None or (
            self._stream_chat and not result.response_metadata.get("finish_reason")
        ):
            # 网络结束不等于模型完成；半截工具 JSON 绝不能进入提交工具。
            raise ModelUnavailable("Agent 流式响应未完整结束")
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

    async def _aggregate_chat_stream(self, messages: list[dict], tools: list[dict]) -> Any:
        """消费供应商 SSE 增量并聚合成完整消息。

        LangChain 的 delta 转换会丢弃 refusal 字段，明确拒绝会退化成
        「既无正文也无工具调用」的协议错误；因此这里直接消费原始流，
        复用其工具参数与用量聚合，只补回被丢弃的拒绝信息。
        """
        from langchain_core.messages import AIMessageChunk
        from langchain_core.utils.function_calling import convert_to_openai_tool
        from langchain_openai.chat_models.base import _astream_with_chunk_timeout

        payload = self.model._get_request_payload(
            messages_from_dict(messages),
            **({"tools": [convert_to_openai_tool(tool) for tool in tools]} if tools else {}),
        )
        payload["stream"] = True
        if self.model._should_stream_usage(None):
            payload["stream_options"] = {"include_usage": True}
        response = await self.model.async_client.create(**payload)
        merged = None
        refusal = None
        default_class = AIMessageChunk
        received_chunks = 0
        try:
            async with response as stream:
                async for raw in _astream_with_chunk_timeout(
                    stream, self.model.stream_chunk_timeout, model_name=self.model.model_name
                ):
                    received_chunks += 1
                    # 首块可能只有角色信息，仍需聚合完整流后校验；不记录正文以免泄露请求内容。
                    data = raw if isinstance(raw, dict) else raw.model_dump()
                    choices = data.get("choices") or []
                    delta = (choices[0].get("delta") or {}) if choices else {}
                    refusal = delta.get("refusal") or refusal
                    chunk = self.model._convert_chunk_to_generation_chunk(data, default_class, {})
                    if chunk is None:
                        continue
                    default_class = chunk.message.__class__
                    # 与 LangChain 自身聚合一致：generation_info 合并进 response_metadata，
                    # 供上层读取 finish_reason，判断流是否完整结束。
                    if info := chunk.generation_info:
                        chunk.message.response_metadata = {
                            **info, **chunk.message.response_metadata,
                        }
                    merged = chunk.message if merged is None else merged + chunk.message
        except Exception as exc:
            # SDK 在流中断时不会附带已经收到的响应头；保留元数据供外层统一落账。
            # 不保存半截模型正文，也不把未完成的工具参数交给 Agent 执行。
            exc._tender_stream_response = response.response
            exc._tender_stream_chunks = received_chunks
            raise
        if merged is not None and refusal:
            # 与静态响应的字段位置保持一致，复用同一处拒绝判断。
            merged.additional_kwargs["refusal"] = refusal
        return merged

    async def aclose(self) -> None:
        # pad
        for name in self._client_names:
            client = getattr(self.model, name, None)
            if client is not None and hasattr(client, "close"):
                result = client.close()
                if inspect.isawaitable(result):
                    await result
