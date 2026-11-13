"""各文本协议的流式收集：推理用于计时，只有完整正式正文进入业务校验。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from tender.adapters.llm.response_timeout import ResponseTimeout, chat_has_increment
from tender.core.error_details import raise_stream_error
from tender.domain.shared.errors import ModelOutputTruncated, ModelUnavailable


async def sse_data(response: httpx.Response) -> AsyncIterator[dict | str]:
    lines: list[str] = []
    event = ""
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            lines.append(line[5:].lstrip(" "))
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif not line and lines:
            data = "\n".join(lines)
            lines.clear()
            if not data.strip():
                # 空data也是保活事件，既不续期也不能提前结束模型等待。
                event = ""
                continue
            if data == "[DONE]":
                yield data
            else:
                try:
                    value = json.loads(data)
                    if not isinstance(value, dict):
                        raise ValueError("事件不是对象")
                except ValueError as exc:
                    raise ModelUnavailable("LLM 流式响应事件无效", http_status=200) from exc
                if event:
                    value.setdefault("type", event)
                yield value
            event = ""
        elif not line:
            event = ""
    # SSE 事件须有空行结束；残缺事件不能冒充完整模型结果。
    if lines:
        raise ModelUnavailable("LLM 流式响应事件未完整结束", http_status=200)


class CompletionStream:
    def __init__(self, mode: str, model: str) -> None:
        self.mode, self.model = mode, model
        self.content: list[str] = []
        self.refusal: list[str] = []
        self.usage: dict = {}
        self.finish: str | None = None
        self.done = False
        self.payload: dict = {}
        self.blocks: dict[int, dict] = {}

    def feed(self, data: dict | str, response: httpx.Response, progress: ResponseTimeout,
             api_key: str | None) -> None:
        progress.observe(False)
        if data == "[DONE]":
            if self.mode == "chat_completions":
                self.done = True
            return
        if not isinstance(data, dict):
            raise ModelUnavailable("LLM 流式响应事件无效", http_status=200)
        if error := data.get("error") or (data if data.get("type") == "error" else None):
            # 同一套状态码分类处理 HTTP 200 流内错误，不能发布此前的半截正文。
            raise_stream_error(response, error, name="LLM", api_key=api_key)
            # 符号错误码也代表失败；兜底不回显供应商正文，避免错误事件携带请求内容。
            raise ModelUnavailable("LLM 流式响应报告错误", http_status=200)
        self.model = data.get("model") or data.get("modelVersion") or self.model
        if self.mode == "chat_completions":
            progress.observe(chat_has_increment(data))
            self.usage = data.get("usage") or self.usage
            for choice in data.get("choices") or []:
                if choice.get("index", 0) != 0:
                    continue
                delta = choice.get("delta") or {}
                for field, parts in (("content", self.content), ("refusal", self.refusal)):
                    value = delta.get(field)
                    if value is not None:
                        if not isinstance(value, str):
                            raise ModelUnavailable("LLM 流式正文类型无效", http_status=200)
                        parts.append(value)
                self.finish = choice.get("finish_reason") or self.finish
        elif self.mode == "responses":
            kind, delta = data.get("type"), data.get("delta")
            effective = kind in {
                "response.output_text.delta", "response.reasoning_text.delta",
                "response.reasoning_summary_text.delta", "response.function_call_arguments.delta",
                "response.refusal.delta",
            } and isinstance(delta, str) and bool(delta)
            progress.observe(effective)
            if kind == "response.output_text.delta":
                self.content.append(delta)
            elif kind == "response.refusal.delta":
                self.refusal.append(delta)
            elif kind in {"response.completed", "response.incomplete", "response.failed"}:
                self.payload = data["response"]
                self.usage = self.payload.get("usage") or {}
                self.model = self.payload.get("model") or self.model
                self.finish = self.payload.get("status") or kind.removeprefix("response.")
                if error := self.payload.get("error"):
                    raise_stream_error(response, error, name="LLM", api_key=api_key)
                    raise ModelUnavailable("LLM 流式响应报告错误", http_status=200)
                self.done = self.finish in {"completed", "incomplete"}
        elif self.mode == "messages":
            kind = data.get("type")
            if kind == "message_start":
                self.payload = data["message"]
                self.model = self.payload.get("model") or self.model
                self.usage.update(self.payload.get("usage") or {})
            elif kind == "content_block_start":
                block = dict(data["content_block"])
                self.blocks[data["index"]] = block
                progress.observe(
                    bool(block.get("text") or block.get("thinking") or block.get("input"))
                )
            elif kind == "content_block_delta":
                delta = data.get("delta") or {}
                progress.observe(any(isinstance(delta.get(k), str) and bool(delta[k])
                                     for k in ("text", "thinking", "partial_json")))
                block = self.blocks.setdefault(data["index"], {"type": "text", "text": ""})
                if isinstance(delta.get("text"), str):
                    block["text"] = block.get("text", "") + delta["text"]
            elif kind == "message_delta":
                self.finish = data.get("delta", {}).get("stop_reason") or self.finish
                self.usage.update(data.get("usage") or {})
            elif kind == "message_stop":
                self.done = True
        else:
            self.usage = data.get("usageMetadata") or self.usage
            candidates = data.get("candidates") or []
            if data.get("promptFeedback", {}).get("blockReason"):
                self.payload = data
                self.finish, self.done = "SAFETY", True
            for candidate in candidates:
                if candidate.get("index", 0) != 0:
                    continue
                parts = candidate.get("content", {}).get("parts") or []
                progress.observe(any((isinstance(p.get("text"), str) and bool(p["text"]))
                                     or bool(p.get("functionCall", {}).get("args")) for p in parts))
                self.content.extend(p["text"] for p in parts
                                    if isinstance(p.get("text"), str) and not p.get("thought"))
                self.finish = candidate.get("finishReason") or self.finish
                # Gemini 没有独立 DONE 事件，以供应商明确的 finishReason 完成收流。
                self.done = self.finish is not None

    def result(self) -> dict:
        if not self.done or not self.finish:
            raise ModelUnavailable("LLM 流式响应未完整结束", http_status=200)
        if self.finish in {"length", "max_tokens", "MAX_TOKENS", "incomplete"}:
            error = ModelOutputTruncated("模型流式输出未完整完成或达到token上限", http_status=200)
            error.prompt_tokens = self.usage.get("prompt_tokens", self.usage.get("input_tokens",
                                                           self.usage.get("promptTokenCount")))
            error.completion_tokens = self.usage.get(
                "completion_tokens",
                self.usage.get("output_tokens", self.usage.get("candidatesTokenCount")),
            )
            raise error
        if self.mode == "responses":
            return self.payload or {"model": self.model, "usage": self.usage, "output": [{
                "content": [{"type": "output_text", "text": "".join(self.content)}],
            }]}
        if self.mode == "messages":
            return {**self.payload, "model": self.model, "usage": self.usage,
                    "stop_reason": self.finish, "content": list(self.blocks.values())}
        if self.mode == "generate_content":
            return {**self.payload, "model": self.model, "usageMetadata": self.usage,
                    "candidates": [{"finishReason": self.finish,
                                    "content": {"parts": [{"text": "".join(self.content)}]}}]}
        return {"model": self.model, "usage": self.usage, "choices": [{
            "finish_reason": self.finish,
            "message": {"content": "".join(self.content), "refusal": "".join(self.refusal)},
        }]}
