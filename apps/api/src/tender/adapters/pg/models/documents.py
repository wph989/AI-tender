"""解析管线表：document / document_version / parse_run / page / element / table_cell。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, BigInteger, Boolean, DateTime, Integer, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tender.adapters.pg.models.base import Base


class Document(Base):
    """逻辑实体「一份标书」。"""

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    project_no: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company_id: Mapped[int] = mapped_column(BigInteger)


class DocumentVersion(Base):
    """文档版本：溯源的根，由内容哈希唯一定位。"""

    __tablename__ = "document_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger)
    version_no: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    mime: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    original_key: Mapped[str] = mapped_column(Text)
    pdf_key: Mapped[str] = mapped_column(Text)
    pdf_sha256: Mapped[str] = mapped_column(CHAR(64))
    is_converted: Mapped[bool] = mapped_column(Boolean)
    converter: Mapped[str | None] = mapped_column(Text)
    converter_version: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    company_id: Mapped[int] = mapped_column(BigInteger)


class ParseRun(Base):
    """一次 MinerU 解析运行，记录全部环境信息以支持重放。"""

    __tablename__ = "parse_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version_id: Mapped[int] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(Text)
    provider_version: Mapped[str] = mapped_column(Text)
    tier: Mapped[str] = mapped_column(Text)
    backend: Mapped[str | None] = mapped_column(Text)
    schema_version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)
    raw_middle_key: Mapped[str | None] = mapped_column(Text)
    raw_content_key: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_job_id: Mapped[str | None] = mapped_column(Text)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Page(Base):
    """页面：坐标基座的一页。"""

    __tablename__ = "page"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version_id: Mapped[int] = mapped_column(BigInteger)
    page_no: Mapped[int] = mapped_column(Integer)
    width_pt: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    height_pt: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    rotation: Mapped[int] = mapped_column(SmallInteger)
    image_key: Mapped[str | None] = mapped_column(Text)
    image_px_w: Mapped[int | None] = mapped_column(Integer)
    image_px_h: Mapped[int | None] = mapped_column(Integer)
    text_layer: Mapped[bool] = mapped_column(Boolean)


class Element(Base):
    """元素（块）：锚点的物理落点。"""

    __tablename__ = "element"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    version_id: Mapped[int] = mapped_column(BigInteger)
    run_id: Mapped[int] = mapped_column(BigInteger)
    page_no: Mapped[int] = mapped_column(Integer)
    order_no: Mapped[int] = mapped_column(Integer)
    anchor: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    level: Mapped[int | None] = mapped_column(Integer)
    parent_id: Mapped[int | None] = mapped_column(BigInteger)
    bbox_x0: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    bbox_y0: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    bbox_x1: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    bbox_y1: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    text: Mapped[str | None] = mapped_column(Text)
    html: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    continues_prev: Mapped[bool] = mapped_column(Boolean)
    mineru_locator: Mapped[str | None] = mapped_column(Text)


class TableCell(Base):
    """表格单元格（二期，一期只到块级）。"""

    __tablename__ = "table_cell"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    element_id: Mapped[int] = mapped_column(BigInteger)
    row_no: Mapped[int] = mapped_column(Integer)
    col_no: Mapped[int] = mapped_column(Integer)
    rowspan: Mapped[int] = mapped_column(Integer)
    colspan: Mapped[int] = mapped_column(Integer)
    bbox_x0: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    bbox_y0: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    bbox_x1: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    bbox_y1: Mapped[Decimal | None] = mapped_column(Numeric(7, 6))
    text: Mapped[str | None] = mapped_column(Text)
