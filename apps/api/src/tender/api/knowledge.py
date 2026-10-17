"""通用知识库、跨文件综合分析与带引用问答；长任务只落库，由 worker 执行。"""

from __future__ import annotations

import asyncio
from pathlib import PurePosixPath
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, exists, func, insert, select, update

from tender.adapters.pg.models import (
    AgentModuleRun,
    AnalysisModule,
    AnalysisReport,
    Job,
    KnowledgeAnswer,
    KnowledgeCollection,
    KnowledgeIndex,
    Lot,
    Project,
    ProjectFile,
    ProjectKnowledgeCollection,
)
from tender.adapters.pg.repositories.agent_runtime import (
    cancel_unlocked_runs,
    execution_active,
    lock_project,
    try_lock_report_execution,
)
from tender.adapters.pg.repositories.knowledge import KnowledgeStore
from tender.api.common import engine, project_row
from tender.api.errors import ApiProblem
from tender.api.logging import throttle_access_log
from tender.api.parsing import ParseRequest, _create_parse_job
from tender.api.project_files import _role_is_parseable
from tender.application.agent_runtime import limits_snapshot
from tender.application.analysis_data import (
    DATA_VERSION,
    ContextError,
    ContextInput,
    build_context,
    display_items,
    module_records,
)
from tender.application.analysis_data_store import (
    accessible_data,
    publish_data_snapshot,
    snapshot_matches_report,
)
from tender.application.analysis_output import output_schema
from tender.application.analysis_skills import MODULES, skill_snapshot, skill_version
from tender.application.deep_analysis import CONTRACT, RUNTIME_VERSION, validate_project_claims
from tender.application.knowledge import (
    CATEGORIES,
    TOPICS,
    align_citation,
    dedupe_citations,
    merge_field_entries,
    source_signature,
    source_state,
)
from tender.application.knowledge_retrieval import retrieve_chunks
from tender.config.schema import field_bounds
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
    # 补跑与配置中心统一允许正整数，避免接口额外挡住较小或较大的输出预算。
    max_output_tokens: int | None = Field(
        default=None, **field_bounds("analysis.max_output_tokens")
    )
    timeout_seconds: int | None = Field(default=None, **field_bounds("analysis.timeout_seconds"))


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
    own = store(request).collection_for_project(project_id)
    if own is None:
        raise ApiProblem(404, "not_found", "项目资料库尚未创建")
    return own


def public_sources(request: Request, ids: list[int]) -> list[dict]:
    return [{**row, "state": source_state(row)} for row in store(request).sources(ids)]


@router.get("/knowledge/collections")
def list_collections(request: Request) -> dict:
    return {"items": store(request).collection_overview()}


@router.post("/knowledge/collections", status_code=201)
def create_collection(payload: CollectionInput, request: Request) -> dict:
    name = payload.name.strip()
    if not name:
        raise ApiProblem(400, "invalid_argument", "知识库名称不能为空")
    with engine(request).begin() as connection:
        pid = connection.execute(
            insert(Project)
            .values(company_id=settings.company_id(), name=name, kind="knowledge")
            .returning(Project.id)
        ).scalar_one()
        row = (
            connection.execute(
                insert(KnowledgeCollection)
                .values(
                    company_id=settings.company_id(),
                    name=name,
                    purpose=payload.purpose,
                    upload_project_id=pid,
                )
                .returning(
                    KnowledgeCollection.id,
                    KnowledgeCollection.company_id,
                    KnowledgeCollection.name,
                    KnowledgeCollection.purpose,
                    KnowledgeCollection.upload_project_id,
                    KnowledgeCollection.is_project,
                    KnowledgeCollection.created_at,
                    KnowledgeCollection.deleted_at,
                )
            )
            .mappings()
            .one()
        )
    return dict(row)


