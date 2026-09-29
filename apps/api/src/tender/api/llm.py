"""LLM 供应商、模型、功能绑定与调用记录 API（设计文档 12）。

这一层只做参数校验、SQL 与响应整形：优先级规则在 application/llm_registry.py，
降级与调用记录在 application/llm_routing.py，密钥加解密在 core/secrets.py。
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from tender.api.common import engine
from tender.api.errors import ApiProblem
from tender.application.llm_registry import DEFAULT_FAILOVER_LIMIT, FEATURES, binding_rows
from tender.core import settings
from tender.core.secrets import SecretKeyUnavailable, decrypt_secret, encrypt_secret, secret_hint
from tender.domain.errors import ModelInUse, TenderError

router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool = True


class ProviderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    # 传空串表示清除已存密钥；不传表示保持原值。
    api_key: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: int
    model_id: str = Field(min_length=1, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0, le=100000)
    enabled: bool = True


class ModelPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0, le=100000)
    enabled: bool | None = None


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_ids: list[str] = Field(min_length=1, max_length=200)


class BindingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 有序即优先级：第 1 个是 1 级，见 application/llm_registry.binding_rows
    model_ids: list[int] = Field(default_factory=list, max_length=10)


class FeaturePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failover_limit: int = Field(ge=1, le=10)


def _provider_row(db: Engine, provider_id: int) -> dict[str, Any]:
    with db.connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT * FROM llm_provider
                       WHERE id = :id AND deleted_at IS NULL"""
                ),
                {"id": provider_id},
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
                text(
                    """SELECT m.*, p.name AS provider_name, p.base_url, p.api_key_ciphertext
                       FROM llm_model AS m
                       JOIN llm_provider AS p ON p.id = m.provider_id
                       WHERE m.id = :id AND m.deleted_at IS NULL AND p.deleted_at IS NULL"""
                ),
                {"id": model_id},
            )
            .mappings()
            .first()
        )
    if row is None:
        raise ApiProblem(404, "not_found", "模型不存在")
    return dict(row)


