"""LLM 管理用例：供应商、模型、功能路由、连通性测试与调用账本。

服务层负责配置语义、版本冲突、能力校验和展示整形；持久化统一委托
``tender.ports.repository.llm``，外部模型调用通过构造时注入的网关工厂完成。
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from tender.application.llm.probes import PROBE_IMAGE
from tender.application.llm.profiles import (
    ADAPTER_VERSION,
    FEATURE_FIELDS,
    MODEL_FIELDS,
    PROFILES,
    required_kind,
    supported_parameters,
    test_capabilities,
    validate_base_url,
    validate_model,
)
from tender.application.llm.registry import (
    DEFAULT_FAILOVER_LIMIT,
    FEATURE_DESCRIPTIONS,
    FEATURES,
    INACTIVE_FEATURES,
    MAX_BINDINGS,
    binding_rows,
)
from tender.application.shared.errors import (
    Conflict,
    Gone,
    InvalidArgument,
    NotFound,
    PreconditionFailed,
    ServiceError,
    Unprocessable,
)
from tender.core.error_details import error_detail
from tender.core.secrets import (
    SecretKeyUnavailable,
    decrypt_secret,
    encrypt_secret,
    secret_hint,
    secret_key_ready,
)
from tender.domain.shared.errors import ModelInUse, TenderError
from tender.ports.llm.media import EmbeddingInput
from tender.ports.repository.llm.management import LlmRepository, LlmTransaction, RecordConflict


class LlmService:
    def __init__(
        self,
        repository: LlmRepository,
        model_gateway: Callable[..., Any],
        *,
        embedding_gateway: Callable[[Mapping[str, Any]], Any],
        image_gateway: Callable[[Mapping[str, Any]], Any],
        rerank_gateway: Callable[[Mapping[str, Any]], Any],
    ) -> None:
        self.repository = repository
        self.model_gateway = model_gateway
        self.embedding_gateway = embedding_gateway
        self.image_gateway = image_gateway
        self.rerank_gateway = rerank_gateway

    @staticmethod
    def settings() -> dict[str, Any]:
        return {
            "secret_key_ready": secret_key_ready(),
            "adapter_profiles": PROFILES,
            "test_valid_seconds": 604800,
            "max_bindings": MAX_BINDINGS,
            "model_fields": MODEL_FIELDS,
            "feature_fields": FEATURE_FIELDS,
            "default_max_total_requests": 6,
        }

    def list_tests(self, model_id: int | None, limit: int) -> dict[str, Any]:
        self.repository.maintain_tests()
        return {"items": [self._test_view(row) for row in self.repository.tests(model_id, limit)]}

    def get_test(self, test_id: int) -> dict[str, Any]:
        self.repository.maintain_tests()
        row = self.repository.test(test_id)
        if row is None:
            raise NotFound("测试记录不存在")
        return self._test_view(row)

    def test_preview(self, test_id: int) -> tuple[bytes, str | None]:
        test = self.get_test(test_id)
        if test["validity"] != "valid":
            raise Gone("测试图片已失效，需显式重新测试", code="test_preview_expired")
        row = self.repository.test_preview(test_id)
        if row is None or not row["preview_data"]:
            raise NotFound("该测试没有图片预览")
        return bytes(row["preview_data"]), row["preview_mime"]

    def list_providers(self) -> dict[str, Any]:
        return {"items": [self._provider_out(row) for row in self.repository.providers()]}

    def create_provider(self, values: Mapping[str, Any]) -> dict[str, Any]:
        try:
            with self.repository.transaction() as transaction:
                provider_id = transaction.insert_provider(
                    {
                        "name": values["name"],
                        "base_url": values["base_url"],
                        "enabled": values["enabled"],
                        "protocol": values["protocol"],
                        "auth_mode": values["auth_mode"],
                    }
                )
                self._store_key(transaction, provider_id, values.get("api_key"))
        except RecordConflict as exc:
            raise Conflict("供应商名称已存在", code="duplicate_name") from exc
        return self._provider_out(self._provider_row(provider_id))

    def update_provider(self, provider_id: int, values: Mapping[str, Any]) -> dict[str, Any]:
        self._provider_row(provider_id)
        if values.get("clear_api_key") and values.get("api_key") is not None:
            raise Unprocessable("清除密钥与填写新密钥不能同时提交")
        base_url = values.get("base_url")
        if base_url is not None:
            try:
                base_url = validate_base_url(base_url)
            except ValueError as exc:
                raise Unprocessable(str(exc)) from exc
        fields = {
            "auth_mode": values.get("auth_mode"),
            "name": values.get("name"),
            "base_url": base_url,
            "enabled": values.get("enabled"),
        }
        try:
            with self.repository.transaction() as transaction:
                current = transaction.lock_provider(provider_id)
                self._check_revision(current, values.get("revision"))
                assert current is not None
                transaction.update_provider(
                    provider_id,
                    {key: value for key, value in fields.items() if value is not None},
                )
                self._store_key(
                    transaction,
                    provider_id,
                    "" if values.get("clear_api_key") else values.get("api_key"),
                )
                changed = (
                    any(
                        value is not None and current[key] != value
                        for key, value in fields.items()
                        if key in {"base_url", "auth_mode"}
                    )
                    or values.get("api_key") is not None
                    or bool(values.get("clear_api_key"))
                )
                transaction.bump_provider_revision(provider_id, config_changed=changed)
        except RecordConflict as exc:
            raise Conflict("供应商名称已存在", code="duplicate_name") from exc
        self.repository.invalidate_provider_tests(provider_id)
        return self._provider_out(self._provider_row(provider_id))

    def delete_provider(self, provider_id: int) -> dict[str, str]:
        self._provider_row(provider_id)
        with self.repository.transaction() as transaction:
            transaction.lock_provider(provider_id)
            model_ids = transaction.lock_provider_models(provider_id)
            if transaction.index_in_use(model_ids):
                raise ModelInUse("模型仍被有效知识索引使用，请先迁移或移除对应来源")
            if transaction.provider_has_binding(provider_id):
                raise ModelInUse("该供应商下仍有模型绑定到功能，请先解绑")
            transaction.soft_delete_provider_models(provider_id)
            transaction.soft_delete_provider(provider_id)
        return {"status": "deleted"}

    async def test_provider(self, provider_id: int) -> dict[str, Any]:
        row = await asyncio.to_thread(self._provider_row, provider_id)
        test_id = await asyncio.to_thread(self._begin_test, row, "catalog", is_model=False)
        started = time.monotonic()
        status, http_status, error = "ok", None, None
        try:
            if row["protocol"] == "rerank_http":
                raise Unprocessable(
                    "专用重排协议没有目录接口，请手动添加模型",
                    code="catalog_unsupported",
                )
            gateway = self.model_gateway(
                row["base_url"],
                "models-probe",
                api_key=self._api_key_for(row),
                timeout=30,
                protocol=row["protocol"],
            )
            try:
                await gateway.list_models()
                http_status = 200
            finally:
                await gateway.aclose()
        except (TenderError, SecretKeyUnavailable, ValueError, ServiceError) as exc:
            status = "unsupported" if isinstance(exc, ServiceError) else "error"
            http_status = getattr(exc, "http_status", None)
            error = str(exc)
        latency_ms = int((time.monotonic() - started) * 1000)
        await asyncio.to_thread(
            self._record_call,
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
        await asyncio.to_thread(
            self._finish_test,
            row,
            test_id,
            status=status,
            error=error,
            latency_ms=latency_ms,
            is_model=False,
        )
        return {
            "test_id": test_id,
            "status": status,
            "latency_ms": latency_ms,
            "http_status": http_status,
            "error": error,
        }

    async def remote_models(self, provider_id: int) -> dict[str, Any]:
        row = await asyncio.to_thread(self._provider_row, provider_id)
        if row["protocol"] == "rerank_http":
            raise Unprocessable(
                "专用重排协议没有目录接口，请手动添加模型",
                code="catalog_unsupported",
            )
        gateway = self.model_gateway(
            row["base_url"],
            "models-probe",
            api_key=self._api_key_for(row),
            timeout=30,
            protocol=row["protocol"],
        )
        try:
            items = list(dict.fromkeys(await gateway.list_models()))
        finally:
            await gateway.aclose()
        return {"items": items}

    def import_models(self, provider_id: int, values: Mapping[str, Any]) -> dict[str, Any]:
        provider = self._provider_row(provider_id)
        self._validate(provider["protocol"], dict(values))
        model_keys = list(dict.fromkeys(values["model_ids"]))
        for key in model_keys:
            if not key.strip() or len(key) > 200:
                raise Unprocessable("模型 ID 不能为空或超过 200 字符")
        with self.repository.transaction() as transaction:
            current = transaction.lock_provider(provider_id)
            self._check_revision(current, None)
            created = transaction.insert_models_if_absent(
                [
                    {
                        "provider_id": provider_id,
                        "model_id": key,
                        "display_name": key,
                        "kind": values["kind"],
                        "api_mode": values["api_mode"],
                        "capabilities": values["capabilities"],
                        "enabled": False,
                        "timeout_seconds": values.get("timeout_seconds") or 90,
                        "temperature": values.get("temperature"),
                        "max_tokens": values.get("max_tokens"),
                        "extra_retries": values["extra_retries"],
                        "parameters": values["parameters"],
                        "supported_parameters": values.get("supported_parameters"),
                        "embedding_space_id": uuid4() if values["kind"] == "embedding" else None,
                    }
                    for key in model_keys
                ]
            )
        return {
            "imported": created,
            "created": created,
            "skipped": len(model_keys) - created,
        }

    def list_models(self, provider_id: int | None) -> dict[str, Any]:
        rows = self.repository.models(provider_id)
        self._attach_test_summaries(rows)
        return {"items": [self._model_out(row) for row in rows]}

    def create_model(self, values: Mapping[str, Any]) -> dict[str, Any]:
        provider = self._provider_row(values["provider_id"])
        self._validate(provider["protocol"], dict(values))
        try:
            with self.repository.transaction() as transaction:
                current = transaction.lock_provider(values["provider_id"])
                self._check_revision(current, None)
                model_id = transaction.insert_model(
                    {
                        "provider_id": values["provider_id"],
                        "model_id": values["model_id"],
                        "display_name": values.get("display_name") or values["model_id"],
                        "timeout_seconds": values.get("timeout_seconds") or 90,
                        "temperature": values.get("temperature"),
                        "max_tokens": values.get("max_tokens"),
                        "enabled": values["enabled"],
                        "kind": values["kind"],
                        "api_mode": values["api_mode"],
                        "capabilities": values["capabilities"],
                        "extra_retries": values["extra_retries"],
                        "parameters": values["parameters"],
                        "supported_parameters": values.get("supported_parameters"),
                        "embedding_space_id": uuid4() if values["kind"] == "embedding" else None,
                    }
                )
        except RecordConflict as exc:
            raise Conflict("该供应商下已存在同名模型", code="duplicate_name") from exc
        return self._model_out(self._model_row(model_id))

    def update_model(self, model_id: int, values: Mapping[str, Any]) -> dict[str, Any]:
        row = self._model_row(model_id)
        fields = {key: value for key, value in values.items() if key != "revision"}
        if any(
            value is None and key not in {"temperature", "max_tokens", "supported_parameters"}
            for key, value in fields.items()
        ):
            raise Unprocessable("只有温度、输出上限和模型参数支持范围允许清空")
        with self.repository.transaction() as transaction:
            current = transaction.lock_model(model_id)
            self._check_revision(current, values.get("revision"))
            assert current is not None
            if current["temperature"] is not None:
                current["temperature"] = float(current["temperature"])
            row.update(current)
            self._validate(row["protocol"], row | fields)
            if (
                fields.get("kind", row["kind"]) != row["kind"]
                or fields.get("capabilities", row["capabilities"]) != row["capabilities"]
            ):
                if any(
                    required_kind(key) != fields.get("kind", row["kind"])
                    or (
                        required_kind(key) == "language"
                        and "json_output" not in fields.get("capabilities", row["capabilities"])
                    )
                    for key in transaction.feature_keys_for_model(model_id)
                ):
                    raise Conflict(
                        "模型种类或 JSON 能力与现有功能绑定不符，请先解绑",
                        code="model_in_use",
                    )
                self._check_index_use(transaction, [model_id])
            transaction.update_model(model_id, fields)
            before = dict(row)
            after = row | fields
            for config in (before, after):
                config["supported_parameters"] = sorted(
                    supported_parameters(row["protocol"], config)
                )
                config["capabilities"] = sorted(config["capabilities"])
            changed = any(
                before[key] != after[key]
                for key in fields
                if key not in {"display_name", "enabled", "extra_retries"}
            )
            if changed and (row["kind"] == "embedding" or fields.get("kind") == "embedding"):
                transaction.update_model(
                    model_id,
                    {
                        "embedding_space_id": uuid4()
                        if fields.get("kind", row["kind"]) == "embedding"
                        else None
                    },
                )
            if changed:
                transaction.invalidate_model_tests(model_id)
            transaction.bump_model_revision(model_id, config_changed=changed)
        return self._model_out(self._model_row(model_id))

    def delete_model(self, model_id: int) -> dict[str, str]:
        self._model_row(model_id)
        with self.repository.transaction() as transaction:
            transaction.lock_model(model_id)
            self._check_index_use(transaction, [model_id])
            if transaction.model_has_binding(model_id):
                raise ModelInUse("该模型仍绑定在功能上，请先解绑")
            transaction.soft_delete_model(model_id)
        return {"status": "deleted"}

    def begin_model_test(
        self, model_id: int, capability: str | None
    ) -> tuple[dict[str, Any], int, str]:
        row = self._model_row(model_id)
        allowed = test_capabilities(row)
        selected = capability or allowed[-1]
        if selected not in allowed:
            raise Unprocessable("所选测试能力未被模型声明或适配", code="capability_unsupported")
        self._validate(row["protocol"], row)
        return row, self._begin_test(row, selected, is_model=True), selected

    async def test_model(self, model_id: int, capability: str | None = None) -> dict[str, Any]:
        row, test_id, selected = await asyncio.to_thread(
            self.begin_model_test, model_id, capability,
        )
        return await self.run_model_test(row, test_id, selected)

    async def run_model_test(
        self, row: Mapping[str, Any], test_id: int, capability: str
    ) -> dict[str, Any]:
        started = time.monotonic()
        status, http_status, error = "ok", None, None
        prompt_tokens = completion_tokens = vector_count = document_count = dimensions = (
            image_count
        ) = None
        preview = None
        try:
            async with asyncio.timeout(float(row["timeout_seconds"])):
                if row["kind"] == "embedding":
                    self._api_key_for(row)
                    gateway = self.embedding_gateway(row)
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
                    gateway = self.rerank_gateway(row | {"api_key": self._api_key_for(row)})
                    try:
                        await gateway.rerank("招标资格", ["投标人资质要求", "天气预报"], 2)
                        document_count = 2
                    finally:
                        await gateway.aclose()
                elif row["kind"] == "image_generation":
                    gateway = self.image_gateway(row | {"api_key": self._api_key_for(row)})
                    try:
                        preview = await gateway.generate(
                            "在纯白背景画一个简单的蓝色圆形，只生成一张小图。"
                        )
                        image_count = 1
                    finally:
                        await gateway.aclose()
                else:
                    gateway = self.model_gateway(
                        row["base_url"],
                        row["model_id"],
                        api_key=self._api_key_for(row),
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
                                "简短说明图片中有哪些颜色。",
                                images=(PROBE_IMAGE,),
                                json_mode=False,
                            )
                        elif "json_output" in row["capabilities"]:
                            completion = await gateway.complete('只返回 JSON：{"ok": true}')
                            if json.loads(completion.content) != {"ok": True}:
                                raise ValueError("测试响应未满足要求的 JSON 结构")
                        else:
                            completion = await gateway.complete(
                                "请简短回复连接成功。", json_mode=False
                            )
                        prompt_tokens = completion.prompt_tokens
                        completion_tokens = completion.completion_tokens
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
        await asyncio.to_thread(
            self._save_model_test, row, test_id, result, preview, prompt_tokens, completion_tokens,
        )
        return result

    def _save_model_test(
        self, row: Mapping[str, Any], test_id: int, result: dict[str, Any],
        preview: Any, prompt_tokens: int | None, completion_tokens: int | None,
    ) -> None:
        # 同一段同步持久化在线程中完成，避免在异步响应收尾时阻塞其它请求。
        with self.repository.transaction() as transaction:
            transaction.store_test_result(
                test_id,
                result=result,
                preview_data=preview.data if preview else None,
                preview_mime=preview.mime_type if preview else None,
            )
        self._record_call(
            provider_id=row["provider_id"],
            model_id=row["id"],
            feature_key=None,
            purpose="test",
            status=result["status"],
            http_status=result["http_status"],
            latency_ms=result["latency_ms"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            error=result["error"],
            snapshot=row,
            vector_count=result["vector_count"],
            document_count=result["document_count"],
            image_count=result["image_count"],
            test_id=test_id,
        )
        self._finish_test(
            row,
            test_id,
            status=result["status"],
            error=result["error"],
            latency_ms=result["latency_ms"],
            is_model=True,
        )

    def list_features(self) -> dict[str, Any]:
        rows, limits = self.repository.feature_rows()
        items = []
        for key, name in FEATURES:
            configured = limits.get(key)
            bindings = [
                {
                    "priority": row["priority"],
                    "model_row_id": row["model_row_id"],
                    "model_id": row["model_id"],
                    "display_name": row["display_name"],
                    "enabled": row["enabled"] and row["provider_enabled"],
                    "kind": row["kind"],
                    "extra_retries": row["extra_retries"],
                    "provider_id": row["provider_id"],
                    "provider_name": row["provider_name"],
                }
                for row in rows
                if row["feature_key"] == key
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

    def feature_item(self, feature_key: str) -> dict[str, Any]:
        items = self.list_features()["items"]
        return next(item for item in items if item["key"] == feature_key)

    def update_feature(self, feature_key: str, values: Mapping[str, Any]) -> dict[str, Any]:
        self._require_feature(feature_key)
        if feature_key in INACTIVE_FEATURES:
            raise Conflict(
                "该功能尚未接入业务调用，无需设置路由预算",
                code="feature_unavailable",
            )
        with self.repository.transaction() as transaction:
            revision = transaction.lock_feature(feature_key)
            if revision is None:
                raise NotFound("功能不存在")
            self._check_feature_revision(revision, int(values["revision"]))
            transaction.update_feature(
                feature_key,
                {
                    "failover_limit": values["failover_limit"],
                    "max_total_requests": values["max_total_requests"],
                    "deadline_seconds": values["deadline_seconds"],
                },
            )
            transaction.bump_feature_revision(feature_key)
        return self.feature_item(feature_key)

    def replace_bindings(self, feature_key: str, values: Mapping[str, Any]) -> dict[str, Any]:
        self._require_feature(feature_key)
        model_ids = list(values["model_ids"])
        if feature_key in INACTIVE_FEATURES and model_ids:
            raise Conflict(
                "该功能尚未接入业务调用，请在模型列表测试",
                code="feature_unavailable",
            )
        if feature_key in {"embedding", "rerank"} and len(model_ids) > 1:
            raise InvalidArgument("当前向量与重排功能只支持绑定一个模型")
        rows = binding_rows(model_ids)
        with self.repository.transaction() as transaction:
            found = transaction.lock_models_for_binding(
                model_ids,
                kind=required_kind(feature_key),
                require_json=True,
            )
            revision = transaction.lock_feature(feature_key)
            if revision is None:
                raise NotFound("功能不存在")
            self._check_feature_revision(revision, int(values["revision"]))
            missing = sorted({model_id for model_id, _ in rows} - found)
            if missing:
                raise InvalidArgument(f"模型不存在或种类与功能不符：{missing}")
            transaction.replace_feature_models(feature_key, rows)
            limits = {
                key: values[key]
                for key in ("failover_limit", "max_total_requests", "deadline_seconds")
                if values.get(key) is not None
            }
            if limits:
                transaction.update_feature(feature_key, limits)
            transaction.bump_feature_revision(feature_key)
        return self.feature_item(feature_key)

    def list_calls(
        self,
        *,
        feature_key: str | None,
        model_id: int | None,
        status: str | None,
        invocation_id: UUID | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        total, rows = self.repository.calls(
            feature_key=feature_key,
            model_id=model_id,
            status=status,
            invocation_id=invocation_id,
            limit=limit,
            offset=offset,
        )
        return {
            "total": total,
            "items": [row | {"error_message": error_detail(row["error_message"])} for row in rows],
        }

    def _provider_row(self, provider_id: int) -> dict[str, Any]:
        row = self.repository.provider(provider_id)
        if row is None:
            raise NotFound("供应商不存在")
        return row

    def _model_row(self, model_id: int) -> dict[str, Any]:
        row = self.repository.model(model_id)
        if row is None:
            raise NotFound("模型不存在")
        if row["temperature"] is not None:
            row["temperature"] = float(row["temperature"])
        self._attach_test_summaries([row])
        return row

    def _attach_test_summaries(self, models: list[dict[str, Any]]) -> None:
        if not models:
            return
        self.repository.maintain_tests()
        tests = self.repository.latest_tests([model["id"] for model in models])
        lookup = {model["id"]: model for model in models}
        for test in tests:
            view = self._test_view(test)
            lookup[test["model_id"]].setdefault("capability_tests", {}).setdefault(
                view["capability"], view
            )

    def _begin_test(self, row: Mapping[str, Any], capability: str, *, is_model: bool) -> int:
        with self.repository.transaction() as transaction:
            return transaction.begin_test(row, capability, is_model=is_model)

    def _finish_test(
        self,
        row: Mapping[str, Any],
        test_id: int,
        *,
        status: str,
        error: str | None,
        latency_ms: int,
        is_model: bool,
    ) -> None:
        with self.repository.transaction() as transaction:
            transaction.finish_test(
                row,
                test_id,
                status=status,
                error=error,
                latency_ms=latency_ms,
                is_model=is_model,
            )

    def _record_call(self, **values: Any) -> None:
        with self.repository.transaction() as transaction:
            transaction.record_call(
                provider_id=values["provider_id"],
                model_id=values["model_id"],
                feature_key=values["feature_key"],
                purpose=values["purpose"],
                status=values["status"],
                http_status=values["http_status"],
                latency_ms=values["latency_ms"],
                prompt_tokens=values["prompt_tokens"],
                completion_tokens=values["completion_tokens"],
                error_message=error_detail(values["error"]),
                snapshot=values["snapshot"],
                vector_count=values.get("vector_count"),
                document_count=values.get("document_count"),
                image_count=values.get("image_count"),
                test_id=values.get("test_id"),
            )

    def _store_key(
        self,
        transaction: LlmTransaction,
        provider_id: int,
        api_key: str | None,
    ) -> None:
        if api_key is None:
            return
        if api_key == "":
            transaction.store_provider_key(provider_id, None, None)
        else:
            transaction.store_provider_key(
                provider_id, encrypt_secret(api_key), secret_hint(api_key)
            )

    @staticmethod
    def _api_key_for(row: Mapping[str, Any]) -> str | None:
        if row.get("auth_mode") == "none":
            return None
        if not row.get("api_key_ciphertext"):
            raise SecretKeyUnavailable("供应商未配置 API Key，请填写密钥或选择匿名服务")
        return decrypt_secret(str(row["api_key_ciphertext"]))

    @staticmethod
    def _validate(protocol: str, model: dict[str, Any]) -> None:
        try:
            validate_model(protocol, model)
        except ValueError as exc:
            raise Unprocessable(str(exc), code="capability_unsupported") from exc

    @staticmethod
    def _require_feature(feature_key: str) -> None:
        if feature_key not in {key for key, _ in FEATURES}:
            raise NotFound("功能不存在")

    @staticmethod
    def _check_revision(row: Mapping[str, Any] | None, revision: int | None) -> None:
        if row is None:
            raise NotFound("配置已删除")
        if revision is not None and row["revision"] != revision:
            raise PreconditionFailed(
                "配置已被修改，请刷新比较后再保存；当前草稿未丢弃",
                code="revision_conflict",
            )

    @staticmethod
    def _check_feature_revision(current: int, requested: int) -> None:
        if current != requested:
            raise PreconditionFailed(
                "配置已被修改，草稿已保留，请刷新后比较最新版本",
                code="revision_conflict",
            )

    def _check_index_use(self, transaction: LlmTransaction, model_ids: list[int]) -> None:
        if transaction.index_in_use(model_ids):
            raise ModelInUse("模型仍被有效知识索引使用，请先迁移或移除对应来源")

    @staticmethod
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

    def _provider_out(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "base_url": row["base_url"],
            "protocol": row["protocol"],
            "auth_mode": row["auth_mode"],
            "revision": row["revision"],
            "api_key_updated_at": row["api_key_updated_at"],
            "test_validity": self._validity(row),
            "api_key_hint": row["api_key_hint"],
            "has_api_key": row["api_key_ciphertext"] is not None,
            "enabled": row["enabled"],
            "last_test_status": row["last_test_status"],
            "last_test_at": row["last_test_at"],
            "last_test_error": error_detail(row["last_test_error"]),
            "rate_limit_remaining_seconds": round(
                float(row.get("rate_limit_remaining_seconds") or 0), 1
            ),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _model_out(self, row: Mapping[str, Any]) -> dict[str, Any]:
        checks = row.get("capability_tests", {})
        states = [
            checks.get(capability, {}).get("validity", "untested")
            for capability in test_capabilities(dict(row))
        ]
        validity = next(
            (
                state
                for state in (
                    "running",
                    "unknown",
                    "config_changed",
                    "failed",
                    "expired",
                    "untested",
                )
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
            "embedding_input_type": (
                "multimodal" if "image_input" in row["capabilities"] else "text"
            )
            if row["kind"] == "embedding"
            else None,
            "embedding_space_id": str(row["embedding_space_id"])
            if row["embedding_space_id"]
            else None,
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
            "last_test_error": error_detail(row["last_test_error"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _test_view(row: Mapping[str, Any]) -> dict[str, Any]:
        item = {
            key: value
            for key, value in row.items()
            if key
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
                and row["model_revision"]
                != row.get("current_model_revision", row["model_revision"])
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
            "error_message": error_detail(row["error_message"]),
            "validity": validity,
            "expires_at": expiry,
            "capability": "text" if row["capability"] == "language" else row["capability"],
        }
