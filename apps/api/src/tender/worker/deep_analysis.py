"""确定性调度全部模块，模块内部的阅读与检索由独立 DeepAgents 子图决定。"""

from __future__ import annotations

import asyncio
import copy
import json
from contextlib import suppress
from datetime import UTC, datetime

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import text

from tender.application.agent_checkpoints import checkpoint_dsn
from tender.application.agent_runtime import (
    AgentRuntime,
    check_report_access,
    requeue_unlocked_runs,
)
from tender.application.analysis_research import AgentLimits, ResearchSession
from tender.application.analysis_skills import MODULES, verify_items
from tender.application.deep_analysis import (
    RoutedAgentModel,
    build_module_agent,
    invoke_module,
    validate_project_claims,
)
from tender.application.knowledge import normalized
from tender.application.knowledge_retrieval import retrieve_chunks
from tender.application.knowledge_store import KnowledgeStore, encode, source_state
from tender.core.di import create_embedding_gateway, create_rerank_gateway
from tender.worker.extraction import _routing_model


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
        db.execute(
            "UPDATE analysis_report SET coverage=CAST(:coverage AS JSONB) WHERE id=:id",
            {"id": report["id"], "coverage": encode(coverage)},
        )
        if not any(s["project_id"] == report["project_id"] for s in usable) or (
            missing and not report["allow_partial"]
        ):
            if any(source_state(s) in {"failed", "unsupported", "partial"} for s in missing):
                raise ValueError("项目资料未完整解析，请修复后重试或选择部分分析")
            db.execute(
                """UPDATE analysis_report SET lease_until=now()+interval '30 seconds'
                WHERE id=:id AND status='waiting'""",
                {"id": report["id"]},
            )
            return None
        report = report | {
            "source_snapshot": own,
            "reference_snapshot": [s for s in sources if s["project_id"] != report["project_id"]],
            "coverage": coverage,
        }
    else:
        usable = [s for s in snapshots if source_state(s) in {"ready", "partial"}]
    check_report_access(db, report, usable)
    with db.engine.begin() as conn:
        row = conn.execute(
            text("""UPDATE analysis_report SET status='running',
            source_snapshot=CAST(:sources AS JSONB),reference_snapshot=CAST(:references AS JSONB)
            WHERE id=:id AND status IN ('waiting','pending','running') RETURNING id"""),
            {
                "id": report["id"],
                "sources": encode(report["source_snapshot"]),
                "references": encode(report["reference_snapshot"]),
            },
        ).first()
        if not row:
            raise InterruptedError("报告已取消")
        requeue_unlocked_runs(conn, report["id"])
        # 全部模块先落库，避免控制器中断导致后半模块从未进入运行管理。
        for key, title in MODULES.items():
            module = (
                conn.execute(
                    text("""INSERT INTO analysis_module(report_id,module_key,title)
                VALUES (:report,:key,:title) ON CONFLICT(report_id,module_key)
                DO UPDATE SET title=EXCLUDED.title RETURNING id,status"""),
                    {"report": report["id"], "key": key, "title": title},
                )
                .mappings()
                .one()
            )
            if module["status"] not in {"pending", "running"}:
                continue
            conn.execute(
                text("""INSERT INTO agent_module_run
                (module_id,company_id,thread_id,limits)
                VALUES (:module,:company,:thread,CAST(:limits AS JSONB))
                ON CONFLICT(module_id,attempt) DO NOTHING"""),
                {
                    "module": module["id"],
                    "company": db.company_id,
                    "thread": f"analysis:{report['id']}:{module['id']}:1",
                    "limits": encode(report["runtime_settings"]),
                },
            )
    return report, usable


def summarize(modules: list[dict]) -> list[dict]:
    """只合并等价断言；不同结论连同各自引文保留，不按上传时间裁决冲突。"""
    grouped = {}
    for module in modules:
        if module["status"] != "completed":
            continue
        for item in module["items"]:
            key = (
                item["kind"],
                normalized(item["title"]),
                normalized(item["text"]),
                json.dumps(item.get("cells", {}), sort_keys=True, ensure_ascii=False),
            )
            if key not in grouped:
                grouped[key] = copy.deepcopy(item) | {"module_keys": [module["module_key"]]}
                continue
            result = grouped[key]
            if module["module_key"] not in result["module_keys"]:
                result["module_keys"].append(module["module_key"])
            for ref in item["citations"]:
                if ref not in result["citations"]:
                    result["citations"].append(ref)
            if item.get("verification") != "supported":
                result["verification"] = item.get("verification", "unsupported")
    return list(grouped.values())


