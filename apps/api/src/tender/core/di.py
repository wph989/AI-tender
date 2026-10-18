"""唯一装配点：API 与 worker 使用相同的外部服务配置。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine

from tender.adapters.configuration.redis_cache import RedisConfigCache
from tender.adapters.documents.gotenberg import GotenbergConverter
from tender.adapters.documents.mineru import MinerUParser
from tender.adapters.jobs.celery_queue import CeleryTaskQueue
from tender.adapters.llm.openai_chat import OpenAIChatModel
from tender.adapters.llm.openai_embedding import OpenAIEmbeddingModel
from tender.adapters.llm.provider_image import ProviderImageModel
from tender.adapters.llm.rerank_http import HttpRerankModel
from tender.adapters.pg.repositories.configuration.releases import ConfigRepository
from tender.adapters.pg.repositories.documents.parsing import ParseRepository
from tender.adapters.pg.repositories.documents.pipeline import DocumentPipelineRepository
from tender.adapters.pg.repositories.documents.versions import VersionRepository
from tender.adapters.pg.repositories.jobs.coordination import TaskLocks
from tender.adapters.pg.repositories.jobs.dispatch import DispatchRepository
from tender.adapters.pg.repositories.jobs.tasks import JobRepository
from tender.adapters.pg.repositories.knowledge.store import KnowledgeStore
from tender.adapters.pg.repositories.llm.management import LlmRepository
from tender.adapters.pg.repositories.llm.provider_cooldown import ProviderCooldown
from tender.adapters.pg.repositories.llm.runtime import ModelRuntimeRepository
from tender.adapters.pg.repositories.projects.files import ProjectFileRepository
from tender.adapters.pg.repositories.projects.projects import ProjectRepository
from tender.adapters.pg.session import create_pg_engine
from tender.adapters.storage.s3 import S3BlobStore
from tender.application.analysis.service import AnalysisService
from tender.application.configuration.service import ConfigService
from tender.application.documents.parsing import ParseService
from tender.application.documents.versions import VersionService
from tender.application.jobs.service import JobService
from tender.application.knowledge.service import KnowledgeService
from tender.application.llm.service import LlmService
from tender.application.projects.files import ProjectFileService
from tender.application.projects.service import ProjectService
from tender.config.registry import ConfigRegistry
from tender.core import settings
from tender.core.secrets import decrypt_secret
from tender.ports.configuration.registry import ConfigReader
from tender.ports.documents.converter import OfficeConverter
from tender.ports.documents.parser import DocumentParser
from tender.ports.jobs.coordination import TaskLocks as TaskLocksPort
from tender.ports.jobs.queue import TaskQueue
from tender.ports.llm.chat import ChatGateway, ModelGateway
from tender.ports.llm.cooldown import ProviderCooldown as ProviderCooldownPort
from tender.ports.llm.embedding import EmbeddingModel
from tender.ports.llm.media import ImageGenerationModel
from tender.ports.llm.rerank import RerankModel
from tender.ports.repository.documents.pipeline import (
    DocumentPipelineRepository as DocumentPipelinePort,
)
from tender.ports.repository.jobs.dispatch import DispatchRepository as DispatchPort
from tender.ports.repository.knowledge.store import KnowledgeStore as KnowledgeStorePort
from tender.ports.repository.llm.runtime import ModelRuntimeRepository as ModelRuntimePort
from tender.ports.storage.blob_store import BlobStore


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


def create_image_gateway(config: dict) -> ImageGenerationModel:
    return ProviderImageModel(
        config["base_url"],
        config["model_id"],
        api_key=config.get("api_key"),
        timeout=float(config["timeout_seconds"]),
        protocol=config["protocol"],
        parameters=config.get("parameters"),
        allow_images="image_input" in config.get("capabilities", []),
    )


def create_rerank_gateway(config: dict) -> RerankModel:
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


# 用例只接收端口；具体仓储和外部网关统一在这里装配，防止业务模块反向依赖实现。
def create_project_service(engine: Engine, company_id: int) -> ProjectService:
    return ProjectService(ProjectRepository(engine, company_id), company_id)


def create_job_service(engine: Engine, company_id: int) -> JobService:
    return JobService(JobRepository(engine, company_id), company_id)


def create_version_service(engine: Engine, company_id: int) -> VersionService:
    return VersionService(VersionRepository(engine, company_id), company_id)


def create_parse_service(engine: Engine, company_id: int, configs: ConfigRegistry) -> ParseService:
    return ParseService(
        ParseRepository(engine, company_id, configs),
        company_id,
        configs,
        VersionRepository(engine, company_id),
    )


def create_project_file_service(
    engine: Engine,
    company_id: int,
    blobs: BlobStore,
    configs: ConfigRegistry,
) -> ProjectFileService:
    return ProjectFileService(
        ProjectFileRepository(engine, company_id, configs),
        company_id,
        blobs,
        configs,
    )


def create_config_service(
    engine: Engine, company_id: int, configs: ConfigRegistry
) -> ConfigService:
    return ConfigService(ConfigRepository(engine, company_id), company_id, configs)


def create_llm_service(
    engine: Engine,
    model_gateway: ModelGateway,
    *,
    embedding_gateway: Any,
    image_gateway: Any,
    rerank_gateway: Any,
) -> LlmService:
    return LlmService(
        LlmRepository(engine),
        model_gateway,
        embedding_gateway=embedding_gateway,
        image_gateway=image_gateway,
        rerank_gateway=rerank_gateway,
    )


def create_knowledge_service(
    engine: Engine,
    company_id: int,
    configs: ConfigRegistry,
) -> KnowledgeService:
    return KnowledgeService(
        KnowledgeStore(engine, company_id, configs),
        company_id,
        configs,
        create_embedding_gateway,
        create_parse_service(engine, company_id, configs),
    )


def create_analysis_service(
    engine: Engine,
    company_id: int,
    configs: ConfigRegistry,
) -> AnalysisService:
    knowledge = create_knowledge_service(engine, company_id, configs)
    return AnalysisService(
        knowledge.store,
        company_id,
        configs,
        create_embedding_gateway,
        knowledge,
    )


@lru_cache(maxsize=1)
def _worker_engine() -> Engine:
    # Worker 的业务模块共用进程内引擎，入口层无需持有连接池或数据库类型。
    return create_pg_engine()


@lru_cache(maxsize=1)
def _worker_configs() -> ConfigRegistry:
    return ConfigRegistry(_worker_engine(), RedisConfigCache())


def create_worker_config_reader() -> ConfigReader:
    return _worker_configs()


def create_document_pipeline_repository(engine: Engine | None = None) -> DocumentPipelinePort:
    selected = engine if engine is not None else _worker_engine()
    return DocumentPipelineRepository(selected, ConfigRegistry(selected))


def create_dispatch_repository(engine: Engine | None = None) -> DispatchPort:
    return DispatchRepository(engine if engine is not None else _worker_engine())


def create_task_locks(engine: Engine | None = None) -> TaskLocksPort:
    return TaskLocks(engine if engine is not None else _worker_engine())


def create_model_runtime_repository(engine: Engine | None = None) -> ModelRuntimePort:
    return ModelRuntimeRepository(engine if engine is not None else _worker_engine())


def create_provider_cooldown() -> ProviderCooldownPort:
    return ProviderCooldown(_worker_engine())


def create_worker_knowledge_store() -> KnowledgeStorePort:
    return KnowledgeStore(_worker_engine(), settings.company_id(), _worker_configs())


def create_document_parser(pdf_loader: Callable[[str], Awaitable[bytes]]) -> DocumentParser:
    return MinerUParser(
        settings.mineru_url(), pdf_loader=pdf_loader, api_key=settings.mineru_api_key()
    )


def open_analysis_checkpoints() -> AbstractAsyncContextManager[Any]:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from tender.adapters.pg.analysis.checkpoints import checkpoint_dsn

    # 返回上下文管理器，检查点连接仍随单次运行关闭，不在 Worker 导入时建表。
    return AsyncPostgresSaver.from_conn_string(checkpoint_dsn())


def run_analysis_async(coroutine: Coroutine[Any, Any, Any]) -> Any:
    from tender.adapters.pg.analysis.checkpoints import run_async

    return run_async(coroutine)
