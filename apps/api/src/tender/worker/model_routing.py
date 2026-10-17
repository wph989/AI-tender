"""分析与问答共用的模型路由装配；不承担文档业务处理。"""
from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tender.adapters.pg.locks import release_lock, try_acquire_lock
from tender.adapters.pg.models import LlmCallLog, LlmFeature, LlmFeatureModel, LlmModel, LlmProvider
from tender.adapters.pg.session import create_pg_engine
from tender.application.llm_routing import CallRecord, ModelCandidate, RoutingModel
from tender.core.di import create_model_gateway
from tender.core.secrets import SecretKeyUnavailable, decrypt_secret

_engine = create_pg_engine()

@contextmanager
def _advisory_lock(lock_key: str) -> Iterator[bool]:
    with _engine.connect() as connection:
        acquired = try_acquire_lock(connection, lock_key)
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                release_lock(connection, lock_key)
                connection.commit()


def _log_call(record: CallRecord) -> None:
    data = asdict(record)
    # 首次先插入 running；返回后只补写同一请求，不新增第二条调用账。
    insert_call = pg_insert(LlmCallLog).values(**data)
    with _engine.begin() as c:
        c.execute(
            insert_call.on_conflict_do_update(
                index_elements=["invocation_id", "request_ordinal"],
                set_={
                    "status": insert_call.excluded.status,
                    "http_status": insert_call.excluded.http_status,
                    "latency_ms": insert_call.excluded.latency_ms,
                    "prompt_tokens": insert_call.excluded.prompt_tokens,
                    "completion_tokens": insert_call.excluded.completion_tokens,
                    "error_message": insert_call.excluded.error_message,
                },
            )
        )


def _key_error_record(
    row: Mapping[str, Any], feature_key: str, purpose: str, message: str
) -> CallRecord:
    return CallRecord(
        provider_id=int(row["provider_id"]),
        model_id=int(row["model_row_id"]),
        feature_key=feature_key,
        purpose=purpose,
        status="error",
        http_status=None,
        latency_ms=0,
        prompt_tokens=None,
        completion_tokens=None,
        error_message=message,
    )


def _load_candidates(feature_key: str, purpose: str) -> list[ModelCandidate]:
    with _engine.connect() as connection:
        rows = (
            connection.execute(
                select(
                    LlmModel.id.label("model_row_id"),
                    LlmModel.model_id,
                    LlmModel.display_name,
                    LlmModel.timeout_seconds,
                    LlmModel.temperature,
                    LlmModel.max_tokens,
                    LlmModel.extra_retries,
                    LlmModel.api_mode,
                    LlmProvider.protocol,
                    LlmModel.parameters,
                    LlmModel.capabilities,
                    LlmProvider.name.label("provider_name"),
                    LlmProvider.auth_mode,
                    LlmProvider.api_key_ciphertext,
                    LlmProvider.id.label("provider_id"),
                    LlmProvider.base_url,
                )
                .select_from(LlmFeatureModel)
                .join(LlmModel, LlmModel.id == LlmFeatureModel.model_id)
                .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                .where(
                    LlmFeatureModel.feature_key == feature_key,
                    LlmModel.enabled.is_(True),
                    LlmModel.deleted_at.is_(None),
                    LlmModel.kind == "language",
                    LlmModel.capabilities.contains(["json_output"]),
                    LlmProvider.enabled.is_(True),
                    LlmProvider.deleted_at.is_(None),
                )
                .order_by(LlmFeatureModel.priority)
            )
            .mappings()
            .all()
        )
    candidates: list[ModelCandidate] = []
    for row in rows:
        try:
            if row["auth_mode"] == "api_key" and not row["api_key_ciphertext"]:
                raise SecretKeyUnavailable("供应商未配置 API Key")
            api_key = (
                decrypt_secret(str(row["api_key_ciphertext"]))
                if row["api_key_ciphertext"] and row["auth_mode"] == "api_key"
                else None
            )
        except SecretKeyUnavailable as exc:
            # 解不开的密钥不能被静默跳过：先落一条失败记录，页面才看得到真正原因。
            _log_call(_key_error_record(row, feature_key, purpose, str(exc)))
            continue
        candidates.append(
            ModelCandidate(
                parameters_json=json.dumps(row["parameters"], sort_keys=True),
                capabilities=tuple(row["capabilities"]),
                extra_retries=int(row["extra_retries"]),
                protocol=row["protocol"],
                api_mode=row["api_mode"],
                provider_name=row["provider_name"],
                registry_model_id=int(row["model_row_id"]),
                provider_id=int(row["provider_id"]),
                display_name=str(row["display_name"]),
                model=str(row["model_id"]),
                base_url=str(row["base_url"]),
                api_key=api_key,
                timeout=float(row["timeout_seconds"]),
                temperature=float(row["temperature"]) if row["temperature"] is not None else None,
                max_tokens=int(row["max_tokens"]) if row["max_tokens"] is not None else None,
            )
        )
    return candidates


def _routing_model(
    feature_key: str,
    purpose: str,
    *,
    before_request=None,
    output_limit: int | None = None,
    on_call=None,
    remaining_seconds=None,
    extra_retries_limit: int | None = None,
    rate_limit_backoff_seconds: float = 30,
    rate_limit_max_wait_seconds: float = 600,
) -> RoutingModel:
    from tender.adapters.pg.repositories.provider_cooldown import ProviderCooldown

    cooldown = ProviderCooldown(_engine)
    candidates = _load_candidates(feature_key, purpose)
    if extra_retries_limit is not None:
        candidates = [
            replace(candidate, extra_retries=min(candidate.extra_retries, extra_retries_limit))
            for candidate in candidates
        ]
    with _engine.connect() as c:
        policy = (
            c.execute(select(LlmFeature).where(LlmFeature.key == feature_key)).mappings().first()
        )

    def recheck(snapshot: ModelCandidate) -> ModelCandidate | None:
        current = next(
            (
                c
                for c in _load_candidates(feature_key, purpose)
                if c.registry_model_id == snapshot.registry_model_id
            ),
            None,
        )
        if current is None or (current.protocol, current.api_mode) != (
            snapshot.protocol,
            snapshot.api_mode,
        ):
            return None
        # 参数与次数固定于调用创建时；端点和密钥必须取同一最新供应商行。
        return replace(snapshot, base_url=current.base_url, api_key=current.api_key)

    def record_call(record):
        _log_call(record)
        if on_call:
            on_call(record)

    return RoutingModel(
        feature_key,
        purpose,
        candidates,
        create_model_gateway,
        record_call,
        failover_limit=policy["failover_limit"] if policy else 3,
        max_total_requests=policy["max_total_requests"] if policy else 6,
        deadline_seconds=policy["deadline_seconds"] if policy else 600,
        recheck=recheck,
        reserve=_log_call,
        before_request=before_request,
        output_limit=output_limit,
        cooldown_remaining=cooldown.remaining,
        defer_provider=cooldown.defer,
        remaining_seconds=remaining_seconds,
        rate_limit_backoff_seconds=rate_limit_backoff_seconds,
        rate_limit_max_wait_seconds=rate_limit_max_wait_seconds,
    )
