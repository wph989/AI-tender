"""抽取与复核：field_instance、extraction、evidence、review_*、gold_item、extraction_conflict。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tender.adapters.pg.models.base import Base


class FieldInstance(Base):
    """字段实例：跨尝试不变的稳定身份。"""

    __tablename__ = "field_instance"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version_id: Mapped[int] = mapped_column(BigInteger)
    field_key: Mapped[str] = mapped_column(Text)
    lot_id: Mapped[int | None] = mapped_column(BigInteger)
    current_extraction_id: Mapped[int | None] = mapped_column(BigInteger)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Extraction(Base):
    """抽取尝试：一次抽取 / 重跑 / 人工修正 = 一行，append-only 永不覆盖。"""

    __tablename__ = "extraction"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    instance_id: Mapped[int] = mapped_column(BigInteger)
    version_id: Mapped[int] = mapped_column(BigInteger)
    run_id: Mapped[int | None] = mapped_column(BigInteger)
    attempt_no: Mapped[int] = mapped_column(Integer)
    machine_attempt_no: Mapped[int | None] = mapped_column(Integer)
    trigger: Mapped[str] = mapped_column(Text)
    hint: Mapped[str | None] = mapped_column(Text)
    field_key: Mapped[str] = mapped_column(Text)
    group_key: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[Any] = mapped_column(JSONB, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    status: Mapped[str] = mapped_column(Text)
    strategy: Mapped[str] = mapped_column(Text)
    evidence_count: Mapped[int] = mapped_column(Integer)
    supersedes_id: Mapped[int | None] = mapped_column(BigInteger)
    is_current: Mapped[bool] = mapped_column(Boolean)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lot_id: Mapped[int | None] = mapped_column(BigInteger)
    field_def_version: Mapped[int] = mapped_column(Integer)
    llm_model_id: Mapped[int | None] = mapped_column(BigInteger)
    llm_model_name: Mapped[str | None] = mapped_column(Text)


class Evidence(Base):
    """证据（核心表）：锚点与原文片段。"""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    extraction_id: Mapped[int] = mapped_column(BigInteger)
    version_id: Mapped[int] = mapped_column(BigInteger)
    seq: Mapped[int] = mapped_column(Integer)
    anchor: Mapped[str] = mapped_column(Text)
    element_id: Mapped[int | None] = mapped_column(BigInteger)
    page_no: Mapped[int] = mapped_column(Integer)
    bbox_x0: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    bbox_y0: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    bbox_x1: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    bbox_y1: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    char_start: Mapped[int | None] = mapped_column(Integer)
    char_end: Mapped[int | None] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    quote_source: Mapped[str] = mapped_column(Text)
    match_type: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewAction(Base):
    """复核动作：事实标准的生产记录，只增不改。"""

    __tablename__ = "review_action"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    instance_id: Mapped[int] = mapped_column(BigInteger)
    attempt_id: Mapped[int] = mapped_column(BigInteger)
    result_attempt_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(Text)
    review_mode: Mapped[str] = mapped_column(Text)
    old_value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSONB, nullable=True)
    evidence: Mapped[Any] = mapped_column(JSONB, nullable=True)
    actor: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewTask(Base):
    """复核队列（待办）：只记「要做什么」，判断结果记在 review_action。"""

    __tablename__ = "review_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    extraction_id: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    assignee: Mapped[str | None] = mapped_column(Text)
    resolved_action_id: Mapped[int | None] = mapped_column(BigInteger)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GoldItem(Base):
    """回归集条目：与生产数据物理隔离。"""

    __tablename__ = "gold_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_instance_id: Mapped[int | None] = mapped_column(BigInteger)
    version_id: Mapped[int] = mapped_column(BigInteger)
    field_key: Mapped[str] = mapped_column(Text)
    expected: Mapped[Any] = mapped_column(JSONB, nullable=False)
    expected_anchors: Mapped[list[str]] = mapped_column(ARRAY(Text))
    origin: Mapped[str] = mapped_column(Text)
    param_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExtractionConflict(Base):
    """跨文件/多值冲突组。"""

    __tablename__ = "extraction_conflict"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger)
    field_key: Mapped[str] = mapped_column(Text)
    lot_id: Mapped[int | None] = mapped_column(BigInteger)
    candidate_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    resolved_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
