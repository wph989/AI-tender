"""运行期配额的用例策略与跨进程硬配额的门面。

职责刻意分两层：**这里**只做「该不该继续跑」的权限与预算判断，以及「哪些成果可以
发布」的应用层投影；配额锁、fencing、`pg_locks` 判断这些持久化细节在
``adapters/pg/repositories/agent_runtime.py``（见 ``ports/repository/agent_runtime.py``）。
数据库会话锁存活时绝不抢占这条底线由实现保证，本层只负责把权限变化变成明确的异常。
"""

from __future__ import annotations

from dataclasses import asdict

from tender.application.analysis.data import display_items, module_data
from tender.application.analysis.research import AgentLimits
from tender.application.analysis.state import published_items
from tender.ports.repository.analysis.reports import ReportRepository
from tender.ports.repository.analysis.runtime import AgentRunStore


def limits_snapshot(db: ReportRepository) -> dict:
    """当前配置解析出的模块预算快照；用户改过预算后补跑必须立刻生效。"""
    values = db.resolved_config()
    return asdict(
        AgentLimits(
            **{
                key: values["analysis." + key]
                for key in asdict(AgentLimits())
                if "analysis." + key in values
            }
        )
    )


def check_report_status(db: ReportRepository, report: dict) -> None:
    """只查报告是否仍可执行；取消检测走轻量主键查询，资料权限另行完整复核。"""
    if db.accessible_report_status(report["id"]) not in {"waiting", "pending", "running"}:
        raise InterruptedError("报告已取消或不再执行")


def check_report_access(db: ReportRepository, report: dict, sources: list[dict]) -> None:
    """报告可执行性与资料权限的复核；权限变化要立刻中断，不能等到下一个检查点。"""
    check_report_status(db, report)
    allowed = db.collections_for_project(report["project_id"])
    if any(s["collection_id"] not in allowed for s in sources):
        raise PermissionError("知识库关联已撤销，停止使用原会话中的资料")
    current = {s["source_id"]: s for s in db.sources(allowed)}
    for source in sources:
        live = current.get(source["source_id"])
        if live is None or any(
            live[k] != source[k]
            for k in (
                "project_id",
                "collection_id",
                "project_file_id",
                "version_id",
                "parse_run_id",
            )
        ):
            raise PermissionError("资料已删除、替换或重新解析，请基于最新版本重新分析")


class AgentRuntime:
    """模块执行的门面：在运行账状态机上叠加权限复核与成果投影。"""

    def __init__(
        self, db: ReportRepository, report: dict, run: dict, sources: list[dict]
    ) -> None:
        self.db, self.report, self.sources = db, report, sources
        self.store: AgentRunStore = db.agent_run_store(report, run)

    @property
    def run(self) -> dict:
        """当前运行账；``claim`` 成功后会被实现替换为最新一行。"""
        return self.store.run

    def event(self, kind: str, detail: dict | None = None) -> None:
        self.store.event(kind, detail)

    def check_access(self) -> None:
        """报告状态与资料权限复核；等待配额与心跳按间隔调用，不能逐轮查询。"""
        check_report_access(self.db, self.report, self.sources)

    def claim(self) -> bool:
        # 实现自身会在取槽事务里锁定报告状态并判断配额；权限复核由等待循环节流执行。
        return self.store.claim()

    def guard(self) -> None:
        check_report_access(self.db, self.report, self.sources)
        self.store.guard()

    def heartbeat(self, full_check: bool = True) -> None:
        # 存储层心跳每次都校验所有权、租约与模块时限；完整资料权限按调用方间隔复核，
        # 其余心跳只做一次轻量报告状态查询，保证取消在 15 秒心跳内被发现。
        if full_check:
            check_report_access(self.db, self.report, self.sources)
        else:
            check_report_status(self.db, self.report)
        self.store.heartbeat()

    def reserve(self, kind: str) -> None:
        self.guard()
        self.store.reserve(kind)

    def record_call(self, record) -> None:
        # unknown 请求也保留已预占次数，不把不确定的供应商请求当作免费。
        self.store.record_call(asdict(record))

    def save(self, state: dict) -> None:
        self.guard()
        self.store.save(state, publish=self._staged_payload(state))

    def finish(
        self,
        status: str,
        error: str | None = None,
        draft: dict | None = None,
        *,
        state: dict | None = None,
    ) -> None:
        topic_settlement = bool(state and state.get("topic_flow")
                                and status in {"partial", "failed"})
        if status in {"completed", "partial"} or topic_settlement:
            # 部分发布同样要复核报告状态、所有权、租约与资料权限。
            if topic_settlement:
                check_report_access(self.db, self.report, self.sources)
                self.store.guard_settlement()
            else:
                self.guard()
        if status == "completed" and draft is not None:
            publish = self._draft_payload(draft)
        elif status == "partial" or topic_settlement:
            # 只有待复核旧版时仍同步展示投影，不能让失败前的 current 标记进入正式快照。
            publish = self._staged_payload(state or {}, include_relations=True)
        else:
            publish = None
        if state and state.get("topic_flow"):
            self.store.finish(status, error, publish=publish, state=state)
        else:
            self.store.finish(status, error, publish=publish)

    def abandon(self, status: str, error: str | None = None) -> None:
        """异常收尾；未领取配额时同样形成终态，避免排队行永远显示等待配额。"""
        self.store.abandon(status, error)

    def release(self) -> None:
        self.store.release()

    @staticmethod
    def _draft_payload(draft: dict) -> dict:
        return {
            "items": display_items(draft.get("fields", [])),
            "business": draft.get("business_data", {}),
            "relations": draft.get("relations") or [],
        }

    @staticmethod
    def _staged_payload(state: dict, *, include_relations: bool = False) -> dict | None:
        """未完成也保存已核实字段的展示投影；未通过校验时不发布。"""
        if not state.get("staged_items_verified") and not state.get("topic_flow"):
            return None
        payload = {
            "items": display_items(
                published_items(state)
            ),
            "business": module_data(state),
        }
        if include_relations:
            # 部分发布只带已通过支持性校验的关系；未审关系不能随暂存成果外泄。
            payload["relations"] = state.get("staged_relations") or []
        return payload
