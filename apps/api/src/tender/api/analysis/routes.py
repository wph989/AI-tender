"""综合分析与报告 HTTP 入口。"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field

from tender.api.shared.common import configs, engine
from tender.api.shared.dto import StrictModel
from tender.api.shared.errors import as_api_problem
from tender.api.shared.logging import throttle_access_log
from tender.application.analysis.data import ContextInput
from tender.application.analysis.service import AnalysisService
from tender.application.knowledge.service import visible_items as _visible_items
from tender.application.shared.errors import ServiceError
from tender.config.schema import field_bounds
from tender.core import settings
from tender.core.di import create_analysis_service

# 路径与现有 OpenAPI 标签保持一致，目录调整不改变客户端契约。
router = APIRouter(prefix="/api/v1", tags=["knowledge"])
Category = Literal["engineering", "goods", "service"]

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
    mode: Literal["restart", "resume"] | None = None
    # 补跑与配置中心统一允许正整数，避免接口额外挡住较小或较大的输出预算。
    max_output_tokens: int | None = Field(
        default=None, **field_bounds("analysis.max_output_tokens")
    )
    timeout_seconds: int | None = Field(default=None, **field_bounds("analysis.timeout_seconds"))


def analysis_service(request: Request) -> AnalysisService:
    return create_analysis_service(engine(request), settings.company_id(), configs(request))


@router.get("/projects/{project_id}/analysis")
# 分析页每三秒刷新状态、报告和专题记录。
@throttle_access_log()
def analysis_status(project_id: int, request: Request) -> dict:
    try:
        return analysis_service(request).analysis_status(project_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.put("/projects/{project_id}/analysis/settings")
def save_settings(project_id: int, payload: AnalysisSettings, request: Request) -> dict:
    try:
        return analysis_service(request).save_settings(
            project_id,
            category=payload.category,
            topics=payload.topics,
            lots=[lot.model_dump() for lot in payload.lots],
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/projects/{project_id}/analysis", status_code=202)
def start_analysis(project_id: int, payload: AnalysisInput, request: Request) -> dict:
    try:
        return analysis_service(request).start_analysis(
            project_id,
            allow_partial=payload.allow_partial,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


def report_row(request: Request, report_id: int) -> dict:
    try:
        return analysis_service(request).report_row(report_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


def visible_items(
    db, items: list[dict], allowed_collections: list[int] | None = None
) -> list[dict]:
    return _visible_items(db, items, allowed_collections)


@router.get("/analysis/reports/{report_id}")
@throttle_access_log()
def get_report(report_id: int, request: Request) -> dict:
    try:
        return analysis_service(request).get_report(report_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


def data_snapshot(request: Request, report_id: int, snapshot_id: int | None = None) -> dict:
    try:
        return analysis_service(request).data_snapshot(report_id, snapshot_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.get("/analysis/reports/{report_id}/modules/{module_key}/records")
@throttle_access_log()
def get_module_records(report_id: int, module_key: str, request: Request) -> dict:
    try:
        return analysis_service(request).get_module_records(report_id, module_key)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.get("/analysis/reports/{report_id}/data")
def get_analysis_data(
    report_id: int,
    request: Request,
    snapshot_id: int | None = Query(None, gt=0),
) -> dict:
    try:
        return analysis_service(request).get_analysis_data(report_id, snapshot_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


def context_data(request: Request, report_id: int, snapshot: dict) -> tuple[dict, dict]:
    try:
        return analysis_service(request).context_data(report_id, snapshot)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/analysis/reports/{report_id}/context")
async def get_analysis_context(
    report_id: int,
    payload: ContextInput,
    request: Request,
) -> dict:
    try:
        return await analysis_service(request).get_analysis_context(report_id, payload)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/analysis/reports/{report_id}/cancel")
def cancel_report(report_id: int, request: Request) -> dict:
    try:
        return analysis_service(request).cancel_report(report_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.get("/analysis/reports/{report_id}/runs/{run_id}/events")
def run_events(
    report_id: int,
    run_id: int,
    request: Request,
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
) -> dict:
    try:
        return analysis_service(request).run_events(
            report_id,
            run_id,
            after=after,
            limit=limit,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/analysis/reports/{report_id}/retry", status_code=202)
def retry_report(report_id: int, payload: RetryInput, request: Request) -> dict:
    try:
        return analysis_service(request).retry_report(
            report_id,
            module_keys=payload.module_keys,
            max_output_tokens=payload.max_output_tokens,
            timeout_seconds=payload.timeout_seconds,
            mode=payload.mode,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc
