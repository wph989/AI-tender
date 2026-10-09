"""知识索引、标书分析与检索问答；解析统一交给 DeepAgents 运行时执行。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from sqlalchemy import create_engine, text

from tender.application.knowledge_retrieval import retrieve_chunks
from tender.application.knowledge_store import KnowledgeStore, encode, source_state
from tender.application.llm_routing import RoutingModel
from tender.application.model_test_maintenance import maintain_model_tests
from tender.application.qa_agent import answer_with_agent
from tender.core import settings
from tender.core.di import create_embedding_gateway, create_rerank_gateway
from tender.worker.celery_app import celery_app
from tender.worker.extraction import _advisory_lock, _routing_model

_engine = create_engine(settings.database_url(), pool_pre_ping=True)


def _store() -> KnowledgeStore:
    return KnowledgeStore(_engine, settings.company_id())


def _model(feature: str, **limits) -> RoutingModel:
    return _routing_model(feature, feature, **limits)


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
    from tender.application.deep_analysis import RUNTIME_VERSION
    from tender.worker.deep_analysis import analyze_report

    # 旧的固定字段解析流程已下线：历史报告只读展示，不能继续执行；版本不一致同样拒绝。
    if report["runtime_version"] != RUNTIME_VERSION:
        _finish("analysis_report", report_id, "failed", "报告使用已下线的解析流程，请重新发起分析")
        return
    await analyze_report(db, report)


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
    if not selected:
        # 问答每次检索都会尝试扩展；无关联时无需反复读取全部资料。
        return hits, []
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

        async def authorize() -> None:
            await asyncio.to_thread(_touch, "knowledge_answer", answer_id)

        async def retrieve_selected(selected: list[dict], query: str):
            return await retrieve_chunks(
                db,
                selected,
                query,
                lambda: _touch("knowledge_answer", answer_id),
                create_embedding_gateway,
                create_rerank_gateway,
            )

        async def read_source(source: dict) -> list[dict]:
            return await asyncio.to_thread(db.readable_chunks, source)

        async def expand_selected(selected: list[dict], hits: list[dict]):
            return await asyncio.to_thread(graph_expand, db, answer["project_id"], hits, selected)

        # 问答由独立 Agent 检索、核对并作答；项目范围取其自身，集合问答回落到资料来源的项目。
        project_id = answer["project_id"]
        if project_id is None and sources:
            project_id = sources[0]["project_id"]
        draft, research = await answer_with_agent(
            model_factory=lambda **limits: _model("knowledge_ask", **limits),
            sources=sources,
            project_id=project_id,
            question=answer["question"],
            retrieve=retrieve_selected,
            read=read_source,
            authorize=authorize,
            expand=expand_selected if answer["project_id"] else None,
        )
        items = draft["fields"]
        searches = [event for event in research.events if event["action"] == "search_result"]
        # 只展示 Agent 实际检索并读到的图谱依据，不能把图外预检结果冒充作答上下文。
        graph_relations = []
        for event in searches:
            for link in event["relations"]:
                if link not in graph_relations:
                    graph_relations.append(link)
        relations = graph_relations + [r for r in draft["relations"] if r not in graph_relations]
        snapshot = {
            **answer["snapshot"],
            "mode": "hybrid" if any(e.get("mode") == "hybrid" for e in searches) else "keyword",
            "reranked": any(e.get("reranked") for e in searches),
            "embedding_configured": any(e.get("embedding_configured") for e in searches),
            "semantic_source_ids": sorted(
                {sid for e in searches for sid in e.get("semantic_source_ids", [])}
            ),
            "warning": "；".join(dict.fromkeys(e["warning"] for e in searches if e.get("warning"))),
            "retrieved_blocks": len(research.seen),
            "graph_used": bool(graph_relations),
            "graph_relation_count": len(graph_relations),
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
