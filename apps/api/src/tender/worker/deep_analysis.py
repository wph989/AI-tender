"""确定性调度全部模块，模块内部的阅读与检索由独立 DeepAgents 子图决定。"""

from __future__ import annotations

import asyncio
import copy
import json
import time
import traceback
from contextlib import suppress
from datetime import UTC, datetime

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from tender.application.agent_checkpoints import checkpoint_dsn
from tender.application.agent_runtime import AgentRuntime, check_report_access
from tender.application.analysis_data_store import publish_data_snapshot
from tender.application.analysis_research import AgentLimits, ResearchSession
from tender.application.analysis_skills import MODULES, verify_items
from tender.application.deep_analysis import (
    RoutedAgentModel,
    build_module_agent,
    invoke_module,
    validate_project_claims,
)
from tender.application.knowledge import encode, normalized, source_state
from tender.application.knowledge_retrieval import retrieve_chunks
from tender.core.di import create_embedding_gateway, create_rerank_gateway
from tender.core.error_details import error_detail
from tender.core.logging import bind_context, get_logger
from tender.ports.repository.knowledge import KnowledgeStore
from tender.worker.model_routing import _routing_model

logger = get_logger(__name__)


def prepare_report(db: KnowledgeStore, report: dict) -> tuple[dict, list[dict]] | None:
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
                "evidence.fail", source_id=source["source_id"], exc_info=True,
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
        if module["status"] != "completed":
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


async def execute_module(
    db: KnowledgeStore, report: dict, module: dict, sources: list[dict]
) -> None:
    # module 是运行账行，id 是 run_id；独立绑定可避免并发专题和后续任务串号。
    with bind_context(
        report_id=report["id"], run_id=module["id"], module_key=module.get("module_key"),
    ):
        await _execute_module(db, report, module, sources)


async def _execute_module(
    db: KnowledgeStore, report: dict, module: dict, sources: list[dict]
) -> None:
    runtime = AgentRuntime(db, report, module, sources)
    model = None
    task = None
    state = {}
    started = time.monotonic()
    try:
        logger.info("module.queued")
        while not await asyncio.to_thread(runtime.claim):
            await asyncio.sleep(1)

        async def authorize():
            await asyncio.to_thread(runtime.guard)

        async def reserve_model():
            await asyncio.to_thread(runtime.reserve, "model")

        async def reserve_tool():
            await asyncio.to_thread(runtime.reserve, "tool")

        async def save(state):
            await asyncio.to_thread(runtime.save, state)

        async def retrieve(selected, query):
            return await retrieve_chunks(
                db,
                selected,
                query,
                lambda: None,
                create_embedding_gateway,
                create_rerank_gateway,
                embedding_timeout=15,
                min_similarity=limits.similarity_threshold,
                max_results=limits.max_search_results,
            )

        async def read(source):
            return await asyncio.to_thread(db.readable_chunks, source)

        state = runtime.run["state"]
        limits = AgentLimits(**runtime.run["limits"])
        logger.info(
            "module.start", resumed=module.get("started_at") is not None,
            attempt=module.get("attempt"),
            queue_ms=int((time.monotonic() - started) * 1000), source_count=len(sources),
            thread_id=runtime.run["thread_id"], timeout_seconds=limits.timeout_seconds,
            max_model_calls=limits.max_model_calls, max_tool_calls=limits.max_tool_calls,
        )
        prior = state.get("research", {})
        research = ResearchSession(
            sources,
            report["project_id"],
            retrieve,
            read,
            authorize,
            limits,
            seen=prior.get("seen", {}),
            events=prior.get("events", []),
            tool_calls=prior.get("tool_calls", 0),
        )
        model = await asyncio.to_thread(
            _routing_model,
            "analysis",
            f"analysis:{report['id']}:{module['module_key']}:{module['attempt']}",
            before_request=reserve_model,
            output_limit=limits.max_output_tokens,
            extra_retries_limit=2,
            rate_limit_backoff_seconds=limits.rate_limit_backoff_seconds,
            rate_limit_max_wait_seconds=limits.rate_limit_max_wait_seconds,
            on_call=runtime.record_call,
            remaining_seconds=lambda: max(
                0, (runtime.run["deadline_at"] - datetime.now(UTC)).total_seconds()
            ),
        )

        async def work():
            async def verification_evidence(items):
                return await expand_evidence(items, seen=research.seen, sources=sources, read=read)

            async def review_support(items):
                # 校验需要同块原文与邻近块才能判断章节归属，不能只看摘录文本。
                # 结论（supported / verification_issues）由 verify_items 写在条目上，
                # 由 Agent 图的校验节点按条目归因到字段纠正次数；整批抛错会让同批字段反复重审。
                evidence = await verification_evidence(items)
                await verify_items(
                    model, items, explain=True, evidence=evidence, select_evidence=True
                )
                # 只对最终被选中且通过支持性校验的ID解析位置，模型不能提供或修改定位字段。
                await authorize()
                resolved = {}
                for item in items:
                    if item.get("verification") != "supported":
                        continue
                    for value in item["values"]:
                        for ref in value["citations"]:
                            key = str(ref["block_id"])
                            if key not in resolved:
                                resolved[key] = await asyncio.to_thread(db.resolve, ref)
                            ref.update(
                                {k: resolved[key][k] for k in ("page_no", "file_name", "bbox")}
                            )

            async with AsyncPostgresSaver.from_conn_string(checkpoint_dsn()) as saver:
                graph, files = build_module_agent(
                    key=module["module_key"],
                    model=RoutedAgentModel(router=model),
                    research=research,
                    state=state,
                    snapshot=report["skill_snapshot"],
                    checkpointer=saver,
                    reserve_tool=reserve_tool,
                    save=save,
                    budget_status=lambda: {
                        "seconds_remaining": max(
                            0, int((runtime.run["deadline_at"] - datetime.now(UTC)).total_seconds())
                        ),
                        "finish_reserve_seconds": min(300, int(limits.timeout_seconds * 0.25)),
                        "model_calls_remaining": limits.max_model_calls
                        - runtime.run["model_calls"],
                        "tool_calls_remaining": limits.max_tool_calls - runtime.run["tool_calls"],
                    },
                    review_support=review_support,
                    # 项目和标段品类可能不同，首次推理前加载全部已明确品类的细则。
                    categories=[report["category"], *[
                        lot.get("category") for lot in report["lot_settings"]
                        if lot.get("category")
                    ]],
                )
                await invoke_module(
                    graph,
                    files,
                    thread_id=runtime.run["thread_id"],
                    state=state,
                    save=save,
                    max_retries=limits.max_subagent_retries,
                    # 每轮可能包含检索、模型、工具和摘要节点，步数随预算增长而非固定卡在256。
                    recursion_limit=max(256, 4 * (limits.max_model_calls + limits.max_tool_calls)),
                    task=(
                        f"分析模块：{MODULES[module['module_key']]}。项目设置："
                        + encode(
                            {
                                "category": report["category"],
                                "topics": report["topics"],
                                "lots": report["lot_settings"],
                            }
                        )
                        + "。运行时已加载当前Skill，先列出资料，自主检索本模块条件并核对补充文件。"
                    ),
                )
            await authorize()
            if "draft" not in state:
                raise ValueError("子 Agent 结束但没有提交通过校验的分析")
            draft = state["draft"]
            # 字段与关系的支持性校验都在子 Agent 的提交工具内完成，此处只做最终权限复核。
            validate_project_claims(draft["fields"], report["project_id"])
            await asyncio.to_thread(runtime.finish, "completed", draft=draft)
            logger.info(
                "module.end", duration_ms=int((time.monotonic() - started) * 1000),
                item_count=len(draft["fields"]), evidence_count=len(research.seen),
                gap_count=len(state.get("business_gaps", [])),
                model_calls=runtime.run["model_calls"], tool_calls=runtime.run["tool_calls"],
            )

        task = asyncio.create_task(work())
        while not task.done():
            await asyncio.wait({task}, timeout=1)
            if not task.done():
                await asyncio.to_thread(runtime.heartbeat)
        await task
    except (Exception, asyncio.CancelledError) as exc:
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
            saved_item_count=sum(i.get("verification") == "supported"
                                 for i in state.get("staged_items", [])),
            # 适配器已对业务异常脱敏；不串联原始 SDK 异常，以免回显其请求或凭证。
            exception=None if canceled else "".join(traceback.format_exception(exc, chain=False)),
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


