"""借助供应商适配器保留原生工具消息；重试统一交给项目模型路由。"""

from __future__ import annotations

import inspect
import json
from typing import Any

import httpx
import httpx2
from jsonschema import Draft202012Validator
from langchain_core.messages import message_chunk_to_message, message_to_dict, messages_from_dict
from langsmith import tracing_context

from tender.adapters.llm.completion_stream import sse_data
from tender.adapters.llm.response_timeout import (
    chat_has_increment,
    message_has_increment,
    response_timeout,
    responses_has_increment,
)
from tender.adapters.llm.usage import log_usage
from tender.core.error_details import (
    quota_window,
    raise_stream_error,
    retry_after,
    stream_error_status,
    upstream_error,
)
from tender.domain.shared.errors import (
    InvalidModelOutput,
    ModelCallFailed,
    ModelOutputTruncated,
    ModelRefused,
    ModelUnavailable,
)
from tender.ports.llm.chat import Completion


def _decode_containers(value: Any, schema: dict, root: dict) -> Any:
    """只解码schema明确要求的容器；允许字符串的正文值必须保持原样。"""
    if ref := schema.get("$ref"):
        if ref.startswith("#/"):
            target = root
            for part in ref[2:].split("/"):
                target = target[part.replace("~1", "/").replace("~0", "~")]
            return _decode_containers(value, target, root)
    variants = schema.get("anyOf", schema.get("oneOf", [schema]))
    if isinstance(value, str) and not any(s.get("type") == "string" for s in variants):
        if any(s.get("type") in ("object", "array") for s in variants):
            try:
                decoded = json.loads(value)
            except ValueError:
                pass
            else:
                if isinstance(decoded, (dict, list)):
                    value = decoded
    for variant in variants:
        if "$ref" in variant:
            return _decode_containers(value, variant, root)
        if isinstance(value, dict) and variant.get("type") == "object":
            properties = variant.get("properties", {})
            additional = variant.get("additionalProperties", {})
            return {key: _decode_containers(child, properties.get(
                key, additional if isinstance(additional, dict) else {},
            ), root) for key, child in value.items()}
        if isinstance(value, list) and variant.get("type") == "array":
            return [_decode_containers(child, variant.get("items", {}), root) for child in value]
    return value


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
        total_timeout: float | None = None,
    ) -> None:
        self._timeout, self._total_timeout = timeout, total_timeout
        self._api_mode = api_mode
        self._model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._stream_chat = (
            protocol in {"openai", "openai_compatible"} and api_mode == "chat_completions"
        )
        # SDK 默认重试会与项目路由相乘；所有供应商必须关掉自己的隐式重试。
        common: dict[str, Any] = {"model": model, "max_retries": 0, "timeout": None}
        if temperature is not None:
            common["temperature"] = temperature
        if max_tokens is not None:
            common["max_tokens"] = max_tokens
        params = {k: v for k, v in parameters.items() if k != "token_limit_field"}
        if protocol in {"openai", "openai_compatible"}:
            from langchain_openai import ChatOpenAI

            # LangChain 默认缓存 httpx 客户端。模块独立关闭/跨 Celery 事件循环恢复时，
            # 共享缓存会让其它模块复用已关闭客户端，因此显式为每个适配器创建连接池。
            self._owned_http = http_async_client or httpx.AsyncClient(timeout=None)
            self._owned_sync_http = httpx.Client(timeout=None)
            self.model = ChatOpenAI(
                **common,
                **params,
                base_url=base_url,
                api_key=api_key or "local-anonymous",
                use_responses_api=api_mode == "responses",
                stream_usage=True,
                stream_chunk_timeout=None,
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
        incomplete_arguments = False
        try:
            # 业务调用记录保存在本项目，不能因终端残留 tracing 配置外发标书正文。
            with tracing_context(enabled=False):
                # 先构造中立消息和供应商载荷，响应计时从实际发送前开始。
                bound = self.model.bind_tools(tools) if tools else None
                options = dict(bound.kwargs) if bound is not None else {}
                if self._api_mode == "generate_content":
                    payload = self.model._prepare_request(messages_from_dict(messages), **options)
                else:
                    payload = self.model._get_request_payload(
                        messages_from_dict(messages), stream=True,
                        **options,
                    )
                async with response_timeout(self._timeout, self._total_timeout) as progress:
                    if self._stream_chat:
                        merged = await self._aggregate_chat_stream(payload, progress)
                    elif self._api_mode == "responses":
                        merged = await self._aggregate_responses_stream(payload, progress)
                    elif self._api_mode == "messages":
                        merged = await self._aggregate_messages_stream(payload, progress)
                    else:
                        merged = await self._aggregate_gemini_stream(payload, progress)
                    if merged is not None:
                        log_usage(self._model, self._api_mode, merged.usage_metadata or {},
                                  agent=True)
                    # LangChain会自动补齐半截JSON；成功结算前必须核对聚合后的原始参数。
                    for call in getattr(merged, "tool_call_chunks", []):
                        try:
                            json.loads(call.get("args", ""))
                        except (ValueError, TypeError):
                            incomplete_arguments = True
                    result = message_chunk_to_message(merged) if merged is not None else None
        except (ModelUnavailable, ModelCallFailed):
            # 应用超时已有首包/间隔/总时限分类，不再被 SDK 通用错误转换掩盖。
            raise
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            stream_response = getattr(exc, "_tender_stream_response", None)
            response = getattr(exc, "response", None) or stream_response
            payload = getattr(exc, "body", None)
            stream_status = None
            if status is None and stream_response is not None:
                # SDK把HTTP 200流中的503/429包装成无status_code的APIError；
                # 采纳明确的流内错误码，才能沿用路由重试且不会将403误判为临时故障。
                stream_status = stream_error_status(payload)
                status = stream_status
            body = None
            if isinstance(response, (httpx.Response, httpx2.Response)) and stream_response is None:
                # SDK 的流式失败响应可能还未读取；只提取上游正文，不回显含请求的异常文本。
                try:
                    await response.aread()
                    body = response.text
                except (httpx.HTTPError, httpx.StreamError, httpx2.HTTPError, httpx2.StreamError):
                    # 响应已关闭时仍保留原错误分类，继续尝试 SDK 已解析的错误正文。
                    pass
            if not body and payload is not None:
                body = (
                    payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
                )
            transport_failure = isinstance(
                exc, (httpx.TransportError, httpx2.TransportError),
            ) or any(
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
                    + (f"：流内错误码 {status}（HTTP {stream_response.status_code}）"
                       if stream_status is not None else
                       f"：HTTP {status}" if status is not None else "")
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
                if isinstance(response, (httpx.Response, httpx2.Response)):
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
                    + (f"：流内错误码 {status}（HTTP {stream_response.status_code}）"
                       if stream_status is not None else
                       f"：HTTP {status}" if status is not None else ""),
                    body,
                    api_key=self._api_key,
                ),
                http_status=status,
            ) from exc
        if result is not None and result.response_metadata.get("status") == "incomplete":
            error = ModelOutputTruncated("模型输出未完整完成或达到token上限", http_status=200)
            usage = result.usage_metadata or {}
            error.prompt_tokens = usage.get("input_tokens")
            error.completion_tokens = usage.get("output_tokens")
            raise error
        if result is None or (
            not (result.response_metadata.get("finish_reason")
                 or result.response_metadata.get("stop_reason")
                 or result.response_metadata.get("status") == "completed")
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
            or str(result.response_metadata.get("finish_reason", "")).lower() in {
                "content_filter", "safety", "recitation", "prohibited_content", "blocklist",
            }
            or result.response_metadata.get("stop_reason") == "refusal"
            or (isinstance(result.content, list) and any(
                isinstance(part, dict) and part.get("type") == "refusal" for part in result.content
            ))
        ):
            raise invalid(ModelRefused, "模型拒绝了该请求")
        required = {
            tool["function"]["name"]: set(
                tool["function"].get("parameters", {}).get("required", [])
            )
            for tool in tools
        }
        issues = []
        call_ids = set()
        for call in result.tool_calls:
            if not call.get("id") or call["id"] in call_ids:
                issues.append("工具调用id须为非空且在本响应中唯一的字符串")
            call_ids.add(call.get("id"))
            if call["name"] not in required:
                # 模型可把正文误塞进工具名，不能回显未知名称；只给出服务端允许的名单。
                issues.append("未知工具；当前可用工具：" + "、".join(required))
            elif absent := required[call["name"]] - call["args"].keys():
                # 缺项来自本次工具schema，无需回显参数值或整份模型响应即可准确纠正。
                issues.append(call["name"] + " 缺少必填参数：" + "、".join(sorted(absent)))
            else:
                schema = next(t["function"].get("parameters", {}) for t in tools
                              if t["function"]["name"] == call["name"])
                # 兼容网关把数组或对象再次编码为字符串；先按schema归一化，再计成功和交给工具。
                call["args"] = _decode_containers(call["args"], schema, schema)
                # 完整协议类型在成功结算前校验；范围和引文等业务规则仍由工具执行判断。
                for error in list(Draft202012Validator(schema).iter_errors(call["args"]))[:6]:
                    path = ".".join(str(p) for p in error.absolute_path) or "args"
                    issues.append(call["name"] + "." + path
                                  + " 不符合工具JSON Schema的 " + error.validator + " 约束")
        missing = bool(issues)
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
        if incomplete_arguments or result.invalid_tool_calls:
            raise invalid(InvalidModelOutput, "模型工具调用参数不是合法 JSON")
        if missing:
            raise invalid(
                InvalidModelOutput,
                "模型工具名称或必填参数无效：" + "；".join(dict.fromkeys(issues))[:1400]
                + "。请按JSON Schema完整返回",
            )
        if not result.content and not result.tool_calls:
            raise invalid(InvalidModelOutput, "模型既未返回正文，也未返回工具调用")
        return Completion(
            content=result.text,
            model=result.response_metadata.get("model_name", str(getattr(self.model, "model", ""))),
            prompt_tokens=usage.get("input_tokens"),
            completion_tokens=usage.get("output_tokens"),
            agent_message=message_to_dict(result),
        )

    async def _full_response(self, response, progress):
        if "text/event-stream" in response.headers.get("content-type", ""):
            return None
        await response.aread()
        progress.observe(False)
        data = response.json()
        # 忽略流式参数的供应商须先返回完整JSON，再按供应商消息结构校验。
        if self._api_mode == "responses":
            from langchain_openai.chat_models.base import _construct_lc_result_from_responses_api
            from openai.types.responses import Response
            result = _construct_lc_result_from_responses_api(
                self.model.root_async_client._process_response_data(
                    data=data, cast_to=Response, response=response,
                ), output_version=self.model.output_version,
            )
        elif self._api_mode == "messages":
            from anthropic.types import Message
            result = self.model._format_output(self.model._async_client._process_response_data(
                data=data, cast_to=Message, response=response,
            ))
        else:
            result = self.model._create_chat_result(data)
        message = result.generations[0].message
        message.response_metadata = {**(result.llm_output or {}), **message.response_metadata}
        if info := result.generations[0].generation_info:
            message.response_metadata = {**info, **message.response_metadata}
        progress.observe(message_has_increment(message))
        return message

    async def _aggregate_chat_stream(
        self, payload: dict, progress
    ) -> Any:
        """消费供应商 SSE 增量并聚合成完整消息。

        LangChain 的 delta 转换会丢弃 refusal 字段，明确拒绝会退化成
        「既无正文也无工具调用」的协议错误；因此这里直接消费原始流，
        复用其工具参数与用量聚合，只补回被丢弃的拒绝信息。
        """
        from langchain_core.messages import AIMessageChunk
        if self.model._should_stream_usage(None):
            payload["stream_options"] = {"include_usage": True}
        response = await self.model.async_client.create(**payload)
        merged = None
        refusal = None
        default_class = AIMessageChunk
        received_chunks = 0
        done = False
        try:
            async with response:
                if full := await self._full_response(response.response, progress):
                    return full
                # SDK会把[DONE]与普通EOF都当作迭代结束；直接读事件才能拒绝缺结束标记的流。
                async for data in sse_data(response.response):
                    progress.observe(False)
                    if data == "[DONE]":
                        done = True
                        break
                    received_chunks += 1
                    # 首块可能只有角色信息，仍需聚合完整流后校验；不记录正文以免泄露请求内容。
                    if error := data.get("error"):
                        raise_stream_error(
                            response.response, error, name="Agent", api_key=self._api_key,
                        )
                        raise ModelCallFailed(upstream_error(
                            "Agent 流内错误", json.dumps(error, ensure_ascii=False),
                            api_key=self._api_key,
                        ), http_status=200)
                    progress.observe(chat_has_increment(data))
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
        if not done:
            raise ModelUnavailable("Agent 流式响应未完整结束", http_status=200)
        if merged is not None and refusal:
            # 与静态响应的字段位置保持一致，复用同一处拒绝判断。
            merged.additional_kwargs["refusal"] = refusal
        return merged

    async def _aggregate_responses_stream(self, payload: dict, progress):
        from langchain_openai.chat_models.base import _convert_responses_chunk_to_generation_chunk
        from openai.types.responses import ResponseStreamEvent

        response = await self.model.root_async_client.responses.create(**payload)
        merged = None
        indexes = (-1, -1, -1)
        received = 0
        done = False
        try:
            async with response as stream:
                if full := await self._full_response(response.response, progress):
                    return full
                async for data in sse_data(response.response):
                    progress.observe(False)
                    if data == "[DONE]":
                        break
                    received += 1
                    # 在 SDK 转换前观察，避免被转换器忽略的推理增量不能续期。
                    progress.observe(responses_has_increment(data))
                    if data.get("type") in {"response.completed", "response.incomplete"}:
                        done = True
                    if data.get("type") in {"response.failed", "error"} or data.get("error"):
                        error = data.get("response", {}).get("error") or data

                        raise_stream_error(
                            response.response, error, name="Agent", api_key=self._api_key
                        )
                        raise ModelCallFailed("Responses 模型未完成请求", http_status=200)
                    raw = stream._client._process_response_data(
                        data=data, cast_to=ResponseStreamEvent, response=response.response,
                    )
                    *indexes, chunk = _convert_responses_chunk_to_generation_chunk(
                        raw, *indexes, output_version=self.model.output_version,
                    )
                    if chunk is not None:
                        merged = chunk.message if merged is None else merged + chunk.message
                    if done:
                        break
        except Exception as exc:
            exc._tender_stream_response = response.response
            exc._tender_stream_chunks = received
            raise
        if not done:
            raise ModelUnavailable("Agent 流式响应未完整结束", http_status=200)
        if merged is not None:
            status = merged.response_metadata.get("status")
            if status == "incomplete":
                error = ModelOutputTruncated(
                    "模型流式输出未完整完成或达到token上限", http_status=200
                )
                usage = merged.usage_metadata or {}
                error.prompt_tokens, error.completion_tokens = (
                    usage.get("input_tokens"),
                    usage.get("output_tokens"),
                )
                raise error
        return merged

    async def _aggregate_messages_stream(self, payload: dict, progress):
        from anthropic.types import RawMessageStreamEvent, Usage
        from langchain_anthropic.chat_models import _create_usage_metadata

        raw_response = await self.model._acreate(payload)
        stream = raw_response.parse()
        if inspect.isawaitable(stream):
            stream = await stream
        merged, block_start, done = None, None, False
        received = 0
        usage = {}
        try:
            async with stream:
                if full := await self._full_response(raw_response.http_response, progress):
                    return full
                async for data in sse_data(raw_response.http_response):
                    progress.observe(False)
                    if data == "[DONE]":
                        break
                    received += 1
                    if error := data.get("error"):
                        raise_stream_error(raw_response.http_response, error, name="Agent",
                                           api_key=self._api_key)
                        raise ModelCallFailed("Anthropic模型流内错误", http_status=200)
                    if data.get("type") == "ping":
                        continue
                    if data.get("type") == "message_start":
                        event_usage = data.get("message", {}).get("usage") or {}
                    elif data.get("type") == "message_delta":
                        event_usage = data.get("usage") or {}
                    else:
                        event_usage = {}
                    # 用量是累计值：覆盖已报告字段，保留首事件输入和缓存；null不表示清零。
                    usage.update({key: value for key, value in event_usage.items()
                                  if value is not None})
                    raw = stream._client._process_response_data(
                        data=data, cast_to=RawMessageStreamEvent,
                        response=raw_response.http_response,
                    )
                    delta = data.get("delta") or data.get("content_block") or {}
                    progress.observe(any(isinstance(delta.get(key), str) and bool(delta[key])
                                         for key in ("text", "thinking", "partial_json"))
                                     or bool(delta.get("input")))
                    done = done or data.get("type") == "message_stop"
                    chunk, block_start = self.model._make_message_chunk_from_anthropic_event(
                        raw, stream_usage=True, coerce_content_to_string=False,
                        block_start_event=block_start,
                    )
                    if chunk is not None:
                        merged = chunk if merged is None else merged + chunk
                    if done:
                        break
        except Exception as exc:
            exc._tender_stream_response = raw_response.http_response
            exc._tender_stream_chunks = received
            raise
        if not done:
            raise ModelUnavailable("Agent 流式响应未完整结束", http_status=200)
        if merged is not None and usage:
            # 转换器忽略首事件输入且会累加多次delta；最终只转换一次供应商累计用量。
            raw_usage = stream._client._process_response_data(
                data=usage, cast_to=Usage, response=raw_response.http_response,
            )
            merged.usage_metadata = _create_usage_metadata(raw_usage)
        return merged

    async def _aggregate_gemini_stream(self, payload: dict, progress):
        from google.genai import _common, types
        from google.genai.models import _GenerateContentParameters_to_mldev
        from langchain_google_genai.chat_models import _response_to_result, _StreamBlockIndexer

        # 复用SDK请求转换及现有连接池。原SDK解析器会把SSE注释当JSON，
        # 原始读流才能过滤心跳、检查完整JSON，并关闭重叠的网络超时和隐式重试。
        api = self.model.client._api_client
        parameters = types._GenerateContentParameters(**payload)
        body = _GenerateContentParameters_to_mldev(api, parameters, None, parameters)
        path = "{model}:streamGenerateContent?alt=sse".format_map(body["_url"])
        body.pop("config", None)
        body = _common.encode_unserializable_types(_common.convert_to_dict(body))
        request = api._build_request("post", path, body, parameters.config.http_options)
        client = api._async_httpx_client
        response = await client.send(client.build_request(
            request.method, request.url, headers=request.headers, json=request.data, timeout=None,
        ), stream=True)
        merged = None
        indexer = _StreamBlockIndexer()
        try:
            from tender.core.error_details import raise_for_status

            if not response.is_success:
                await response.aread()
                raise_for_status(response, name="Agent", api_key=self._api_key)
            if "text/event-stream" in response.headers.get("content-type", ""):
                stream = sse_data(response)
            else:
                # 完整JSON读完才交给消息转换，分段JSON不能提前续期。
                await response.aread()

                async def complete_json():
                    yield response.json()

                stream = complete_json()
            async for data in stream:
                progress.observe(False)
                if not isinstance(data, dict):
                    raise ModelUnavailable("Agent Gemini响应事件无效", http_status=200)
                if error := data.get("error"):
                    raise_stream_error(response, error, name="Agent", api_key=self._api_key)
                    raise ModelCallFailed("Agent Gemini流内错误", http_status=200)
                raw = types.GenerateContentResponse.model_validate(data)
                parts = [
                    part
                    for candidate in data.get("candidates", [])[:1]
                    for part in candidate.get("content", {}).get("parts", [])
                ]
                progress.observe(
                    any(
                        (isinstance(part.get("text"), str) and bool(part["text"]))
                        or bool(part.get("function_call", {}).get("args"))
                        or bool(part.get("functionCall", {}).get("args"))
                        for part in parts
                    )
                )
                generation = _response_to_result(
                    raw,
                    stream=True,
                    prev_usage=merged.usage_metadata if merged is not None else None,
                ).generations[0]
                chunk = generation.message
                indexer.assign(chunk)
                if generation.generation_info:
                    chunk.response_metadata = {
                        **generation.generation_info,
                        **chunk.response_metadata,
                    }
                merged = chunk if merged is None else merged + chunk
                if chunk.response_metadata.get("finish_reason"):
                    break
        finally:
            await response.aclose()
        return merged

    async def aclose(self) -> None:
        if self._api_mode == "generate_content":
            # Gemini 的公开 aclose 同时清理本次事件循环中的异步客户端。
            await self.model.aclose()
            return
        for name in self._client_names:
            client = getattr(self.model, name, None)
            if client is not None and hasattr(client, "close"):
                result = client.close()
                if inspect.isawaitable(result):
                    await result
