"""唯一装配点：API 与 worker 使用相同的外部服务配置。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine

from tender.adapters.celery_queue import CeleryTaskQueue
from tender.adapters.gotenberg import GotenbergConverter
from tender.adapters.openai_chat import OpenAIChatModel
from tender.adapters.openai_embedding import OpenAIEmbeddingModel
from tender.adapters.pg.session import create_pg_engine
from tender.adapters.provider_image import ProviderImageModel
from tender.adapters.redis_cache import RedisConfigCache
from tender.adapters.rerank_http import HttpRerankModel
from tender.adapters.s3 import S3BlobStore
from tender.config.registry import ConfigRegistry
from tender.core import settings
from tender.core.secrets import decrypt_secret
from tender.ports.blob_store import BlobStore
from tender.ports.converter import OfficeConverter
from tender.ports.embedding import EmbeddingModel
from tender.ports.llm import ChatGateway, ModelGateway
from tender.ports.task_queue import TaskQueue


def create_model_gateway(
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
) -> ChatGateway:
    """按供应商连接信息构造客户端；api 与 worker 共用同一实现。

    放在装配点而不是各调用方：api 不认识 httpx，worker 也不需要重复一份构造逻辑。
    """
    return OpenAIChatModel(
        base_url,
        model,
        api_key=api_key,
        timeout=timeout,
        temperature=temperature,
        max_tokens=max_tokens,
        protocol=protocol,
        api_mode=api_mode,
        parameters=parameters,
        capabilities=capabilities,
    )


def create_embedding_gateway(config: dict) -> EmbeddingModel:
    if config.get("auth_mode", "none") == "api_key" and not config["api_key_ciphertext"]:
        raise ValueError("嵌入服务未配置 API Key")
    return OpenAIEmbeddingModel(
        config["base_url"],
        config["model_id"],
        api_key=decrypt_secret(config["api_key_ciphertext"])
        if config["api_key_ciphertext"] and config.get("auth_mode", "api_key") != "none"
        else None,
        timeout=float(config["timeout_seconds"]),
        protocol=config.get("protocol", "openai_compatible"),
        parameters=config.get("parameters"),
        allow_images="image_input" in config.get("capabilities", []),
    )


def create_image_gateway(config: dict) -> ProviderImageModel:
    return ProviderImageModel(
        config["base_url"],
        config["model_id"],
        api_key=config.get("api_key"),
        timeout=float(config["timeout_seconds"]),
        protocol=config["protocol"],
        parameters=config.get("parameters"),
        allow_images="image_input" in config.get("capabilities", []),
    )


def create_rerank_gateway(config: dict) -> HttpRerankModel:
    key = config.get("api_key")
    if "api_key" not in config and config.get("auth_mode") == "api_key":
        if not config.get("api_key_ciphertext"):
            raise ValueError("重排服务未配置 API Key")
        key = decrypt_secret(config["api_key_ciphertext"])
    return HttpRerankModel(
        config["base_url"],
        config["model_id"],
        api_key=key,
        timeout=float(config["timeout_seconds"]),
        top_n_limit=config.get("parameters", {}).get("top_n"),
    )


@dataclass(slots=True)
class ApiComponents:
    engine: Engine
    blobs: BlobStore
    converter: OfficeConverter
    # 任务投递本身走 beat（worker/dispatch.py）；这里保留队列装配点，
    # 给 P3 的回归回放/抽检这类"从 API 主动排队"的入口用。
    queue: TaskQueue
    blob_client: Any
    model_gateway: ModelGateway
    configs: ConfigRegistry

    async def aclose(self) -> None:
        await self.converter.aclose()
        self.blob_client.close()
        self.configs.close()
        self.engine.dispose()


def create_api_components() -> ApiComponents:
    credentials = settings.gotenberg_credentials()
    blobs = S3BlobStore()
    engine = create_pg_engine()
    return ApiComponents(
        engine=engine,
        blobs=blobs,
        converter=GotenbergConverter(
            settings.gotenberg_url(),
            username=credentials[0] if credentials else None,
            password=credentials[1] if credentials else None,
        ),
        queue=CeleryTaskQueue(),
        blob_client=blobs,
        model_gateway=create_model_gateway,
        configs=ConfigRegistry(engine, RedisConfigCache()),
    )
