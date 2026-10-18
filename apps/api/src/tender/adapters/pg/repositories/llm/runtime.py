"""模型候选、调用账本和测试维护的数据库实现。"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tender.adapters.pg.models import LlmCallLog, LlmFeature, LlmFeatureModel, LlmModel, LlmProvider
from tender.adapters.pg.repositories.llm.model_test import maintain_model_tests


class ModelRuntimeRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def candidates(self, feature_key: str) -> list[Mapping[str, Any]]:
        with self.engine.connect() as connection:
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
        return list(rows)

    def record_call(self, values: Mapping[str, Any]) -> None:
        data = dict(values)
        # 首次先插入 running；返回后只补写同一请求，不新增第二条调用账。
        insert_call = pg_insert(LlmCallLog).values(**data)
        with self.engine.begin() as c:
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

    def policy(self, feature_key: str) -> Mapping[str, Any] | None:
        with self.engine.connect() as connection:
            return (
                connection.execute(select(LlmFeature).where(LlmFeature.key == feature_key))
                .mappings()
                .first()
            )

    def maintain_tests(self) -> None:
        maintain_model_tests(self.engine)
