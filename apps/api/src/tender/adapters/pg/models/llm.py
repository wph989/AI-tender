"""模型管理：llm_provider、llm_model、llm_feature*、llm_call_log、llm_test。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Double,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tender.adapters.pg.models.base import Base


class LlmProvider(Base):
    __tablename__ = "llm_provider"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(Text)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    api_key_hint: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean)
    last_test_status: Mapped[str | None] = mapped_column(Text)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_error: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    protocol: Mapped[str] = mapped_column(Text)
    auth_mode: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)
    config_revision: Mapped[int] = mapped_column(Integer)
    credential_revision: Mapped[int] = mapped_column(Integer)
    api_key_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_config_revision: Mapped[int | None] = mapped_column(Integer)
    last_test_id: Mapped[int | None] = mapped_column(BigInteger)
    rate_limited_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LlmModel(Base):
    __tablename__ = "llm_model"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider_id: Mapped[int] = mapped_column(BigInteger)
    model_id: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    timeout_seconds: Mapped[Decimal] = mapped_column(Numeric(6, 1))
    temperature: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    max_tokens: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean)
    last_test_status: Mapped[str | None] = mapped_column(Text)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_error: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(Text)
    api_mode: Mapped[str] = mapped_column(Text)
    capabilities: Mapped[list[str]] = mapped_column(JSONB)
    extra_retries: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    config_revision: Mapped[int] = mapped_column(Integer)
    last_test_config_revision: Mapped[int | None] = mapped_column(Integer)
    last_test_provider_revision: Mapped[int | None] = mapped_column(Integer)
    last_test_id: Mapped[int | None] = mapped_column(BigInteger)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB)
    supported_parameters: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    embedding_space_id: Mapped[UUID | None] = mapped_column(Uuid)


class LlmFeature(Base):
    __tablename__ = "llm_feature"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    failover_limit: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_total_requests: Mapped[int] = mapped_column(Integer)
    deadline_seconds: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)


class LlmFeatureModel(Base):
    __tablename__ = "llm_feature_model"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    feature_key: Mapped[str] = mapped_column(Text)
    model_id: Mapped[int] = mapped_column(BigInteger)
    priority: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LlmCallLog(Base):
    __tablename__ = "llm_call_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider_id: Mapped[int | None] = mapped_column(BigInteger)
    model_id: Mapped[int | None] = mapped_column(BigInteger)
    feature_key: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    invocation_id: Mapped[UUID | None] = mapped_column(Uuid)
    candidate_ordinal: Mapped[int | None] = mapped_column(Integer)
    retry_ordinal: Mapped[int | None] = mapped_column(Integer)
    request_ordinal: Mapped[int | None] = mapped_column(Integer)
    model_name_snapshot: Mapped[str | None] = mapped_column(Text)
    provider_name_snapshot: Mapped[str | None] = mapped_column(Text)
    model_key_snapshot: Mapped[str | None] = mapped_column(Text)
    vector_count: Mapped[int | None] = mapped_column(Integer)
    document_count: Mapped[int | None] = mapped_column(Integer)
    image_count: Mapped[int | None] = mapped_column(Integer)


class LlmTest(Base):
    __tablename__ = "llm_test"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider_id: Mapped[int] = mapped_column(BigInteger)
    model_id: Mapped[int | None] = mapped_column(BigInteger)
    capability: Mapped[str] = mapped_column(Text)
    provider_revision: Mapped[int] = mapped_column(Integer)
    model_revision: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    call_log_id: Mapped[int | None] = mapped_column(BigInteger)
    timeout_seconds: Mapped[float] = mapped_column(Double)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    preview_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    preview_mime: Mapped[str | None] = mapped_column(Text)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