@router.get("/knowledge/collections/{collection_id}")
# 知识库页面持续查询来源处理和索引状态。
@throttle_access_log()
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
    store(request).update_collection(
        collection_id, name=payload.name.strip(), purpose=payload.purpose
    )
    return get_collection(collection_id, request)


@router.delete("/knowledge/collections/{collection_id}")
def delete_collection(collection_id: int, request: Request) -> dict:
    collection = collection_or_404(request, collection_id)
    if collection["is_project"]:
        raise ApiProblem(409, "project_collection", "请从项目入口管理项目资料")
    store(request).soft_delete_collection(collection_id)
    return {"deleted": True}


@router.post("/knowledge/collections/{collection_id}/reindex", status_code=202)
def reindex_collection(collection_id: int, request: Request) -> dict:
    collection_or_404(request, collection_id)
    count = 0
    with engine(request).begin() as connection:
        lock_project(connection, -collection_id)
        for source in store(request).sources([collection_id]):
            if source_state(source) not in {"ready", "partial"}:
                continue
            pending = connection.execute(
                select(KnowledgeIndex.id).where(
                    KnowledgeIndex.source_id == source["source_id"],
                    KnowledgeIndex.run_id == source["parse_run_id"],
                    KnowledgeIndex.status.in_(("pending", "running")),
                )
            ).first()
            if pending:
                continue
            connection.execute(
                insert(KnowledgeIndex).values(
                    source_id=source["source_id"],
                    version_id=source["version_id"],
                    run_id=source["parse_run_id"],
                )
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
    source = store(request).source_for_processing(source_id)
    if source is None:
        raise ApiProblem(404, "not_found", "资料不存在")
    suffix = PurePosixPath(source["display_name"]).suffix.lower()
    if not _role_is_parseable(source["role"], suffix):
        raise ApiProblem(
            409, "unsupported_format", "此格式暂不支持解析，请提供 PDF、Office 或文本版本"
        )
    db = store(request)
    db.mark_source_parseable(source["id"])
    if source["version_id"] is not None:
        return _create_parse_job(
            source["version_id"],
            ParseRequest(reason="资料重新处理"),
            request,
            force=db.has_parse_run(source["version_id"]),
        )
    config = request.app.state.components.configs
    active = config.active(settings.company_id())
    with engine(request).begin() as connection:
        connection.execute(
            select(ProjectFile.id).where(ProjectFile.id == source["id"]).with_for_update()
        )
        inflight = connection.execute(
            select(Job.id).where(
                Job.project_file_id == source["id"],
                Job.status.in_(("pending", "running", "submitting")),
                Job.finished_at.is_(None),
            )
        ).first()
        if inflight:
            raise ApiProblem(409, "process_in_flight", "该资料已有处理任务")
        job_id = "job_" + uuid4().hex
        connection.execute(
            insert(Job).values(
                id=job_id,
                company_id=settings.company_id(),
                project_id=source["project_id"],
                project_file_id=source["id"],
                status="pending",
                stage="probing" if suffix == ".pdf" else "converting",
                config_snapshot={"tier": "standard", "ocr_mode": "auto", "auto_parse": True},
                config_snapshot_id=config.snapshot_for_job(connection, active),
            )
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
            delete(ProjectKnowledgeCollection).where(
                ProjectKnowledgeCollection.project_id == project_id
            )
        )
        for cid in ids:
            connection.execute(
                insert(ProjectKnowledgeCollection).values(project_id=project_id, collection_id=cid)
            )
    return {"linked_collection_ids": ids}


@router.get("/projects/{project_id}/analysis")
# 分析页每三秒刷新状态、报告和专题记录。
@throttle_access_log()
def analysis_status(project_id: int, request: Request) -> dict:
    own_id = project_collection(request, project_id)
    db = store(request)
    project = db.analysis_settings(project_id)
    if project is None:
        raise ApiProblem(404, "not_found", "项目不存在")
    return {
        **project,
        "lots": db.project_lots(project_id),
        "reports": db.analysis_reports(project_id),
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
    known = set(store(request).project_lot_ids(project_id))
    if any(lot.id not in known for lot in payload.lots):
        raise ApiProblem(400, "invalid_lot", "标段不属于当前项目")
    with engine(request).begin() as connection:
        connection.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(analysis_category=payload.category, analysis_topics=payload.topics)
        )
        for lot in payload.lots:
            connection.execute(
                update(Lot)
                .where(Lot.id == lot.id, Lot.project_id == project_id)
                .values(analysis_category=lot.category, analysis_topics=lot.topics)
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
    rules["__analysis_data_version__"] = DATA_VERSION
    db = store(request)
    references = [
        s
        for s in db.sources(db.collections_for_project(project_id))
        if s["project_id"] != project_id
    ]
    runtime_settings = limits_snapshot(db)
    with engine(request).begin() as connection:
        lock_project(connection, project_id)
        active = connection.execute(
            select(AnalysisReport.id).where(
                AnalysisReport.project_id == project_id,
                AnalysisReport.status.in_(("waiting", "pending", "running")),
            )
        ).scalar_one_or_none()
        if active:
            raise ApiProblem(409, "analysis_in_flight", "项目已有分析任务，请等待或取消等待任务")
        row = (
            connection.execute(
                insert(AnalysisReport)
                .values(
                    project_id=project_id,
                    company_id=settings.company_id(),
                    allow_partial=payload.allow_partial,
                    category=state["analysis_category"],
                    topics=state["analysis_topics"],
                    lot_settings=state["lots"],
                    source_snapshot=state["sources"],
                    skill_version=skill_version(rules),
                    skill_snapshot=rules,
                    runtime_version=RUNTIME_VERSION,
                    runtime_settings=runtime_settings,
                    reference_snapshot=references,
                )
                .returning(AnalysisReport.id, AnalysisReport.status)
            )
            .mappings()
            .one()
        )
    return dict(row)


def report_row(request: Request, report_id: int) -> dict:
    report = store(request).report(report_id)
    if report is None:
        raise ApiProblem(404, "not_found", "报告不存在")
    return report


def visible_items(
    db: KnowledgeStore, items: list[dict], allowed_collections: list[int] | None = None
) -> list[dict]:
    result = []
    for item in items:
        accessible = True
        values: list[dict] = []
        # 同一元素会被多个值引用，解析结果按元素复用，避免反复查库与重复解析正文。
        resolved_elements: dict[tuple, dict] = {}
        for value in item.get("values", []):
            refs: list[dict] = []
            for ref in value.get("citations", []):
                try:
                    if (
                        allowed_collections is not None
                        and ref["collection_id"] not in allowed_collections
                    ):
                        raise LookupError("已解除知识库关联")
                    element_key = (
                        ref.get("version_id"),
                        ref.get("parse_run_id"),
                        ref.get("element_id"),
                        ref.get("anchor"),
                    )
                    resolved = resolved_elements.get(element_key)
                    if resolved is None:
                        # 只判可见性时不需要正文，避免为被丢弃的 plain_text 渲染全文。
                        resolved = db.resolve(ref, with_content=not item.get("output"))
                        resolved_elements[element_key] = resolved
                except LookupError:
                    accessible = False
                    break
                # 历史报告可能把同块其它事实当摘录；展示前按值回查元素原文收敛定位，
                # 只在原文里确定性找到该值时改写，找不到就保留原引用，不伪造位置。
                refs.append(
                    dict(ref) if item.get("output") else align_citation(
                        {str(ref.get("block_id")): resolved},
                        ref,
                        str(value.get("value") or ""),
                    )
                )
            if not accessible:
                break
            values.append({**value, "citations": dedupe_citations(refs)})
        if accessible and values:
            item = {**item, "values": values}
        result.append(
            item
            if accessible
            else {
                "id": item["id"],
                **({"record_id": item["record_id"]} if item.get("record_id") else {}),
                "field": item.get("field", "来源已不可用"),
                "group": item.get("group", ""),
                "sort_order": item.get("sort_order", 0),
                "values": [],
                "note": "资料已删除或解除关联，请更新分析。",
                "verification": "unavailable",
            }
        )
    return result


@router.get("/analysis/reports/{report_id}")
@throttle_access_log()
def get_report(report_id: int, request: Request) -> dict:
    report = report_row(request, report_id)
    report.pop("skill_snapshot", None)
    db = store(request)
    modules = db.report_modules(report_id)
    allowed = db.collections_for_project(report["project_id"])
    for module in modules:
        # 工具日志只供服务端重放，不在产品界面暴露整段中间提示词。
        module.pop("trace", None)
        business = module.pop("business_data", None) or {}
        module["research_summary"] = business.get("research_summary", "")
        module["research_gaps"] = business.get("gaps", [])
    runs = db.report_runs(report_id)
    for module in modules:
        module["runs"] = [r for r in runs if r["module_id"] == module["id"]]
        latest = module["runs"][-1] if module["runs"] else {}
        merged = {item["id"]: item for item in module["items"]}
        # 已有报告的合格暂存字段也可直接展示，无需补跑模型或重写历史运行账。
        if module["status"] != "completed":
            merged.update(
                {
                    item["id"]: item
                    for item in latest.get("saved_items") or []
                    if item.get("verification") == "supported"
                }
            )
        # 同一字段的多版本在这里并成一行，历史报告也不再出现重复行与重复定位。
        module["items"] = visible_items(
            db,
            display_items(
                merge_field_entries(
                    list(merged.values()),
                    is_outline=module["module_key"] == "bid_format_outline_parsing",
                )
            ),
            allowed,
        )
    for run in runs:
        run.pop("saved_items", None)
    report["summary"] = visible_items(db, report["summary"], allowed)
    current = analysis_status(report["project_id"], request)
    live = {s["source_id"]: s for s in db.sources(allowed)}
    if any(
        source["source_id"] not in live
        or any(source.get(key) != live[source["source_id"]].get(key)
               for key in ("collection_id", "version_id", "parse_run_id"))
        for source in report["source_snapshot"] + report["reference_snapshot"]
    ):
        # 检索说明也可能包含已撤销资料的内容，不能只隐藏条目正文而留下说明旁路。
        for module in modules:
            module["research_summary"] = ""
            module["research_gaps"] = []
    # 旧运行时报告只读展示：前端据此隐藏补跑入口，服务端补跑也会拒绝。
    retired = report["runtime_version"] != RUNTIME_VERSION
    stale = (
        source_signature(current["sources"]) != source_signature(report["source_snapshot"])
        or current["analysis_category"] != report["category"]
        or current["analysis_topics"] != report["topics"]
        or [
            lot
            for lot in current["lots"]
            if not (
                lot["id"] in report.get("derived_lot_ids", [])
                and lot["id"] not in {old["id"] for old in report["lot_settings"]}
                and lot["category"] is None
                and lot["topics"] is None
            )
        ]
        != report["lot_settings"]
        # 参考来源快照只有当前运行时才会记录；旧报告该列为空，比较会恒判为已变化。
        or (
            not retired
            and source_signature(
                [s for s in db.sources(allowed) if s["project_id"] != report["project_id"]]
            )
            != source_signature(report["reference_snapshot"])
        )
    )
    with engine(request).connect() as connection:
        canceling = report["status"] == "canceled" and execution_active(connection, report_id)
    return {
        **report,
        "canceling": canceling,
        "modules": modules,
        "stale": stale,
        "runtime_retired": retired,
        "data_schema_version": None if retired else DATA_VERSION,
    }


def data_snapshot(request: Request, report_id: int, snapshot_id: int | None = None) -> dict:
    report = report_row(request, report_id)
    if report["runtime_version"] != RUNTIME_VERSION:
        raise ApiProblem(409, "data_reanalysis_required", "此报告没有业务数据，请重新发起分析")
    snapshot = store(request).data_snapshot(report_id, snapshot_id)
    if snapshot is None:
        raise ApiProblem(409, "data_not_ready", "正式业务数据快照尚未就绪")
    return snapshot


@router.get("/analysis/reports/{report_id}/modules/{module_key}/records")
@throttle_access_log()
def get_module_records(report_id: int, module_key: str, request: Request) -> dict:
    """直接读取子 Agent 逐条产出的 JSON，证据单独返回，不从报告文本反向解析。"""
    report = report_row(request, report_id)
    db = store(request)
    module = next((m for m in db.report_modules(report_id) if m["module_key"] == module_key), None)
    if module is None:
        raise ApiProblem(404, "not_found", "分析维度不存在")
    business = module.get("business_data") or {}
    allowed = db.collections_for_project(report["project_id"])
    stored_evidence = business.get("evidence", {})
    # records 可直接引用落盘证据；生成规则与写入时保持一致，避免两套指纹口径漂移。
    candidates = [
        record for record in module_records(business)
        if record.get("kind") != "coverage"
        and record.get("evidence_ids")
        and all(key in stored_evidence for key in record["evidence_ids"])
    ]
    # 一次判定全部记录的实时可见性，避免逐条解析同一批原文。
    visible = visible_items(db, [{
        "id": record["id"], "field": record.get("title", ""),
        "output": True,
        "values": [{"value": "", "citations": record["citations"]}],
    } for record in candidates], allowed)
    records, evidence = [], {}
    for record, result in zip(candidates, visible, strict=True):
        # 任一必要依据撤销时整条隐藏，不能用独立 JSON 绕过报告的实时权限检查。
        if result.get("verification") == "unavailable":
            continue
        data = {k: v for k, v in record.items() if k not in {"citations", "evidence_ids"}}
        data["evidence_ids"] = list(record["evidence_ids"])
        evidence.update({key: stored_evidence[key] for key in data["evidence_ids"]})
        records.append(data)
    return {"schema_version": DATA_VERSION, "module_key": module_key,
            "status": module["status"], "records": records, "evidence": evidence,
            # 布局取报告冻结的 Skill，前端不再抄写一套分类和列名规则。
            "output_schema": output_schema(report["skill_snapshot"], module_key)}


@router.get("/analysis/reports/{report_id}/data")
def get_analysis_data(
    report_id: int,
    request: Request,
    snapshot_id: int | None = Query(None, gt=0),
) -> dict:
    snapshot = data_snapshot(request, report_id, snapshot_id)
    report = get_report(report_id, request)
    db = store(request)
    return {
        "report_id": report_id,
        "snapshot_id": snapshot["id"],
        "revision": snapshot["revision"],
        "schema_version": snapshot["schema_version"],
        "stale": (
            report["stale"]
            or report["status"] in {"waiting", "pending", "running"}
            or data_snapshot(request, report_id)["id"] != snapshot["id"]
            or not snapshot_matches_report(db, snapshot)
        ),
        "data": accessible_data(
            db,
            snapshot["data"],
            db.collections_for_project(report["project_id"]),
            sources=snapshot["input_snapshot"]["source_snapshot"]
            + snapshot["input_snapshot"]["reference_snapshot"],
        ),
    }


def context_data(request: Request, report_id: int, snapshot: dict) -> tuple[dict, dict]:
    """取数前后共用有效性门禁，网络检索期间发生的撤销或补跑同样生效。"""
    report = get_report(report_id, request)
    if report["status"] in {"waiting", "pending", "running"}:
        raise ApiProblem(409, "report_running", "报告正在更新，请在本轮分析结束后获取编制依据")
    db = store(request)
    allowed = db.collections_for_project(report["project_id"])
    data = accessible_data(
        db,
        snapshot["data"],
        allowed,
        sources=snapshot["input_snapshot"]["source_snapshot"]
        + snapshot["input_snapshot"]["reference_snapshot"],
    )
    if any(g["code"] == "source_unavailable" for g in data["gaps"]):
        raise ApiProblem(409, "source_unavailable", "部分来源已删除或撤销访问，请更新分析")
    if (
        report["stale"]
        or data_snapshot(request, report_id)["id"] != snapshot["id"]
        or not snapshot_matches_report(db, snapshot)
    ):
        raise ApiProblem(409, "data_stale", "依据已更新，请使用当前有效分析快照")
    return report, data


@router.post("/analysis/reports/{report_id}/context")
async def get_analysis_context(report_id: int, payload: ContextInput, request: Request) -> dict:
    snapshot = data_snapshot(request, report_id, payload.snapshot_id)
    report, data = context_data(request, report_id, snapshot)
    try:
        context = build_context(data, payload)
    except ContextError as exc:
        raise ApiProblem(422, exc.code, str(exc)) from exc
    if payload.purpose == "content":
        sources = [
            s for s in report["reference_snapshot"] if s["purpose"] in {"company", "history"}
        ]
        if sources and context["requirements"]:
            db = store(request)
            rows, meta = await retrieve_chunks(
                db,
                sources,
                "\n".join(r["text"] for r in context["requirements"]),
                lambda: None,
                create_embedding_gateway,
                embedding_timeout=15,
            )
            # 不只重查参考片段；招标依据也可能在等待参考检索时被撤销或重跑。
            context_data(request, report_id, snapshot)
            live = db.collections_for_project(report["project_id"])
            for row in rows[:12]:
                if row["collection_id"] not in live:
                    continue
                try:
                    citation = db.resolve(
                        {
                            k: row[k]
                            for k in (
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
                    raise ApiProblem(
                        409,
                        "source_unavailable",
                        "参考来源已撤销，请更新分析",
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


@router.post("/analysis/reports/{report_id}/cancel")
def cancel_report(report_id: int, request: Request) -> dict:
    report_row(request, report_id)
    with engine(request).begin() as connection:
        status = connection.execute(
            select(AnalysisReport.status)
            .where(
                AnalysisReport.id == report_id,
                AnalysisReport.company_id == settings.company_id(),
            )
            .with_for_update()
        ).scalar_one()
        if status in {"waiting", "pending", "running", "canceled"}:
            connection.execute(
                update(AnalysisReport)
                .where(AnalysisReport.id == report_id)
                .values(
                    status="canceled",
                    finished_at=func.coalesce(AnalysisReport.finished_at, func.now()),
                    lease_until=None,
                )
            )
            cancel_unlocked_runs(connection, report_id)
            status = "canceled"
        canceling = status == "canceled" and execution_active(connection, report_id)
    publish_data_snapshot(store(request), report_id)
    return {"status": status, "canceling": canceling}


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
    if not db.run_belongs_to_report(run_id, report_id):
        raise ApiProblem(404, "not_found", "模块运行记录不存在")
    rows = db.run_events(run_id, after=after, limit=limit)
    return {"events": rows, "next_after": rows[-1]["id"] if rows else after}


@router.post("/analysis/reports/{report_id}/retry", status_code=202)
def retry_report(report_id: int, payload: RetryInput, request: Request) -> dict:
    report = report_row(request, report_id)
    # 旧固定字段流程已下线：历史报告只读展示，补跑必须先重新发起分析。
    if report["runtime_version"] != RUNTIME_VERSION:
        raise ApiProblem(409, "runtime_retired", "该报告由已下线的解析流程生成，请重新发起分析")
    # 补跑限制只看“是否正在执行”：失败/部分完成/已取消按原语义补跑未完成模块，
    # 显式指定模块时已完成的模块也可以重新解析；排队或执行中的报告必须拒绝，
    # 否则会与正在运行的 attempt 争抢同一模块。
    if report["status"] in {"waiting", "pending", "running"}:
        raise ApiProblem(409, "report_running", "报告正在排队或执行，请等待完成或先取消再补跑")
    keys = payload.module_keys or list(MODULES)
    if set(keys) - MODULES.keys():
        raise ApiProblem(400, "invalid_module", "未知解析模块")
    explicit = bool(payload.module_keys)
    with engine(request).begin() as connection:
        lock_project(connection, report["project_id"])
        # 并发点击补跑只能有一个请求创建新 attempt，不能重复重置预算。
        current_status = connection.execute(
            select(AnalysisReport.status).where(AnalysisReport.id == report_id).with_for_update()
        ).scalar_one()
        if current_status in {"waiting", "pending", "running"}:
            raise ApiProblem(409, "report_running", "报告已进入执行，请勿重复补跑")
        # 控制器持有整个执行周期的会话锁；旧 finally 完成前不可重置报告状态。
        if execution_active(connection, report_id) or not try_lock_report_execution(
            connection, report_id
        ):
            raise ApiProblem(409, "cancellation_pending", "任务正在停止，请等待模块退出后重新解析")
        if current_status == "canceled":
            cancel_unlocked_runs(connection, report_id)
        other = connection.execute(
            select(AnalysisReport.id).where(
                AnalysisReport.project_id == report["project_id"],
                AnalysisReport.id != report_id,
                AnalysisReport.status.in_(("waiting", "pending", "running")),
            )
        ).first()
        if other:
            raise ApiProblem(409, "analysis_in_flight", "项目已有其它分析任务")
        # 未指定模块时只补跑失败/已取消模块，保留已完成成果；显式指定时连已完成模块
        # 一起重跑，否则“重新解析本专题”会被静默忽略。
        modules_query = (
            select(AnalysisModule.id, AnalysisModule.status)
            .where(AnalysisModule.report_id == report_id, AnalysisModule.module_key.in_(keys))
            .with_for_update()
        )
        if not explicit:
            modules_query = modules_query.where(AnalysisModule.status.in_(("failed", "canceled")))
        rows = connection.execute(modules_query).mappings().all()
        has_modules = connection.execute(
            select(exists().where(AnalysisModule.report_id == report_id))
        ).scalar_one()
        if not rows and (explicit or has_modules):
            raise ApiProblem(
                409, "nothing_to_retry", "没有需要补跑的模块；重新解析已完成模块请显式指定模块"
            )
        # 已完成的模块重新解析时必须从零开始，否则继承的旧草稿会让新图直接收尾（等于没重跑）。
        restarted = {row["id"] for row in rows if row["status"] == "completed"}
        if restarted:
            connection.execute(
                update(AnalysisModule)
                .where(AnalysisModule.id.in_(sorted(restarted)))
                .values(items=[], business_data={})
            )
        retried = [row["id"] for row in rows]
        connection.execute(
            update(AnalysisModule)
            .where(AnalysisModule.id.in_(retried))
            .values(status="pending", error_message=None)
        )
        # 限值取配置中心当前值：用户调整预算后补跑必须生效，不能被创建时的旧快照锁死。
        limits = limits_snapshot(store(request))
        if payload.max_output_tokens is not None:
            limits["max_output_tokens"] = payload.max_output_tokens
        if payload.timeout_seconds is not None:
            limits["timeout_seconds"] = payload.timeout_seconds
        if not has_modules:
            connection.execute(
                update(AnalysisReport)
                .where(AnalysisReport.id == report_id)
                .values(runtime_settings=limits)
            )
        # 已有模块的运行账不因补跑改写；无模块的报告更新快照供延迟创建使用。
        for module_id in sorted(retried):
            attempt = connection.execute(
                select(func.coalesce(func.max(AgentModuleRun.attempt), 0) + 1).where(
                    AgentModuleRun.module_id == module_id
                )
            ).scalar_one()
            previous_state = (
                connection.execute(
                    select(AgentModuleRun.state)
                    .where(AgentModuleRun.module_id == module_id)
                    .order_by(AgentModuleRun.attempt.desc())
                    .limit(1)
                ).scalar_one_or_none()
                or {}
            )
            # 报告保持同一资料快照，访问权限会在恢复时重新检查；已核实字段无需再次调用模型。
            carry = (
                previous_state
                if module_id not in restarted
                and (previous_state.get("draft") or previous_state.get("staged_items"))
                else {}
            )
            if carry:
                # draft 会让新图直接结束，必须转成暂存后继续补齐未完成内容。
                draft = carry.pop("draft", None)
                if draft:
                    carry["staged_items"] = draft["fields"]
                    carry["staged_relations"] = draft.get("relations", [])
                    carry["staged_items_verified"] = all(
                        item.get("verification") == "supported" for item in draft["fields"]
                    )
                # 新attempt保留成果和证据，但不能继承旧调用ID缓存与纠错次数。
                carry.pop("tool_results", None)
                carry.pop("invalid_submissions", None)
                carry.pop("consecutive_invalid_submissions", None)
                carry.pop("consecutive_unsubmitted_responses", None)
                carry.pop("last_unsubmitted_message_id", None)
                carry.pop("field_failures", None)
                carry.pop("unavailable_submissions", None)
                for key in (
                    "loaded_skill",
                    "correction_failures",
                    "tool_failures",
                    "consecutive_tool_failures",
                    "identical_tool_calls",
                    "read_tool_cache",
                    "progress_message_id",
                    "progress_signature",
                    "no_progress_rounds",
                    "finish_only",
                    "subagent_retries",
                ):
                    carry.pop(key, None)
                # 旧校验失败可能遗留收尾意图；新 attempt 必须允许补读并重新确认完成。
                carry.pop("pending_final", None)
                try:
                    validate_project_claims(
                        carry.get("draft", {}).get("fields", carry.get("staged_items", [])),
                        report["project_id"],
                    )
                except ValueError:
                    carry = {}
            connection.execute(
                insert(AgentModuleRun).values(
                    module_id=module_id,
                    company_id=settings.company_id(),
                    attempt=attempt,
                    thread_id=f"analysis:{report_id}:{module_id}:{attempt}",
                    limits=limits,
                    state=carry,
                )
            )
        # 已固定检索批次的报告直接进入执行；从未开始的报告需要重新等候资料可用。
        status = (
            "pending"
            if retried and report["coverage"].get("mode") == "agent_research"
            else "waiting"
        )
        connection.execute(
            update(AnalysisReport)
            .where(AnalysisReport.id == report_id)
            .values(status=status, lease_until=None, error_message=None, finished_at=None)
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
                insert(KnowledgeAnswer)
                .values(
                    company_id=settings.company_id(),
                    project_id=project_id,
                    collection_ids=ids,
                    question=question,
                    snapshot={"sources": sources},
                )
                .returning(KnowledgeAnswer.id, KnowledgeAnswer.status)
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
# 问答执行期间前端每 2.5 秒查询进度和回答。
@throttle_access_log()
def get_answer(answer_id: int, request: Request) -> dict:
    db = store(request)
    answer = db.answer(answer_id)
    if answer is None:
        raise ApiProblem(404, "not_found", "回答不存在")
    allowed = (
        db.collections_for_project(answer["project_id"])
        if answer["project_id"]
        else answer["collection_ids"]
    )
    answer["items"] = visible_items(db, answer["items"], allowed)
    relations = []
    for relation in answer["relations"]:
        candidate = {
            "id": str(relation.get("id", "relation")),
            "values": [{"value": "", "citations": relation["citations"]}],
        }
        if visible_items(db, [candidate], allowed)[0].get("verification") != "unavailable":
            relations.append(relation)
    answer["relations"] = relations
    return answer
