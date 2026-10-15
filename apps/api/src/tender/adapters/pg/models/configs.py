"""配置中心：config_* / job_config_snapshot。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tender.adapters.pg.models.base import Base


class ConfigItem(Base):
    """配置项定义（元数据：类型、默认值、是否受门禁约束）。"""

    __tablename__ = "config_item"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    layer: Mapped[str] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(Text)
    # 值域随 value_type 变化（int/bool/string/json），不是固定结构
    default_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    description: Mapped[str] = mapped_column(Text)
    requires_gate: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConfigRelease(Base):
    """配置版本：一次提交 = 一个 release，values 为全量值（非 diff）。"""

    __tablename__ = "config_release"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger)
    version_no: Mapped[int] = mapped_column(Integer)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text)
    based_on: Mapped[int | None] = mapped_column(BigInteger)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JobConfigSnapshot(Base):
    """任务级配置快照（不可变）。"""

    __tablename__ = "job_config_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    release_id: Mapped[int] = mapped_column(BigInteger)
    resolved: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConfigAudit(Base):
    """变更审计。"""

    __tablename__ = "config_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    release_id: Mapped[int] = mapped_column(BigInteger)
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConfigAck(Base):
    """变更影响清单的逐条确认记录。"""

    __tablename__ = "config_ack"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    release_id: Mapped[int] = mapped_column(BigInteger)
    item_kind: Mapped[str] = mapped_column(Text)
    item_ref: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
