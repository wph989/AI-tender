"""知识索引、按版本路由分析及检索问答；历史快照保留原执行契约。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from sqlalchemy import create_engine, text

from tender.application.analysis_skills import (
    MODULES,
    REPORT_CONTRACT,
    DocumentTools,
    json_completion,
    run_module,
    scan_document,
    verify_items,
)
from tender.application.knowledge import validate_items
from tender.application.knowledge_retrieval import retrieve_chunks
from tender.application.knowledge_store import KnowledgeStore, encode, source_state
from tender.application.llm_routing import RoutingModel
from tender.application.model_test_maintenance import maintain_model_tests
from tender.core import settings
from tender.core.di import create_embedding_gateway, create_rerank_gateway
from tender.worker.celery_app import celery_app
from tender.worker.extraction import _advisory_lock, _routing_model

_engine = create_engine(settings.database_url(), pool_pre_ping=True)


def _store() -> KnowledgeStore:
    return KnowledgeStore(_engine, settings.company_id())


def _model(feature: str) -> RoutingModel:
    return _routing_model(feature, feature)


def _touch(table: str, record_id: int) -> None:
    # 表名只来自本模块常量，不能将外部传入的表名拼进 SQL。
    _store().execute(
        f"UPDATE {table} SET lease_until=now()+interval '5 minutes' WHERE id=:id", {"id": record_id}
    )
    if table == "analysis_report":
        rows = _store().rows("SELECT status FROM analysis_report WHERE id=:id", {"id": record_id})
        if not rows or rows[0]["status"] == "canceled":
            raise InterruptedError("分析已取消")


def _finish(table: str, record_id: int, status: str, error: str | None = None) -> None:
    _store().execute(
        f"""UPDATE {table} SET status=:status,error_message=:error,
        finished_at=now(),lease_until=NULL WHERE id=:id AND status<>'canceled' """,
        {"id": record_id, "status": status, "error": error},
    )


@celery_app.task(name="tender.worker.knowledge.dispatch_knowledge")
def dispatch_knowledge() -> None:
    with _advisory_lock("knowledge_dispatch") as acquired:
        if not acquired:
            return
        db = _store()
        maintain_model_tests(_engine)
        collections = db.rows("""SELECT k.id FROM knowledge_collection k
            JOIN project p ON p.id=k.upload_project_id
            WHERE k.company_id=:company_id AND k.deleted_at IS NULL AND p.deleted_at IS NULL""")
        for source in db.sources([r["id"] for r in collections]):
            if source_state(source) not in {"ready", "partial"} or source["index_id"]:
                continue
            db.execute(
                """INSERT INTO knowledge_index (source_id,version_id,run_id)
                VALUES (:source,:version,:run)""",
                {
                    "source": source["source_id"],
                    "version": source["version_id"],
                    "run": source["parse_run_id"],
                },
            )
        # 小批次派发限制消息积压；长任务定期续约，重复消息由会话锁拒绝。
        for table, task in (
            ("knowledge_index", "build_index"),
            ("analysis_report", "analyze_project"),
            ("knowledge_answer", "answer_question"),
        ):
            ownership = (
                "id IN (SELECT i.id FROM knowledge_index i "
                "JOIN knowledge_source s ON s.id=i.source_id "
                "JOIN knowledge_collection k ON k.id=s.collection_id "
                "WHERE k.company_id=:company AND k.deleted_at IS NULL)"
                if table == "knowledge_index"
                else "company_id=:company"
            )
            with _engine.begin() as connection:
                ids = (
                    connection.execute(
                        text(f"""SELECT id FROM {table}
                    WHERE status IN ('pending','waiting','running')
                      AND {ownership}
                      AND (lease_until IS NULL OR lease_until<now()) ORDER BY id LIMIT 2
                    FOR UPDATE SKIP LOCKED"""),
                        {"company": settings.company_id()},
                    )
                    .scalars()
                    .all()
                )
                for record_id in ids:
                    connection.execute(
                        text(
                            f"UPDATE {table} SET lease_until=now()+interval '5 minutes' "
                            "WHERE id=:id"
                        ),
                        {"id": record_id},
                    )
            for record_id in ids:
                celery_app.send_task(f"tender.worker.knowledge.{task}", args=[record_id])


@celery_app.task(name="tender.worker.knowledge.build_index")
def build_index(index_id: int) -> None:
    with _advisory_lock(f"knowledge_index:{index_id}") as acquired:
        if acquired:
            asyncio.run(_build_index(index_id))


async def _build_index(index_id: int) -> None:
    db = _store()
    rows = db.rows(
        """SELECT i.*,s.collection_id FROM knowledge_index i
        JOIN knowledge_source s ON s.id=i.source_id
        JOIN knowledge_collection k ON k.id=s.collection_id
        WHERE i.id=:id AND k.company_id=:company_id""",
        {"id": index_id},
    )
    if not rows or rows[0]["status"] not in {"pending", "running"}:
        return
    index = rows[0]
    client = None
    try:
        db.collection(index["collection_id"])
        source = next(
            (
                s
                for s in db.sources([index["collection_id"]])
                if s["source_id"] == index["source_id"] and s["parse_run_id"] == index["run_id"]
            ),
            None,
        )
        if source is None:
            raise ValueError("资料已更新或删除，请使用最新解析结果重建索引")
        db.execute("UPDATE knowledge_index SET status='running' WHERE id=:id", {"id": index_id})
        chunks = db.readable_chunks(source)
        if not chunks:
            raise ValueError("解析结果没有可索引的文字，请检查原文或使用 OCR 重新解析")
        config = db.embedding_config()
        vectors = None
        if config:
            client = create_embedding_gateway(config)
            vectors = []
            for start in range(0, len(chunks), 16):
                _touch("knowledge_index", index_id)
                vectors.extend(
                    await client.embed([r["content"] for r in chunks[start : start + 16]])
                )
            if vectors and any(len(v) != len(vectors[0]) for v in vectors):
                raise ValueError("向量模型在索引期间改变了维度")
        with _engine.begin() as connection:
            connection.execute(
                text("DELETE FROM knowledge_chunk WHERE index_id=:id"), {"id": index_id}
            )
            for i, chunk in enumerate(chunks):
                connection.execute(
                    text("""INSERT INTO knowledge_chunk
                    (index_id,element_id,ordinal,char_start,char_end,chapter,content,embedding)
                    VALUES (:id,:element_id,:ordinal,:char_start,:char_end,
                            :chapter,:content,:embedding)"""),
                    {**chunk, "id": index_id, "embedding": vectors[i] if vectors else None},
                )
            connection.execute(
                text("""UPDATE knowledge_index SET status='completed',
                embedding_model_id=:model,embedding_signature=:signature,dimension=:dimension,
                error_message=NULL,finished_at=now(),lease_until=NULL WHERE id=:id"""),
                {
                    "id": index_id,
                    "model": config["id"] if config else None,
                    "signature": config["signature"] if config else None,
                    "dimension": len(vectors[0]) if vectors else None,
                },
            )
    except Exception as exc:
        _finish("knowledge_index", index_id, "failed", str(exc)[:1000])
    finally:
        if client:
            await client.aclose()


@celery_app.task(name="tender.worker.knowledge.analyze_project")
def analyze_project(report_id: int) -> None:
    from tender.application.agent_checkpoints import run_async

    with _advisory_lock(f"analysis_report:{report_id}") as acquired:
        if acquired:
            run_async(_analyze_project(report_id))


async def _analyze_project(report_id: int) -> None:
    db = _store()
    rows = db.rows(
        """SELECT r.* FROM analysis_report r JOIN project p ON p.id=r.project_id
        WHERE r.id=:id AND r.company_id=:company_id AND p.deleted_at IS NULL""",
        {"id": report_id},
    )
    if not rows or rows[0]["status"] not in {"waiting", "pending", "running"}:
        return
    report = rows[0]
    if report.get("runtime_version", "legacy") != "legacy":
        from tender.application.deep_analysis import RUNTIME_VERSION
        from tender.worker.deep_analysis import analyze_report

        if report["runtime_version"] != RUNTIME_VERSION:
            _finish("analysis_report", report_id, "failed", "不支持的分析运行时版本")
            return
        await analyze_report(db, report)
        return
    model = _model("analysis")
    try:
        snapshots = report["source_snapshot"]
        if report["status"] == "waiting":
            live = {
                r["source_id"]: r
                for r in db.sources(sorted({r["collection_id"] for r in snapshots}))
            }
            sources = [
                live.get(r["source_id"], r | {"parse_status": "failed", "is_parseable": False})
                for r in snapshots
            ]
            missing = [r for r in sources if source_state(r) != "ready"]
            usable = [r for r in sources if source_state(r) in {"ready", "partial"}]
            coverage = {
                "files": [
                    {"name": r["file_name"], "source_id": r["source_id"], "state": source_state(r)}
                    for r in sources
                ],
                "partial": bool(missing),
                "scanned_blocks": 0,
                "total_blocks": 0,
            }
            db.execute(
                "UPDATE analysis_report SET coverage=CAST(:coverage AS JSONB) WHERE id=:id",
                {"id": report_id, "coverage": encode(coverage)},
            )
            if not usable or (missing and not report["allow_partial"]):
                blocked = [
                    r for r in missing if source_state(r) in {"failed", "unsupported", "partial"}
                ]
                if blocked and (not report["allow_partial"] or len(missing) == len(blocked)):
                    # 已终止的文件任务不会自行恢复；结束等待让用户能修复材料后重新分析。
                    names = "、".join(r["file_name"] for r in blocked)
                    raise ValueError(
                        f"以下资料未完整解析：{names}。请重新处理后重试，或选择部分分析。"
                    )
                db.execute(
                    "UPDATE analysis_report SET lease_until=now()+interval '30 seconds' "
                    "WHERE id=:id",
                    {"id": report_id},
                )
                return
            snapshots = sources
            db.execute(
                """UPDATE analysis_report SET status='running',
                    source_snapshot=CAST(:sources AS JSONB)
                WHERE id=:id AND status<>'canceled' """,
                {"id": report_id, "sources": encode(snapshots)},
            )
        else:
            usable = [r for r in snapshots if source_state(r) in {"ready", "partial"}]
            coverage = report["coverage"]
            db.execute(
                "UPDATE analysis_report SET status='running' WHERE id=:id AND status<>'canceled'",
                {"id": report_id},
            )
        blocks = []
        for source in usable:
            read = db.readable_chunks(source)
            if not read:
                raise ValueError(f"无法读取已固定的原文：{source['file_name']}")
            blocks.extend(read)
        if not blocks:
            raise ValueError("当前材料没有可分析的文字块")

        def checkpoint(scanned: int, total: int) -> None:
            _touch("analysis_report", report_id)
            coverage.update(scanned_blocks=scanned, total_blocks=total)
            db.execute(
                "UPDATE analysis_report SET coverage=CAST(:coverage AS JSONB) WHERE id=:id",
                {"id": report_id, "coverage": encode(coverage)},
            )

        candidates, discoveries = await scan_document(
            model, DocumentTools(blocks), checkpoint, snapshot=report.get("skill_snapshot")
        )
        for key, title in MODULES.items():
            _touch("analysis_report", report_id)
            with _engine.begin() as connection:
                module = dict(
                    connection.execute(
                        text("""INSERT INTO analysis_module (report_id,module_key,title)
                    VALUES (:report,:key,:title) ON CONFLICT (report_id,module_key)
                    DO UPDATE SET title=EXCLUDED.title RETURNING *"""),
                        {"report": report_id, "key": key, "title": title},
                    )
                    .mappings()
                    .one()
                )
            # 重试入口只把用户选中的失败模块置为 pending，未选中的失败项保持原状态。
            # running 则可能来自进程中断，需要恢复；新模块由插入时默认置为 pending。
            if module["status"] in {"completed", "failed"}:
                continue
            db.execute(
                "UPDATE analysis_module SET status='running' WHERE id=:id", {"id": module["id"]}
            )
            try:
                items, relations, trace = await run_module(
                    model,
                    key,
                    blocks,
                    report["category"],
                    report["topics"],
                    report["lot_settings"],
                    candidates[key],
                    lambda: _touch("analysis_report", report_id),
                    snapshot=report.get("skill_snapshot") or None,
                )
                if key == "general_module_parsing":
                    items = await verify_items(model, discoveries) + items
                # 关系单独验证后才用于图谱扩展；路径存在不能自动证明关系成立。
                relation_items = [
                    {
                        "kind": "judgment",
                        "title": r["subject"],
                        "text": r["subject"]
                        + r["predicate"]
                        + r["object"]
                        + "；适用范围："
                        + r["scope"]
                        + "；条件："
                        + r["condition"],
                        "citations": r["citations"],
                    }
                    for r in relations
                ]
                await verify_items(model, relation_items)
                with _engine.begin() as connection:
                    connection.execute(
                        text("""UPDATE analysis_module SET status='completed',
                        items=CAST(:items AS JSONB),
                        trace=CAST(:trace AS JSONB),error_message=NULL WHERE id=:id"""),
                        {"id": module["id"], "items": encode(items), "trace": encode(trace)},
                    )
                    connection.execute(
                        text("DELETE FROM knowledge_relation WHERE module_id=:id"),
                        {"id": module["id"]},
                    )
                    for rel, verdict in zip(relations, relation_items, strict=True):
                        if verdict["verification"] != "supported":
                            continue
                        connection.execute(
                            text("""INSERT INTO knowledge_relation
                            (report_id,module_id,subject,predicate,object,scope,condition,citations,verified)
                            VALUES (:report,:module,:subject,:predicate,:object,:scope,
                                    :condition,CAST(:citations AS JSONB),true)"""),
                            {
                                **rel,
                                "report": report_id,
                                "module": module["id"],
                                "citations": encode(rel["citations"]),
                            },
                        )
            except InterruptedError:
                raise
            except Exception as exc:
                db.execute(
                    "UPDATE analysis_module SET status='failed',error_message=:error WHERE id=:id",
                    {"id": module["id"], "error": str(exc)[:1000]},
                )
        failed = db.rows(
            "SELECT id FROM analysis_module WHERE report_id=:id AND status='failed'",
            {"id": report_id},
        )
        _finish(
            "analysis_report",
            report_id,
            "partial" if failed or coverage.get("partial") else "completed",
        )
    except InterruptedError:
        pass
    except Exception as exc:
        _finish("analysis_report", report_id, "failed", str(exc)[:1000])
    finally:
        await model.aclose()


async def retrieve(
    db: KnowledgeStore, sources: list[dict], question: str, heartbeat: Callable[[], None]
) -> tuple[list[dict], dict]:
    return await retrieve_chunks(
        db, sources, question, heartbeat, create_embedding_gateway, create_rerank_gateway
    )


def graph_expand(
    db: KnowledgeStore, project_id: int, hits: list[dict], sources: list[dict]
) -> tuple[list[dict], list[dict]]:
    source_runs = {(s["source_id"], s["parse_run_id"]) for s in sources}
    relations = db.rows(
        """SELECT rel.* FROM knowledge_relation rel
        JOIN analysis_report r ON r.id=rel.report_id JOIN project p ON p.id=r.project_id
        WHERE r.project_id=:project AND r.company_id=:company_id AND p.deleted_at IS NULL
          AND rel.verified AND r.id=(SELECT max(id) FROM analysis_report
              WHERE project_id=:project AND status IN ('completed','partial'))""",
        {"project": project_id},
    )
    relations = [
        r
        for r in relations
        if r["citations"]
        and all((ref["source_id"], ref["parse_run_id"]) in source_runs for ref in r["citations"])
    ]
    selected = []
    names = set()
    text_hits = "\n".join(r["content"] for r in hits)
    for _depth in range(2):
        next_names = set()
        for rel in relations:
            if rel in selected:
                continue
            if (
                rel["subject"] in text_hits
                or rel["object"] in text_hits
                or (
                    (rel["subject"], rel["scope"]) in names
                    or (rel["object"], rel["scope"]) in names
                )
            ):
                selected.append(rel)
                next_names.update(((rel["subject"], rel["scope"]), (rel["object"], rel["scope"])))
                if len(selected) >= 24:
                    break
        if len(selected) >= 24:
            break
        text_hits = ""
        names = next_names
    seen = {r["block_id"] for r in hits}
    wanted = {ref["element_id"] for rel in selected for ref in rel["citations"]}
    for source in sources:
        for block in db.readable_chunks(source):
            if block["element_id"] in wanted and block["block_id"] not in seen:
                hits.append(block)
                seen.add(block["block_id"])
    return hits, selected


@celery_app.task(name="tender.worker.knowledge.answer_question")
def answer_question(answer_id: int) -> None:
    with _advisory_lock(f"knowledge_answer:{answer_id}") as acquired:
        if acquired:
            asyncio.run(_answer_question(answer_id))


async def _answer_question(answer_id: int) -> None:
    db = _store()
    answers = db.rows(
        "SELECT * FROM knowledge_answer WHERE id=:id AND company_id=:company_id", {"id": answer_id}
    )
    if not answers or answers[0]["status"] not in {"pending", "running"}:
        return
    answer = answers[0]
    model = _model("knowledge_ask")
    try:
        ids = answer["collection_ids"]
        if answer["project_id"] and set(ids) - set(
            db.collections_for_project(answer["project_id"])
        ):
            raise ValueError("知识库关联已变更，请重新提问")
        for cid in ids:
            db.collection(cid)
        sources = answer["snapshot"]["sources"]
        db.execute("UPDATE knowledge_answer SET status='running' WHERE id=:id", {"id": answer_id})
        hits, info = await retrieve(
            db, sources, answer["question"], lambda: _touch("knowledge_answer", answer_id)
        )
        relations = []
        if answer["project_id"]:
            hits, relations = graph_expand(db, answer["project_id"], hits, sources)
        tools = DocumentTools(hits)
        context = tools.reveal(hits)
        items = []
        if hits:
            result = await json_completion(
                model,
                REPORT_CONTRACT + '\n回答问题，返回 {"items":[...]}。'
                "当前招标材料说明本项目要求；企业资料提供企业事实；历史和参考资料只用于建议。"
                "引用的用途见原文元数据，禁止混同。不得声称本次 top-k 问答穷尽全部风险；"
                "涉及全部要求时提示查看全文分析报告。\n问题："
                + answer["question"]
                + "\n来源用途："
                + encode(
                    [{k: s[k] for k in ("source_id", "purpose", "file_name")} for s in sources]
                )
                + "\n原文："
                + encode(context)
                + "\n已校验关系："
                + encode(relations),
            )
            items = await verify_items(model, validate_items(result.get("items"), tools.seen))
        snapshot = {
            **answer["snapshot"],
            **info,
            "retrieved_blocks": len(hits),
            "graph_used": bool(relations),
            "graph_relation_count": len(relations),
            "no_evidence": not bool(items),
        }
        db.execute(
            """UPDATE knowledge_answer SET items=CAST(:items AS JSONB),
            relations=CAST(:relations AS JSONB),
            snapshot=CAST(:snapshot AS JSONB) WHERE id=:id""",
            {
                "id": answer_id,
                "items": encode(items),
                "relations": encode(relations),
                "snapshot": encode(snapshot),
            },
        )
        _finish("knowledge_answer", answer_id, "completed")
    except Exception as exc:
        _finish("knowledge_answer", answer_id, "failed", str(exc)[:1000])
    finally:
        await model.aclose()
