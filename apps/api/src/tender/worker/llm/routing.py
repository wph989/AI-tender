"""分析与问答共用的模型路由装配；不承担文档业务处理。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, replace
from typing import Any

from tender.application.llm.routing import CallRecord, ModelCandidate, RoutingModel
from tender.core.di import (
    create_model_gateway,
    create_model_runtime_repository,
    create_provider_cooldown,
)
from tender.core.secrets import SecretKeyUnavailable, decrypt_secret

_repository = create_model_runtime_repository()


def _log_call(record: CallRecord) -> None:
    _repository.record_call(asdict(record))


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
    rows = _repository.candidates(feature_key)
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

    cooldown = create_provider_cooldown()
    candidates = _load_candidates(feature_key, purpose)
    if extra_retries_limit is not None:
        candidates = [
            replace(candidate, extra_retries=min(candidate.extra_retries, extra_retries_limit))
            for candidate in candidates
        ]
    policy = _repository.policy(feature_key)

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
