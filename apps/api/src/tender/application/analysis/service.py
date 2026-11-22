"""跨文件综合分析、报告展示、补跑与问答前置校验。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any, Literal

from tender.application.analysis.data import (
    DATA_VERSION,
    ContextError,
    ContextInput,
    build_context,
    display_items,
    module_records,
)
from tender.application.analysis.data_store import (
    accessible_data,
    citations_accessible,
    matching_snapshot_state,
    publish_data_snapshot,
)
from tender.application.analysis.human_review import (
    CORRECTABLE_KINDS,
    RecordReviewInput,
    review_projection,
    review_record,
    reviewed_compilation,
)
from tender.application.analysis.output import output_schema
from tender.application.analysis.quality import (
    aggregate_quality,
    input_changed,
    quality_status,
    refresh_input,
)
from tender.application.analysis.runtime import limits_snapshot
from tender.application.analysis.skills import MODULES, skill_snapshot, skill_version
from tender.application.knowledge.content import (
    CATEGORIES,
    TOPICS,
    merge_field_entries,
    source_signature,
)
from tender.application.knowledge.retrieval import retrieve_chunks
from tender.application.knowledge.service import KnowledgeService, visible_items
from tender.application.projects.files import role_is_parseable
from tender.application.shared.errors import (
    Conflict,
    InvalidArgument,
    NotFound,
    ServiceError,
    Unprocessable,
)
from tender.domain.analysis.contract import (
    FLOW_VERSION,
    FLOW_VERSION_KEY,
    RUNTIME_VERSION,
    is_current_report,
)
from tender.ports.configuration.registry import ConfigReader
from tender.ports.llm.embedding import EmbeddingModel
from tender.ports.repository.analysis.reports import ReportRepository


def report_inputs_changed(
    report: dict, settings: dict, lots: list[dict], sources: list[dict], references: list[dict],
) -> bool:
    # 发布自动派生的标段不算用户改动，除非它随后有了自己的分析设置。
    frozen_lot_ids = {lot["id"] for lot in report["lot_settings"]}
    derived = set(report.get("derived_lot_ids", [])) - frozen_lot_ids
    return (
        source_signature(sources) != source_signature(report["source_snapshot"])
        or settings["analysis_category"] != report["category"]
        or settings["analysis_topics"] != report["topics"]
        or [lot for lot in lots if not (lot["id"] in derived and lot["category"] is None
                                        and lot["topics"] is None)] != report["lot_settings"]
        or source_signature(references) != source_signature(report["reference_snapshot"])
    )


class AnalysisService:
    def __init__(
        self,
        repository: ReportRepository,
        company_id: int,
        configs: ConfigReader,
        embedding_gateway: Callable[[dict], EmbeddingModel],
        knowledge: KnowledgeService,
    ) -> None:
        self.company_id = company_id
        self.configs = configs
        self.embedding_gateway = embedding_gateway
        self.store = repository
        self.knowledge = knowledge

    def analysis_status(self, project_id: int) -> dict[str, Any]:
        own_id = self.knowledge.project_collection(project_id)
        project = self.store.analysis_settings(project_id)
        if project is None:
            raise NotFound("项目不存在")
        return {
            **project,
            "lots": self.store.project_lots(project_id),
            "reports": self.store.analysis_reports(project_id),
            "sources": self.knowledge.public_sources([own_id]),
            "categories": CATEGORIES,
            "topics": TOPICS,
        }

    def save_settings(
        self,
        project_id: int,
        *,
        category: str,
        topics: list[str],
        lots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.store.project_exists(project_id):
            raise NotFound("项目不存在")
        if set(topics) - TOPICS.keys() or any(
            set(lot.get("topics") or []) - TOPICS.keys() for lot in lots
        ):
            raise InvalidArgument("存在不支持的分析专题", code="invalid_topic")
        known = set(self.store.project_lot_ids(project_id))
        if any(lot["id"] not in known for lot in lots):
            raise InvalidArgument("标段不属于当前项目", code="invalid_lot")
        self.store.update_analysis_settings(
            project_id,
            category=category,
            topics=topics,
            lots=lots,
        )
        return self.analysis_status(project_id)

    def start_analysis(self, project_id: int, *, allow_partial: bool) -> dict[str, Any]:
        state = self.analysis_status(project_id)
        if state["analysis_category"] is None:
            raise InvalidArgument(
                "开始分析前请选择工程、货物或服务",
                code="category_required",
            )
        if not state["sources"]:
            raise InvalidArgument("请先上传项目文件", code="files_required")
        for source in state["sources"]:
            suffix = PurePosixPath(source["file_name"]).suffix.lower()
            if source["state"] in {"pending", "unsupported"} and role_is_parseable(
                source["role"], suffix
            ):
                try:
                    self.knowledge.process_source(source["source_id"])
                except ServiceError as exc:
                    if exc.code not in {"process_in_flight", "parse_in_flight"}:
                        raise
        rules = skill_snapshot()
        rules["__analysis_data_version__"] = DATA_VERSION
        rules[FLOW_VERSION_KEY] = FLOW_VERSION
        references = [
            source
            for source in self.store.sources(self.store.collections_for_project(project_id))
            if source["project_id"] != project_id
        ]
        runtime_settings = limits_snapshot(self.store)
        with self.store.transaction() as tx:
            tx.lock_project(project_id)
            if tx.active_report(project_id) is not None:
                raise Conflict(
                    "项目已有分析任务，请等待或取消等待任务",
                    code="analysis_in_flight",
                )
            return tx.insert_report(
                {
                    "project_id": project_id,
                    "company_id": self.company_id,
                    "allow_partial": allow_partial,
                    "category": state["analysis_category"],
                    "topics": state["analysis_topics"],
                    "lot_settings": state["lots"],
                    "source_snapshot": state["sources"],
                    "skill_version": skill_version(rules),
                    "skill_snapshot": rules,
                    "runtime_version": RUNTIME_VERSION,
                    "runtime_settings": runtime_settings,
                    "reference_snapshot": references,
                }
            )

    def report_row(self, report_id: int) -> dict[str, Any]:
        report = self.store.report(report_id)
        if report is None:
            raise NotFound("报告不存在")
        if not is_current_report(report):
            raise Conflict(
                "此报告协议已退役，请重新发起分析",
                code="runtime_retired",
            )
        return report

    def get_report(self, report_id: int) -> dict[str, Any]:
        report = self.report_row(report_id)
        report.pop("skill_snapshot", None)
        modules = self.store.report_modules(report_id)
        allowed = self.store.collections_for_project(report["project_id"])
        module_inputs = {}
        for module in modules:
            # 工具日志只供服务端重放，不在产品界面暴露整段中间提示词。
            module.pop("trace", None)
            business = module.pop("business_data", None) or {}
            module_inputs[module["id"]] = {"quality_input_signature": business.get(
                "quality_input_signature")}
            module["research_summary"] = business.get("research_summary", "")
            module["research_gaps"] = business.get("gaps", [])
            module["quality_status"] = quality_status(business)
            module["quality_issues"] = business.get("quality_issues", [])
        runs = self.store.report_runs(report_id)
        for module in modules:
            module["runs"] = [run for run in runs if run["module_id"] == module["id"]]
            latest = module["runs"][-1] if module["runs"] else {}
            progress = latest.get("agent_progress")
            if progress and progress.get("protocol") == FLOW_VERSION:
                module["progress"] = progress
            module["items"] = visible_items(
                self.store,
                display_items(
                    merge_field_entries(
                        module["items"],
                        is_outline=module["module_key"] == "bid_format_outline_parsing",
                    )
                ),
                allowed,
            )
        report["summary"] = visible_items(self.store, report["summary"], allowed)
        live = {source["source_id"]: source for source in self.store.sources(allowed)}
        current_sources = [source for source in live.values()
                           if source["project_id"] == report["project_id"]]
        current_references = [source for source in live.values()
                              if source["project_id"] != report["project_id"]]
        for module in modules:
            # 页面入口与补跑事务共用专题输入判断，报告快照已更新也不能禁用其他专题。
            module["input_changed"] = input_changed(
                module_inputs[module["id"]], current_sources + current_references,
            )
        if any(
            source["source_id"] not in live
            or any(
                source.get(key) != live[source["source_id"]].get(key)
                for key in ("collection_id", "version_id", "parse_run_id")
            )
            for source in report["source_snapshot"] + report["reference_snapshot"]
        ):
            # 检索说明也可能包含已撤销资料的内容，不能只隐藏条目正文而留下说明旁路。
            for module in modules:
                module["research_summary"] = ""
                module["research_gaps"] = []
                module["quality_issues"] = []
                module.pop("progress", None)
                for run in module["runs"]:
                    run.pop("agent_progress", None)
        settings = self.store.analysis_settings(report["project_id"])
        if settings is None:
            raise NotFound("项目不存在")
        stale = report_inputs_changed(
            report, settings, self.store.project_lots(report["project_id"]),
            current_sources, current_references,
        )
        canceling = report["status"] == "canceled" and self.store.execution_active(report_id)
        return {
            **report,
            "canceling": canceling,
            "modules": modules,
            "quality_status": aggregate_quality([m["quality_status"] for m in modules]),
            "stale": stale,
            "data_schema_version": DATA_VERSION,
        }

    def data_snapshot(self, report_id: int, snapshot_id: int | None = None) -> dict:
        self.report_row(report_id)
        snapshot = self.store.data_snapshot(report_id, snapshot_id)
        if snapshot is None:
            raise Conflict("正式业务数据快照尚未就绪", code="data_not_ready")
        return snapshot

    def get_module_records(self, report_id: int, module_key: str) -> dict[str, Any]:
        report = self.report_row(report_id)
        module = next(
            (
                item
                for item in self.store.report_modules(report_id)
                if item["module_key"] == module_key
            ),
            None,
        )
        if module is None:
            raise NotFound("分析维度不存在")
        business = module.get("business_data") or {}
        allowed = self.store.collections_for_project(report["project_id"])
        stored_evidence = business.get("evidence", {})
        candidates = [
            record
            for record in module_records(business)
            if record.get("evidence_ids")
            and all(key in stored_evidence for key in record["evidence_ids"])
        ]
        visible = visible_items(
            self.store,
            [
                {
                    "id": record["id"],
                    "field": record.get("title", ""),
                    "output": True,
                    "values": [{"value": "", "citations": record["citations"]}],
                }
                for record in candidates
            ],
            allowed,
        )
        records, evidence = [], {}
        for record, result in zip(candidates, visible, strict=True):
            if result.get("verification") == "unavailable":
                continue
            data = {
                key: value
                for key, value in record.items()
                if key not in {"citations", "evidence_ids"}
            }
            data["evidence_ids"] = list(record["evidence_ids"])
            evidence.update({key: stored_evidence[key] for key in data["evidence_ids"]})
            records.append(data)
        inputs_accessible = self.progress_accessible(report, allowed)
        return {
            "schema_version": DATA_VERSION,
            "module_key": module_key,
            "status": module["status"],
            "quality_status": quality_status(business),
            "quality_issues": (business.get("quality_issues", [])
                               if inputs_accessible else []),
            "records": records,
            "evidence": evidence,
            "output_schema": output_schema(report["skill_snapshot"], module_key),
        }

    def progress_accessible(self, report: dict, allowed: list[int]) -> bool:
        # 待办和核对说明也可能包含资料内容，与原文一样校验冻结身份及当前授权。
        live = {s["source_id"]: s for s in self.store.sources(allowed)}
        return all(s["source_id"] in live and all(
            s.get(k) == live[s["source_id"]].get(k)
            for k in ("collection_id", "version_id", "parse_run_id")
        ) for s in report["source_snapshot"] + report["reference_snapshot"])

    def get_analysis_data(
        self,
        report_id: int,
        snapshot_id: int | None = None,
    ) -> dict[str, Any]:
        snapshot = self.data_snapshot(report_id, snapshot_id)
        report = self.get_report(report_id)
        state = self._current_snapshot_state(report, snapshot)
        data = self._review_data(report, snapshot, state)
        return {
            "report_id": report_id,
            "snapshot_id": snapshot["id"],
            "revision": snapshot["revision"],
            "schema_version": snapshot["schema_version"],
            "stale": state is None,
            "data": data,
        }

    def _current_snapshot_state(self, report: dict, snapshot: dict) -> dict | None:
        if (report["stale"] or report["status"] in {"waiting", "pending", "running"}
                or self.data_snapshot(report["id"])["id"] != snapshot["id"]):
            return None
        return matching_snapshot_state(self.store.snapshot_state, snapshot)

    def _review_data(self, report: dict, snapshot: dict, state: dict | None) -> dict:
        inputs = snapshot["input_snapshot"]
        sources = inputs["source_snapshot"] + inputs["reference_snapshot"]
        signature = source_signature(sources)
        signatures = inputs["module_input_signatures"]
        data = accessible_data(
            self.store, snapshot["data"], self.store.collections_for_project(report["project_id"]),
            sources=sources,
        )
        data["quality_status"] = quality_status({"quality_status": data.get("quality_status")})
        # 来源撤销后不回显可能含原文的人工备注或修正结果。
        if any(gap["code"] == "source_unavailable" for gap in data["gaps"]):
            return review_projection(data, signatures, signature, {}, current=False)
        return review_projection(
            data, signatures, signature, self.store.record_reviews(snapshot["id"]),
            current=state is not None,
        )

    def context_data(self, report_id: int, snapshot: dict) -> tuple[dict, dict]:
        report = self.get_report(report_id)
        if report["status"] in {"waiting", "pending", "running"}:
            raise Conflict(
                "报告正在更新，请在本轮分析结束后获取编制依据",
                code="report_running",
            )
        state = self._current_snapshot_state(report, snapshot)
        data = self._review_data(report, snapshot, state)
        if any(gap["code"] == "source_unavailable" for gap in data["gaps"]):
            raise Conflict(
                "部分来源已删除或撤销访问，请更新分析",
                code="source_unavailable",
            )
        if state is None:
            raise Conflict("依据已更新，请使用当前有效分析快照", code="data_stale")
        return report, data

    def record_human_review(
        self, report_id: int, payload: RecordReviewInput, *, actor: str,
    ) -> dict[str, Any]:
        snapshot = self.data_snapshot(report_id, payload.snapshot_id)
        report, data = self.context_data(report_id, snapshot)
        record = review_record(data, payload.record_id)
        if record is None:
            raise NotFound("事项不存在或原文已不可访问")
        if record["human_review_status"] == "outdated":
            raise Conflict("该专题尚未核对当前资料，请重新解析后复核", code="record_outdated")
        if not record.get("citations"):
            raise Conflict("该事项的原文依据尚未齐备", code="record_unready")
        if payload.decision == "corrected" and record["kind"] not in CORRECTABLE_KINDS:
            raise InvalidArgument("只有项目事实和招标要求支持人工修正正文")
        with self.store.transaction() as tx:
            tx.lock_project(report["project_id"])
            row = tx.lock_report(report_id)
            if (tx.latest_snapshot_id(report_id) != snapshot["id"]
                    or matching_snapshot_state(tx.snapshot_state, snapshot) is None):
                raise Conflict("报告已更新，请刷新后再复核", code="data_stale")
            # 等锁期间资料可能变化；落笔前只查当前输入和本事项的证据。
            project_id = row["project_id"]
            settings, lots, allowed, live = tx.review_inputs(project_id)
            if settings is None or report_inputs_changed(
                row, settings, lots,
                [s for s in live if s["project_id"] == project_id],
                [s for s in live if s["project_id"] != project_id],
            ):
                raise Conflict("报告已更新，请刷新后再复核", code="data_stale")
            if not citations_accessible(tx.resolve, record["citations"], allowed, {}):
                raise Conflict("部分来源已删除或撤销访问，请更新分析", code="source_unavailable")
            last = tx.record_review(snapshot["id"], payload.record_id)
            if (last["id"] if last else None) != payload.previous_review_id:
                raise Conflict("该事项已被其他人复核，请刷新后再提交", code="review_conflict")
            return tx.insert_record_review(
                payload.model_dump(exclude={"previous_review_id"}) | {"actor": actor},
            )

    async def get_analysis_context(
        self,
        report_id: int,
        payload: ContextInput,
    ) -> dict[str, Any]:
        snapshot = await asyncio.to_thread(self.data_snapshot, report_id, payload.snapshot_id)
        report, data = await asyncio.to_thread(self.context_data, report_id, snapshot)
        try:
            context = build_context(reviewed_compilation(data), payload)
        except ContextError as exc:
            raise Unprocessable(str(exc), code=exc.code) from exc
        if payload.purpose == "content":
            sources = [
                source
                for source in report["reference_snapshot"]
                if source["purpose"] in {"company", "history"}
            ]
            if sources and context["requirements"]:
                rows, meta = await retrieve_chunks(
                    self.store,
                    sources,
                    "\n".join(item["text"] for item in context["requirements"]),
                    lambda: None,
                    self.embedding_gateway,
                    embedding_timeout=15,
                )
                # 不只重查参考片段；招标依据也可能在等待参考检索时被撤销或重跑。
                _, refreshed = await asyncio.to_thread(self.context_data, report_id, snapshot)
                if refreshed != data:
                    raise Conflict("事项复核已变更，请重新获取编制依据", code="review_conflict")
                live = await asyncio.to_thread(
                    self.store.collections_for_project, report["project_id"],
                )
                for row in rows[:12]:
                    if row["collection_id"] not in live:
                        continue
                    try:
                        citation = await asyncio.to_thread(
                            self.store.resolve,
                            {
                                key: row[key]
                                for key in (
                                    "source_id",
                                    "collection_id",
                                    "project_id",
                                    "project_file_id",
                                    "version_id",
                                    "parse_run_id",
                                    "element_id",
                                    "anchor",
                                    "page_no",
                                    "bbox",
                                    "file_name",
                                )
                            }
                            | {"purpose": row["purpose"], "quote": row["content"]}
                        )
                    except LookupError as exc:
                        raise Conflict(
                            "参考来源已撤销，请更新分析",
                            code="source_unavailable",
                        ) from exc
                    context["references"].append(
                        {
                            "purpose": row["purpose"],
                            "text": row["content"],
                            "citation": citation,
                        }
                    )
                context["reference_warning"] = meta.get("warning")
        return context

    def cancel_report(self, report_id: int) -> dict[str, Any]:
        self.report_row(report_id)
        with self.store.transaction() as tx:
            status = tx.report_status(report_id, lock=True)
            if status in {"waiting", "pending", "running", "canceled"}:
                tx.mark_report_canceled(report_id)
                status = "canceled"
            canceling = status == "canceled" and tx.execution_active(report_id)
        publish_data_snapshot(self.store, report_id)
        return {"status": status, "canceling": canceling}

    def run_events(
        self,
        report_id: int,
        run_id: int,
        *,
        after: int,
        limit: int,
    ) -> dict[str, Any]:
        self.report_row(report_id)
        if not self.store.run_belongs_to_report(run_id, report_id):
            raise NotFound("模块运行记录不存在")
        rows = self.store.run_events(run_id, after=after, limit=limit)
        return {"events": rows, "next_after": rows[-1]["id"] if rows else after}

    def retry_report(
        self,
        report_id: int,
        *,
        module_keys: list[str],
        max_output_tokens: int | None,
        timeout_seconds: int | None,
        mode: Literal["restart", "resume"] | None = None,
    ) -> dict[str, Any]:
        report = self.report_row(report_id)
        if report["status"] in {"waiting", "pending", "running"}:
            raise Conflict(
                "报告正在排队或执行，请等待完成或先取消再补跑",
                code="report_running",
            )
        keys = module_keys or list(MODULES)
        if set(keys) - MODULES.keys():
            raise InvalidArgument("未知解析模块", code="invalid_module")
        # 显式选择模块默认重新解析，全量补跑默认续跑。
        mode = mode or ("restart" if module_keys else "resume")
        if mode not in {"restart", "resume"}:
            raise InvalidArgument("未知重解析模式", code="invalid_retry_mode")
        explicit = mode == "restart" or bool(module_keys)
        with self.store.transaction() as tx:
            tx.lock_project(report["project_id"])
            current_status = tx.report_status(report_id, lock=True)
            if current_status in {"waiting", "pending", "running"}:
                raise Conflict("报告已进入执行，请勿重复补跑", code="report_running")
            if tx.execution_active(report_id) or not tx.try_lock_execution(report_id):
                raise Conflict(
                    "任务正在停止，请等待模块退出后重新解析",
                    code="cancellation_pending",
                )
            if current_status == "canceled":
                tx.cancel_unlocked_runs(report_id)
            if tx.other_active_report(report["project_id"], report_id) is not None:
                raise Conflict("项目已有其它分析任务", code="analysis_in_flight")
            # 完成状态不能证明已处理当前资料；统一取回后按专题输入和质量筛选。
            rows = tx.modules_for_retry(report_id, keys, explicit=explicit)
            changed = False
            current_sources = report.get("source_snapshot", [])
            current_references = report.get("reference_snapshot", [])
            if "source_snapshot" in report:
                current_sources = self.analysis_status(report["project_id"])["sources"]
                current_references = [source for source in self.store.sources(
                    self.store.collections_for_project(report["project_id"]))
                    if source["project_id"] != report["project_id"]]
                changed = (source_signature(current_sources)
                           != source_signature(report["source_snapshot"])
                           or source_signature(current_references)
                           != source_signature(report.get("reference_snapshot", [])))
                if changed:
                    tx.update_report(report_id, {"source_snapshot": current_sources,
                                                 "reference_snapshot": current_references})
            # 草稿尚未发布时，已消费输入记在工作区；不能用旧正式成果让有效自查失效。
            previous_states = {row["id"]: tx.previous_run_state(row["id"])
                               for row in rows} if mode == "resume" else {}
            current_signature = source_signature(current_sources + current_references)
            changed_modules = {row["id"] for row in rows if "source_snapshot" in report and (
                previous_states.get(row["id"], {}).get("quality_input_signature")
                or (row.get("business_data") or {}).get("quality_input_signature")
            ) != current_signature}
            if mode == "resume":
                # 中断轮尚未发布正式成果，质量必须取本轮工作区；未结算时不能沿用旧缺件结论。
                module_qualities = {row["id"]: quality_status(
                    (row.get("business_data") or {}) if row["status"] == "completed"
                    else previous_states[row["id"]]
                ) for row in rows}
                rows = [row for row in rows if (
                    row["id"] in changed_modules
                    or module_qualities[row["id"]] == "needs_review"
                    or (row["status"] in {"failed", "canceled", "partial"}
                        and module_qualities[row["id"]] != "needs_input")
                )]
            has_modules = tx.report_has_modules(report_id)
            if not rows and (explicit or has_modules):
                raise Conflict(
                    "没有需要补跑的模块；重新解析已完成模块请显式指定模块",
                    code="nothing_to_retry",
                )
            # 重跑期间保留上一轮正式投影；只有新Agent显式final并原子发布后才替换。
            retried = [row["id"] for row in rows]
            tx.mark_modules_pending(retried)
            limits = limits_snapshot(self.store)
            if max_output_tokens is not None:
                limits["max_output_tokens"] = max_output_tokens
            if timeout_seconds is not None:
                limits["timeout_seconds"] = timeout_seconds
            if not has_modules:
                tx.update_report(report_id, {"runtime_settings": limits})
            for module_id in sorted(retried):
                attempt = tx.module_attempt(module_id)
                # 冷启动连旧检查点都不读取，避免经草稿、待办或缓存旁路继承旧内容。
                previous_state = previous_states.get(module_id, {})
                # 仅显式补跑新attempt重置调用额度；草稿、自查与问题身份继续保留。
                from tender.application.analysis.drafts import resume_workspace

                carry = resume_workspace(previous_state)
                if module_id in changed_modules and carry:
                    refresh_input(carry, current_sources + current_references)
                carry["execution_mode"] = mode
                tx.insert_module_run(
                    module_id=module_id,
                    attempt=attempt,
                    thread_id=f"analysis:{report_id}:{module_id}:{attempt}",
                    limits=limits,
                    state=carry,
                )
            status = (
                "pending"
                if retried and report["coverage"].get("mode") == "agent_research"
                else "waiting"
            )
            tx.update_report(
                report_id,
                {
                    "status": status,
                    "snapshot_pending": False,
                    "lease_until": None,
                    "error_message": None,
                    "finished_at": None,
                },
            )
        return {"id": report_id, "status": status}
