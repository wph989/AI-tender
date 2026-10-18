"""知识库、综合分析与问答 HTTP 入口；业务逻辑在服务层。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field

from tender.api.shared.common import configs, engine
from tender.api.shared.dto import StrictModel
from tender.api.shared.errors import as_api_problem
from tender.api.shared.logging import throttle_access_log
from tender.application.knowledge.service import KnowledgeService
from tender.application.shared.errors import ServiceError
from tender.core import settings
from tender.core.di import create_knowledge_service

router = APIRouter(prefix="/api/v1", tags=["knowledge"])
Purpose = Literal["tender", "company", "history", "reference"]




class CollectionInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    purpose: Purpose


class LinkedCollections(StrictModel):
    collection_ids: list[int] = Field(max_length=100)










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


def knowledge_service(request: Request) -> KnowledgeService:
    return create_knowledge_service(engine(request), settings.company_id(), configs(request))




def store(request: Request):
    """兼容既有测试辅助；业务代码不应从路由层取仓储。"""
    return knowledge_service(request).store


def collection_or_404(request: Request, collection_id: int) -> dict:
    try:
        return knowledge_service(request).collection(collection_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


def project_collection(request: Request, project_id: int) -> int:
    try:
        return knowledge_service(request).project_collection(project_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


def public_sources(request: Request, ids: list[int]) -> list[dict]:
    return knowledge_service(request).public_sources(ids)


@router.get("/knowledge/collections")
def list_collections(request: Request) -> dict:
    return knowledge_service(request).list_collections()


@router.post("/knowledge/collections", status_code=201)
def create_collection(payload: CollectionInput, request: Request) -> dict:
    try:
        return knowledge_service(request).create_collection(
            name=payload.name,
            purpose=payload.purpose,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.get("/knowledge/collections/{collection_id}")
# 知识库页面持续查询来源处理和索引状态。
@throttle_access_log()
def get_collection(collection_id: int, request: Request) -> dict:
    try:
        return knowledge_service(request).get_collection(collection_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.patch("/knowledge/collections/{collection_id}")
def update_collection(collection_id: int, payload: CollectionInput, request: Request) -> dict:
    try:
        return knowledge_service(request).update_collection(
            collection_id,
            name=payload.name,
            purpose=payload.purpose,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.delete("/knowledge/collections/{collection_id}")
def delete_collection(collection_id: int, request: Request) -> dict:
    try:
        return knowledge_service(request).delete_collection(collection_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/knowledge/collections/{collection_id}/reindex", status_code=202)
def reindex_collection(collection_id: int, request: Request) -> dict:
    try:
        return knowledge_service(request).reindex_collection(collection_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.get("/knowledge/collections/{collection_id}/search")
async def search_collection(
    collection_id: int,
    request: Request,
    q: str = Query(min_length=1, max_length=2000),
) -> dict:
    try:
        return await knowledge_service(request).search_collection(collection_id, q)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/knowledge/citations/resolve")
def resolve_citation(payload: CitationInput, request: Request) -> dict:
    try:
        return knowledge_service(request).resolve_citation(payload.model_dump())
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/knowledge/embedding/test")
async def test_embedding(request: Request) -> dict:
    try:
        return await knowledge_service(request).test_embedding()
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/knowledge/sources/{source_id}/process", status_code=202)
def process_source(source_id: int, request: Request) -> dict:
    try:
        return knowledge_service(request).process_source(source_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.get("/projects/{project_id}/knowledge")
def project_knowledge(project_id: int, request: Request) -> dict:
    try:
        return knowledge_service(request).project_knowledge(project_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.put("/projects/{project_id}/knowledge/collections")
def link_collections(project_id: int, payload: LinkedCollections, request: Request) -> dict:
    try:
        return knowledge_service(request).link_collections(
            project_id,
            payload.collection_ids,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc






























def enqueue_question(
    request: Request,
    payload: AskInput,
    ids: list[int],
    project_id: int | None,
) -> dict:
    try:
        return knowledge_service(request).enqueue_question(
            question=payload.question,
            collection_ids=ids,
            project_id=project_id,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/knowledge/collections/{collection_id}/ask", status_code=202)
def ask_collection(collection_id: int, payload: AskInput, request: Request) -> dict:
    try:
        return knowledge_service(request).ask_collection(collection_id, payload.question)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/projects/{project_id}/knowledge/ask", status_code=202)
def ask_project(project_id: int, payload: AskInput, request: Request) -> dict:
    try:
        return knowledge_service(request).ask_project(
            project_id,
            payload.question,
            payload.collection_ids,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.get("/knowledge/answers/{answer_id}")
# 问答执行期间前端每 2.5 秒查询进度和回答。
@throttle_access_log()
def get_answer(answer_id: int, request: Request) -> dict:
    try:
        return knowledge_service(request).get_answer(answer_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc
