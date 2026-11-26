"""报告只读查询；与知识来源分开维护，事务写入仍由组合仓储统一管理。"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from sqlalchemy import Connection, Engine, Text, cast, column, exists, func, literal, select, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased

from tender.adapters.pg.models import (
    AgentModuleRun,
    AgentRunEvent,
    AnalysisDataSnapshot,
    AnalysisModule,
    AnalysisReport,
    LlmCallLog,
    Lot,
    Project,
)
from tender.adapters.pg.models.analysis import AgentModelInvocation, AnalysisRecordReview
from tender.core.error_details import MAX_ERROR_LENGTH, error_detail, model_error_details
from tender.domain.analysis.contract import FLOW_VERSION, FLOW_VERSION_KEY, RUNTIME_VERSION


def current_protocol():
    # 先筛掉退役报告，避免它们占用列表名额或被再次派发。
    return (
        (AnalysisReport.runtime_version == RUNTIME_VERSION)
        & (AnalysisReport.skill_snapshot[FLOW_VERSION_KEY].astext == FLOW_VERSION)
    )


class ReportQueries:
    engine: Engine
    company_id: int

    def accessible_report_status(self, report_id: int) -> str | None:
        """报告状态；权限已撤销时返回 ``None``（与「报告不在了」区分见端口文档）。"""
        with self.engine.connect() as connection:
            return connection.execute(
                select(AnalysisReport.status)
                .join(Project, Project.id == AnalysisReport.project_id)
                .where(
                    AnalysisReport.id == report_id,
                    AnalysisReport.company_id == self.company_id,
                    Project.deleted_at.is_(None),
                )
            ).scalar_one_or_none()

    def report(self, report_id: int) -> dict[str, Any] | None:
        """取报告；项目已删除或跨公司时返回 ``None``。"""
        return self._report_row(report_id)

    def report_for_analysis(self, report_id: int) -> dict[str, Any] | None:
        """worker 侧取报告以判断能否执行；项目已删除时返回 ``None``。"""
        return self._report_row(report_id)

    def _report_row(self, report_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(AnalysisReport)
                    .join(Project, Project.id == AnalysisReport.project_id)
                    .where(
                        AnalysisReport.id == report_id,
                        AnalysisReport.company_id == self.company_id,
                        Project.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def report_view(
        self, report_id: int, module_keys: list[str] | None = None,
    ) -> dict[str, Any] | None:
        # 展示只消费输出声明；完整工作方法仍由 Worker 和正式发布读取。
        paths = [FLOW_VERSION_KEY, *(key + "/references/output_schema.json"
                                    for key in dict.fromkeys(module_keys or []))]
        # 与模块摘要一样一次解析所需字段，避免重复解压或展开其余工作方法。
        skill = func.jsonb_to_record(AnalysisReport.skill_snapshot).table_valued(
            *(column(path, JSONB) for path in paths),
        ).render_derived(name="skill", with_types=True)
        snapshot = func.jsonb_build_object(
            *(part for path in paths for part in (literal(path), skill.c[path])),
            type_=JSONB,
        ).label("skill_snapshot")
        columns = [column for column in AnalysisReport.__table__.c
                   if column.key != "skill_snapshot"]
        with self.engine.connect() as connection:
            row = connection.execute(
                select(*columns, snapshot)
                .join(Project, Project.id == AnalysisReport.project_id)
                .join(skill, true())
                .where(
                    AnalysisReport.id == report_id,
                    AnalysisReport.company_id == self.company_id,
                    Project.deleted_at.is_(None),
                )
            ).mappings().first()
        return dict(row) if row is not None else None

    def analysis_settings(
        self, project_id: int, *, bound: Connection | None = None,
    ) -> dict[str, Any] | None:
        """项目的分析类别与专题设置。"""
        with (nullcontext(bound) if bound is not None else self.engine.connect()) as connection:
            row = (
                connection.execute(
                    select(Project.analysis_category, Project.analysis_topics).where(
                        Project.id == project_id,
                        Project.company_id == self.company_id,
                        Project.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def project_lots(
        self, project_id: int, *, bound: Connection | None = None,
    ) -> list[dict[str, Any]]:
        """项目的全部标段及各自的分析设置，按序号排序。"""
        with (nullcontext(bound) if bound is not None else self.engine.connect()) as connection:
            rows = connection.execute(
                select(
                    Lot.id,
                    Lot.name,
                    Lot.analysis_category.label("category"),
                    Lot.analysis_topics.label("topics"),
                )
                .where(Lot.project_id == project_id)
                .order_by(Lot.sort_no, Lot.id)
            ).mappings()
            return [dict(row) for row in rows]

    def project_lot_ids(self, project_id: int) -> list[int]:
        """项目的全部标段 id；用于校验设置里的标段归属。"""
        with self.engine.connect() as connection:
            return list(
                connection.execute(select(Lot.id).where(Lot.project_id == project_id)).scalars()
            )

    def analysis_reports(self, project_id: int) -> list[dict[str, Any]]:
        """项目最近 30 份分析报告的概要。"""
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    AnalysisReport.id,
                    AnalysisReport.status,
                    AnalysisReport.created_at,
                    AnalysisReport.finished_at,
                    AnalysisReport.allow_partial,
                )
                .where(
                    AnalysisReport.project_id == project_id,
                    AnalysisReport.company_id == self.company_id,
                    current_protocol(),
                )
                .order_by(AnalysisReport.id.desc())
                .limit(30)
            ).mappings()
            return [dict(row) for row in rows]

    def report_modules(
        self, report_id: int, module_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """直接限定所选专题，避免为部分刷新加载整份报告正文。"""
        if module_keys == []:
            return []
        statement = (
            select(AnalysisModule)
            .join(AnalysisReport, AnalysisReport.id == AnalysisModule.report_id)
            .where(AnalysisModule.report_id == report_id,
                   AnalysisReport.company_id == self.company_id)
            .order_by(AnalysisModule.id)
        )
        if module_keys is not None:
            statement = statement.where(AnalysisModule.module_key.in_(module_keys))
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings()
            return [dict(row) for row in rows]

    def report_module(self, report_id: int, module_key: str) -> dict[str, Any] | None:
        """正文逐专题读取，直接限定模块以免每次重复加载整份报告。"""
        with self.engine.connect() as connection:
            row = connection.execute(
                select(AnalysisModule)
                .join(AnalysisReport, AnalysisReport.id == AnalysisModule.report_id)
                .where(
                    AnalysisModule.report_id == report_id,
                    AnalysisModule.module_key == module_key,
                    AnalysisReport.company_id == self.company_id,
                )
            ).mappings().first()
            return dict(row) if row is not None else None

    def report_module_summaries(self, report_id: int) -> list[dict[str, Any]]:
        fields = ("research_summary", "quality_status", "quality_issues", "quality_input_signature")
        # 一次解压提取摘要字段，不反复访问包含全部正文和证据的 JSON。
        summary = func.jsonb_to_record(AnalysisModule.business_data).table_valued(
            column("research_summary", Text), column("quality_status", Text),
            column("quality_issues", JSONB), column("quality_input_signature", Text),
        ).render_derived(name="summary", with_types=True)
        business = func.jsonb_build_object(
            *(part for key in fields for part in (literal(key), summary.c[key])),
            type_=JSONB,
        ).label("business_data")
        columns = [column for column in AnalysisModule.__table__.c
                   if column.key != "business_data"]
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(*columns, business)
                .join(AnalysisReport, AnalysisReport.id == AnalysisModule.report_id)
                .join(summary, true())
                .where(AnalysisModule.report_id == report_id,
                       AnalysisReport.company_id == self.company_id)
                .order_by(AnalysisModule.id)
            ).mappings()
            return [dict(row) for row in rows]

    def report_runs(self, report_id: int) -> list[dict[str, Any]]:
        """报告的全部模块运行账与进度，按 attempt 升序。"""
        # 成功计数在请求结算事务中维护，直接读运行账即可，避免每次轮询扫描审计事件。
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    AgentModuleRun.id,
                    AgentModuleRun.module_id,
                    AgentModuleRun.attempt,
                    AgentModuleRun.thread_id,
                    AgentModuleRun.status,
                    AgentModuleRun.started_at,
                    AgentModuleRun.deadline_at,
                    AgentModuleRun.finished_at,
                    AgentModuleRun.lease_until,
                    AgentModuleRun.model_calls,
                    AgentModuleRun.tool_calls,
                    AgentModuleRun.successful_model_calls,
                    AgentModuleRun.successful_tool_calls,
                    AgentModuleRun.prompt_tokens,
                    AgentModuleRun.completion_tokens,
                    AgentModuleRun.limits,
                    AgentModuleRun.error_message,
                    AgentModuleRun.state["stop_reason"].label("stop_reason"),
                    AgentModuleRun.state["quality_status"].astext.label("quality_status"),
                    AgentModuleRun.state["execution_mode"].astext.label("mode"),
                    AgentModuleRun.state["agent_progress"].label("agent_progress"),
                )
                .select_from(AgentModuleRun)
                .join(AnalysisModule, AnalysisModule.id == AgentModuleRun.module_id)
                .where(
                    AnalysisModule.report_id == report_id,
                    AgentModuleRun.company_id == self.company_id,
                )
                .order_by(AgentModuleRun.attempt, AgentModuleRun.id)
            ).mappings()
            runs = [dict(row) for row in rows]
            self._actual_run_errors(connection, runs)
            return runs

    @staticmethod
    def _actual_run_errors(connection: Connection, runs: list[dict]) -> None:
        generic = "模型调用已达到总请求次数或模块时间上限，请查看调用记录"
        affected = {run["id"]: run for run in runs if run.get("error_message") == generic}
        if not affected:
            return
        # 已保存的旧提示同样从真实调用账恢复原因，只改变读取投影，不改写运行审计。
        statement = select(
            AgentModelInvocation.run_id,
            AgentModelInvocation.progress["policy"]["max_total"].astext.label("request_limit"),
            func.jsonb_array_length(AgentModelInvocation.progress["requests"]).label("request_count"),
            LlmCallLog.model_id, LlmCallLog.model_name_snapshot, LlmCallLog.model_key_snapshot,
            LlmCallLog.provider_name_snapshot, LlmCallLog.error_message,
        ).select_from(AgentModelInvocation).join(
            LlmCallLog,
            cast(LlmCallLog.invocation_id, Text)
            == AgentModelInvocation.progress["invocation_id"].astext,
        ).where(
            AgentModelInvocation.run_id.in_(affected),
            AgentModelInvocation.progress["result"].is_(None),
            LlmCallLog.status.in_(["error", "unknown"]),
            LlmCallLog.error_message.is_not(None),
        ).order_by(AgentModelInvocation.run_id, AgentModelInvocation.call_key,
                   LlmCallLog.request_ordinal, LlmCallLog.id)
        failures: dict[int, list[dict]] = {}
        limits = {}
        for row in connection.execute(statement).mappings():
            failures.setdefault(row["run_id"], []).append({
                # 模型删除后外键为空，仍使用保存的模型与供应商身份，避免合并不同模型的错误。
                "model_key": str(row["model_id"]) if row["model_id"] is not None
                else f"{row['provider_name_snapshot']}/{row['model_key_snapshot']}",
                "model": (row["model_name_snapshot"] or row["model_key_snapshot"]
                          or "未记录模型名称"),
                "provider": row["provider_name_snapshot"], "message": row["error_message"],
            })
            limits[row["run_id"]] = (row["request_count"], row["request_limit"])
        for run_id, items in failures.items():
            count, limit = limits[run_id]
            prefix = (f"本次模型调用已尝试{count}次，达到当时配置的{limit}次请求上限\n\n"
                      if limit and count is not None and str(limit).isdigit()
                      and count >= int(limit) else "")
            detail = error_detail(prefix + model_error_details(
                items, limit=MAX_ERROR_LENGTH - len(prefix),
            ))
            run = affected[run_id]
            run["error_message"] = detail
            if run.get("stop_reason"):
                run["stop_reason"] = {**run["stop_reason"], "message": detail}

    def report_active_modules(self, report_id: int) -> list[dict[str, Any]]:
        """各模块最新一个 attempt 中仍处于等待/运行的行（含 ``module_key``）。"""
        latest = aliased(AgentModuleRun)
        newest = (
            select(func.max(latest.id))
            .where(latest.module_id == AgentModuleRun.module_id)
            .correlate(AgentModuleRun)
            .scalar_subquery()
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(AgentModuleRun, AnalysisModule.module_key)
                .join(AnalysisModule, AnalysisModule.id == AgentModuleRun.module_id)
                .where(
                    AnalysisModule.report_id == report_id,
                    AgentModuleRun.company_id == self.company_id,
                    AgentModuleRun.id == newest,
                    AgentModuleRun.status.in_(("pending", "running")),
                )
                .order_by(AnalysisModule.id)
            ).mappings()
            return [dict(row) for row in rows]

    def run_belongs_to_report(self, run_id: int, report_id: int) -> bool:
        """该运行是否属于本报告与本公司；用于接口层的越权检查。"""
        with self.engine.connect() as connection:
            return bool(
                connection.execute(
                    select(
                        exists().where(
                            AgentModuleRun.id == run_id,
                            AgentModuleRun.company_id == self.company_id,
                            AgentModuleRun.module_id.in_(
                                select(AnalysisModule.id).where(
                                    AnalysisModule.report_id == report_id
                                )
                            ),
                        )
                    )
                ).scalar_one()
            )

    def run_events(self, run_id: int, *, after: int, limit: int) -> list[dict[str, Any]]:
        """运行的审计事件增量（``id > after``），按 id 升序。"""
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    AgentRunEvent.id,
                    AgentRunEvent.kind,
                    AgentRunEvent.detail,
                    AgentRunEvent.created_at,
                )
                .where(AgentRunEvent.run_id == run_id, AgentRunEvent.id > after)
                .order_by(AgentRunEvent.id)
                .limit(limit)
            ).mappings()
            return [dict(row) for row in rows]

    def data_snapshot(
        self, report_id: int, snapshot_id: int | None = None
    ) -> dict[str, Any] | None:
        """正式业务数据快照；不指定 ``snapshot_id`` 时取最新一版。"""
        statement = select(AnalysisDataSnapshot).where(AnalysisDataSnapshot.report_id == report_id)
        if snapshot_id is not None:
            statement = statement.where(AnalysisDataSnapshot.id == snapshot_id)
        with self.engine.connect() as connection:
            row = (
                connection.execute(statement.order_by(AnalysisDataSnapshot.id.desc()).limit(1))
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def latest_snapshot_id(self, report_id: int) -> int | None:
        # 版本检查只需要ID，避免再次传输和解码整份业务快照。
        with self.engine.connect() as connection:
            return connection.execute(
                select(AnalysisDataSnapshot.id)
                .join(AnalysisReport, AnalysisReport.id == AnalysisDataSnapshot.report_id)
                .join(Project, Project.id == AnalysisReport.project_id)
                .where(AnalysisDataSnapshot.report_id == report_id,
                       AnalysisReport.company_id == self.company_id,
                       Project.deleted_at.is_(None))
                .order_by(AnalysisDataSnapshot.id.desc()).limit(1)
            ).scalar_one_or_none()

    def snapshot_pending(self, report_id: int) -> bool:
        with self.engine.connect() as connection:
            return bool(connection.execute(
                select(AnalysisReport.snapshot_pending).where(
                    AnalysisReport.id == report_id,
                    AnalysisReport.company_id == self.company_id,
                )
            ).scalar_one_or_none())

    def record_reviews(self, snapshot_id: int) -> dict[str, dict[str, Any]]:
        # 裁定追加写入，递增ID确定每条事项的最新决定，旧裁定仍保留在原表。
        latest = (
            select(func.max(AnalysisRecordReview.id))
            .where(AnalysisRecordReview.snapshot_id == snapshot_id)
            .group_by(AnalysisRecordReview.record_id)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(AnalysisRecordReview)
                .where(AnalysisRecordReview.id.in_(latest))
            ).mappings()
            return {row["record_id"]: dict(row) for row in rows}

    def snapshot_state(
        self, report_id: int, *, bound: Connection | None = None,
    ) -> dict[str, Any] | None:
        """报告状态 + 运行账 + 模块成果，**一条语句**读出以免拼出混合版本。"""
        runs = (
            select(
                func.coalesce(
                    func.jsonb_agg(
                        func.jsonb_build_object(
                            "id",
                            AgentModuleRun.id,
                            "status",
                            AgentModuleRun.status,
                            "attempt",
                            AgentModuleRun.attempt,
                            "module_id",
                            AgentModuleRun.module_id,
                        )
                    ).aggregate_order_by(AgentModuleRun.id),
                    literal([], type_=JSONB),
                )
            )
            .select_from(AgentModuleRun)
            .join(AnalysisModule, AnalysisModule.id == AgentModuleRun.module_id)
            .where(AnalysisModule.report_id == AnalysisReport.id)
            .correlate(AnalysisReport)
            .scalar_subquery()
        )
        modules = (
            select(
                func.coalesce(
                    func.jsonb_agg(
                        func.jsonb_build_object(
                            "id",
                            AnalysisModule.id,
                            "module_key",
                            AnalysisModule.module_key,
                            "status",
                            AnalysisModule.status,
                            "business_data",
                            AnalysisModule.business_data,
                        )
                    ).aggregate_order_by(AnalysisModule.id),
                    literal([], type_=JSONB),
                )
            )
            .select_from(AnalysisModule)
            .where(AnalysisModule.report_id == AnalysisReport.id)
            .correlate(AnalysisReport)
            .scalar_subquery()
        )
        with (nullcontext(bound) if bound is not None else self.engine.connect()) as connection:
            row = (
                connection.execute(
                    select(
                        AnalysisReport.status,
                        AnalysisReport.snapshot_pending,
                        AnalysisReport.source_snapshot,
                        AnalysisReport.reference_snapshot,
                        AnalysisReport.category,
                        AnalysisReport.topics,
                        AnalysisReport.lot_settings,
                        AnalysisReport.skill_version,
                        AnalysisReport.runtime_version,
                        runs.label("runs"),
                        modules.label("modules"),
                    ).where(
                        AnalysisReport.id == report_id,
                        AnalysisReport.company_id == self.company_id,
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None