async def execute_module(
    db: KnowledgeStore, report: dict, module: dict, sources: list[dict]
) -> None:
    runtime = AgentRuntime(db, report, module, sources)
    model = None
    task = None
    try:
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
            )

        async def read(source):
            return await asyncio.to_thread(db.readable_chunks, source)

        state = runtime.run["state"]
        limits = AgentLimits(**runtime.run["limits"])
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
            on_call=runtime.record_call,
            remaining_seconds=lambda: max(
                0, (runtime.run["deadline_at"] - datetime.now(UTC)).total_seconds()
            ),
        )

        async def work():
            async def validate_support(items):
                await verify_items(model, items, explain=True)
                unsupported = [
                    item["title"] + "：" + "；".join(item.get("verification_issues", []))
                    for item in items
                    if item["verification"] != "supported"
                ]
                if unsupported:
                    raise ValueError(
                        "以下条目包含引用未支持的断言，请删除推断、补齐双方引文或移入检索缺口："
                        + "；".join(unsupported)
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
                        "model_calls_remaining": limits.max_model_calls
                        - runtime.run["model_calls"],
                        "tool_calls_remaining": limits.max_tool_calls - runtime.run["tool_calls"],
                    },
                    validate_support=validate_support,
                )
                await invoke_module(
                    graph,
                    files,
                    thread_id=runtime.run["thread_id"],
                    task=(
                        f"分析模块：{MODULES[module['module_key']]}。项目设置："
                        + encode(
                            {
                                "category": report["category"],
                                "topics": report["topics"],
                                "lots": report["lot_settings"],
                            }
                        )
                        + "。先列出资料与按需读取 Skill，自主检索本模块条件并核对补充文件。"
                    ),
                )
            await authorize()
            if "draft" not in state:
                raise ValueError("子 Agent 结束但没有提交通过校验的分析")
            draft = state["draft"]
            validate_project_claims(draft["items"], report["project_id"])
            if not state.get("verified"):
                if not state.get("items_verified"):
                    await validate_support(draft["items"])
                relation_items = [
                    {
                        "kind": "judgment",
                        "title": r["subject"],
                        "text": r["subject"]
                        + r["predicate"]
                        + r["object"]
                        + "；范围："
                        + r["scope"]
                        + "；条件："
                        + r["condition"],
                        "citations": r["citations"],
                    }
                    for r in draft["relations"]
                ]
                await verify_items(model, relation_items)
                draft["relations"] = [
                    r
                    for r, item in zip(draft["relations"], relation_items, strict=True)
                    if item["verification"] == "supported"
                ]
                state["verified"] = True
                await save(state)
            await asyncio.to_thread(runtime.finish, "completed", draft=draft)

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
        if runtime.lock_connection is not None:
            await asyncio.to_thread(runtime.finish, status, str(exc)[:1000])
        else:
            # 尚在排队的任务也必须形成终态，避免被取消后仍显示等待配额。
            with db.engine.begin() as conn:
                changed = conn.execute(
                    text("""UPDATE agent_module_run SET status=:status,
                    error_message=:error,finished_at=now() WHERE id=:id AND status='pending'
                    RETURNING module_id"""),
                    {"id": module["id"], "status": status, "error": str(exc)[:1000]},
                ).scalar_one_or_none()
                if changed:
                    conn.execute(
                        text(
                            "UPDATE analysis_module SET status=:status,error_message=:error"
                            " WHERE id=:id"
                        ),
                        {"id": changed, "status": status, "error": str(exc)[:1000]},
                    )
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        try:
            if model:
                try:
                    await model.aclose()
                except Exception as exc:
                    await asyncio.to_thread(
                        runtime.event, "client_close_failed", {"error_type": type(exc).__name__}
                    )
        finally:
            # SDK关闭异常也必须释放配额，否则一个失败模块会永久堵住其它报告。
            await asyncio.to_thread(runtime.release)


async def analyze_report(db: KnowledgeStore, report: dict) -> None:
    tasks = []
    try:
        prepared = await asyncio.to_thread(prepare_report, db, report)
        if prepared is None:
            return
        report, sources = prepared
        modules = db.rows(
            """SELECT a.*,m.module_key FROM agent_module_run a
            JOIN analysis_module m ON m.id=a.module_id
            WHERE m.report_id=:id AND a.status IN ('pending','running')
              AND a.attempt=(SELECT max(attempt) FROM agent_module_run WHERE module_id=m.id)
            ORDER BY m.id""",
            {"id": report["id"]},
        )
        tasks = [
            asyncio.create_task(execute_module(db, report, module, sources)) for module in modules
        ]
        while tasks and not all(t.done() for t in tasks):
            await asyncio.wait(tasks, timeout=1)
            await asyncio.to_thread(check_report_access, db, report, sources)
            db.execute(
                """UPDATE analysis_report SET lease_until=now()+interval '5 minutes'
                WHERE id=:id AND status='running'""",
                {"id": report["id"]},
            )
        await asyncio.gather(*tasks)
        rows = db.rows(
            "SELECT * FROM analysis_module WHERE report_id=:id ORDER BY id", {"id": report["id"]}
        )
        partial = report["coverage"].get("partial") or any(r["status"] != "completed" for r in rows)
        completed = any(r["status"] == "completed" for r in rows)
        status = "failed" if not completed else "partial" if partial else "completed"
        db.execute(
            """UPDATE analysis_report SET status=:status,summary=CAST(:summary AS JSONB),
            error_message=:error,finished_at=now(),lease_until=NULL
            WHERE id=:id AND status='running'""",
            {
                "id": report["id"],
                "status": status,
                "error": "没有模块完成，请查看各模块错误并补跑" if not completed else None,
                "summary": encode(summarize(rows)),
            },
        )
    except (Exception, asyncio.CancelledError) as exc:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        db.execute(
            """UPDATE analysis_report SET status='failed',error_message=:error,
            finished_at=now(),lease_until=NULL WHERE id=:id AND status<>'canceled'""",
            {"id": report["id"], "error": str(exc)[:1000]},
        )
        if isinstance(exc, asyncio.CancelledError):
            raise