def _provider_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "base_url": row["base_url"],
        "api_key_hint": row["api_key_hint"],
        "has_api_key": row["api_key_ciphertext"] is not None,
        "enabled": row["enabled"],
        "last_test_status": row["last_test_status"],
        "last_test_at": row["last_test_at"],
        "last_test_error": row["last_test_error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _model_out(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "provider_id": row["provider_id"],
        "provider_name": row.get("provider_name"),
        "model_id": row["model_id"],
        "display_name": row["display_name"],
        "timeout_seconds": float(row["timeout_seconds"]),
        "temperature": float(row["temperature"]) if row["temperature"] is not None else None,
        "max_tokens": row["max_tokens"],
        "enabled": row["enabled"],
        "last_test_status": row["last_test_status"],
        "last_test_at": row["last_test_at"],
        "last_test_error": row["last_test_error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _api_key_for(row: Mapping[str, Any]) -> str | None:
    """库内密文优先，其次 .env 的 LLM_API_KEY（已部署环境的兼容路径）。"""
    ciphertext = row.get("api_key_ciphertext")
    if ciphertext:
        return decrypt_secret(str(ciphertext))
    return settings.llm_api_key()


def _store_key(connection: Any, provider_id: int, api_key: str | None) -> None:
    """写入或清除密钥；空串表示清除，None 表示不动。"""
    if api_key is None:
        return
    if api_key == "":
        connection.execute(
            text(
                "UPDATE llm_provider SET api_key_ciphertext = NULL, api_key_hint = NULL "
                "WHERE id = :id"
            ),
            {"id": provider_id},
        )
        return
    connection.execute(
        text(
            "UPDATE llm_provider SET api_key_ciphertext = :ciphertext, api_key_hint = :hint "
            "WHERE id = :id"
        ),
        {"id": provider_id, "ciphertext": encrypt_secret(api_key), "hint": secret_hint(api_key)},
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
) -> None:
    with db.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO llm_call_log
                       (provider_id, model_id, feature_key, purpose, status, http_status,
                        latency_ms, prompt_tokens, completion_tokens, error_message)
                   VALUES
                       (:provider_id, :model_id, :feature_key, :purpose, :status, :http_status,
                        :latency_ms, :prompt_tokens, :completion_tokens, :error_message)"""
            ),
            {
                "provider_id": provider_id,
                "model_id": model_id,
                "feature_key": feature_key,
                "purpose": purpose,
                "status": status,
                "http_status": http_status,
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "error_message": error[:500] if error else None,
            },
        )


def _write_test_result(db: Engine, table: str, row_id: int, status: str, error: str | None) -> None:
    # table 只由本模块的两个常量传入，不是用户输入，不存在注入面。
    with db.begin() as connection:
        connection.execute(
            text(
                f"UPDATE {table} SET last_test_status = :status, last_test_at = now(), "
                "last_test_error = :error, updated_at = now() WHERE id = :id"
            ),
            {"id": row_id, "status": status, "error": error[:500] if error else None},
        )


@router.get("/providers")
def list_providers(request: Request) -> dict[str, Any]:
    with engine(request).connect() as connection:
        rows = (
            connection.execute(
                text(
                    """SELECT * FROM llm_provider
                       WHERE deleted_at IS NULL ORDER BY name"""
                )
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
                text(
                    """INSERT INTO llm_provider (name, base_url, enabled)
                       VALUES (:name, :base_url, :enabled) RETURNING id"""
                ),
                {"name": payload.name, "base_url": payload.base_url, "enabled": payload.enabled},
            ).scalar_one()
            _store_key(connection, int(provider_id), payload.api_key)
    except IntegrityError as exc:
        raise ApiProblem(409, "duplicate_name", "供应商名称已存在") from exc
    return _provider_out(_provider_row(db, int(provider_id)))


@router.patch("/providers/{provider_id}")
def update_provider(provider_id: int, payload: ProviderPatch, request: Request) -> dict[str, Any]:
    db = engine(request)
    _provider_row(db, provider_id)
    fields = {
        "name": payload.name,
        "base_url": payload.base_url,
        "enabled": payload.enabled,
    }
    try:
        with db.begin() as connection:
            for column, value in fields.items():
                if value is None:
                    continue
                connection.execute(
                    text(
                        f"UPDATE llm_provider SET {column} = :value, updated_at = now() "
                        "WHERE id = :id"
                    ),
                    {"id": provider_id, "value": value},
                )
            _store_key(connection, provider_id, payload.api_key)
    except IntegrityError as exc:
        raise ApiProblem(409, "duplicate_name", "供应商名称已存在") from exc
    return _provider_out(_provider_row(db, provider_id))


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, request: Request) -> dict[str, Any]:
    db = engine(request)
    _provider_row(db, provider_id)
    with db.begin() as connection:
        bound = connection.execute(
            text(
                """SELECT 1 FROM llm_feature_model AS fm
                   JOIN llm_model AS m ON m.id = fm.model_id
                   WHERE m.provider_id = :id LIMIT 1"""
            ),
            {"id": provider_id},
        ).scalar_one_or_none()
        if bound is not None:
            raise ModelInUse("该供应商下仍有模型绑定到功能，请先解绑")
        connection.execute(
            text("UPDATE llm_provider SET deleted_at = now() WHERE id = :id"), {"id": provider_id}
        )
    return {"status": "deleted"}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: int, request: Request) -> dict[str, Any]:
    db = engine(request)
    row = _provider_row(db, provider_id)
    started = time.monotonic()
    status, http_status, error = "ok", None, None
    try:
        # model 名称对 /models 无意义，占位即可；测的是连接与鉴权。
        gateway = request.app.state.components.model_gateway(
            row["base_url"], "models-probe", api_key=_api_key_for(row), timeout=30
        )
        try:
            await gateway.list_models()
            http_status = 200
        finally:
            await gateway.aclose()
    except (TenderError, SecretKeyUnavailable, ValueError) as exc:
        status = "error"
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
    )
    _write_test_result(db, "llm_provider", provider_id, status, error)
    return {"status": status, "latency_ms": latency_ms, "http_status": http_status, "error": error}


@router.get("/providers/{provider_id}/remote-models")
async def remote_models(provider_id: int, request: Request) -> dict[str, Any]:
    db = engine(request)
    row = _provider_row(db, provider_id)
    gateway = request.app.state.components.model_gateway(
        row["base_url"], "models-probe", api_key=_api_key_for(row), timeout=30
    )
    try:
        items = await gateway.list_models()
    finally:
        await gateway.aclose()
    return {"items": items}


@router.post("/providers/{provider_id}/models/import")
def import_models(provider_id: int, payload: ImportRequest, request: Request) -> dict[str, Any]:
    db = engine(request)
    _provider_row(db, provider_id)
    model_ids = list(dict.fromkeys(payload.model_ids))
    with db.begin() as connection:
        for model_id in model_ids:
            connection.execute(
                text(
                    """INSERT INTO llm_model (provider_id, model_id, display_name)
                       VALUES (:provider_id, :model_id, :model_id)
                       ON CONFLICT (provider_id, model_id) DO UPDATE
                       SET deleted_at = NULL, enabled = true, updated_at = now()"""
                ),
                {"provider_id": provider_id, "model_id": model_id},
            )
    return {"imported": len(model_ids)}


@router.get("/models")
def list_models(request: Request, provider_id: int | None = None) -> dict[str, Any]:
    condition = "AND m.provider_id = :provider_id" if provider_id is not None else ""
    with engine(request).connect() as connection:
        rows = (
            connection.execute(
                text(
                    f"""SELECT m.*, p.name AS provider_name
                        FROM llm_model AS m
                        JOIN llm_provider AS p ON p.id = m.provider_id
                        WHERE m.deleted_at IS NULL AND p.deleted_at IS NULL {condition}
                        ORDER BY p.name, m.display_name"""
                ),
                {"provider_id": provider_id} if provider_id is not None else {},
            )
            .mappings()
            .all()
        )
    return {"items": [_model_out(row) for row in rows]}


@router.post("/models", status_code=201)
def create_model(payload: ModelCreate, request: Request) -> dict[str, Any]:
    db = engine(request)
    _provider_row(db, payload.provider_id)
    display_name = payload.display_name or payload.model_id
    try:
        with db.begin() as connection:
            model_id = connection.execute(
                text(
                    """INSERT INTO llm_model
                           (provider_id, model_id, display_name, timeout_seconds,
                            temperature, max_tokens, enabled)
                       VALUES (:provider_id, :model_id, :display_name, :timeout_seconds,
                               :temperature, :max_tokens, :enabled)
                       RETURNING id"""
                ),
                {
                    "provider_id": payload.provider_id,
                    "model_id": payload.model_id,
                    "display_name": display_name,
                    "timeout_seconds": payload.timeout_seconds or 90,
                    "temperature": payload.temperature,
                    "max_tokens": payload.max_tokens,
                    "enabled": payload.enabled,
                },
            ).scalar_one()
    except IntegrityError as exc:
        raise ApiProblem(409, "duplicate_name", "该供应商下已存在同名模型") from exc
    return _model_out(_model_row(db, int(model_id)))


@router.patch("/models/{model_id}")
def update_model(model_id: int, payload: ModelPatch, request: Request) -> dict[str, Any]:
    db = engine(request)
    _model_row(db, model_id)
    fields = {
        "display_name": payload.display_name,
        "timeout_seconds": payload.timeout_seconds,
        "temperature": payload.temperature,
        "max_tokens": payload.max_tokens,
        "enabled": payload.enabled,
    }
    with db.begin() as connection:
        for column, value in fields.items():
            if value is None:
                continue
            connection.execute(
                text(f"UPDATE llm_model SET {column} = :value, updated_at = now() WHERE id = :id"),
                {"id": model_id, "value": value},
            )
    return _model_out(_model_row(db, model_id))


@router.delete("/models/{model_id}")
def delete_model(model_id: int, request: Request) -> dict[str, Any]:
    db = engine(request)
    _model_row(db, model_id)
    with db.begin() as connection:
        bound = connection.execute(
            text("SELECT 1 FROM llm_feature_model WHERE model_id = :id LIMIT 1"),
            {"id": model_id},
        ).scalar_one_or_none()
        if bound is not None:
            raise ModelInUse("该模型仍绑定在功能上，请先解绑")
        connection.execute(
            text("UPDATE llm_model SET deleted_at = now() WHERE id = :id"), {"id": model_id}
        )
    return {"status": "deleted"}


@router.post("/models/{model_id}/test")
async def test_model(model_id: int, request: Request) -> dict[str, Any]:
    db = engine(request)
    row = _model_row(db, model_id)
    started = time.monotonic()
    status, http_status, error = "ok", None, None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    try:
        gateway = request.app.state.components.model_gateway(
            row["base_url"],
            row["model_id"],
            api_key=_api_key_for(row),
            timeout=float(row["timeout_seconds"]),
            # NUMERIC 读回来是 Decimal，直接塞进 JSON 会序列化失败，这里统一转 float。
            temperature=float(row["temperature"]) if row["temperature"] is not None else None,
            max_tokens=row["max_tokens"],
        )
        try:
            # 用一次真实的 JSON 输出请求验证：能返回 JSON 才算"这个模型可用于抽取"。
            completion = await gateway.complete('只返回 JSON：{"ok": true}')
            http_status = 200
            prompt_tokens = completion.prompt_tokens
            completion_tokens = completion.completion_tokens
        finally:
            await gateway.aclose()
    except (TenderError, SecretKeyUnavailable, ValueError) as exc:
        status = "error"
        http_status = getattr(exc, "http_status", None)
        error = str(exc)
    latency_ms = int((time.monotonic() - started) * 1000)
    _record_call(
        db,
        provider_id=int(row["provider_id"]),
        model_id=model_id,
        feature_key=None,
        purpose="test",
        status=status,
        http_status=http_status,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        error=error,
    )
    _write_test_result(db, "llm_model", model_id, status, error)
    return {"status": status, "latency_ms": latency_ms, "http_status": http_status, "error": error}


@router.get("/features")
def list_features(request: Request) -> dict[str, Any]:
    with engine(request).connect() as connection:
        rows = (
            connection.execute(
                text(
                    """SELECT fm.feature_key, fm.priority, m.id AS model_row_id,
                              m.model_id, m.display_name, m.enabled,
                              p.id AS provider_id, p.name AS provider_name
                       FROM llm_feature_model AS fm
                       JOIN llm_model AS m ON m.id = fm.model_id
                       JOIN llm_provider AS p ON p.id = m.provider_id
                       WHERE m.deleted_at IS NULL AND p.deleted_at IS NULL
                       ORDER BY fm.feature_key, fm.priority"""
                )
            )
            .mappings()
            .all()
        )
        limits = {
            model_row["key"]: model_row
            for model_row in connection.execute(
                text("SELECT key, failover_limit, description FROM llm_feature")
            )
            .mappings()
            .all()
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
                "enabled": model_row["enabled"],
                "provider_id": model_row["provider_id"],
                "provider_name": model_row["provider_name"],
            }
            for model_row in rows
            if model_row["feature_key"] == key
        ]
        items.append(
            {
                "key": key,
                "name": name,
                "failover_limit": int(configured["failover_limit"])
                if configured
                else DEFAULT_FAILOVER_LIMIT,
                "description": str(configured["description"]) if configured else "",
                "bindings": bindings,
            }
        )
    return {"items": items}


@router.patch("/features/{feature_key}")
def update_feature(feature_key: str, payload: FeaturePatch, request: Request) -> dict[str, Any]:
    if feature_key not in {key for key, _ in FEATURES}:
        raise ApiProblem(404, "not_found", "功能不存在")
    with engine(request).begin() as connection:
        connection.execute(
            text(
                """INSERT INTO llm_feature (key, name, failover_limit)
                   VALUES (:key, :name, :limit)
                   ON CONFLICT (key) DO UPDATE
                   SET failover_limit = EXCLUDED.failover_limit, updated_at = now()"""
            ),
            {
                "key": feature_key,
                "name": dict(FEATURES)[feature_key],
                "limit": payload.failover_limit,
            },
        )
    return {"key": feature_key, "failover_limit": payload.failover_limit}


@router.put("/features/{feature_key}/models")
def replace_bindings(
    feature_key: str, payload: BindingsRequest, request: Request
) -> dict[str, Any]:
    if feature_key not in {key for key, _ in FEATURES}:
        raise ApiProblem(404, "not_found", "功能不存在")
    rows = binding_rows(payload.model_ids)
    db = engine(request)
    with db.begin() as connection:
        locked = connection.execute(
            text("SELECT key FROM llm_feature WHERE key = :key FOR UPDATE"),
            {"key": feature_key},
        ).scalar_one_or_none()
        if locked is None:
            raise ApiProblem(404, "not_found", "功能不存在")
        if rows:
            found = {
                int(value)
                for value in connection.execute(
                    text(
                        """SELECT id FROM llm_model
                           WHERE id = ANY(CAST(:ids AS BIGINT[])) AND deleted_at IS NULL"""
                    ),
                    {"ids": [model_id for model_id, _ in rows]},
                ).scalars()
            }
            missing = sorted({model_id for model_id, _ in rows} - found)
            if missing:
                raise ApiProblem(400, "invalid_argument", f"模型不存在：{missing}")
        connection.execute(
            text("DELETE FROM llm_feature_model WHERE feature_key = :key"), {"key": feature_key}
        )
        for model_id, priority in rows:
            connection.execute(
                text(
                    """INSERT INTO llm_feature_model (feature_key, model_id, priority)
                       VALUES (:feature_key, :model_id, :priority)"""
                ),
                {"feature_key": feature_key, "model_id": model_id, "priority": priority},
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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    conditions = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if feature_key is not None:
        conditions.append("c.feature_key = :feature_key")
        params["feature_key"] = feature_key
    if model_id is not None:
        conditions.append("c.model_id = :model_id")
        params["model_id"] = model_id
    if status is not None:
        conditions.append("c.status = :status")
        params["status"] = status
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with engine(request).connect() as connection:
        total = connection.execute(
            text(f"SELECT count(*) FROM llm_call_log AS c {where}"), params
        ).scalar_one()
        rows = (
            connection.execute(
                text(
                    f"""SELECT c.*, m.display_name, p.name AS provider_name
                        FROM llm_call_log AS c
                        LEFT JOIN llm_model AS m ON m.id = c.model_id
                        LEFT JOIN llm_provider AS p ON p.id = c.provider_id
                        {where}
                        ORDER BY c.created_at DESC, c.id DESC
                        LIMIT :limit OFFSET :offset"""
                ),
                params,
            )
            .mappings()
            .all()
        )
    return {"total": int(total), "items": [dict(row) for row in rows]}
