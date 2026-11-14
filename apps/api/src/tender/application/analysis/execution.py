"""确定性调度全部模块，模块内部的阅读与检索由独立 DeepAgents 子图决定。"""

from __future__ import annotations

import asyncio
import copy
import json
import random
import time
import traceback
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, suppress
from datetime import UTC, datetime
from typing import Any

from tender.application.analysis.agent import (
    RoutedAgentModel,
    VerificationUnavailable,
    build_module_agent,
    invoke_module,
    validate_project_claims,
)
from tender.application.analysis.data_store import publish_data_snapshot
from tender.application.analysis.research import AgentLimits, ResearchSession
from tender.application.analysis.runtime import AgentRuntime, check_report_access
from tender.application.analysis.search_control import TopicSearch
from tender.application.analysis.skills import MODULES
from tender.application.analysis.topic_flow import TopicIncomplete, enabled
from tender.application.knowledge.content import encode, normalized, source_signature, source_state
from tender.application.knowledge.retrieval import retrieve_chunks
from tender.application.llm.routing import RoutingModel
from tender.core.error_details import error_detail
from tender.core.logging import bind_context, get_logger
from tender.domain.shared.errors import BudgetExhausted, ModelBudgetExhausted, ModelUnavailable
from tender.ports.analysis.archive import AnalysisArchive
from tender.ports.llm.embedding import EmbeddingModel
from tender.ports.llm.rerank import RerankModel
from tender.ports.repository.analysis.reports import ReportRepository

logger = get_logger(__name__)

# 租约 45 秒：心跳取三分之一，每两次心跳（30 秒）做一次完整权限复核。
HEARTBEAT_INTERVAL_SECONDS = 15.0
FULL_ACCESS_HEARTBEATS = 2
# 等待配额时权限检查与等待事件都按约 30 秒节流，避免 13 个模块逐秒打满权限查询。
CLAIM_ACCESS_CHECK_SECONDS = 30.0
CLAIM_WAIT_EVENT_SECONDS = 30.0


def next_claim_delay(attempt: int, random_value: float) -> float:
    """等待配额的下一次轮询间隔：1 秒起步、指数增长、封顶 8 秒，并带 0.5—1.0 抖动。

    抖动避免 13 个模块在同一时刻一起抢锁；领取成功后调用方把轮次归零，恢复 1 秒起步。
    """
    # 必须先限制指数；长队列可能等待上千轮，先乘浮点数再封顶仍会溢出。
    base = 2.0 ** min(max(1, attempt) - 1, 3)
    jitter = 0.5 + 0.5 * min(max(random_value, 0.0), 1.0)
    return base * jitter


async def wait_for_claim(runtime: AgentRuntime) -> None:
    """等待配额领取运行；退避轮询，权限复核与等待事件按 30 秒节流。

    领取前复核一次报告与资料权限；之后不再逐轮查询，避免 13 个模块以 1 秒间隔
    打满权限查询。``store.claim`` 自身会在取槽事务里锁定报告状态并判断配额。
    """
    await asyncio.to_thread(runtime.check_access)
    attempt = 0
    waited = 0.0
    checked = 0.0
    notified = False
    while True:
        deadline = runtime.run.get("deadline_at")
        if deadline is not None and deadline <= datetime.now(UTC):
            raise TimeoutError("模块总时长预算已耗尽，恢复不会重置时限")
        if await asyncio.to_thread(runtime.claim):
            return
        attempt += 1
        delay = next_claim_delay(attempt, random.random())
        if waited >= CLAIM_WAIT_EVENT_SECONDS and not notified:
            notified = True
            # 只写一条等待事件，不逐轮刷库；等待变长说明配额确实被占满。
            await asyncio.to_thread(
                runtime.event,
                "claim_wait",
                {"seconds": int(waited), "rounds": attempt - 1},
            )
        await asyncio.sleep(delay)
        waited += delay
        if waited - checked >= CLAIM_ACCESS_CHECK_SECONDS:
            checked = waited
            await asyncio.to_thread(runtime.check_access)


