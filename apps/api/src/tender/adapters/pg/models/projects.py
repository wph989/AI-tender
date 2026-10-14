"""项目与标段：project / project_file / lot。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CHAR, BigInteger, Boolean, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tender.adapters.pg.models.base import Base


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(Text)
    project_no: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(Text)
    analysis_category: Mapped[str | None] = mapped_column(Text)
    analysis_topics: Mapped[list[Any]] = mapped_column(JSONB)


class ProjectFile(Base):
    """项目内文件：可增删改；软删除 + 替代关系。"""

    __tablename__ = "project_file"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger)
    version_id: Mapped[int | None] = mapped_column(BigInteger)
    role: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    is_parseable: Mapped[bool] = mapped_column(Boolean)
    replaces_id: Mapped[int | None] = mapped_column(BigInteger)
    sort_no: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    original_key: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(CHAR(64))
    mime: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)


class Lot(Base):
    """标段。"""

    __tablename__ = "lot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger)
    code: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    sort_no: Mapped[int] = mapped_column(Integer)
    analysis_category: Mapped[str | None] = mapped_column(Text)
    analysis_topics: Mapped[list[Any] | None] = mapped_column(JSONB)