async def analyze_report(db: KnowledgeStore, report: dict) -> None:
    with bind_context(report_id=report["id"]):
        await _analyze_report(db, report)


async def _analyze_report(db: KnowledgeStore, report: dict) -> None:
    tasks = []
    started = time.monotonic()
    try:
        prepared = await asyncio.to_thread(prepare_report, db, report)
        if prepared is None:
            return
        report, sources = prepared
        modules = db.report_active_modules(report["id"])
        logger.info("report.start", project_id=report.get("project_id"),
                    module_count=len(modules), source_count=len(sources))
        tasks = [
            asyncio.create_task(execute_module(db, report, module, sources)) for module in modules
        ]
        while tasks and not all(t.done() for t in tasks):
            done, _ = await asyncio.wait(
                tasks, timeout=1, return_when=asyncio.FIRST_EXCEPTION
            )
            # 收尾异常可能留下占据队首的运行，必须先检查异常再续租；等所有模块
            # 结束才 gather 会让其余模块永久排队，控制器却一直显示仍在执行。
            for finished_task in done:
                finished_task.result()
            await asyncio.to_thread(check_report_access, db, report, sources)
            await asyncio.to_thread(db.renew_report_lease, report["id"], 300, status="running")
        await asyncio.gather(*tasks)
        rows = db.report_modules(report["id"])
        partial = report["coverage"].get("partial") or any(r["status"] != "completed" for r in rows)
        completed = any(r["status"] == "completed" for r in rows)
        status = "failed" if not completed else "partial" if partial else "completed"
        db.finish_report(
            report["id"],
            status=status,
            summary=summarize(rows),
            error="没有模块完成，请查看各模块错误并补跑" if not completed else None,
        )
        log = logger.info if status == "completed" else logger.warning
        log("report.end", status=status,
            duration_ms=int((time.monotonic() - started) * 1000),
            completed_modules=sum(r["status"] == "completed" for r in rows), module_count=len(rows))
    except (Exception, asyncio.CancelledError) as exc:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        log = (
            logger.info if isinstance(exc, (InterruptedError, asyncio.CancelledError))
            else logger.error
        )
        log(
            "report.abort",
            exception="".join(traceback.format_exception(exc, chain=False)),
        )
        db.fail_report(report["id"], str(exc)[:1000])
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        # 取消或失败时各模块已由上面的异常分支等待退出，再固定已核实成果。
        await asyncio.to_thread(publish_data_snapshot, db, report["id"])
