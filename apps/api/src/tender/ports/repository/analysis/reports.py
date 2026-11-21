"""按调用者能力定义的仓储端口；SQL 与共享事务由同一实现提供。"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol

from tender.ports.repository.analysis.runtime import AgentRunStore
from tender.ports.repository.jobs.lifecycle import TaskLifecycle
from tender.ports.repository.knowledge.retrieval import RetrievalRepository
from tender.ports.repository.knowledge.sources import SourceReader
from tender.ports.repository.shared.schema import SchemaReader


class ReportTransaction(Protocol):
    def lock_project(self, project_id: int) -> None:
        """取项目的会话锁，串行化同项目的发布与取消。"""
        ...

    def lock_report(self, report_id: int) -> dict[str, Any]:
        """锁定报告行并返回全字段；报告不存在时抛 ``LookupError``。"""
        ...

    def start_report(
        self,
        report_id: int,
        *,
        source_snapshot: list[dict[str, Any]],
        reference_snapshot: list[dict[str, Any]],
    ) -> bool:
        """把等待/排队中的报告置为执行中并固定资料快照；已被取消时返回 ``False``。"""
        ...

    def requeue_unlocked_runs(self, report_id: int) -> None:
        """把没有执行者持锁的在途运行退回等待，避免僵尸运行长期占住执行名额。"""
        ...

    def ensure_modules(self, report_id: int, modules: dict[str, str]) -> list[dict[str, Any]]:
        """确保报告的模块行存在（标题随 Skill 更新），返回各模块当前 ``id`` / ``status``。"""
        ...

    def ensure_module_run(
        self,
        module_id: int,
        *,
        company_id: int,
        thread_id: str,
        limits: dict[str, Any],
    ) -> None:
        """确保首次 attempt（=1）的运行账存在；重复投递或补跑不覆盖既有行。"""
        ...

    def report_runs(self, report_id: int) -> list[dict[str, Any]]:
        """报告下全部模块运行，含独立的 successful_model_calls / successful_tool_calls。

        成功数只统计已确认的结果；model_calls / tool_calls 保留实际尝试数。
        """
        ...

    def report_modules(self, report_id: int) -> list[dict[str, Any]]:
        """报告下全部模块及其成果，按 id 升序。"""
        ...

    def snapshot_by_manifest(self, report_id: int, manifest_hash: str) -> dict[str, Any] | None:
        """已存在同一份成果指纹的快照时直接复用，不重复发布。"""
        ...

    def latest_snapshot_id(self, report_id: int) -> int | None: ...

    def snapshot_state(self, report_id: int) -> dict[str, Any] | None: ...

    def review_inputs(
        self, project_id: int,
    ) -> tuple[dict | None, list[dict], list[int], list[dict]]:
        """同事务读取项目设置、标段、可读资料库和当前资料。"""
        ...

    def resolve(self, ref: dict[str, Any]) -> dict[str, Any]: ...

    def record_review(self, snapshot_id: int, record_id: str) -> dict[str, Any] | None: ...

    def insert_record_review(self, values: dict[str, Any]) -> dict[str, Any]: ...

    def lot_id_for_code(self, project_id: int, code: str) -> int | None:
        """按标段编号取已有标段 id；重名时取 id 最小的那条（与既有口径一致）。"""
        ...

    def create_lot(self, project_id: int, *, code: str, name: str) -> int:
        """新建标段，序号接在现有最大序号之后。"""
        ...

    def set_derived_lots(self, report_id: int, lot_ids: list[int]) -> None:
        """记录本次发布自动派生出的标段，供前端区分「识别到」与「人工设定」。"""
        ...

    def next_snapshot_revision(self, report_id: int) -> int:
        """下一版快照号；同一报告的快照按 revision 递增，旧版本保留可回溯。"""
        ...

    def insert_snapshot(
        self,
        *,
        report_id: int,
        revision: int,
        schema_version: str,
        manifest_hash: str,
        inputs: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """写入快照并返回整行。"""
        ...

    def active_report(self, project_id: int) -> int | None: ...

    def other_active_report(self, project_id: int, report_id: int) -> int | None: ...

    def insert_report(self, values: dict[str, Any]) -> dict[str, Any]: ...

    def report_status(self, report_id: int, *, lock: bool = False) -> str: ...

    def update_report(self, report_id: int, values: dict[str, Any]) -> None: ...

    def mark_report_canceled(self, report_id: int) -> None: ...

    def execution_active(self, report_id: int) -> bool: ...

    def try_lock_execution(self, report_id: int) -> bool: ...

    def cancel_unlocked_runs(self, report_id: int) -> None: ...

    def modules_for_retry(
        self, report_id: int, keys: list[str], *, explicit: bool
    ) -> list[dict[str, Any]]: ...

    def report_has_modules(self, report_id: int) -> bool: ...

    def reset_modules(self, module_ids: list[int]) -> None: ...

    def mark_modules_pending(self, module_ids: list[int]) -> None: ...

    def module_attempt(self, module_id: int) -> int: ...

    def previous_run_state(self, module_id: int) -> dict[str, Any]: ...

    def insert_module_run(
        self,
        *,
        module_id: int,
        attempt: int,
        thread_id: str,
        limits: dict[str, Any],
        state: dict[str, Any],
    ) -> None: ...


class ReportRepository(SourceReader, RetrievalRepository, SchemaReader, TaskLifecycle, Protocol):
    def transaction(self) -> AbstractContextManager[ReportTransaction]: ...

    def resolved_config(self) -> dict[str, Any]:
        """本公司的运行期配置全量值（默认值已合并）；供预算上限等参数读取。"""
        ...

    def report(self, report_id: int) -> dict[str, Any] | None:
        """取报告；项目已删除或跨公司时返回 ``None``。"""
        ...

    def report_for_analysis(self, report_id: int) -> dict[str, Any] | None:
        """worker 侧取报告以判断能否执行；项目已删除时返回 ``None``。"""
        ...

    def accessible_report_status(self, report_id: int) -> str | None:
        """报告状态；权限已撤销时返回 ``None``。

        与 ``report`` 分开：调用方要区分「报告不在了」和「报告还在但不能访问」，
        而这里只需要一个可执行性判断。
        """
        ...

    def analysis_settings(self, project_id: int) -> dict[str, Any] | None:
        """项目的分析类别与专题设置。"""
        ...

    def project_lots(self, project_id: int) -> list[dict[str, Any]]:
        """项目的全部标段及各自的分析设置，按序号排序。"""
        ...

    def project_lot_ids(self, project_id: int) -> list[int]:
        """项目的全部标段 id；用于校验设置里的标段归属。"""
        ...

    def analysis_reports(self, project_id: int) -> list[dict[str, Any]]:
        """项目最近 30 份分析报告的概要。"""
        ...

    def report_modules(self, report_id: int) -> list[dict[str, Any]]:
        """报告的全部模块（含成果与工具日志），按 id 升序。"""
        ...

    def report_runs(self, report_id: int) -> list[dict[str, Any]]:
        """报告的运行账及成功调用数（含尚未核实的暂存成果），按 attempt 升序。"""
        ...

    def report_active_modules(self, report_id: int) -> list[dict[str, Any]]:
        """各模块最新一个 attempt 中仍处于等待/运行的行。"""
        ...

    def run_belongs_to_report(self, run_id: int, report_id: int) -> bool:
        """该运行是否属于本报告与本公司；用于接口层的越权检查。"""
        ...

    def run_events(self, run_id: int, *, after: int, limit: int) -> list[dict[str, Any]]:
        """运行的审计事件增量（``id > after``），按 id 升序。"""
        ...

    def data_snapshot(
        self, report_id: int, snapshot_id: int | None = None
    ) -> dict[str, Any] | None:
        """正式业务数据快照；不指定 ``snapshot_id`` 时取最新一版。"""
        ...

    def snapshot_state(self, report_id: int) -> dict[str, Any] | None:
        """报告状态 + 运行账 + 模块成果，一次读出以判断快照是否仍然有效。"""
        ...

    def snapshot_pending(self, report_id: int) -> bool: ...

    def record_reviews(self, snapshot_id: int) -> dict[str, dict[str, Any]]: ...

    def set_report_coverage(self, report_id: int, coverage: dict[str, Any]) -> None:
        """记录本次分析覆盖了哪些资料。"""
        ...

    def defer_report(self, report_id: int, seconds: int) -> None:
        """资料未就绪时把等待中的报告推迟多久再次尝试。"""
        ...

    def renew_report_lease(
        self, report_id: int, seconds: int, *, status: str | None = None
    ) -> None:
        """续租报告；``status`` 给定时空值也必须匹配（避免续到已换状态的报告上）。"""
        ...

    def finish_report(
        self,
        report_id: int,
        *,
        status: str,
        summary: list[Any],
        error: str | None,
    ) -> None:
        """报告收口：写终态、汇总与结束时间，并清掉租约。"""
        ...

    def agent_run_store(self, report: dict[str, Any], run: dict[str, Any]) -> AgentRunStore:
        """取报告/模块运行的状态机入口（见 ``ports.repository.agent_runtime``）。"""
        ...

    def append_run_event(self, run_id: int, kind: str, detail: dict[str, Any] | None) -> None:
        """写一条运行审计事件（独立短事务，不参与配额事务）。"""
        ...

    def update_analysis_settings(
        self, project_id: int, *, category: str, topics: list[str], lots: list[dict[str, Any]]
    ) -> None: ...

    def execution_active(self, report_id: int) -> bool: ...
