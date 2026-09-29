"""唯一装配点：API 与 worker 使用相同的外部服务配置。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, create_engine

from tender.adapters.celery_queue import CeleryTaskQueue
from tender.adapters.gotenberg import GotenbergConverter
from tender.adapters.openai_chat import OpenAIChatModel
from tender.adapters.redis_cache import RedisConfigCache
from tender.adapters.s3 import S3BlobStore
from tender.config.registry import ConfigRegistry
from tender.core import settings
from tender.ports.blob_store import BlobStore
from tender.ports.converter import OfficeConverter
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
    engine = create_engine(settings.database_url(), pool_pre_ping=True)
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
