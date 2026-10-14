"""知识库：knowledge_collection / knowledge_source / knowledge_index / knowledge_chunk /
knowledge_relation / knowledge_answer 与 project_knowledge_collection 关联表。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Double, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tender.adapters.pg.models.base import Base


class KnowledgeCollection(Base):
    __tablename__ = "knowledge_collection"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(Text)
    purpose: Mapped[str] = mapped_column(Text)
    upload_project_id: Mapped[int] = mapped_column(BigInteger)
    is_project: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectKnowledgeCollection(Base):
    """项目 ↔ 知识库关联（联合主键）。"""

    __tablename__ = "project_knowledge_collection"

    project_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    collection_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_source"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    collection_id: Mapped[int] = mapped_column(BigInteger)
    project_file_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class KnowledgeIndex(Base):
    """索引任务：一个知识源的一次向量化。"""

    __tablename__ = "knowledge_index"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(BigInteger)
    version_id: Mapped[int] = mapped_column(BigInteger)
    run_id: Mapped[int] = mapped_column(BigInteger)
    embedding_model_id: Mapped[int | None] = mapped_column(BigInteger)
    embedding_signature: Mapped[str | None] = mapped_column(Text)
    dimension: Mapped[int | None] = mapped_column(Integer)
    chunk_version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunk"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    index_id: Mapped[int] = mapped_column(BigInteger)
    element_id: Mapped[int] = mapped_column(BigInteger)
    ordinal: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    chapter: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Double))


class KnowledgeRelation(Base):
    __tablename__ = "knowledge_relation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    report_id: Mapped[int] = mapped_column(BigInteger)
    module_id: Mapped[int] = mapped_column(BigInteger)
    subject: Mapped[str] = mapped_column(Text)
    predicate: Mapped[str] = mapped_column(Text)
    object: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text)
    condition: Mapped[str] = mapped_column(Text)
    citations: Mapped[list[Any]] = mapped_column(JSONB)
    verified: Mapped[bool] = mapped_column(Boolean)


class KnowledgeAnswer(Base):
    __tablename__ = "knowledge_answer"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(BigInteger)
    project_id: Mapped[int | None] = mapped_column(BigInteger)
    collection_ids: Mapped[list[int]] = mapped_column(JSONB)
    question: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list[Any]] = mapped_column(JSONB)
    relations: Mapped[list[Any]] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
