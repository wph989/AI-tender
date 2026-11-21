"""智能分析：analysis_report / analysis_module / analysis_data_snapshot /
agent_module_run / agent_run_event。

注意 agent_module_run 的 id 是 SERIAL（INTEGER），不是其余表的 BIGSERIAL；
thread_id 对应 agent_runtime schema 里的 LangGraph checkpoint 线程。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tender.adapters.pg.models.base import Base


class AnalysisReport(Base):
    __tablename__ = "analysis_report"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger)
    company_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    allow_partial: Mapped[bool] = mapped_column(Boolean)
    category: Mapped[str] = mapped_column(Text)
    topics: Mapped[list[Any]] = mapped_column(JSONB)
    lot_settings: Mapped[list[Any]] = mapped_column(JSONB)
    source_snapshot: Mapped[list[Any]] = mapped_column(JSONB)
    coverage: Mapped[dict[str, Any]] = mapped_column(JSONB)
    skill_version: Mapped[str] = mapped_column(Text)
    skill_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runtime_version: Mapped[str] = mapped_column(Text)
    runtime_settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reference_snapshot: Mapped[list[Any]] = mapped_column(JSONB)
    summary: Mapped[list[Any]] = mapped_column(JSONB)
    derived_lot_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    snapshot_pending: Mapped[bool] = mapped_column(Boolean)


class AnalysisModule(Base):
    __tablename__ = "analysis_module"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    report_id: Mapped[int] = mapped_column(BigInteger)
    module_key: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    items: Mapped[list[Any]] = mapped_column(JSONB)
    trace: Mapped[list[Any]] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    business_data: Mapped[dict[str, Any]] = mapped_column(JSONB)


class AgentModuleRun(Base):
    """模块运行账：一次 DeepAgents 模块执行的配额、租约与计数。"""

    __tablename__ = "agent_module_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    module_id: Mapped[int] = mapped_column(BigInteger)
    company_id: Mapped[int] = mapped_column(BigInteger)
    attempt: Mapped[int] = mapped_column(Integer)
    thread_id: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    owner: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_calls: Mapped[int] = mapped_column(Integer)
    tool_calls: Mapped[int] = mapped_column(Integer)
    successful_model_calls: Mapped[int | None] = mapped_column(Integer)
    successful_tool_calls: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int] = mapped_column(BigInteger)
    completion_tokens: Mapped[int] = mapped_column(BigInteger)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)


class AgentRunEvent(Base):
    __tablename__ = "agent_run_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentCallAttempt(Base):
    __tablename__ = "agent_call_attempt"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    call_key: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB)


class AgentModelInvocation(Base):
    __tablename__ = "agent_model_invocation"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    call_key: Mapped[str] = mapped_column(Text, primary_key=True)
    progress: Mapped[dict[str, Any]] = mapped_column(JSONB)


class AnalysisDataSnapshot(Base):
    """业务数据快照：报告数据不可变版本的载体。"""

    __tablename__ = "analysis_data_snapshot"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    report_id: Mapped[int] = mapped_column(BigInteger)
    revision: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(Text)
    manifest_hash: Mapped[str] = mapped_column(Text)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisRecordReview(Base):
    """人工裁定按快照和事项追加，机器再次提交不会改写历史裁定。"""

    __tablename__ = "analysis_record_review"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(BigInteger)
    record_id: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)
    corrected_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
