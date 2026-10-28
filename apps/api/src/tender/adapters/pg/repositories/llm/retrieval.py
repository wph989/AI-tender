"""检索模型配置查询；模型与供应商字段变化在 LLM 仓储内维护。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, select

from tender.adapters.pg.models import LlmFeatureModel, LlmModel, LlmProvider
from tender.domain.shared.digest import fingerprint


class RetrievalModelQueries:
    engine: Engine

    def embedding_config(self) -> dict[str, Any] | None:
        statement = (
            select(
                LlmModel.id,
                LlmModel.model_id,
                LlmModel.timeout_seconds,
                LlmProvider.base_url,
                LlmModel.config_revision,
                LlmModel.parameters,
                LlmModel.capabilities,
                LlmModel.embedding_space_id,
                LlmProvider.protocol,
                LlmModel.api_mode,
                LlmProvider.auth_mode,
                LlmProvider.api_key_ciphertext,
            )
            .select_from(LlmFeatureModel)
            .join(LlmModel, LlmModel.id == LlmFeatureModel.model_id)
            .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
            .where(
                LlmFeatureModel.feature_key == "embedding",
                LlmModel.kind == "embedding",
                LlmModel.enabled,
                LlmProvider.enabled,
                LlmModel.deleted_at.is_(None),
                LlmProvider.deleted_at.is_(None),
            )
            .order_by(LlmFeatureModel.priority)
            .limit(1)
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        if row is None:
            return None
        return dict(row) | {
            # 同一注册行改模型名/服务地址也必须重建，不仅以数据库 id 判断嵌入空间。
            "signature": fingerprint(
                [
                    row["id"],
                    row["model_id"],
                    row["base_url"],
                    row["protocol"],
                    row["api_mode"],
                    row["embedding_space_id"],
                    row["parameters"],
                ]
            )
        }

    def rerank_config(self) -> dict[str, Any] | None:
        statement = (
            select(
                LlmModel,
                LlmProvider.base_url,
                LlmProvider.auth_mode,
                LlmProvider.api_key_ciphertext,
            )
            .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
            .join(LlmFeatureModel, LlmFeatureModel.model_id == LlmModel.id)
            .where(
                LlmFeatureModel.feature_key == "rerank",
                LlmModel.kind == "rerank",
                LlmModel.enabled,
                LlmProvider.enabled,
                LlmModel.deleted_at.is_(None),
                LlmProvider.deleted_at.is_(None),
            )
            .order_by(LlmFeatureModel.priority)
            .limit(1)
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return dict(row) if row is not None else None
