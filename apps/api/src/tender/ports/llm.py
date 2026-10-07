"""模型端口；application 只依赖协议，不感知 HTTP 与模型网关。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from tender.ports.model_media import ModelImage


@dataclass(frozen=True, slots=True)
class Completion:
    """一次补全的结果。

    token 用量与注册表 id 拿不到时为 None：用量字段并非所有兼容网关都返回，
    注册表 id 只有走管理模块路由时才有值（直接调 .env 单模型时为 None）。
    """

    content: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    registry_model_id: int | None = None
    # Agent 消息单独保留工具调用及供应商元数据，不能塞进普通 JSON 正文冒充工具协议。
    agent_message: dict | None = None


class StructuredTextModel(Protocol):
    """抽取用例需要的最小能力。"""

    async def complete(self, prompt: str) -> Completion:
        """返回一段 JSON 文本；schema 与字段约束由用例层负责验证。"""
        ...

    async def aclose(self) -> None:
        """释放连接池。"""
        ...


class ChatGateway(StructuredTextModel, Protocol):
    """管理页与抽取共用的完整能力：补全 + 远端模型列表。"""

    async def complete(
        self, prompt: str, *, images: tuple[ModelImage, ...] = (), json_mode: bool = True
    ) -> Completion: ...

    async def chat(self, messages: list[dict], tools: list[dict]) -> Completion:
        """原生多轮工具调用；消息为可持久化的中立字典，不携带连接或凭证。"""
        ...

    async def list_models(self) -> list[str]:
        """读取供应商侧的模型 id 列表，仅用于页面勾选导入。"""
        ...


class ModelGateway(Protocol):
    """按供应商连接信息构造网关客户端。

    装配点（core/di.py）提供实现，api 与 worker 只调用；用例层不认识 httpx。
    推理参数存在模型行上，因此在这里按可选参数传入。
    """

    def __call__(
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
    ) -> ChatGateway: ...
