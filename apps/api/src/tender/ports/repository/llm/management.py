"""数据库访问端口：用例声明所需操作，PostgreSQL 实现负责 SQL 与事务。"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any, Protocol
from uuid import UUID


class RecordConflict(Exception):
    """持久化唯一性或完整性约束冲突，不携带驱动和 SQL 细节。"""


class LlmTransaction(Protocol):
    def lock_provider(self, provider_id: int) -> dict[str, Any] | None: ...

    def insert_provider(self, values: Mapping[str, Any]) -> int: ...

    def update_provider(self, provider_id: int, values: Mapping[str, Any]) -> None: ...

    def store_provider_key(
        self, provider_id: int, ciphertext: str | None, hint: str | None
    ) -> None: ...

    def bump_provider_revision(self, provider_id: int, *, config_changed: bool) -> None: ...

    def lock_provider_models(self, provider_id: int) -> list[int]: ...

    def index_in_use(self, model_ids: list[int]) -> bool: ...

    def provider_has_binding(self, provider_id: int) -> bool: ...

    def model_has_binding(self, model_id: int) -> bool: ...

    def feature_keys_for_model(self, model_id: int) -> list[str]: ...

    def soft_delete_provider_models(self, provider_id: int) -> None: ...

    def soft_delete_provider(self, provider_id: int) -> None: ...

    def lock_model(self, model_id: int) -> dict[str, Any] | None: ...

    def insert_model(self, values: Mapping[str, Any]) -> int: ...

    def insert_models_if_absent(self, rows: list[Mapping[str, Any]]) -> int: ...

    def update_model(self, model_id: int, values: Mapping[str, Any]) -> None: ...

    def invalidate_model_tests(self, model_id: int) -> None: ...

    def bump_model_revision(self, model_id: int, *, config_changed: bool) -> None: ...

    def soft_delete_model(self, model_id: int) -> None: ...

    def lock_models_for_binding(
        self, model_ids: list[int], *, kind: str, require_json: bool
    ) -> set[int]: ...

    def lock_feature(self, feature_key: str) -> int | None: ...

    def replace_feature_models(self, feature_key: str, rows: list[tuple[int, int]]) -> None: ...

    def update_feature(self, feature_key: str, values: Mapping[str, Any]) -> None: ...

    def bump_feature_revision(self, feature_key: str) -> None: ...

    def begin_test(self, row: Mapping[str, Any], capability: str, *, is_model: bool) -> int: ...

    def store_test_result(
        self,
        test_id: int,
        *,
        result: Mapping[str, Any],
        preview_data: bytes | None,
        preview_mime: str | None,
    ) -> None: ...

    def finish_test(
        self,
        row: Mapping[str, Any],
        test_id: int,
        *,
        status: str,
        error: str | None,
        latency_ms: int,
        is_model: bool,
    ) -> None: ...

    def record_call(
        self,
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
        error_message: str | None,
        snapshot: Mapping[str, Any],
        vector_count: int | None,
        document_count: int | None,
        image_count: int | None,
        test_id: int | None,
    ) -> None: ...


class LlmRepository(Protocol):
    def transaction(self) -> AbstractContextManager[LlmTransaction]: ...

    def provider(self, provider_id: int) -> dict[str, Any] | None: ...

    def providers(self) -> list[dict[str, Any]]: ...

    def model(self, model_id: int) -> dict[str, Any] | None: ...

    def models(self, provider_id: int | None = None) -> list[dict[str, Any]]: ...

    def maintain_tests(self) -> None: ...

    def latest_tests(self, model_ids: list[int]) -> list[dict[str, Any]]: ...

    def tests(self, model_id: int | None, limit: int) -> list[dict[str, Any]]: ...

    def test(self, test_id: int) -> dict[str, Any] | None: ...

    def test_preview(self, test_id: int) -> dict[str, Any] | None: ...

    def feature_rows(self) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]: ...

    def calls(
        self,
        *,
        feature_key: str | None,
        model_id: int | None,
        status: str | None,
        invocation_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[int, list[dict[str, Any]]]: ...

    def invalidate_provider_tests(self, provider_id: int) -> None: ...
