"""模型路由用例工厂：候选快照、重查和记账，外部实现由构造参数注入。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, replace
from typing import Any

from tender.application.llm.routing import CallRecord, ModelCandidate, RoutingModel
from tender.core.secrets import SecretKeyUnavailable, decrypt_secret
from tender.ports.llm.chat import ModelGateway
from tender.ports.llm.cooldown import ProviderCooldown
from tender.ports.repository.llm.runtime import ModelRuntimeRepository


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


class RoutingModelFactory:
    def __init__(
        self, repository: ModelRuntimeRepository, cooldown: ProviderCooldown, gateway: ModelGateway
    ) -> None:
        # API/Worker/独立验收共用同一候选和调用账规则，不在使用方创建客户端。
        self.repository, self.cooldown, self.gateway = repository, cooldown, gateway

    def _log_call(self, record: CallRecord) -> None:
        self.repository.record_call(asdict(record))

    def _load_candidates(self, feature_key: str, purpose: str) -> list[ModelCandidate]:
        rows = self.repository.candidates(feature_key)
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
                self._log_call(_key_error_record(row, feature_key, purpose, str(exc)))
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
                    total_timeout=float(row["total_timeout_seconds"])
                    if row.get("total_timeout_seconds") is not None
                    else None,
                    temperature=float(row["temperature"])
                    if row["temperature"] is not None
                    else None,
                    max_tokens=int(row["max_tokens"]) if row["max_tokens"] is not None else None,
                )
            )
        return candidates

    def __call__(
        self,
        feature_key: str,
        purpose: str,
        *,
        before_request=None,
        output_limit: int | None = None,
        on_call=None,
        remaining_seconds=None,
        rate_limit_backoff_seconds: float = 30,
        rate_limit_max_wait_seconds: float = 600,
        invocation_store=None,
        before_call=None,
    ) -> RoutingModel:

        cooldown = self.cooldown
        def load_route() -> tuple[list[ModelCandidate], int]:
            candidates = self._load_candidates(feature_key, purpose)
            policy = self.repository.policy(feature_key)
            return candidates, policy["failover_limit"] if policy else 3

        def recheck(snapshot: ModelCandidate) -> ModelCandidate | None:
            current = next(
                (
                    c
                    for c in self._load_candidates(feature_key, purpose)
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
            self._log_call(record)
            if on_call:
                on_call(record)

        return RoutingModel(
            feature_key,
            purpose,
            (),
            self.gateway,
            record_call,
            load_route=load_route,
            recheck=recheck,
            reserve=self._log_call,
            before_request=before_request,
            output_limit=output_limit,
            cooldown_remaining=cooldown.remaining,
            defer_provider=cooldown.defer,
            remaining_seconds=remaining_seconds,
            rate_limit_backoff_seconds=rate_limit_backoff_seconds,
            rate_limit_max_wait_seconds=rate_limit_max_wait_seconds,
            invocation_store=invocation_store,
            before_call=before_call,
        )
