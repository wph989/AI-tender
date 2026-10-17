"""LLM 供应商、模型、功能绑定与调用记录 API（设计文档 12）。

这一层只做参数校验、SQL 与响应整形：优先级规则在 application/llm_registry.py，
降级与调用记录在 application/llm_routing.py，密钥加解密在 core/secrets.py。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Engine, delete, exists, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from tender.adapters.pg.models import (
    KnowledgeCollection,
    KnowledgeIndex,
    KnowledgeSource,
    LlmCallLog,
    LlmFeature,
    LlmFeatureModel,
    LlmModel,
    LlmProvider,
    LlmTest,
    ProjectFile,
)
from tender.adapters.pg.repositories.model_test import maintain_model_tests
from tender.api.common import engine
from tender.api.errors import ApiProblem
from tender.application.llm_registry import (
    DEFAULT_FAILOVER_LIMIT,
    FEATURE_DESCRIPTIONS,
    FEATURES,
    INACTIVE_FEATURES,
    MAX_BINDINGS,
    binding_rows,
)
from tender.application.model_probes import PROBE_IMAGE
from tender.application.model_profiles import (
    ADAPTER_VERSION,
    FEATURE_FIELDS,
    LANGUAGE,
    MODEL_FIELDS,
    PROFILES,
    field_bounds,
    required_kind,
    supported_parameters,
    test_capabilities,
    validate_base_url,
    validate_model,
)
from tender.core.di import create_embedding_gateway, create_image_gateway
from tender.core.error_details import error_detail
from tender.core.secrets import (
    SecretKeyUnavailable,
    decrypt_secret,
    encrypt_secret,
    secret_hint,
    secret_key_ready,
)
from tender.domain.errors import ModelInUse, TenderError
from tender.ports.model_media import EmbeddingInput

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


def _error_summary(value: str | None) -> str | None:
    if not value:
        return None
    # 详情已由适配器处理已知密钥；读取时保留正文，并兼顾历史记录中的常见凭证字段。
    return error_detail(value)


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
    # 传空串表示清除已存密钥；不传表示保持原值。
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
    timeout_seconds: float | None = Field(
        default=None, allow_inf_nan=False, **field_bounds(MODEL_FIELDS["timeout_seconds"])
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

    # 有序即优先级：第 1 个是 1 级，见 application/llm_registry.binding_rows
    model_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(
        default_factory=list, max_length=MAX_BINDINGS
    )
    revision: int = Field(ge=1)
    # 绑定与预算在同一事务保存，避免前端两次写入留下半份配置。
    failover_limit: int | None = Field(
        default=None, strict=True, **field_bounds(FEATURE_FIELDS["failover_limit"])
    )
    max_total_requests: int | None = Field(
        default=None, strict=True, **field_bounds(FEATURE_FIELDS["max_total_requests"])
    )
    deadline_seconds: int | None = Field(
        default=None, strict=True, **field_bounds(FEATURE_FIELDS["deadline_seconds"])
    )


class FeaturePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failover_limit: int = Field(strict=True, **field_bounds(FEATURE_FIELDS["failover_limit"]))
    max_total_requests: int = Field(
        default=6, strict=True, **field_bounds(FEATURE_FIELDS["max_total_requests"])
    )
    deadline_seconds: int = Field(
        default=600, strict=True, **field_bounds(FEATURE_FIELDS["deadline_seconds"])
    )
    revision: int = Field(ge=1)


def _provider_row(db: Engine, provider_id: int) -> dict[str, Any]:
    with db.connect() as connection:
        row = (
            connection.execute(
                select(LlmProvider).where(
                    LlmProvider.id == provider_id, LlmProvider.deleted_at.is_(None)
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise ApiProblem(404, "not_found", "供应商不存在")
    return dict(row)


def _model_row(db: Engine, model_id: int) -> dict[str, Any]:
    with db.connect() as connection:
        row = (
            connection.execute(
                select(
                    LlmModel,
                    LlmProvider.name.label("provider_name"),
                    LlmProvider.base_url,
                    LlmProvider.api_key_ciphertext,
                    LlmProvider.protocol,
                    LlmProvider.auth_mode,
                    LlmProvider.config_revision.label("provider_config_revision"),
                    LlmProvider.enabled.label("provider_enabled"),
                )
                .select_from(LlmModel)
                .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                .where(
                    LlmModel.id == model_id,
                    LlmModel.deleted_at.is_(None),
                    LlmProvider.deleted_at.is_(None),
                )
            )
            .mappings()
            .first()
        )
    if row is None:
        raise ApiProblem(404, "not_found", "模型不存在")
    result = dict(row)
    # NUMERIC 列经 psycopg 返回 Decimal：归一成 float，供校验、比较与 JSON 序列化共用。
    if result["temperature"] is not None:
        result["temperature"] = float(result["temperature"])
    _attach_test_summaries(db, [result])
    return result


def _provider_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "base_url": row["base_url"],
        "protocol": row["protocol"],
        "auth_mode": row["auth_mode"],
        "revision": row["revision"],
        "api_key_updated_at": row["api_key_updated_at"],
        "test_validity": _validity(row),
        "api_key_hint": row["api_key_hint"],
        "has_api_key": row["api_key_ciphertext"] is not None,
        "enabled": row["enabled"],
        "last_test_status": row["last_test_status"],
        "last_test_at": row["last_test_at"],
        "last_test_error": _error_summary(row["last_test_error"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _model_out(row: Mapping[str, Any]) -> dict[str, Any]:
    # 总览也按全部已声明的测试能力聚合；文本成功不能把图文模型整体标成通过。
    checks = row.get("capability_tests", {})
    states = [
        checks.get(cap, {}).get("validity", "untested") for cap in test_capabilities(dict(row))
    ]
    validity = next(
        (
            state
            for state in ("running", "unknown", "config_changed", "failed", "expired", "untested")
            if state in states
        ),
        "valid",
    )
    return {
        "id": row["id"],
        "provider_id": row["provider_id"],
        "provider_name": row.get("provider_name"),
        "provider_enabled": row.get("provider_enabled", True),
        "kind": row["kind"],
        "api_mode": row["api_mode"],
        "capabilities": row["capabilities"],
        "extra_retries": row["extra_retries"],
        "revision": row["revision"],
        "test_validity": validity,
        "supported_parameters": supported_parameters(row["protocol"], dict(row)),
        "parameters": row["parameters"],
        "embedding_input_type": ("multimodal" if "image_input" in row["capabilities"] else "text")
        if row["kind"] == "embedding"
        else None,
        "embedding_space_id": str(row["embedding_space_id"]) if row["embedding_space_id"] else None,
        "test_capabilities": test_capabilities(dict(row)),
        "capability_tests": row.get("capability_tests", {}),
        "model_id": row["model_id"],
        "display_name": row["display_name"],
        "timeout_seconds": float(row["timeout_seconds"]),
        "temperature": float(row["temperature"]) if row["temperature"] is not None else None,
        "max_tokens": row["max_tokens"],
        "enabled": row["enabled"],
        "last_test_status": row["last_test_status"],
        "last_test_at": row["last_test_at"],
        "last_test_error": _error_summary(row["last_test_error"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _validity(row: Mapping[str, Any]) -> str:
    if row.get("last_test_status") is None:
        return "untested"
    if row.get("last_test_config_revision") != row["config_revision"]:
        return "config_changed"
    if (
        "provider_config_revision" in row
        and row.get("last_test_provider_revision") != row["provider_config_revision"]
    ):
        return "config_changed"
    if row["last_test_status"] in {"running", "unsupported"}:
        return row["last_test_status"]
    if row["last_test_status"] != "ok":
        return "failed"
    if row["last_test_at"] and row["last_test_at"] + timedelta(days=7) <= datetime.now(UTC):
        return "expired"
    return "valid"


def _api_key_for(row: Mapping[str, Any]) -> str | None:
    # 匿名必须显式声明，清空凭证不能悄悄改用环境中的另一套身份。
    if row.get("auth_mode") == "none":
        return None
    if not row.get("api_key_ciphertext"):
        raise SecretKeyUnavailable("供应商未配置 API Key，请填写密钥或选择匿名服务")
    return decrypt_secret(str(row["api_key_ciphertext"]))


def _store_key(connection: Any, provider_id: int, api_key: str | None) -> None:
    """写入或清除密钥；空串表示清除，None 表示不动。"""
    if api_key is None:
        return
    connection.execute(
        update(LlmProvider)
        .where(LlmProvider.id == provider_id)
        .values(
            credential_revision=LlmProvider.credential_revision + 1,
            api_key_updated_at=func.now(),
        )
    )
    if api_key == "":
        connection.execute(
            update(LlmProvider)
            .where(LlmProvider.id == provider_id)
            .values(api_key_ciphertext=None, api_key_hint=None)
        )
        return
    connection.execute(
        update(LlmProvider)
        .where(LlmProvider.id == provider_id)
        .values(api_key_ciphertext=encrypt_secret(api_key), api_key_hint=secret_hint(api_key))
    )


def _record_call(
    db: Engine,
    *,
    provider_id: int | None,
    model_id: int | None,
    feature_key: str | None,
    purpose: str,
    status: str,
    http_status: int | None,
    latency_ms: int,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    error: str | None,
    snapshot: Mapping[str, Any],
    vector_count: int | None = None,
    document_count: int | None = None,
    image_count: int | None = None,
    test_id: int | None = None,
) -> None:
    with db.begin() as connection:
        if test_id is not None:
            # 测试身份先落账本，结果回写时只更新可变量，避免覆盖建账时的模型快照。
            connection.execute(
                update(LlmCallLog)
                .where(
                    LlmCallLog.id
                    == select(LlmTest.call_log_id).where(LlmTest.id == test_id).scalar_subquery()
                )
                .values(
                    status=status,
                    http_status=http_status,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_message=error_detail(error),
                    vector_count=vector_count,
                    document_count=document_count,
                    image_count=image_count,
                )
            )
        else:
            connection.execute(
                insert(LlmCallLog).values(
                    provider_id=provider_id,
                    model_id=model_id,
                    feature_key=feature_key,
                    purpose=purpose,
                    status=status,
                    http_status=http_status,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_message=error_detail(error),
                    provider_name_snapshot=snapshot.get("provider_name", snapshot.get("name")),
                    model_name_snapshot=snapshot.get("display_name"),
                    model_key_snapshot=snapshot.get("model_id"),
                    vector_count=vector_count,
                    document_count=document_count,
                    image_count=image_count,
                )
            )


def _begin_test(db: Engine, row: dict, capability: str, is_model: bool) -> int:
    with db.begin() as c:
        call_id = None
        if is_model:
            # 调用账本与测试身份同事务建立，登记失败时不能发送供应商请求。
            call_id = c.execute(
                insert(LlmCallLog)
                .values(
                    provider_id=row["provider_id"],
                    model_id=row["id"],
                    purpose="test",
                    status="running",
                    latency_ms=0,
                    provider_name_snapshot=row["provider_name"],
                    model_name_snapshot=row["display_name"],
                    model_key_snapshot=row["model_id"],
                )
                .returning(LlmCallLog.id)
            ).scalar_one()
        test_id = int(
            c.execute(
                insert(LlmTest)
                .values(
                    provider_id=row["provider_id"] if is_model else row["id"],
                    model_id=row["id"] if is_model else None,
                    capability=capability,
                    provider_revision=row["provider_config_revision"]
                    if is_model
                    else row["config_revision"],
                    model_revision=row["config_revision"] if is_model else None,
                    timeout_seconds=float(row.get("timeout_seconds", 90)),
                    call_log_id=call_id,
                )
                .returning(LlmTest.id)
            ).scalar_one()
        )
        entity = LlmModel if is_model else LlmProvider
        values: dict[str, Any] = {
            "last_test_id": test_id,
            "last_test_status": "running",
            "last_test_error": None,
            "last_test_config_revision": row["config_revision"],
        }
        if is_model:
            values["last_test_provider_revision"] = row.get("provider_config_revision")
        # 测试开始顺序也参与比较，后启动的测试运行中时，旧结果不能倒灌摘要。
        c.execute(
            update(entity)
            .where(
                entity.id == row["id"],
                entity.config_revision == row["config_revision"],
                func.coalesce(entity.last_test_id, 0) < test_id,
            )
            .values(**values)
        )
        return test_id


def _finish_test(
    db: Engine,
    row: dict,
    test_id: int,
    status: str,
    error: str | None,
    latency: int,
    is_model: bool,
) -> None:
    entity = LlmModel if is_model else LlmProvider
    with db.begin() as c:
        c.execute(
            update(LlmTest)
            .where(LlmTest.id == test_id)
            .values(status=status, error_message=error, latency_ms=latency, finished_at=func.now())
        )
        values: dict[str, Any] = {
            "last_test_status": status,
            "last_test_at": func.now(),
            "last_test_error": error,
            "last_test_config_revision": row["config_revision"],
            "last_test_id": test_id,
        }
        if is_model:
            values["last_test_provider_revision"] = row.get("provider_config_revision")
        conditions = [
            entity.id == row["id"],
            entity.config_revision == row["config_revision"],
            entity.last_test_id == test_id,
            entity.deleted_at.is_(None),
        ]
        if is_model:
            # 模型测试同时核验供应商版本，防止轮换凭证后回写旧证明。
            conditions.append(
                exists().where(
                    LlmProvider.id == LlmModel.provider_id,
                    LlmProvider.config_revision == row.get("provider_config_revision"),
                    LlmProvider.deleted_at.is_(None),
                )
            )
        # 结果保留为历史事实。
        c.execute(update(entity).where(*conditions).values(**values))


@router.get("/settings")
def llm_settings() -> dict[str, Any]:
    return {
        "secret_key_ready": secret_key_ready(),
        "adapter_profiles": PROFILES,
        "test_valid_seconds": 604800,
        "max_bindings": MAX_BINDINGS,
        "model_fields": MODEL_FIELDS,
        "feature_fields": FEATURE_FIELDS,
        "default_max_total_requests": 6,
    }


def _test_view(row: Mapping[str, Any]) -> dict:
    item = {
        k: v
        for k, v in row.items()
        if k
        not in {
            "preview_data",
            "preview_mime",
            "current_model_revision",
            "current_provider_revision",
        }
    }
    changed = (
        row.get("invalidated_at") is not None
        or row["provider_revision"]
        != row.get("current_provider_revision", row["provider_revision"])
        or (
            row["model_id"] is not None
            and row["model_revision"] != row.get("current_model_revision", row["model_revision"])
        )
    )
    expiry = row["finished_at"] + timedelta(days=7) if row["finished_at"] else None
    validity = (
        "config_changed"
        if changed
        else "running"
        if row["status"] == "running"
        else "unknown"
        if row["status"] == "unknown"
        else "failed"
        if row["status"] == "error"
        else "unsupported"
        if row["status"] == "unsupported"
        else "expired"
        if expiry and expiry <= datetime.now(UTC)
        else "valid"
    )
    return item | {
        "error_message": _error_summary(row["error_message"]),
        "validity": validity,
        "expires_at": expiry,
        "capability": "text" if row["capability"] == "language" else row["capability"],
    }


def _test_select() -> Any:
    return (
        select(
            LlmTest.id,
            LlmTest.provider_id,
            LlmTest.model_id,
            LlmTest.capability,
            LlmTest.provider_revision,
            LlmTest.model_revision,
            LlmTest.status,
            LlmTest.latency_ms,
            LlmTest.error_message,
            LlmTest.created_at,
            LlmTest.finished_at,
            LlmTest.result,
            LlmTest.invalidated_at,
            LlmProvider.config_revision.label("current_provider_revision"),
            LlmModel.config_revision.label("current_model_revision"),
        )
        .select_from(LlmTest)
        .join(LlmProvider, LlmProvider.id == LlmTest.provider_id)
        .outerjoin(LlmModel, LlmModel.id == LlmTest.model_id)
    )


def _attach_test_summaries(db: Engine, models: list[dict]) -> None:
    if not models:
        return
    maintain_model_tests(db)
    latest = (
        select(func.max(LlmTest.id))
        .where(LlmTest.model_id.in_([m["id"] for m in models]))
        .group_by(LlmTest.model_id, LlmTest.capability)
    )
    with db.connect() as c:
        tests = (
            c.execute(_test_select().where(LlmTest.id.in_(latest)).order_by(LlmTest.id.desc()))
            .mappings()
            .all()
        )
    lookup = {m["id"]: m for m in models}
    for test in tests:
        view = _test_view(test)
        lookup[test["model_id"]].setdefault("capability_tests", {}).setdefault(
            view["capability"], view
        )


@router.get("/tests")
def list_tests(
    request: Request, model_id: int | None = None, limit: int = Query(default=30, ge=1, le=100)
) -> dict:
    maintain_model_tests(engine(request))
    statement = _test_select()
    if model_id is not None:
        statement = statement.where(LlmTest.model_id == model_id)
    with engine(request).connect() as c:
        rows = c.execute(statement.order_by(LlmTest.id.desc()).limit(limit)).mappings().all()
    return {"items": [_test_view(r) for r in rows]}


@router.get("/tests/{test_id}")
def get_test(test_id: int, request: Request) -> dict:
    maintain_model_tests(engine(request))
    with engine(request).connect() as c:
        row = c.execute(_test_select().where(LlmTest.id == test_id)).mappings().first()
    if row is None:
        raise ApiProblem(404, "not_found", "测试记录不存在")
    return _test_view(row)


@router.get("/tests/{test_id}/preview")
def test_preview(test_id: int, request: Request) -> Response:
    test = get_test(test_id, request)
    if test["validity"] != "valid":
        raise ApiProblem(410, "test_preview_expired", "测试图片已失效，需显式重新测试")
    with engine(request).connect() as c:
        row = (
            c.execute(
                select(LlmTest.preview_data, LlmTest.preview_mime).where(LlmTest.id == test_id)
            )
            .mappings()
            .one()
        )
    if not row["preview_data"]:
        raise ApiProblem(404, "not_found", "该测试没有图片预览")
    return Response(
        content=bytes(row["preview_data"]),
        media_type=row["preview_mime"],
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/providers")
def list_providers(request: Request) -> dict[str, Any]:
    with engine(request).connect() as connection:
        rows = (
            connection.execute(
                select(LlmProvider)
                .where(LlmProvider.deleted_at.is_(None))
                .order_by(LlmProvider.name)
            )
            .mappings()
            .all()
        )
    return {"items": [_provider_out(row) for row in rows]}


@router.post("/providers", status_code=201)
def create_provider(payload: ProviderCreate, request: Request) -> dict[str, Any]:
    db = engine(request)
    try:
        with db.begin() as connection:
            provider_id = connection.execute(
                insert(LlmProvider)
                .values(
                    name=payload.name,
                    base_url=payload.base_url,
                    enabled=payload.enabled,
                    protocol=payload.protocol,
                    auth_mode=payload.auth_mode,
                )
                .returning(LlmProvider.id)
            ).scalar_one()
            _store_key(connection, int(provider_id), payload.api_key)
    except IntegrityError as exc:
        raise ApiProblem(409, "duplicate_name", "供应商名称已存在") from exc
    return _provider_out(_provider_row(db, int(provider_id)))


@router.patch("/providers/{provider_id}")
def update_provider(provider_id: int, payload: ProviderPatch, request: Request) -> dict[str, Any]:
    db = engine(request)
    _provider_row(db, provider_id)
    if payload.clear_api_key and payload.api_key is not None:
        raise ApiProblem(422, "invalid_argument", "清除密钥与填写新密钥不能同时提交")
    if payload.base_url is not None:
        try:
            payload.base_url = validate_base_url(payload.base_url)
        except ValueError as exc:
            raise ApiProblem(422, "invalid_argument", str(exc)) from exc
    fields = {
        "auth_mode": payload.auth_mode,
        "name": payload.name,
        "base_url": payload.base_url,
        "enabled": payload.enabled,
    }
    try:
        with db.begin() as connection:
            current = (
                connection.execute(
                    select(LlmProvider)
                    .where(LlmProvider.id == provider_id, LlmProvider.deleted_at.is_(None))
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            _check_revision(current, payload.revision)
            for column, value in fields.items():
                if value is None:
                    continue
                connection.execute(
                    update(LlmProvider)
                    .where(LlmProvider.id == provider_id)
                    .values(**{column: value}, updated_at=func.now())
                )
            _store_key(connection, provider_id, "" if payload.clear_api_key else payload.api_key)
            changed = (
                any(
                    value is not None and current[key] != value
                    for key, value in fields.items()
                    if key in {"base_url", "auth_mode"}
                )
                or payload.api_key is not None
                or payload.clear_api_key
            )
            connection.execute(
                update(LlmProvider)
                .where(LlmProvider.id == provider_id)
                .values(
                    revision=LlmProvider.revision + 1,
                    config_revision=LlmProvider.config_revision + int(changed),
                )
            )
    except IntegrityError as exc:
        raise ApiProblem(409, "duplicate_name", "供应商名称已存在") from exc
    with db.begin() as c:
        c.execute(
            update(LlmTest)
            .where(
                LlmTest.provider_id == provider_id,
                LlmTest.provider_revision
                != select(LlmProvider.config_revision)
                .where(LlmProvider.id == LlmTest.provider_id)
                .scalar_subquery(),
            )
            .values(invalidated_at=func.coalesce(LlmTest.invalidated_at, func.now()))
        )
    return _provider_out(_provider_row(db, provider_id))


def _check_revision(row: Mapping[str, Any] | None, revision: int | None) -> None:
    if row is None:
        raise ApiProblem(404, "not_found", "配置已删除")
    if revision is not None and row["revision"] != revision:
        raise ApiProblem(
            412, "revision_conflict", "配置已被修改，请刷新比较后再保存；当前草稿未丢弃"
        )


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, request: Request) -> dict[str, Any]:
    db = engine(request)
    _provider_row(db, provider_id)
    with db.begin() as connection:
        connection.execute(
            select(LlmProvider.id).where(LlmProvider.id == provider_id).with_for_update()
        )
        ids = list(
            connection.execute(
                select(LlmModel.id)
                .where(LlmModel.provider_id == provider_id)
                .order_by(LlmModel.id)
                .with_for_update()
            ).scalars()
        )
        _check_index_use(connection, ids)
        bound = connection.execute(
            select(LlmFeatureModel.id)
            .select_from(LlmFeatureModel)
            .join(LlmModel, LlmModel.id == LlmFeatureModel.model_id)
            .where(LlmModel.provider_id == provider_id)
            .limit(1)
        ).scalar_one_or_none()
        if bound is not None:
            raise ModelInUse("该供应商下仍有模型绑定到功能，请先解绑")
        connection.execute(
            update(LlmModel)
            .where(LlmModel.provider_id == provider_id)
            .values(deleted_at=func.now())
        )
        connection.execute(
            update(LlmProvider).where(LlmProvider.id == provider_id).values(deleted_at=func.now())
        )
    return {"status": "deleted"}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: int, request: Request) -> dict[str, Any]:
    db = engine(request)
    row = _provider_row(db, provider_id)
    test_id = _begin_test(db, row, "catalog", False)
    started = time.monotonic()
    status, http_status, error = "ok", None, None
    try:
        if row["protocol"] == "rerank_http":
            raise ApiProblem(422, "catalog_unsupported", "专用重排协议没有目录接口，请手动添加模型")
        # model 名称对 /models 无意义，占位即可；测的是连接与鉴权。
        gateway = request.app.state.components.model_gateway(
            row["base_url"],
            "models-probe",
            api_key=_api_key_for(row),
            timeout=30,
            protocol=row["protocol"],
        )
        try:
            await gateway.list_models()
            http_status = 200
        finally:
            await gateway.aclose()
    except (TenderError, SecretKeyUnavailable, ValueError, ApiProblem) as exc:
        status = "unsupported" if isinstance(exc, ApiProblem) else "error"
        http_status = getattr(exc, "http_status", None)
        error = str(exc)
    latency_ms = int((time.monotonic() - started) * 1000)
    _record_call(
        db,
        provider_id=provider_id,
        model_id=None,
        feature_key=None,
        purpose="test",
        status=status,
        http_status=http_status,
        latency_ms=latency_ms,
        prompt_tokens=None,
        completion_tokens=None,
        error=error,
        snapshot=row,
    )
    _finish_test(db, row, test_id, status, error, latency_ms, False)
    return {
        "test_id": test_id,
        "status": status,
        "latency_ms": latency_ms,
        "http_status": http_status,
        "error": error,
    }


@router.get("/providers/{provider_id}/remote-models")
async def remote_models(provider_id: int, request: Request) -> dict[str, Any]:
    db = engine(request)
    row = _provider_row(db, provider_id)
    if row["protocol"] == "rerank_http":
        raise ApiProblem(422, "catalog_unsupported", "专用重排协议没有目录接口，请手动添加模型")
    gateway = request.app.state.components.model_gateway(
        row["base_url"],
        "models-probe",
        api_key=_api_key_for(row),
        timeout=30,
        protocol=row["protocol"],
    )
    try:
        items = list(dict.fromkeys(await gateway.list_models()))
    finally:
        await gateway.aclose()
    return {"items": items}


@router.post("/providers/{provider_id}/models/import")
def import_models(provider_id: int, payload: ImportRequest, request: Request) -> dict[str, Any]:
    db = engine(request)
    provider = _provider_row(db, provider_id)
    _validate(provider["protocol"], payload.model_dump())
    model_ids = list(dict.fromkeys(payload.model_ids))
    created = 0
    with db.begin() as c:
        current = (
            c.execute(
                select(LlmProvider)
                .where(LlmProvider.id == provider_id, LlmProvider.deleted_at.is_(None))
                .with_for_update()
            )
            .mappings()
            .first()
        )
        _check_revision(current, None)
        for key in model_ids:
            if not key.strip() or len(key) > 200:
                raise ApiProblem(422, "invalid_argument", "模型 ID 不能为空或超过 200 字符")
            # ON CONFLICT DO NOTHING 下 RETURNING 只回传真正插入的行；不能用 rowcount
            # （带 RETURNING 的语句在 psycopg 下不提供 rowcount）。
            inserted = (
                c.execute(
                    pg_insert(LlmModel)
                    .values(
                        provider_id=provider_id,
                        model_id=key,
                        display_name=key,
                        kind=payload.kind,
                        api_mode=payload.api_mode,
                        capabilities=payload.capabilities,
                        enabled=False,
                        timeout_seconds=payload.timeout_seconds or 90,
                        temperature=payload.temperature,
                        max_tokens=payload.max_tokens,
                        extra_retries=payload.extra_retries,
                        parameters=payload.parameters,
                        supported_parameters=payload.supported_parameters,
                        embedding_space_id=uuid4() if payload.kind == "embedding" else None,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["provider_id", "model_id"],
                        index_where=LlmModel.deleted_at.is_(None),
                    )
                    .returning(LlmModel.id)
                )
                .scalars()
                .all()
            )
            created += len(inserted)
    return {"imported": created, "created": created, "skipped": len(model_ids) - created}


def _validate(protocol: str, model: dict) -> None:
    try:
        validate_model(protocol, model)
    except ValueError as exc:
        raise ApiProblem(422, "capability_unsupported", str(exc)) from exc


@router.get("/models")
def list_models(request: Request, provider_id: int | None = None) -> dict[str, Any]:
    statement = (
        select(
            LlmModel,
            LlmProvider.name.label("provider_name"),
            LlmProvider.enabled.label("provider_enabled"),
            LlmProvider.config_revision.label("provider_config_revision"),
            LlmProvider.protocol,
        )
        .select_from(LlmModel)
        .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
        .where(LlmModel.deleted_at.is_(None), LlmProvider.deleted_at.is_(None))
        .order_by(LlmProvider.name, LlmModel.display_name)
    )
    if provider_id is not None:
        statement = statement.where(LlmModel.provider_id == provider_id)
    with engine(request).connect() as connection:
        rows = connection.execute(statement).mappings().all()
    items = [dict(row) for row in rows]
    _attach_test_summaries(engine(request), items)
    return {"items": [_model_out(row) for row in items]}


@router.post("/models", status_code=201)
def create_model(payload: ModelCreate, request: Request) -> dict[str, Any]:
    db = engine(request)
    provider = _provider_row(db, payload.provider_id)
    _validate(provider["protocol"], payload.model_dump())
    display_name = payload.display_name or payload.model_id
    try:
        with db.begin() as connection:
            current = (
                connection.execute(
                    select(LlmProvider)
                    .where(LlmProvider.id == payload.provider_id, LlmProvider.deleted_at.is_(None))
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            _check_revision(current, None)
            model_id = connection.execute(
                insert(LlmModel)
                .values(
                    provider_id=payload.provider_id,
                    model_id=payload.model_id,
                    display_name=display_name,
                    timeout_seconds=payload.timeout_seconds or 90,
                    temperature=payload.temperature,
                    max_tokens=payload.max_tokens,
                    enabled=payload.enabled,
                    kind=payload.kind,
                    api_mode=payload.api_mode,
                    capabilities=payload.capabilities,
                    extra_retries=payload.extra_retries,
                    parameters=payload.parameters,
                    supported_parameters=payload.supported_parameters,
                    embedding_space_id=uuid4() if payload.kind == "embedding" else None,
                )
                .returning(LlmModel.id)
            ).scalar_one()
    except IntegrityError as exc:
        raise ApiProblem(409, "duplicate_name", "该供应商下已存在同名模型") from exc
    return _model_out(_model_row(db, int(model_id)))


@router.patch("/models/{model_id}")
def update_model(model_id: int, payload: ModelPatch, request: Request) -> dict[str, Any]:
    db = engine(request)
    row = _model_row(db, model_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"revision"})
    if any(
        v is None and k not in {"temperature", "max_tokens", "supported_parameters"}
        for k, v in fields.items()
    ):
        raise ApiProblem(422, "invalid_argument", "只有温度、输出上限和模型参数支持范围允许清空")
    with db.begin() as c:
        current = (
            c.execute(
                select(LlmModel)
                .where(LlmModel.id == model_id, LlmModel.deleted_at.is_(None))
                .with_for_update()
            )
            .mappings()
            .first()
        )
        _check_revision(current, payload.revision)
        # 重读行的温度同样是 Decimal，先归一避免与请求里的 float 比较不等而误判配置变更。
        current = dict(current)
        if current["temperature"] is not None:
            current["temperature"] = float(current["temperature"])
        row.update(current)
        _validate(row["protocol"], row | fields)
        if (
            fields.get("kind", row["kind"]) != row["kind"]
            or fields.get("capabilities", row["capabilities"]) != row["capabilities"]
        ):
            bound = (
                c.execute(
                    select(LlmFeatureModel.feature_key).where(LlmFeatureModel.model_id == model_id)
                )
                .scalars()
                .all()
            )
            if any(
                required_kind(key) != fields.get("kind", row["kind"])
                or (
                    required_kind(key) == "language"
                    and "json_output" not in fields.get("capabilities", row["capabilities"])
                )
                for key in bound
            ):
                raise ApiProblem(
                    409, "model_in_use", "模型种类或 JSON 能力与现有功能绑定不符，请先解绑"
                )
            _check_index_use(c, [model_id])
        for column, value in fields.items():
            c.execute(update(LlmModel).where(LlmModel.id == model_id).values(**{column: value}))
        # 默认参数清单与显式相同清单等价；编辑旧模型时不能仅因表单展开默认值就使证明失效。
        before = dict(row)
        after = row | fields
        for config in (before, after):
            config["supported_parameters"] = sorted(supported_parameters(row["protocol"], config))
            config["capabilities"] = sorted(config["capabilities"])
        changed = any(
            before[k] != after[k]
            for k in fields
            if k not in {"display_name", "enabled", "extra_retries"}
        )
        # 参数/能力变化重新分配空间身份，旧索引凭证不可被新配置冒用。
        if changed and (row["kind"] == "embedding" or fields.get("kind") == "embedding"):
            c.execute(
                update(LlmModel)
                .where(LlmModel.id == model_id)
                .values(
                    embedding_space_id=uuid4()
                    if fields.get("kind", row["kind"]) == "embedding"
                    else None
                )
            )
        if changed:
            c.execute(
                update(LlmTest)
                .where(LlmTest.model_id == model_id)
                .values(invalidated_at=func.coalesce(LlmTest.invalidated_at, func.now()))
            )
        c.execute(
            update(LlmModel)
            .where(LlmModel.id == model_id)
            .values(
                updated_at=func.now(),
                revision=LlmModel.revision + 1,
                config_revision=LlmModel.config_revision + int(changed),
            )
        )
    return _model_out(_model_row(db, model_id))


def _check_index_use(c: Any, ids: list[int]) -> None:
    used = c.execute(
        select(KnowledgeIndex.id)
        .select_from(KnowledgeIndex)
        .join(KnowledgeSource, KnowledgeSource.id == KnowledgeIndex.source_id)
        .join(ProjectFile, ProjectFile.id == KnowledgeSource.project_file_id)
        .join(KnowledgeCollection, KnowledgeCollection.id == KnowledgeSource.collection_id)
        .where(
            KnowledgeIndex.embedding_model_id.in_(ids),
            ProjectFile.deleted_at.is_(None),
            KnowledgeCollection.deleted_at.is_(None),
            KnowledgeIndex.status.in_(("completed", "running")),
        )
        .limit(1)
    ).scalar_one_or_none()
    if used:
        raise ModelInUse("模型仍被有效知识索引使用，请先迁移或移除对应来源")


@router.delete("/models/{model_id}")
def delete_model(model_id: int, request: Request) -> dict[str, Any]:
    db = engine(request)
    _model_row(db, model_id)
    with db.begin() as connection:
        connection.execute(select(LlmModel.id).where(LlmModel.id == model_id).with_for_update())
        _check_index_use(connection, [model_id])
        bound = connection.execute(
            select(LlmFeatureModel.id).where(LlmFeatureModel.model_id == model_id).limit(1)
        ).scalar_one_or_none()
        if bound is not None:
            raise ModelInUse("该模型仍绑定在功能上，请先解绑")
        connection.execute(
            update(LlmModel).where(LlmModel.id == model_id).values(deleted_at=func.now())
        )
    return {"status": "deleted"}


def _prepare_model_test(
    model_id: int, request: Request, payload: TestRequest | None
) -> tuple[dict, int, str]:
    db = engine(request)
    row = _model_row(db, model_id)
    allowed = test_capabilities(row)
    capability = (payload.capability if payload else None) or allowed[-1]
    if capability not in allowed:
        raise ApiProblem(422, "capability_unsupported", "所选测试能力未被模型声明或适配")
    _validate(row["protocol"], row)
    return row, _begin_test(db, row, capability, True), capability


@router.post("/models/{model_id}/test")
async def test_model(
    model_id: int, request: Request, payload: TestRequest | None = None
) -> dict[str, Any]:
    row, test_id, capability = _prepare_model_test(model_id, request, payload)
    return await _run_model_test(request, row, test_id, capability)


@router.post("/models/{model_id}/tests", status_code=202)
async def start_model_test(
    model_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: TestRequest | None = None,
) -> dict:
    row, test_id, capability = _prepare_model_test(model_id, request, payload)
    # 先持久化，再返回身份；页面刷新后按身份继续查询，不重复发起收费请求。
    background_tasks.add_task(_run_model_test, request, row, test_id, capability)
    return {"test_id": test_id, "status": "running", "capability": capability}


async def _run_model_test(request: Request, row: dict, test_id: int, capability: str) -> dict:
    db = engine(request)
    started = time.monotonic()
    status, http_status, error = "ok", None, None
    prompt_tokens = completion_tokens = vector_count = document_count = dimensions = image_count = (
        None
    )
    preview = None
    try:
        async with asyncio.timeout(float(row["timeout_seconds"])):
            if row["kind"] == "embedding":
                _api_key_for(row)
                gateway = create_embedding_gateway(row)
                try:
                    if capability == "multimodal_embedding":
                        vectors = await gateway.embed_inputs(
                            [EmbeddingInput("这是一张由红色和蓝色组成的示意图", (PROBE_IMAGE,))]
                        )
                    else:
                        vectors = await gateway.embed(["知识库连接测试"])
                    vector_count, dimensions = len(vectors), len(vectors[0])
                finally:
                    await gateway.aclose()
            elif row["kind"] == "rerank":
                from tender.core.di import create_rerank_gateway

                gateway = create_rerank_gateway(row | {"api_key": _api_key_for(row)})
                try:
                    await gateway.rerank("招标资格", ["投标人资质要求", "天气预报"], 2)
                    document_count = 2
                finally:
                    await gateway.aclose()
            elif row["kind"] == "image_generation":
                gateway = create_image_gateway(row | {"api_key": _api_key_for(row)})
                try:
                    preview = await gateway.generate(
                        "在纯白背景画一个简单的蓝色圆形，只生成一张小图。"
                    )
                    image_count = 1
                finally:
                    await gateway.aclose()
            else:
                gateway = request.app.state.components.model_gateway(
                    row["base_url"],
                    row["model_id"],
                    api_key=_api_key_for(row),
                    timeout=float(row["timeout_seconds"]),
                    temperature=row["temperature"],
                    max_tokens=row["max_tokens"],
                    protocol=row["protocol"],
                    api_mode=row["api_mode"],
                    parameters=row["parameters"],
                    capabilities=row["capabilities"],
                )
                try:
                    if capability == "vision":
                        completion = await gateway.complete(
                            "简短说明图片中有哪些颜色。", images=(PROBE_IMAGE,), json_mode=False
                        )
                    elif "json_output" in row["capabilities"]:
                        completion = await gateway.complete('只返回 JSON：{"ok": true}')
                        if json.loads(completion.content) != {"ok": True}:
                            raise ValueError("测试响应未满足要求的 JSON 结构")
                    else:
                        completion = await gateway.complete("请简短回复连接成功。", json_mode=False)
                    prompt_tokens, completion_tokens = (
                        completion.prompt_tokens,
                        completion.completion_tokens,
                    )
                finally:
                    await gateway.aclose()
            http_status = 200
    except TimeoutError:
        status, error = "unknown", "测试请求超时，供应商结果未知；不会自动重发"
    except (TenderError, SecretKeyUnavailable, ValueError) as exc:
        status, http_status, error = "error", getattr(exc, "http_status", None), str(exc)
    latency_ms = int((time.monotonic() - started) * 1000)
    result = {
        "test_id": test_id,
        "status": status,
        "capability": capability,
        "latency_ms": latency_ms,
        "http_status": http_status,
        "error": error,
        "vector_count": vector_count,
        "embedding_dimensions": dimensions,
        "document_count": document_count,
        "image_count": image_count,
        "adapter_version": ADAPTER_VERSION,
        "preview_url": f"/api/v1/llm/tests/{test_id}/preview" if preview else None,
    }
    with db.begin() as c:
        c.execute(
            update(LlmTest)
            .where(LlmTest.id == test_id)
            .values(
                result=result,
                preview_data=preview.data if preview else None,
                preview_mime=preview.mime_type if preview else None,
            )
        )
    _record_call(
        db,
        provider_id=row["provider_id"],
        model_id=row["id"],
        feature_key=None,
        purpose="test",
        status=status,
        http_status=http_status,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        error=error,
        snapshot=row,
        vector_count=vector_count,
        document_count=document_count,
        image_count=image_count,
        test_id=test_id,
    )
    _finish_test(db, row, test_id, status, error, latency_ms, True)
    return result


@router.get("/features")
def list_features(request: Request) -> dict[str, Any]:
    with engine(request).connect() as connection:
        rows = (
            connection.execute(
                select(
                    LlmFeatureModel.feature_key,
                    LlmFeatureModel.priority,
                    LlmModel.id.label("model_row_id"),
                    LlmModel.model_id,
                    LlmModel.display_name,
                    LlmModel.enabled,
                    LlmProvider.id.label("provider_id"),
                    LlmProvider.name.label("provider_name"),
                    LlmProvider.enabled.label("provider_enabled"),
                    LlmModel.kind,
                    LlmModel.extra_retries,
                )
                .select_from(LlmFeatureModel)
                .join(LlmModel, LlmModel.id == LlmFeatureModel.model_id)
                .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                .where(LlmModel.deleted_at.is_(None), LlmProvider.deleted_at.is_(None))
                .order_by(LlmFeatureModel.feature_key, LlmFeatureModel.priority)
            )
            .mappings()
            .all()
        )
        limits = {
            model_row["key"]: model_row
            for model_row in connection.execute(select(LlmFeature)).mappings().all()
        }
    items = []
    for key, name in FEATURES:
        configured = limits.get(key)
        bindings = [
            {
                "priority": model_row["priority"],
                "model_row_id": model_row["model_row_id"],
                "model_id": model_row["model_id"],
                "display_name": model_row["display_name"],
                "enabled": model_row["enabled"] and model_row["provider_enabled"],
                "kind": model_row["kind"],
                "extra_retries": model_row["extra_retries"],
                "provider_id": model_row["provider_id"],
                "provider_name": model_row["provider_name"],
            }
            for model_row in rows
            if model_row["feature_key"] == key
        ]
        items.append(
            {
                "key": key,
                "revision": configured["revision"] if configured else 1,
                "max_total_requests": configured["max_total_requests"] if configured else 6,
                "deadline_seconds": configured["deadline_seconds"] if configured else 600,
                "required_kind": required_kind(key),
                "name": name,
                "failover_limit": int(configured["failover_limit"])
                if configured
                else DEFAULT_FAILOVER_LIMIT,
                "description": FEATURE_DESCRIPTIONS[key],
                "binding_available": key not in INACTIVE_FEATURES,
                "bindings": bindings,
            }
        )
    return {"items": items}


@router.patch("/features/{feature_key}")
def update_feature(feature_key: str, payload: FeaturePatch, request: Request) -> dict[str, Any]:
    if feature_key not in {key for key, _ in FEATURES}:
        raise ApiProblem(404, "not_found", "功能不存在")
    if feature_key in INACTIVE_FEATURES:
        raise ApiProblem(409, "feature_unavailable", "该功能尚未接入业务调用，无需设置路由预算")
    with engine(request).begin() as c:
        row = c.execute(
            select(LlmFeature.revision).where(LlmFeature.key == feature_key).with_for_update()
        ).first()
        if row is None:
            raise ApiProblem(404, "not_found", "功能不存在")
        if row[0] != payload.revision:
            raise ApiProblem(
                412, "revision_conflict", "配置已被修改，草稿已保留，请刷新后比较最新版本"
            )
        c.execute(
            update(LlmFeature)
            .where(LlmFeature.key == feature_key)
            .values(
                failover_limit=payload.failover_limit,
                max_total_requests=payload.max_total_requests,
                deadline_seconds=payload.deadline_seconds,
                revision=LlmFeature.revision + 1,
                updated_at=func.now(),
            )
        )
    return _feature_item(request, feature_key)


@router.put("/features/{feature_key}/models")
def replace_bindings(
    feature_key: str, payload: BindingsRequest, request: Request
) -> dict[str, Any]:
    if feature_key not in {key for key, _ in FEATURES}:
        raise ApiProblem(404, "not_found", "功能不存在")
    if feature_key in INACTIVE_FEATURES and payload.model_ids:
        raise ApiProblem(409, "feature_unavailable", "该功能尚未接入业务调用，请在模型列表测试")
    if feature_key in {"embedding", "rerank"} and len(payload.model_ids) > 1:
        raise ApiProblem(400, "invalid_argument", "当前向量与重排功能只支持绑定一个模型")
    rows = binding_rows(payload.model_ids)
    db = engine(request)
    with db.begin() as connection:
        # 先锁模型再锁功能，与删除/修改共用顺序；等待结束后重新核验软删除状态。
        found = set()
        if rows:
            found = set(
                connection.execute(
                    select(LlmModel.id)
                    .select_from(LlmModel)
                    .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                    .where(
                        LlmModel.id.in_(payload.model_ids),
                        LlmModel.deleted_at.is_(None),
                        LlmProvider.deleted_at.is_(None),
                        LlmModel.kind == required_kind(feature_key),
                        or_(
                            LlmModel.kind != "language",
                            LlmModel.capabilities.contains(["json_output"]),
                        ),
                    )
                    .order_by(LlmModel.id)
                    .with_for_update(of=LlmModel)
                ).scalars()
            )
        locked = connection.execute(
            select(LlmFeature.revision).where(LlmFeature.key == feature_key).with_for_update()
        ).scalar_one_or_none()
        if locked is None:
            raise ApiProblem(404, "not_found", "功能不存在")
        if locked != payload.revision:
            raise ApiProblem(
                412, "revision_conflict", "配置已被修改，草稿已保留，请刷新后比较最新版本"
            )
        if rows:
            missing = sorted({model_id for model_id, _ in rows} - found)
            if missing:
                raise ApiProblem(400, "invalid_argument", f"模型不存在或种类与功能不符：{missing}")
        connection.execute(
            delete(LlmFeatureModel).where(LlmFeatureModel.feature_key == feature_key)
        )
        for model_id, priority in rows:
            connection.execute(
                insert(LlmFeatureModel).values(
                    feature_key=feature_key, model_id=model_id, priority=priority
                )
            )
        for column in ("failover_limit", "max_total_requests", "deadline_seconds"):
            value = getattr(payload, column)
            if value is not None:
                connection.execute(
                    update(LlmFeature)
                    .where(LlmFeature.key == feature_key)
                    .values(**{column: value})
                )
        connection.execute(
            update(LlmFeature)
            .where(LlmFeature.key == feature_key)
            .values(revision=LlmFeature.revision + 1, updated_at=func.now())
        )
    return _feature_item(request, feature_key)


def _feature_item(request: Request, feature_key: str) -> dict[str, Any]:
    items = list_features(request)["items"]
    return next(item for item in items if item["key"] == feature_key)


@router.get("/calls")
def list_calls(
    request: Request,
    feature_key: str | None = None,
    model_id: int | None = None,
    status: str | None = None,
    invocation_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    conditions = []
    if feature_key is not None:
        conditions.append(LlmCallLog.feature_key == feature_key)
    if model_id is not None:
        conditions.append(LlmCallLog.model_id == model_id)
    if status is not None:
        conditions.append(LlmCallLog.status == status)
    if invocation_id is not None:
        conditions.append(LlmCallLog.invocation_id == invocation_id)
    order = (
        (LlmCallLog.request_ordinal.asc(),)
        if invocation_id
        else (LlmCallLog.created_at.desc(), LlmCallLog.id.desc())
    )
    with engine(request).connect() as connection:
        total = connection.execute(
            select(func.count()).select_from(LlmCallLog).where(*conditions)
        ).scalar_one()
        rows = (
            connection.execute(
                select(
                    LlmCallLog,
                    func.coalesce(LlmCallLog.model_name_snapshot, LlmModel.display_name).label(
                        "display_name"
                    ),
                    func.coalesce(LlmCallLog.provider_name_snapshot, LlmProvider.name).label(
                        "provider_name"
                    ),
                )
                .select_from(LlmCallLog)
                .outerjoin(LlmModel, LlmModel.id == LlmCallLog.model_id)
                .outerjoin(LlmProvider, LlmProvider.id == LlmCallLog.provider_id)
                .where(*conditions)
                .order_by(*order)
                .limit(limit)
                .offset(offset)
            )
            .mappings()
            .all()
        )
    return {
        "total": int(total),
        "items": [
            dict(row) | {"error_message": _error_summary(row["error_message"])} for row in rows
        ],
    }
