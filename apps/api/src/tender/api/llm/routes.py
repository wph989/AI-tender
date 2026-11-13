"""LLM 供应商、模型、功能绑定与调用记录 HTTP 入口。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from tender.api.shared.common import engine
from tender.api.shared.errors import translate_service_errors
from tender.api.shared.logging import throttle_access_log
from tender.application.llm.profiles import (
    FEATURE_FIELDS,
    LANGUAGE,
    MODEL_FIELDS,
    field_bounds,
    validate_base_url,
)
from tender.application.llm.registry import MAX_BINDINGS
from tender.application.llm.service import LlmService
from tender.core.di import (
    create_embedding_gateway,
    create_image_gateway,
    create_llm_service,
    create_rerank_gateway,
)

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = True
    protocol: Literal["openai_compatible", "openai", "anthropic", "gemini", "rerank_http"] = (
        "openai_compatible"
    )
    auth_mode: Literal["api_key", "none"] = "api_key"

    _url = field_validator("base_url")(validate_base_url)


class ProviderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int | None = Field(default=None, ge=1, strict=True)
    auth_mode: Literal["api_key", "none"] | None = None
    clear_api_key: bool = False
    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["language", "embedding", "rerank", "image_generation"] = "language"
    api_mode: Literal[
        "chat_completions",
        "responses",
        "messages",
        "generate_content",
        "embeddings",
        "rerank",
        "image_generation",
    ] = "chat_completions"
    capabilities: list[str] = Field(default_factory=lambda: ["text_input", "json_output"])
    extra_retries: int = Field(
        default=1, strict=True, **field_bounds(MODEL_FIELDS["extra_retries"])
    )
    provider_id: int
    model_id: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    timeout_seconds: float = Field(
        default_factory=lambda values: 10 if values.get("kind", "language") == "language" else 90,
        allow_inf_nan=False,
        **field_bounds(MODEL_FIELDS["timeout_seconds"]),
    )
    total_timeout_seconds: float | None = Field(
        default=None, allow_inf_nan=False, **field_bounds(MODEL_FIELDS["total_timeout_seconds"])
    )
    temperature: float | None = Field(default=None, **field_bounds(LANGUAGE["temperature"]))
    max_tokens: int | None = Field(
        default=None, strict=True, **field_bounds(LANGUAGE["max_tokens"])
    )
    parameters: dict[str, Any] = Field(default_factory=dict)
    supported_parameters: list[str] | None = None
    enabled: bool = True


class ModelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int | None = Field(default=None, ge=1, strict=True)
    kind: Literal["language", "embedding", "rerank", "image_generation"] | None = None
    api_mode: (
        Literal[
            "chat_completions",
            "responses",
            "messages",
            "generate_content",
            "embeddings",
            "rerank",
            "image_generation",
        ]
        | None
    ) = None
    capabilities: list[str] | None = None
    extra_retries: int | None = Field(
        default=None, strict=True, **field_bounds(MODEL_FIELDS["extra_retries"])
    )
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    timeout_seconds: float | None = Field(
        default=None, allow_inf_nan=False, **field_bounds(MODEL_FIELDS["timeout_seconds"])
    )
    total_timeout_seconds: float | None = Field(
        default=None, allow_inf_nan=False, **field_bounds(MODEL_FIELDS["total_timeout_seconds"])
    )
    temperature: float | None = Field(default=None, **field_bounds(LANGUAGE["temperature"]))
    max_tokens: int | None = Field(
        default=None, strict=True, **field_bounds(LANGUAGE["max_tokens"])
    )
    parameters: dict[str, Any] | None = None
    supported_parameters: list[str] | None = None
    enabled: bool | None = None


class TestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: (
        Literal["text", "vision", "embedding", "multimodal_embedding", "rerank", "image_generation"]
        | None
    ) = None


class ImportRequest(ModelCreate):
    model_config = ConfigDict(extra="forbid")

    provider_id: int = 0
    model_id: str = "import"
    model_ids: list[str] = Field(min_length=1, max_length=100)


class BindingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(
        default_factory=list, max_length=MAX_BINDINGS
    )
    revision: int = Field(ge=1)
    failover_limit: int | None = Field(
        default=None, strict=True, **field_bounds(FEATURE_FIELDS["failover_limit"])
    )
    max_total_requests: int | None = Field(
        default=None, strict=True, **field_bounds(FEATURE_FIELDS["max_total_requests"])
    )


class FeaturePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failover_limit: int = Field(strict=True, **field_bounds(FEATURE_FIELDS["failover_limit"]))
    max_total_requests: int = Field(
        default=6, strict=True, **field_bounds(FEATURE_FIELDS["max_total_requests"])
    )
    revision: int = Field(ge=1)


def _service_from_engine(db: Any) -> LlmService:
    return create_llm_service(
        db,
        lambda *args, **kwargs: None,
        embedding_gateway=create_embedding_gateway,
        image_gateway=create_image_gateway,
        rerank_gateway=create_rerank_gateway,
    )


def _service(request: Request) -> LlmService:
    return create_llm_service(
        engine(request),
        request.app.state.components.model_gateway,
        embedding_gateway=create_embedding_gateway,
        image_gateway=create_image_gateway,
        rerank_gateway=create_rerank_gateway,
    )


@router.get("/settings")
@throttle_access_log()
def llm_settings() -> dict[str, Any]:
    return LlmService.settings()


@router.get("/tests")
@translate_service_errors
def list_tests(
    request: Request,
    model_id: int | None = None,
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, Any]:
    return _service(request).list_tests(model_id, limit)


@router.get("/tests/{test_id}")
@translate_service_errors
def get_test(test_id: int, request: Request) -> dict[str, Any]:
    return _service(request).get_test(test_id)


@router.get("/tests/{test_id}/preview")
@translate_service_errors
def test_preview(test_id: int, request: Request) -> Response:
    content, media_type = _service(request).test_preview(test_id)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/providers")
@throttle_access_log()
@translate_service_errors
def list_providers(request: Request) -> dict[str, Any]:
    return _service(request).list_providers()


@router.post("/providers", status_code=201)
@translate_service_errors
def create_provider(payload: ProviderCreate, request: Request) -> dict[str, Any]:
    return _service(request).create_provider(payload.model_dump())


@router.patch("/providers/{provider_id}")
@translate_service_errors
def update_provider(provider_id: int, payload: ProviderPatch, request: Request) -> dict[str, Any]:
    return _service(request).update_provider(provider_id, payload.model_dump())


@router.delete("/providers/{provider_id}")
@translate_service_errors
def delete_provider(provider_id: int, request: Request) -> dict[str, Any]:
    return _service(request).delete_provider(provider_id)


@router.post("/providers/{provider_id}/test")
@translate_service_errors
async def test_provider(provider_id: int, request: Request) -> dict[str, Any]:
    return await _service(request).test_provider(provider_id)


@router.get("/providers/{provider_id}/remote-models")
@translate_service_errors
async def remote_models(provider_id: int, request: Request) -> dict[str, Any]:
    return await _service(request).remote_models(provider_id)


@router.post("/providers/{provider_id}/models/import")
@translate_service_errors
def import_models(
    provider_id: int, payload: ImportRequest, request: Request
) -> dict[str, Any]:
    return _service(request).import_models(provider_id, payload.model_dump())


@router.get("/models")
@throttle_access_log()
@translate_service_errors
def list_models(request: Request, provider_id: int | None = None) -> dict[str, Any]:
    return _service(request).list_models(provider_id)


@router.post("/models", status_code=201)
@translate_service_errors
def create_model(payload: ModelCreate, request: Request) -> dict[str, Any]:
    return _service(request).create_model(payload.model_dump())


@router.patch("/models/{model_id}")
@translate_service_errors
def update_model(model_id: int, payload: ModelPatch, request: Request) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True, exclude={"revision"})
    values["revision"] = payload.revision
    return _service(request).update_model(model_id, values)


@router.delete("/models/{model_id}")
@translate_service_errors
def delete_model(model_id: int, request: Request) -> dict[str, Any]:
    return _service(request).delete_model(model_id)


@router.post("/models/{model_id}/test")
@translate_service_errors
async def test_model(
    model_id: int, request: Request, payload: TestRequest | None = None
) -> dict[str, Any]:
    return await _service(request).test_model(
        model_id, payload.capability if payload else None
    )


@router.post("/models/{model_id}/tests", status_code=202)
@translate_service_errors
async def start_model_test(
    model_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: TestRequest | None = None,
) -> dict[str, Any]:
    service = _service(request)
    row, test_id, capability = await asyncio.to_thread(
        service.begin_model_test,
        model_id, payload.capability if payload else None
    )
    background_tasks.add_task(service.run_model_test, row, test_id, capability)
    return {"test_id": test_id, "status": "running", "capability": capability}


@router.get("/features")
@throttle_access_log()
@translate_service_errors
def list_features(request: Request) -> dict[str, Any]:
    return _service(request).list_features()


@router.patch("/features/{feature_key}")
@translate_service_errors
def update_feature(
    feature_key: str, payload: FeaturePatch, request: Request
) -> dict[str, Any]:
    return _service(request).update_feature(feature_key, payload.model_dump())


@router.put("/features/{feature_key}/models")
@translate_service_errors
def replace_bindings(
    feature_key: str, payload: BindingsRequest, request: Request
) -> dict[str, Any]:
    return _service(request).replace_bindings(feature_key, payload.model_dump())


@router.get("/calls")
@translate_service_errors
def list_calls(
    request: Request,
    feature_key: str | None = None,
    model_id: int | None = None,
    status: str | None = None,
    invocation_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return _service(request).list_calls(
        feature_key=feature_key,
        model_id=model_id,
        status=status,
        invocation_id=invocation_id,
        limit=limit,
        offset=offset,
    )


def _api_key_for(row: Mapping[str, Any]) -> str | None:
    """兼容旧测试的纯函数入口；真实规则仍在服务层。"""
    return LlmService._api_key_for(row)


def _feature_item(request: Request, feature_key: str) -> dict[str, Any]:
    """兼容既有管理测试，避免测试为了取一项配置而复制展示逻辑。"""
    return _service(request).feature_item(feature_key)


def _model_row(db: Any, model_id: int) -> dict[str, Any]:
    return _service_from_engine(db)._model_row(model_id)


def _begin_test(db: Any, row: Mapping[str, Any], capability: str, is_model: bool) -> int:
    return _service_from_engine(db)._begin_test(row, capability, is_model=is_model)


def _finish_test(
    db: Any,
    row: Mapping[str, Any],
    test_id: int,
    status: str,
    error: str | None,
    latency_ms: int,
    is_model: bool,
) -> None:
    _service_from_engine(db)._finish_test(
        row,
        test_id,
        status=status,
        error=error,
        latency_ms=latency_ms,
        is_model=is_model,
    )
