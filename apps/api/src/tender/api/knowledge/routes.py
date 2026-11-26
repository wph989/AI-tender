"""知识库、资料检索与问答HTTP入口；业务流程与异常映射由用例和全局处理器负责。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field

from tender.api.shared.common import configs, engine
from tender.api.shared.dto import StrictModel
from tender.api.shared.logging import throttle_access_log
from tender.api.shared.responses import (
    CitationResolutionResponse,
    CollectionResponse,
    DeleteResponse,
    EmbeddingTestResponse,
    IdStatusResponse,
    KnowledgeAnswerResponse,
    KnowledgeCollectionListResponse,
    KnowledgeSearchResponse,
    KnowledgeSourcesResponse,
    LinkedCollectionsResponse,
    QueuedCountResponse,
)
from tender.application.knowledge.service import KnowledgeService
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


@router.get("/knowledge/collections", response_model=KnowledgeCollectionListResponse,
            response_model_exclude_unset=True)
def list_collections(request: Request) -> dict:
    return knowledge_service(request).list_collections()


@router.post("/knowledge/collections", status_code=201, response_model=CollectionResponse,
             response_model_exclude_unset=True)
def create_collection(payload: CollectionInput, request: Request) -> dict:
    return knowledge_service(request).create_collection(
        name=payload.name,
        purpose=payload.purpose,
    )


@router.get("/knowledge/collections/{collection_id}", response_model=CollectionResponse,
            response_model_exclude_unset=True)
# 知识库页面持续查询来源处理和索引状态。
@throttle_access_log()
def get_collection(collection_id: int, request: Request) -> dict:
    return knowledge_service(request).get_collection(collection_id)


@router.patch("/knowledge/collections/{collection_id}", response_model=CollectionResponse,
              response_model_exclude_unset=True)
def update_collection(collection_id: int, payload: CollectionInput, request: Request) -> dict:
    return knowledge_service(request).update_collection(
        collection_id,
        name=payload.name,
        purpose=payload.purpose,
    )


@router.delete("/knowledge/collections/{collection_id}", response_model=DeleteResponse)
def delete_collection(collection_id: int, request: Request) -> dict:
    return knowledge_service(request).delete_collection(collection_id)


@router.post("/knowledge/collections/{collection_id}/reindex", status_code=202,
             response_model=QueuedCountResponse)
def reindex_collection(collection_id: int, request: Request) -> dict:
    return knowledge_service(request).reindex_collection(collection_id)


@router.get("/knowledge/collections/{collection_id}/search",
            response_model=KnowledgeSearchResponse, response_model_exclude_unset=True)
async def search_collection(
    collection_id: int,
    request: Request,
    q: str = Query(min_length=1, max_length=2000),
) -> dict:
    return await knowledge_service(request).search_collection(collection_id, q)


@router.post("/knowledge/citations/resolve", response_model=CitationResolutionResponse,
             response_model_exclude_unset=True)
def resolve_citation(payload: CitationInput, request: Request) -> dict:
    return knowledge_service(request).resolve_citation(payload.model_dump())


@router.post("/knowledge/embedding/test", response_model=EmbeddingTestResponse)
async def test_embedding(request: Request) -> dict:
    return await knowledge_service(request).test_embedding()


@router.post("/knowledge/sources/{source_id}/process", status_code=202,
             response_model=IdStatusResponse, response_model_exclude_unset=True)
def process_source(source_id: int, request: Request) -> dict:
    return knowledge_service(request).process_source(source_id)


@router.get("/projects/{project_id}/knowledge", response_model=KnowledgeSourcesResponse,
            response_model_exclude_unset=True)
def project_knowledge(project_id: int, request: Request) -> dict:
    return knowledge_service(request).project_knowledge(project_id)


@router.put("/projects/{project_id}/knowledge/collections",
            response_model=LinkedCollectionsResponse)
def link_collections(project_id: int, payload: LinkedCollections, request: Request) -> dict:
    return knowledge_service(request).link_collections(
        project_id,
        payload.collection_ids,
    )


def enqueue_question(
    request: Request,
    payload: AskInput,
    ids: list[int],
    project_id: int | None,
) -> dict:
    return knowledge_service(request).enqueue_question(
        question=payload.question,
        collection_ids=ids,
        project_id=project_id,
    )


@router.post("/knowledge/collections/{collection_id}/ask", status_code=202,
             response_model=IdStatusResponse, response_model_exclude_unset=True)
def ask_collection(collection_id: int, payload: AskInput, request: Request) -> dict:
    return knowledge_service(request).ask_collection(collection_id, payload.question)


@router.post("/projects/{project_id}/knowledge/ask", status_code=202,
             response_model=IdStatusResponse, response_model_exclude_unset=True)
def ask_project(project_id: int, payload: AskInput, request: Request) -> dict:
    return knowledge_service(request).ask_project(
        project_id,
        payload.question,
        payload.collection_ids,
    )


@router.get("/knowledge/answers/{answer_id}", response_model=KnowledgeAnswerResponse,
            response_model_exclude_unset=True)
# 问答执行期间前端每 2.5 秒查询进度和回答。
@throttle_access_log()
def get_answer(answer_id: int, request: Request) -> dict:
    return knowledge_service(request).get_answer(answer_id)