def model_recovery_delay(attempt: int, remaining_seconds: float) -> float | None:
    """同一线程内模型不可用的退避；剩余时限不够等待时直接放弃，不睡到超时。

    指数退避 5 秒、15 秒，封顶 30 秒。恢复次数由 ``AgentLimits.max_model_recoveries``
    控制；这里只决定下一次等待多久，不改变路由自身的有限重试。
    """
    delay = min(5.0 * 3 ** min(max(1, attempt) - 1, 2), 30.0)
    return delay if remaining_seconds > delay else None


def prepare_report(db: ReportRepository, report: dict) -> tuple[dict, list[dict]] | None:
    snapshots = report["source_snapshot"] + report["reference_snapshot"]
    if report["status"] == "waiting":
        allowed = db.collections_for_project(report["project_id"])
        if any(s["collection_id"] not in allowed for s in snapshots):
            raise PermissionError("报告固定的知识库关联已撤销")
        live = {s["source_id"]: s for s in db.sources(allowed)}
        if any(s["source_id"] not in live for s in snapshots):
            raise PermissionError("报告中的资料已被删除或替换")
        sources = [live[s["source_id"]] for s in snapshots]
        own = [s for s in sources if s["project_id"] == report["project_id"]]
        missing = [s for s in own if source_state(s) != "ready"]
        usable = [s for s in sources if source_state(s) in {"ready", "partial"}]
        coverage = {
            "mode": "agent_research",
            "partial": bool(missing),
            "files": [
                {"name": s["file_name"], "source_id": s["source_id"], "state": source_state(s)}
                for s in sources
            ],
        }
        db.set_report_coverage(report["id"], coverage)
        if not any(s["project_id"] == report["project_id"] for s in usable) or (
            missing and not report["allow_partial"]
        ):
            if any(source_state(s) in {"failed", "unsupported", "partial"} for s in missing):
                raise ValueError("项目资料未完整解析，请修复后重试或选择部分分析")
            db.defer_report(report["id"], 30)
            return None
        report = report | {
            "source_snapshot": own,
            "reference_snapshot": [s for s in sources if s["project_id"] != report["project_id"]],
            "coverage": coverage,
        }
    else:
        usable = [s for s in snapshots if source_state(s) in {"ready", "partial"}]
    check_report_access(db, report, usable)
    with db.transaction() as session:
        if not session.start_report(
            report["id"],
            source_snapshot=report["source_snapshot"],
            reference_snapshot=report["reference_snapshot"],
        ):
            raise InterruptedError("报告已取消")
        session.requeue_unlocked_runs(report["id"])
        # 全部模块先落库，避免控制器中断导致后半模块从未进入运行管理。
        for module in session.ensure_modules(report["id"], MODULES):
            if module["status"] not in {"pending", "running"}:
                continue
            session.ensure_module_run(
                module["id"],
                company_id=db.company_id,
                thread_id=f"analysis:{report['id']}:{module['id']}:1",
                limits=report["runtime_settings"],
            )
    return report, usable


async def expand_evidence(
    items: list[dict],
    *,
    seen: dict,
    sources: list[dict],
    read,
) -> dict:
    """校验要能看到引文在原文里的物理邻域，不能只看本模块读过的块。

    章节标题（如前附表、第六章）往往没被模块读取，只给已读块会把正确归属判成无依据；
    这里按引文所属资料补读整份原文用于取窗口。引文本身仍由 validate_items 限定为
    已读块，所以不会放宽“只能引用读过的原文”这条底线。读不到时退回已读块，
    校验仍可进行，只是归属证据更少。
    """
    wanted: set[object] = set()
    for item in items:
        for value in item.get("values", []):
            for ref in value.get("citations", []):
                if not isinstance(ref, dict):
                    continue
                source_id = ref.get("source_id")
                if source_id is None:
                    # 引文缺少 source_id 时用已读块回查所属资料。
                    row = seen.get(str(ref.get("block_id")))
                    source_id = row.get("source_id") if isinstance(row, dict) else None
                if source_id is not None:
                    wanted.add(source_id)
    evidence = dict(seen)
    for source in sources:
        if source["source_id"] not in wanted:
            continue
        try:
            rows = await read(source)
        except Exception:
            logger.warning(
                "evidence.fail",
                source_id=source["source_id"],
                exc_info=True,
                fallback="use_already_read_evidence",
            )
            continue
        for row in rows:
            evidence.setdefault(str(row["block_id"]), row)
    return evidence


