"""通用知识库、跨文件综合分析与带引用问答；长任务只落库，由 worker 执行。"""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from tender.api.common import engine, project_row
from tender.api.errors import ApiProblem
from tender.api.parsing import ParseRequest, _create_parse_job
from tender.api.project_files import _role_is_parseable
from tender.application.agent_runtime import limits_snapshot
from tender.application.analysis_skills import MODULES, skill_snapshot, skill_version
from tender.application.deep_analysis import CONTRACT, RUNTIME_VERSION, validate_project_claims
from tender.application.knowledge import CATEGORIES, TOPICS
from tender.application.knowledge_retrieval import retrieve_chunks
from tender.application.knowledge_store import (
    KnowledgeStore,
    encode,
    source_signature,
    source_state,
)
from tender.core import settings
from tender.core.di import create_embedding_gateway

router = APIRouter(prefix="/api/v1", tags=["knowledge"])
Category = Literal["engineering", "goods", "service"]
Purpose = Literal["tender", "company", "history", "reference"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CollectionInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    purpose: Purpose


class LinkedCollections(StrictModel):
    collection_ids: list[int] = Field(max_length=100)


class LotSettings(StrictModel):
    id: int = Field(gt=0)
    category: Category | None = None
    topics: list[str] | None = None


class AnalysisSettings(StrictModel):
    category: Category
    topics: list[str] = Field(default_factory=list, max_length=3)
    lots: list[LotSettings] = Field(default_factory=list, max_length=100)


class AnalysisInput(StrictModel):
    allow_partial: bool = False


class RetryInput(StrictModel):
    module_keys: list[str] = Field(default_factory=list, max_length=13)
    max_output_tokens: int | None = Field(default=None, ge=512, le=16384)
    timeout_seconds: int | None = Field(default=None, ge=300, le=3600)


class AskInput(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    collection_ids: list[int] = Field(default_factory=list, max_length=100)


class CitationInput(StrictModel):
    source_id: int = Field(gt=0)
    collection_id: int = Field(gt=0)
    project_id: int = Field(gt=0)
    project_file_id: int = Field(gt=0)
    version_id: int = Field(gt=0)
    parse_run_id: int = Field(gt=0)
    element_id: int = Field(gt=0)
    anchor: str = Field(min_length=1, max_length=80)


def store(request: Request) -> KnowledgeStore:
    return KnowledgeStore(engine(request), settings.company_id())


def collection_or_404(request: Request, collection_id: int) -> dict:
    try:
        return store(request).collection(collection_id)
    except LookupError as exc:
        raise ApiProblem(404, "not_found", str(exc)) from exc


def project_collection(request: Request, project_id: int) -> int:
    project_row(engine(request), project_id)
    rows = store(request).rows(
        """SELECT id FROM knowledge_collection
        WHERE upload_project_id = :id AND company_id = :company_id AND deleted_at IS NULL""",
        {"id": project_id},
    )
    if not rows:
        raise ApiProblem(404, "not_found", "项目资料库尚未创建")
    return rows[0]["id"]


def public_sources(request: Request, ids: list[int]) -> list[dict]:
    return [{**row, "state": source_state(row)} for row in store(request).sources(ids)]


@router.get("/knowledge/collections")
def list_collections(request: Request) -> dict:
    return {
        "items": store(request).rows("""SELECT k.*, count(f.id) AS file_count
        FROM knowledge_collection k JOIN project p ON p.id = k.upload_project_id
        LEFT JOIN project_file f ON f.project_id = p.id AND f.deleted_at IS NULL
        WHERE k.company_id = :company_id AND k.deleted_at IS NULL AND p.deleted_at IS NULL
        GROUP BY k.id ORDER BY k.is_project, k.id DESC""")
    }


@router.post("/knowledge/collections", status_code=201)
def create_collection(payload: CollectionInput, request: Request) -> dict:
    name = payload.name.strip()
    if not name:
        raise ApiProblem(400, "invalid_argument", "知识库名称不能为空")
    with engine(request).begin() as connection:
        pid = connection.execute(
            text("""INSERT INTO project (company_id, name, kind)
            VALUES (:company, :name, 'knowledge') RETURNING id"""),
            {"company": settings.company_id(), "name": name},
        ).scalar_one()
        row = (
            connection.execute(
                text("""INSERT INTO knowledge_collection
            (company_id, name, purpose, upload_project_id) VALUES (:company, :name, :purpose, :pid)
            RETURNING *"""),
                {
                    "company": settings.company_id(),
                    "name": name,
                    "purpose": payload.purpose,
                    "pid": pid,
                },
            )
            .mappings()
            .one()
        )
    return dict(row)


@router.get("/knowledge/collections/{collection_id}")
def get_collection(collection_id: int, request: Request) -> dict:
    collection = collection_or_404(request, collection_id)
    embedding = store(request).embedding_config()
    sources = public_sources(request, [collection_id])
    for source in sources:
        source["semantic_ready"] = bool(
            embedding
            and source["index_status"] == "completed"
            and source["embedding_signature"] == embedding["signature"]
            and source["dimension"]
        )
        source["needs_reindex"] = bool(
            embedding and source["index_status"] == "completed" and not source["semantic_ready"]
        )
    return {
        **collection,
        "sources": sources,
        "embedding_configured": embedding is not None,
        "embedding_model": embedding["model_id"] if embedding else None,
    }


@router.patch("/knowledge/collections/{collection_id}")
def update_collection(collection_id: int, payload: CollectionInput, request: Request) -> dict:
    collection = collection_or_404(request, collection_id)
    if collection["is_project"]:
        raise ApiProblem(409, "project_collection", "项目资料库的名称与用途由项目维护")
    if not payload.name.strip():
        raise ApiProblem(400, "invalid_argument", "知识库名称不能为空")
    # 用途变更不能悄悄改变已有答案的证据含义，只允许在空库时改。
    if payload.purpose != collection["purpose"] and store(request).sources([collection_id]):
        raise ApiProblem(409, "collection_not_empty", "已有资料的知识库不能修改用途，请新建知识库")
    store(request).execute(
        """UPDATE knowledge_collection SET name=:name, purpose=:purpose
        WHERE id=:id AND company_id=:company_id""",
        {"name": payload.name.strip(), "purpose": payload.purpose, "id": collection_id},
    )
    return get_collection(collection_id, request)


@router.delete("/knowledge/collections/{collection_id}")
def delete_collection(collection_id: int, request: Request) -> dict:
    collection = collection_or_404(request, collection_id)
    if collection["is_project"]:
        raise ApiProblem(409, "project_collection", "请从项目入口管理项目资料")
    store(request).execute(
        "UPDATE knowledge_collection SET deleted_at=now() WHERE id=:id AND company_id=:company_id",
        {"id": collection_id},
    )
    return {"deleted": True}


@router.post("/knowledge/collections/{collection_id}/reindex", status_code=202)
def reindex_collection(collection_id: int, request: Request) -> dict:
    collection_or_404(request, collection_id)
    count = 0
    with engine(request).begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": -collection_id})
        for source in store(request).sources([collection_id]):
            if source_state(source) not in {"ready", "partial"}:
                continue
            pending = connection.execute(
                text("""SELECT id FROM knowledge_index WHERE source_id=:id
                AND run_id=:run AND status IN ('pending','running')"""),
                {"id": source["source_id"], "run": source["parse_run_id"]},
            ).first()
            if pending:
                continue
            connection.execute(
                text("""INSERT INTO knowledge_index (source_id, version_id, run_id)
                VALUES (:source, :version, :run)"""),
                {
                    "source": source["source_id"],
                    "version": source["version_id"],
                    "run": source["parse_run_id"],
                },
            )
            count += 1
    return {"queued_count": count}


@router.get("/knowledge/collections/{collection_id}/search")
async def search_collection(
    collection_id: int, request: Request, q: str = Query(min_length=1, max_length=2000)
) -> dict:
    collection_or_404(request, collection_id)
    db = store(request)
    hits, info = await retrieve_chunks(
        db,
        await asyncio.to_thread(db.sources, [collection_id]),
        q,
        lambda: None,
        create_embedding_gateway,
        embedding_timeout=15,
    )
    for hit in hits:
        hit.pop("embedding", None)
    return {"items": hits, **info}


@router.post("/knowledge/citations/resolve")
def resolve_citation(payload: CitationInput, request: Request) -> dict:
    try:
        return store(request).resolve(payload.model_dump())
    except LookupError as exc:
        raise ApiProblem(404, "citation_unavailable", str(exc)) from exc


@router.post("/knowledge/embedding/test")
async def test_embedding(request: Request) -> dict:
    config = store(request).embedding_config()
    if config is None:
        raise ApiProblem(409, "embedding_not_configured", "请先在模型管理中绑定语义检索向量模型")
    client = create_embedding_gateway(config)
    try:
        vectors = await client.embed(["招标资格条件与证明材料"])
        return {"status": "ok", "model": config["model_id"], "dimension": len(vectors[0])}
    finally:
        await client.aclose()


@router.post("/knowledge/sources/{source_id}/process", status_code=202)
def process_source(source_id: int, request: Request) -> dict:
    rows = store(request).rows(
        """SELECT f.*,s.collection_id FROM knowledge_source s
        JOIN project_file f ON f.id=s.project_file_id JOIN project p ON p.id=f.project_id
        JOIN knowledge_collection k ON k.id=s.collection_id
        WHERE s.id=:id AND p.company_id=:company_id AND k.company_id=:company_id
          AND f.deleted_at IS NULL AND p.deleted_at IS NULL AND k.deleted_at IS NULL""",
        {"id": source_id},
    )
    if not rows:
        raise ApiProblem(404, "not_found", "资料不存在")
    source = rows[0]
    suffix = PurePosixPath(source["display_name"]).suffix.lower()
    if not _role_is_parseable(source["role"], suffix):
        raise ApiProblem(
            409, "unsupported_format", "此格式暂不支持解析，请提供 PDF、Office 或文本版本"
        )
    store(request).execute(
        "UPDATE project_file SET is_parseable=true WHERE id=:id", {"id": source["id"]}
    )
    if source["version_id"] is not None:
        prior = store(request).rows(
            "SELECT id FROM parse_run WHERE version_id=:id", {"id": source["version_id"]}
        )
        return _create_parse_job(
            source["version_id"], ParseRequest(reason="资料重新处理"), request, force=bool(prior)
        )
    config = request.app.state.components.configs
    active = config.active(settings.company_id())
    with engine(request).begin() as connection:
        connection.execute(
            text("SELECT id FROM project_file WHERE id=:id FOR UPDATE"), {"id": source["id"]}
        )
        inflight = connection.execute(
            text("""SELECT id FROM job WHERE project_file_id=:id
            AND status IN ('pending','running','submitting') AND finished_at IS NULL"""),
            {"id": source["id"]},
        ).first()
        if inflight:
            raise ApiProblem(409, "process_in_flight", "该资料已有处理任务")
        job_id = "job_" + uuid4().hex
        connection.execute(
            text("""INSERT INTO job
            (id,company_id,project_id,project_file_id,status,stage,config_snapshot,config_snapshot_id)
            VALUES (:job,:company,:project,:file,'pending',:stage,
                    CAST(:snapshot AS JSONB),:config)"""),
            {
                "job": job_id,
                "company": settings.company_id(),
                "project": source["project_id"],
                "file": source["id"],
                "stage": "probing" if suffix == ".pdf" else "converting",
                "snapshot": encode({"tier": "standard", "ocr_mode": "auto", "auto_parse": True}),
                "config": config.snapshot_for_job(connection, active),
            },
        )
    return {"job_id": job_id, "status": "pending"}


@router.get("/projects/{project_id}/knowledge")
def project_knowledge(project_id: int, request: Request) -> dict:
    own_id = project_collection(request, project_id)
    ids = store(request).collections_for_project(project_id)
    return {
        "collection_id": own_id,
        "linked_collection_ids": [i for i in ids if i != own_id],
        "sources": public_sources(request, [own_id]),
    }


@router.put("/projects/{project_id}/knowledge/collections")
def link_collections(project_id: int, payload: LinkedCollections, request: Request) -> dict:
    own_id = project_collection(request, project_id)
    ids = sorted(set(payload.collection_ids) - {own_id})
    for cid in ids:
        collection = collection_or_404(request, cid)
        if collection["is_project"]:
            raise ApiProblem(400, "invalid_collection", "请关联独立知识库；项目材料按各项目隔离")
    with engine(request).begin() as connection:
        connection.execute(
            text("DELETE FROM project_knowledge_collection WHERE project_id=:id"),
            {"id": project_id},
        )
        for cid in ids:
            connection.execute(
                text("INSERT INTO project_knowledge_collection VALUES (:p,:c)"),
                {"p": project_id, "c": cid},
            )
    return {"linked_collection_ids": ids}


@router.get("/projects/{project_id}/analysis")
def analysis_status(project_id: int, request: Request) -> dict:
    own_id = project_collection(request, project_id)
    db = store(request)
    project = db.rows(
        """SELECT analysis_category, analysis_topics FROM project
        WHERE id=:id AND company_id=:company_id""",
        {"id": project_id},
    )[0]
    lots = db.rows(
        """SELECT id, name, analysis_category AS category, analysis_topics AS topics
        FROM lot WHERE project_id=:id ORDER BY sort_no,id""",
        {"id": project_id},
    )
    reports = db.rows(
        """SELECT id,status,created_at,finished_at,allow_partial FROM analysis_report
        WHERE project_id=:id AND company_id=:company_id ORDER BY id DESC LIMIT 30""",
        {"id": project_id},
    )
    return {
        **project,
        "lots": lots,
        "reports": reports,
        "sources": public_sources(request, [own_id]),
        "categories": CATEGORIES,
        "topics": TOPICS,
    }


@router.put("/projects/{project_id}/analysis/settings")
def save_settings(project_id: int, payload: AnalysisSettings, request: Request) -> dict:
    project_row(engine(request), project_id)
    if set(payload.topics) - TOPICS.keys() or any(
        set(lot.topics or []) - TOPICS.keys() for lot in payload.lots
    ):
        raise ApiProblem(400, "invalid_topic", "存在不支持的分析专题")
    known = {
        row["id"]
        for row in store(request).rows(
            "SELECT id FROM lot WHERE project_id=:id", {"id": project_id}
        )
    }
    if any(lot.id not in known for lot in payload.lots):
        raise ApiProblem(400, "invalid_lot", "标段不属于当前项目")
    with engine(request).begin() as connection:
        connection.execute(
            text("""UPDATE project SET analysis_category=:category,
            analysis_topics=CAST(:topics AS JSONB) WHERE id=:id"""),
            {"id": project_id, "category": payload.category, "topics": encode(payload.topics)},
        )
        for lot in payload.lots:
            connection.execute(
                text("""UPDATE lot SET analysis_category=:category,
                analysis_topics=CAST(:topics AS JSONB) WHERE id=:id AND project_id=:project"""),
                {
                    "id": lot.id,
                    "project": project_id,
                    "category": lot.category,
                    "topics": encode(lot.topics) if lot.topics is not None else None,
                },
            )
    return analysis_status(project_id, request)


@router.post("/projects/{project_id}/analysis", status_code=202)
def start_analysis(project_id: int, payload: AnalysisInput, request: Request) -> dict:
    state = analysis_status(project_id, request)
    if state["analysis_category"] is None:
        raise ApiProblem(400, "category_required", "开始分析前请选择工程、货物或服务")
    if not state["sources"]:
        raise ApiProblem(400, "files_required", "请先上传项目文件")
    for source in state["sources"]:
        suffix = PurePosixPath(source["file_name"]).suffix.lower()
        if source["state"] in {"pending", "unsupported"} and _role_is_parseable(
            source["role"], suffix
        ):
            try:
                process_source(source["source_id"], request)
            except ApiProblem as exc:
                if exc.code not in {"process_in_flight", "parse_in_flight"}:
                    raise
    rules = skill_snapshot()
    rules["__deep_contract__"] = CONTRACT
    db = store(request)
    references = [
        s
        for s in db.sources(db.collections_for_project(project_id))
        if s["project_id"] != project_id
    ]
    runtime_settings = limits_snapshot(db)
    with engine(request).begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": project_id})
        active = connection.execute(
            text("""SELECT id FROM analysis_report WHERE project_id=:id
            AND status IN ('waiting','pending','running')"""),
            {"id": project_id},
        ).scalar_one_or_none()
        if active:
            raise ApiProblem(409, "analysis_in_flight", "项目已有分析任务，请等待或取消等待任务")
        row = (
            connection.execute(
                text("""INSERT INTO analysis_report
            (project_id,company_id,allow_partial,category,topics,lot_settings,source_snapshot,
             skill_version,skill_snapshot,runtime_version,runtime_settings,reference_snapshot)
            VALUES (:project,:company,:partial,:category,
                    CAST(:topics AS JSONB),CAST(:lots AS JSONB),
                    CAST(:sources AS JSONB),:skill,CAST(:rules AS JSONB),:runtime,
                    CAST(:runtime_settings AS JSONB),CAST(:references AS JSONB))
                    RETURNING id,status"""),
                {
                    "project": project_id,
                    "company": settings.company_id(),
                    "partial": payload.allow_partial,
                    "category": state["analysis_category"],
                    "topics": encode(state["analysis_topics"]),
                    "lots": encode(state["lots"]),
                    "sources": encode(state["sources"]),
                    "skill": skill_version(rules),
                    "rules": encode(rules),
                    "runtime": RUNTIME_VERSION,
                    "runtime_settings": encode(runtime_settings),
                    "references": encode(references),
                },
            )
            .mappings()
            .one()
        )
    return dict(row)


def report_row(request: Request, report_id: int) -> dict:
    rows = store(request).rows(
        """SELECT r.* FROM analysis_report r JOIN project p ON p.id=r.project_id
        WHERE r.id=:id AND r.company_id=:company_id AND p.deleted_at IS NULL""",
        {"id": report_id},
    )
    if not rows:
        raise ApiProblem(404, "not_found", "报告不存在")
    return rows[0]


def visible_items(
    db: KnowledgeStore, items: list[dict], allowed_collections: list[int] | None = None
) -> list[dict]:
    result = []
    for item in items:
        accessible = True
        for ref in item["citations"]:
            try:
                if (
                    allowed_collections is not None
                    and ref["collection_id"] not in allowed_collections
                ):
                    raise LookupError("已解除知识库关联")
                db.resolve(ref)
            except LookupError:
                accessible = False
                break
        result.append(
            item
            if accessible
            else {
                "id": item["id"],
                "kind": "insufficient",
                "title": "来源已不可用",
                "text": "资料已删除或解除关联，请更新分析。",
                "presentation": "paragraph",
                "cells": {},
                "citations": [],
                "verification": "unavailable",
            }
        )
    return result


@router.get("/analysis/reports/{report_id}")
def get_report(report_id: int, request: Request) -> dict:
    report = report_row(request, report_id)
    report.pop("skill_snapshot", None)
    db = store(request)
    modules = db.rows(
        "SELECT * FROM analysis_module WHERE report_id=:id ORDER BY id", {"id": report_id}
    )
    allowed = db.collections_for_project(report["project_id"])
    for module in modules:
        module["items"] = visible_items(db, module["items"], allowed)
        # 工具日志只供服务端重放，不在产品界面暴露整段中间提示词。
        module.pop("trace", None)
    if report.get("runtime_version", "legacy") != "legacy":
        runs = db.rows(
            """SELECT a.id,a.module_id,a.attempt,a.thread_id,a.status,a.started_at,
            a.deadline_at,a.finished_at,a.lease_until,a.model_calls,a.tool_calls,
            a.prompt_tokens,a.completion_tokens,a.limits,a.error_message
            FROM agent_module_run a JOIN analysis_module m ON m.id=a.module_id
            WHERE m.report_id=:id AND a.company_id=:company_id ORDER BY a.attempt""",
            {"id": report_id},
        )
        for module in modules:
            module["runs"] = [r for r in runs if r["module_id"] == module["id"]]
        report["summary"] = visible_items(db, report["summary"], allowed)
    current = analysis_status(report["project_id"], request)
    stale = (
        source_signature(current["sources"]) != source_signature(report["source_snapshot"])
        or current["analysis_category"] != report["category"]
        or current["analysis_topics"] != report["topics"]
        or current["lots"] != report["lot_settings"]
        or (
            report.get("runtime_version", "legacy") != "legacy"
            and source_signature(
                [s for s in db.sources(allowed) if s["project_id"] != report["project_id"]]
            )
            != source_signature(report["reference_snapshot"])
        )
    )
    return {**report, "modules": modules, "stale": stale}


@router.post("/analysis/reports/{report_id}/cancel")
def cancel_report(report_id: int, request: Request) -> dict:
    report_row(request, report_id)
    store(request).execute(
        """UPDATE analysis_report SET status='canceled',finished_at=now(),lease_until=NULL
        WHERE id=:id AND company_id=:company_id AND status IN ('waiting','pending','running')""",
        {"id": report_id},
    )
    return {"status": report_row(request, report_id)["status"]}


@router.get("/analysis/reports/{report_id}/runs/{run_id}/events")
def run_events(
    report_id: int,
    run_id: int,
    request: Request,
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
) -> dict:
    report_row(request, report_id)
    db = store(request)
    runs = db.rows(
        """SELECT a.id FROM agent_module_run a
        JOIN analysis_module m ON m.id=a.module_id
        WHERE a.id=:run AND m.report_id=:report AND a.company_id=:company_id""",
        {"run": run_id, "report": report_id},
    )
    if not runs:
        raise ApiProblem(404, "not_found", "模块运行记录不存在")
    rows = db.rows(
        """SELECT id,kind,detail,created_at FROM agent_run_event
        WHERE run_id=:run AND id>:after ORDER BY id LIMIT :limit""",
        {"run": run_id, "after": after, "limit": limit},
    )
    return {"events": rows, "next_after": rows[-1]["id"] if rows else after}


@router.post("/analysis/reports/{report_id}/retry", status_code=202)
def retry_report(report_id: int, payload: RetryInput, request: Request) -> dict:
    report = report_row(request, report_id)
    if report["status"] not in {"partial", "failed"}:
        raise ApiProblem(409, "report_not_retryable", "只有失败或部分完成的报告可以补跑")
    keys = payload.module_keys or list(MODULES)
    if set(keys) - MODULES.keys():
        raise ApiProblem(400, "invalid_module", "未知解析模块")
    with engine(request).begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": report["project_id"]})
        # 并发点击补跑只能有一个请求创建新 attempt，不能重复重置预算。
        current_status = connection.execute(
            text("SELECT status FROM analysis_report WHERE id=:id FOR UPDATE"), {"id": report_id}
        ).scalar_one()
        if current_status not in {"partial", "failed"}:
            raise ApiProblem(409, "report_not_retryable", "任务已进入执行，请勿重复补跑")
        other = connection.execute(
            text("""SELECT id FROM analysis_report WHERE project_id=:project
            AND id<>:id AND status IN ('waiting','pending','running')"""),
            {"project": report["project_id"], "id": report_id},
        ).first()
        if other:
            raise ApiProblem(409, "analysis_in_flight", "项目已有其它分析任务")
        retried = (
            connection.execute(
                text("""UPDATE analysis_module SET status='pending',error_message=NULL
            WHERE report_id=:id AND module_key=ANY(:keys) AND status IN ('failed','canceled')
            RETURNING id"""),
                {"id": report_id, "keys": keys},
            )
            .scalars()
            .all()
        )
        if report.get("runtime_version", "legacy") != "legacy":
            limits = dict(report["runtime_settings"])
            if payload.max_output_tokens is not None:
                limits["max_output_tokens"] = payload.max_output_tokens
            if payload.timeout_seconds is not None:
                limits["timeout_seconds"] = payload.timeout_seconds
            # 新attempt可以显式调整输出与时限上限，旧报告快照及运行账不回写。
            for module_id in sorted(retried):
                attempt = connection.execute(
                    text(
                        "SELECT COALESCE(max(attempt),0)+1"
                        " FROM agent_module_run WHERE module_id=:id"
                    ),
                    {"id": module_id},
                ).scalar_one()
                previous_state = (
                    connection.execute(
                        text(
                            "SELECT state FROM agent_module_run WHERE module_id=:id "
                            "ORDER BY attempt DESC LIMIT 1"
                        ),
                        {"id": module_id},
                    ).scalar_one_or_none()
                    or {}
                )
                # 已通过结构/引文校验的草稿可接着做支持性验证，避免预算末尾失败后重复检索。
                # 已完成后被质量拒绝的结果必须重新生成，不能携带旧verified绕过新的校验。
                carry = (
                    previous_state
                    if (previous_state.get("draft") or previous_state.get("staged_items"))
                    and not previous_state.get("verified")
                    else {}
                )
                if carry:
                    carry.pop("items_verified", None)
                    # 新attempt保留成果和证据，但不能继承旧调用ID缓存与纠错次数。
                    carry.pop("tool_results", None)
                    carry.pop("invalid_submissions", None)
                    try:
                        validate_project_claims(
                            carry.get("draft", {}).get("items", carry.get("staged_items", [])),
                            report["project_id"],
                        )
                    except ValueError:
                        carry = {}
                connection.execute(
                    text("""INSERT INTO agent_module_run
                    (module_id,company_id,attempt,thread_id,limits,state)
                    VALUES (:module,:company,:attempt,:thread,CAST(:limits AS JSONB),
                            CAST(:state AS JSONB))"""),
                    {
                        "module": module_id,
                        "company": settings.company_id(),
                        "attempt": attempt,
                        "thread": f"analysis:{report_id}:{module_id}:{attempt}",
                        "limits": encode(limits),
                        "state": encode(carry),
                    },
                )
        # 全文扫描前失败的任务尚未固定可用解析批次，重试时重新等候原范围内的资料。
        status = (
            "pending"
            if (
                report["coverage"].get("total_blocks")
                or report["coverage"].get("mode") == "agent_research"
                and retried
            )
            else "waiting"
        )
        connection.execute(
            text("""UPDATE analysis_report SET status=:status,lease_until=NULL,
            error_message=NULL,finished_at=NULL WHERE id=:id"""),
            {"id": report_id, "status": status},
        )
    return {"id": report_id, "status": status}


def enqueue_question(
    request: Request, payload: AskInput, ids: list[int], project_id: int | None
) -> dict:
    question = payload.question.strip()
    if not question:
        raise ApiProblem(400, "invalid_argument", "请输入问题")
    for cid in ids:
        collection_or_404(request, cid)
    sources = store(request).sources(ids)
    if not any(source_state(s) in {"ready", "partial"} for s in sources):
        raise ApiProblem(409, "sources_unavailable", "当前范围没有可读取的资料，请先完成文件解析")
    with engine(request).begin() as connection:
        row = (
            connection.execute(
                text("""INSERT INTO knowledge_answer
            (company_id,project_id,collection_ids,question,snapshot)
            VALUES (:company,:project,CAST(:ids AS JSONB),:question,CAST(:snapshot AS JSONB))
            RETURNING id,status"""),
                {
                    "company": settings.company_id(),
                    "project": project_id,
                    "ids": encode(ids),
                    "question": question,
                    "snapshot": encode({"sources": sources}),
                },
            )
            .mappings()
            .one()
        )
    return dict(row)


@router.post("/knowledge/collections/{collection_id}/ask", status_code=202)
def ask_collection(collection_id: int, payload: AskInput, request: Request) -> dict:
    return enqueue_question(request, payload, [collection_id], None)


@router.post("/projects/{project_id}/knowledge/ask", status_code=202)
def ask_project(project_id: int, payload: AskInput, request: Request) -> dict:
    own_id = project_collection(request, project_id)
    allowed = store(request).collections_for_project(project_id)
    ids = sorted({own_id, *payload.collection_ids})
    if set(ids) - set(allowed):
        raise ApiProblem(403, "collection_not_linked", "只能检索本项目已关联的知识库")
    return enqueue_question(request, payload, ids, project_id)


@router.get("/knowledge/answers/{answer_id}")
def get_answer(answer_id: int, request: Request) -> dict:
    db = store(request)
    rows = db.rows(
        "SELECT * FROM knowledge_answer WHERE id=:id AND company_id=:company_id", {"id": answer_id}
    )
    if not rows:
        raise ApiProblem(404, "not_found", "回答不存在")
    answer = rows[0]
    allowed = (
        db.collections_for_project(answer["project_id"])
        if answer["project_id"]
        else answer["collection_ids"]
    )
    answer["items"] = visible_items(db, answer["items"], allowed)
    relations = []
    for relation in answer["relations"]:
        candidate = {"id": str(relation.get("id", "relation")), "citations": relation["citations"]}
        if visible_items(db, [candidate], allowed)[0].get("verification") != "unavailable":
            relations.append(relation)
    answer["relations"] = relations
    return answer
