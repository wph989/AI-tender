"""任务流水线：job。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tender.adapters.pg.models.base import Base


class Job(Base):
    """从上传到解析的任务；id 是调度器生成的 TEXT 键，不是自增序列。"""

    __tablename__ = "job"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger)
    project_id: Mapped[int] = mapped_column(BigInteger)
    project_file_id: Mapped[int] = mapped_column(BigInteger)
    version_id: Mapped[int | None] = mapped_column(BigInteger)
    run_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(Text)
    progress: Mapped[dict[str, Any]] = mapped_column(JSONB)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config_snapshot_id: Mapped[int | None] = mapped_column(BigInteger)