def summarize(modules: list[dict]) -> list[dict]:
    """只合并等价的字段断言；不按上传时间裁决冲突，不同结论各自保留。"""
    grouped = {}
    for module in modules:
        # 部分完成的模块只含已核实条目，同样进入报告摘要并标注来源。
        if module["status"] not in {"completed", "partial"}:
            continue
        for item in module["items"]:
            key = (
                normalized(item["field"]),
                normalized(item.get("group", "")),
                json.dumps(item.get("values", []), sort_keys=True, ensure_ascii=False, default=str),
                normalized(item.get("note", "")),
            )
            if key not in grouped:
                grouped[key] = copy.deepcopy(item) | {"module_keys": [module["module_key"]]}
                continue
            result = grouped[key]
            if module["module_key"] not in result["module_keys"]:
                result["module_keys"].append(module["module_key"])
            # 同一字段的多个值按顺序一一对应，合并各自引用而不改动值本身。
            for target, source in zip(result["values"], item["values"], strict=True):
                for ref in source["citations"]:
                    if ref not in target["citations"]:
                        target["citations"].append(ref)
            if item.get("verification") != "supported":
                result["verification"] = item.get("verification", "unsupported")
    return list(grouped.values())


class AnalysisExecutor:
    """报告执行用例；队列入口与隔离验收使用同一套规则及依赖。"""

    def __init__(
        self,
        db: ReportRepository,
        *,
        model_factory: Callable[..., RoutingModel],
        embedding_gateway: Callable[[dict], EmbeddingModel],
        rerank_gateway: Callable[[dict], RerankModel],
        checkpoints: Callable[[], AbstractAsyncContextManager[Any]],
        archive: AnalysisArchive | None = None,
    ) -> None:
        # 外部能力由装配点选择，业务流程无需认识 Celery 或数据库连接。
        self.db = db
        self.model_factory = model_factory
        self.embedding_gateway = embedding_gateway
        self.rerank_gateway = rerank_gateway
        self.checkpoints = checkpoints
        self.archive = archive

    async def execute_module(self, report: dict, module: dict, sources: list[dict]) -> None:
        # 按项目、报告和专题直接定位；协程与线程继承独立上下文，避免并发项目串号。
        with bind_context(
            project_id=report.get("project_id"),
            report_id=report["id"],
            module_key=module.get("module_key"),
        ):
            await self._execute_module(report, module, sources)

    async def _execute_module(self, report: dict, module: dict, sources: list[dict]) -> None:
        db = self.db
        runtime = (AgentRuntime(db, report, module, sources, archive=self.archive)
                   if self.archive is not None else AgentRuntime(db, report, module, sources))
        model = None
        task = None
        state = {}
        started = time.monotonic()
        try:
            await wait_for_claim(runtime)
            queue_ms = int((time.monotonic() - started) * 1000)

            async def authorize():
                await asyncio.to_thread(runtime.guard)

            async def begin_model(record):
                await asyncio.to_thread(runtime.reserve, "model",
                                        f"{record.invocation_id}:{record.request_ordinal}")

            async def reserve_tool():
                await asyncio.to_thread(runtime.reserve, "tool")

            async def begin_tool(call_key):
                return await asyncio.to_thread(runtime.reserve, "tool", call_key)

            async def save(state):
                await asyncio.to_thread(runtime.save, state)

            async def retrieve(selected, query):
                return await retrieve_chunks(
                    db,
                    selected,
                    query,
                    lambda: None,
                    self.embedding_gateway,
                    self.rerank_gateway,
                    embedding_timeout=15,
                    min_similarity=limits.similarity_threshold,
                    # 一次取回候选窗口供同一查询分页，避免改同义词反复检索。
                    max_results=limits.search_window,
                )

            async def read_window(source, offset, limit):
                return await asyncio.to_thread(db.read_chunk_window, source, offset, limit)

            state = runtime.run["state"]
            state.setdefault("execution_mode", "restart" if runtime.run.get("attempt", 1) == 1
                             else "resume")
            # 与补跑和页面使用同一完整输入快照，部分资料尚不可读时也不丢失其身份。
            state["quality_input_signature"] = source_signature(
                report["source_snapshot"] + report["reference_snapshot"],
            )
            from tender.application.analysis.protocol import PROTOCOL_VERSION

            if report["skill_snapshot"].get("__analysis_flow_version__") != PROTOCOL_VERSION:
                raise ValueError("解析协议已升级，旧检查点不能恢复；请重新创建报告")
            limits = AgentLimits(**runtime.run["limits"])
            prior = state.get("research", {})
            # 历史attempt已交付的小块身份不能被新分块重新解释；从零重解析始终使用新大块。
            legacy_sources = {row["source_id"] for key, row in prior.get("seen", {}).items()
                              if key == (f"s{row['source_id']}r{row['parse_run_id']}"
                                         f"c{row['offset']}" )}
            sources = [{**source, "chunk_format_version": "1"}
                       if source["source_id"] in legacy_sources else source for source in sources]
            research = ResearchSession(
                sources,
                report["project_id"],
                retrieve,
                read_window,
                authorize,
                limits,
                seen=prior.get("seen", {}),
                events=prior.get("events", []),
                tool_calls=prior.get("tool_calls", 0),
                dependencies=prior.get("dependencies", {}),
            )
            model = await asyncio.to_thread(
                self.model_factory,
                "analysis",
                f"analysis:{report['id']}:{module['module_key']}:{module['attempt']}",
                before_call=begin_model,
                invocation_store=runtime.store,
                output_limit=limits.max_output_tokens,
                rate_limit_backoff_seconds=limits.rate_limit_backoff_seconds,
                rate_limit_max_wait_seconds=limits.rate_limit_max_wait_seconds,
                on_call=runtime.record_call,
                remaining_seconds=lambda: max(
                    0, (runtime.run["deadline_at"] - datetime.now(UTC)).total_seconds()
                ),
            )

            async def work():
                async def review_all(payload):
                    from tender.application.analysis.review import review_combined
                    from tender.application.knowledge.content import citation

                    result = await review_combined(model, payload, limits=limits)
                    await authorize()
                    selected = {bid for verdict in result["reviews"].values()
                                if verdict["supported"] for bid in verdict["block_ids"]}
                    locations = {}
                    for cid in selected:
                        raw = research.seen[cid]
                        ref = citation(raw, raw["content"])
                        locations[cid] = await asyncio.to_thread(db.resolve, ref)
                    result["locations"] = locations
                    return result

                async with self.checkpoints() as saver:
                    graph, files = build_module_agent(
                        key=module["module_key"],
                        model=RoutedAgentModel(router=model),
                        research=research,
                        state=state,
                        snapshot=report["skill_snapshot"],
                        checkpointer=saver,
                        reserve_tool=reserve_tool,
                        begin_tool=begin_tool,
                        save=save,
                        budget_status=lambda: {
                            "seconds_remaining": max(
                                0,
                                int(
                                    (runtime.run["deadline_at"] - datetime.now(UTC)).total_seconds()
                                ),
                            ),
                            "finish_reserve_seconds": min(300, int(limits.timeout_seconds * 0.25)),
                            "model_calls_remaining": limits.max_model_calls
                            - (runtime.run.get("successful_model_calls") or 0),
                            "tool_calls_remaining": limits.max_tool_calls
                            - (runtime.run.get("successful_tool_calls") or 0),
                        },
                        review_combined=review_all,
                        lots=report["lot_settings"],
                        event=runtime.event,
                        # 项目和标段品类可能不同，首次推理前加载全部已明确品类的细则。
                        categories=[
                            report["category"],
                            *[
                                lot.get("category")
                                for lot in report["lot_settings"]
                                if lot.get("category")
                            ],
                        ],
                    )
                    # 同一次执行恢复必须沿用已落库的次数，不能因Worker重启重获额度。
                    attempts = state.get("model_unavailable_retries", 0)
                    while True:
                        try:
                            await invoke_module(
                                graph,
                                files,
                                thread_id=runtime.run["thread_id"],
                                state=state,
                                save=save,
                                max_retries=limits.max_subagent_retries,
                                # 每轮含检索、模型、工具和摘要节点，步数随预算增长而非固定256。
                                recursion_limit=max(
                                    256, 4 * (limits.max_model_calls + limits.max_tool_calls)
                                ),
                                task=(
                                    f"分析模块：{MODULES[module['module_key']]}。项目设置："
                                    + encode(
                                        {
                                            "category": report["category"],
                                            "topics": report["topics"],
                                            "lots": report["lot_settings"],
                                        }
                                    )
                                    + "。运行时已加载当前Skill，先列出资料，"
                                    "自主检索本模块条件并核对补充文件。"
                                ),
                            )
                            break
                        except ModelUnavailable as exc:
                            if exc.invocation_exhausted:
                                # 路由已耗尽原窗口，恢复只会读取同一失败；直接保留成果收尾。
                                raise
                            # 未耗尽窗口的临时故障按检查点在同一 thread/attempt 内恢复，
                            # 不修改 invoke_module 的重试元组，避免与路由重试次数相乘。
                            if attempts >= limits.max_model_recoveries:
                                raise
                            remaining = (
                                runtime.run["deadline_at"] - datetime.now(UTC)
                            ).total_seconds()
                            delay = model_recovery_delay(attempts + 1, remaining)
                            if delay is None:
                                raise
                            attempts += 1
                            # 计数先落库，恢复过程再失败时补跑仍能看到已用掉的恢复次数。
                            state["model_unavailable_retries"] = attempts
                            await save(state)
                            await asyncio.to_thread(
                                runtime.event,
                                "model_unavailable_recovery",
                                {
                                    "attempt": attempts,
                                    "delay_seconds": round(delay, 1),
                                    "deadline_remaining": int(remaining),
                                    "error": error_detail(str(exc)),
                                },
                            )
                            logger.warning(
                                "module.model_recovery",
                                attempt=attempts,
                                delay_seconds=round(delay, 1),
                                deadline_remaining=int(remaining),
                                error=error_detail(str(exc)),
                            )
                            await asyncio.sleep(delay)
                await authorize()
                if "draft" not in state:
                    raise ValueError("子 Agent 结束但没有提交通过校验的分析")
                draft = state["draft"]
                # 字段与关系的支持性校验都在子 Agent 的提交工具内完成，此处只做最终权限复核。
                validate_project_claims(draft["fields"], report["project_id"])
                await asyncio.to_thread(runtime.finish, "completed", draft=draft, state=state)
                logger.info(
                    "module.result",
                    status="completed",
                    execution_mode=state["execution_mode"],
                    quality_status=state.get("quality_status", "unknown"),
                    attempt=module.get("attempt"),
                    queue_ms=queue_ms,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    item_count=len(draft["fields"]),
                    evidence_count=len(research.seen),
                    gap_count=len(state.get("business_gaps", [])),
                    model_calls=runtime.run["model_calls"],
                    tool_calls=runtime.run["tool_calls"],
                    **TopicSearch.summary(state),
                )

            task = asyncio.create_task(work())
            heartbeats = 0
            while not task.done():
                await asyncio.wait({task}, timeout=HEARTBEAT_INTERVAL_SECONDS)
                if not task.done():
                    heartbeats += 1
                    # 两次心跳做一次完整撤权/取消复核；其余心跳只续租并校验所有权与时限。
                    await asyncio.to_thread(
                        runtime.heartbeat, heartbeats % FULL_ACCESS_HEARTBEATS == 0
                    )
            await task
        except (VerificationUnavailable, ModelUnavailable, TopicIncomplete) as exc:
            # 校验网关或模型恢复不可用不等于分析无成果：只发布已核实条目。
            await self._settle_incomplete(runtime, state, task, started, exc)
        except (Exception, asyncio.CancelledError) as exc:
            if isinstance(exc, (TimeoutError, ModelBudgetExhausted, BudgetExhausted)) and enabled(
                report.get("skill_snapshot", {})
            ):
                await self._settle_incomplete(runtime, state, task, started, exc)
                return
            if task and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
            canceled = isinstance(exc, (InterruptedError, asyncio.CancelledError))
            status = "canceled" if canceled else "failed"
            log = logger.info if canceled else logger.error
            log(
                "module.cancel" if canceled else "module.fail",
                duration_ms=int((time.monotonic() - started) * 1000),
                reason=error_detail(str(exc)) if canceled else None,
                saved_item_count=sum(
                    i.get("verification") == "supported" for i in state.get("staged_items", [])
                ),
                **TopicSearch.summary(state),
                # 适配器已对业务异常脱敏；不串联原始 SDK 异常，以免回显其请求或凭证。
                exception=None
                if canceled
                else "".join(traceback.format_exception(exc, chain=False)),
            )
            # 尚在排队的任务也必须形成终态，避免被取消后仍显示等待配额。
            await asyncio.to_thread(runtime.abandon, status, str(exc)[:1000])
            if isinstance(exc, asyncio.CancelledError):
                raise

        finally:
            try:
                if model:
                    try:
                        await model.aclose()
                    except Exception as exc:
                        logger.warning("client.close_fail", exc_info=True)
                        await asyncio.to_thread(
                            runtime.event, "client_close_failed", {"error_type": type(exc).__name__}
                        )
            finally:
                # SDK关闭异常也必须释放配额，否则一个失败模块会永久堵住其它报告。
                await asyncio.to_thread(runtime.release)

    async def _settle_incomplete(
        self,
        runtime: AgentRuntime,
        state: dict,
        task: asyncio.Task | None,
        started: float,
        exc: Exception,
    ) -> None:
        """模型或校验不可用时收尾：有已核实成果才是 partial，否则明确失败。"""
        reason = str(exc)
        state["quality_status"] = "needs_review"
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        from tender.application.analysis.state import published_items

        supported = len(published_items(state, final=bool(state.get("topic_flow"))))
        if state.get("topic_flow"):
            state["business_gaps"] = [*state.get("business_gaps", []), {
                "key": "execution:incomplete", "topic": "运行收尾",
                "scope": {"kind": "unknown", "lot_refs": []},
                "code": "search_exhausted", "detail": reason[:2000],
            }]
        if supported:
            await asyncio.to_thread(runtime.finish, "partial", reason[:1000], state=state)
            await asyncio.to_thread(
                runtime.event,
                "partial_publish",
                {"item_count": supported, "reason_type": type(exc).__name__},
            )
            logger.warning(
                "module.partial",
                duration_ms=int((time.monotonic() - started) * 1000),
                saved_item_count=supported,
                pending_count=state.get("verification_degraded", {}).get("pending_count"),
                gap_count=len(state.get("business_gaps", [])),
                reason=error_detail(reason),
                **TopicSearch.summary(state),
            )
        else:
            if state.get("topic_flow"):
                await asyncio.to_thread(runtime.finish, "failed", reason[:1000], state=state)
            else:
                await asyncio.to_thread(runtime.abandon, "failed", reason[:1000])
            logger.error(
                "module.fail",
                duration_ms=int((time.monotonic() - started) * 1000),
                saved_item_count=0,
                # 显式保留脱敏原因，避免仅依赖500字符异常摘要丢失后备模型的错误。
                error=error_detail(reason),
                **TopicSearch.summary(state),
                # 业务异常已脱敏；不串联原始 SDK 原因，避免回显请求或凭证。
                exception="".join(traceback.format_exception(exc, chain=False)),
            )

    async def analyze_report(self, report: dict) -> None:
        with bind_context(project_id=report.get("project_id"), report_id=report["id"]):
            await self._analyze_report(report)

    async def _analyze_report(self, report: dict) -> None:
        db = self.db
        tasks = []
        started = time.monotonic()
        try:
            prepared = await asyncio.to_thread(prepare_report, db, report)
            if prepared is None:
                return
            report, sources = prepared
            modules = db.report_active_modules(report["id"])
            tasks = [
                asyncio.create_task(self.execute_module(report, module, sources))
                for module in modules
            ]
            while tasks and not all(t.done() for t in tasks):
                done, _ = await asyncio.wait(tasks, timeout=1, return_when=asyncio.FIRST_EXCEPTION)
                # 收尾异常可能留下占据队首的运行，必须先检查异常再续租；等所有模块
                # 结束才 gather 会让其余模块永久排队，控制器却一直显示仍在执行。
                for finished_task in done:
                    finished_task.result()
                await asyncio.to_thread(check_report_access, db, report, sources)
                await asyncio.to_thread(db.renew_report_lease, report["id"], 300, status="running")
            await asyncio.gather(*tasks)
            rows = db.report_modules(report["id"])
            # 部分完成的模块仍有已核实成果，属于可用模块；完全没有可用成果才算失败。
            usable = any(r["status"] in {"completed", "partial"} for r in rows)
            partial = report["coverage"].get("partial") or any(
                r["status"] != "completed" for r in rows
            )
            status = "failed" if not usable else "partial" if partial else "completed"
            db.finish_report(
                report["id"],
                status=status,
                summary=summarize(rows),
                error="没有模块完成，请查看各模块错误并补跑" if not usable else None,
            )
            log = logger.info if status == "completed" else logger.warning
            log(
                "report.result",
                status=status,
                duration_ms=int((time.monotonic() - started) * 1000),
                completed_modules=sum(r["status"] == "completed" for r in rows),
                partial_modules=sum(r["status"] == "partial" for r in rows),
                module_count=len(rows),
                source_count=len(sources),
            )
        except (Exception, asyncio.CancelledError) as exc:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            log = (
                logger.info
                if isinstance(exc, (InterruptedError, asyncio.CancelledError))
                else logger.error
            )
            log(
                "report.abort",
                duration_ms=int((time.monotonic() - started) * 1000),
                exception="".join(traceback.format_exception(exc, chain=False)),
            )
            db.finish_task("report", report["id"], "failed", str(exc)[:1000])
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            # 取消或失败时各模块已由上面的异常分支等待退出，再固定已核实成果。
            await asyncio.to_thread(publish_data_snapshot, db, report["id"])

    async def execute(self, report_id: int) -> None:
        db = self.db
        if db.accessible_report_status(report_id) not in {"waiting", "pending", "running"}:
            return
        from tender.application.analysis.contract import RUNTIME_VERSION
        from tender.application.shared.schema_guard import missing_schema

        # ORM 全列读取也会访问新列，所以先只读旧版已有的状态列，再核对结构；
        # 否则缺列异常会在门禁前抛出，报告无法记录失败原因并结束派发。
        absent = missing_schema(db)
        if absent:
            db.finish_task(
                "report",
                report_id,
                "failed",
                "数据库结构落后于当前代码，请先执行数据库迁移；缺少 " + "、".join(absent),
            )
            return
        report = db.report_for_analysis(report_id)
        if report is None or report["status"] not in {"waiting", "pending", "running"}:
            return
        # 旧的固定字段解析流程已下线：历史报告只读展示，不能继续执行；版本不一致同样拒绝。
        if report["runtime_version"] != RUNTIME_VERSION:
            db.finish_task(
                "report", report_id, "failed", "报告使用已下线的解析流程，请重新发起分析"
            )
            return
        await self.analyze_report(report)
