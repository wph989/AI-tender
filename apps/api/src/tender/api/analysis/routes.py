"""综合分析与报告 HTTP 入口。"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field

from tender.api.shared.common import actor, configs, engine
from tender.api.shared.dto import StrictModel
from tender.api.shared.logging import throttle_access_log
from tender.api.shared.responses import (
    AnalysisContextResponse,
    AnalysisDataResponse,
    AnalysisEventsResponse,
    AnalysisReportResponse,
    AnalysisStartResponse,
    AnalysisStatusResponse,
    CancelReportResponse,
    HumanReviewResponse,
    ModuleRecordsResponse,
    ReportRecordsResponse,
    RetriedReportResponse,
)
from tender.application.analysis.data import ContextInput
from tender.application.analysis.human_review import RecordReviewInput
from tender.application.analysis.service import AnalysisService
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


class ReportRecordsInput(StrictModel):
    module_keys: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(max_length=13)
    versions: dict[str, Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]] = Field(
        default_factory=dict, max_length=13,
    )


def analysis_service(request: Request) -> AnalysisService:
    return create_analysis_service(engine(request), settings.company_id(), configs(request))


@router.get("/projects/{project_id}/analysis", response_model=AnalysisStatusResponse,
            response_model_exclude_unset=True)
# 分析页每三秒刷新状态、报告和专题记录。
@throttle_access_log()
def analysis_status(project_id: int, request: Request) -> dict:
    return analysis_service(request).analysis_status(project_id)


@router.put("/projects/{project_id}/analysis/settings", response_model=AnalysisStatusResponse,
            response_model_exclude_unset=True)
def save_settings(project_id: int, payload: AnalysisSettings, request: Request) -> dict:
    return analysis_service(request).save_settings(
        project_id,
        category=payload.category,
        topics=payload.topics,
        lots=[lot.model_dump() for lot in payload.lots],
    )


@router.post("/projects/{project_id}/analysis", status_code=202,
             response_model=AnalysisStartResponse, response_model_exclude_unset=True)
def start_analysis(project_id: int, payload: AnalysisInput, request: Request) -> dict:
    return analysis_service(request).start_analysis(
        project_id,
        allow_partial=payload.allow_partial,
    )


@router.get("/analysis/reports/{report_id}", response_model=AnalysisReportResponse,
            response_model_exclude_unset=True)
@throttle_access_log()
def get_report(report_id: int, request: Request) -> dict:
    return analysis_service(request).get_report(report_id)


@router.get("/analysis/reports/{report_id}/modules/{module_key}/records",
            response_model=ModuleRecordsResponse, response_model_exclude_unset=True)
def get_module_records(report_id: int, module_key: str, request: Request) -> dict:
    return analysis_service(request).get_module_records(report_id, module_key)


@router.post("/analysis/reports/{report_id}/records", response_model=ReportRecordsResponse,
             response_model_exclude_unset=True)
@throttle_access_log()
def get_report_records(report_id: int, payload: ReportRecordsInput, request: Request) -> dict:
    return analysis_service(request).get_report_records(
        report_id, payload.module_keys, payload.versions,
    )


@router.get("/analysis/reports/{report_id}/data", response_model=AnalysisDataResponse)
def get_analysis_data(
    report_id: int,
    request: Request,
    snapshot_id: int | None = Query(None, gt=0),
) -> dict:
    return analysis_service(request).get_analysis_data(report_id, snapshot_id)


@router.post("/analysis/reports/{report_id}/context", response_model=AnalysisContextResponse,
             response_model_exclude_unset=True)
async def get_analysis_context(
    report_id: int,
    payload: ContextInput,
    request: Request,
) -> dict:
    return await analysis_service(request).get_analysis_context(report_id, payload)


@router.post("/analysis/reports/{report_id}/cancel", response_model=CancelReportResponse)
def cancel_report(report_id: int, request: Request) -> dict:
    return analysis_service(request).cancel_report(report_id)


@router.get("/analysis/reports/{report_id}/runs/{run_id}/events",
            response_model=AnalysisEventsResponse)
def run_events(
    report_id: int,
    run_id: int,
    request: Request,
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
) -> dict:
    return analysis_service(request).run_events(
        report_id,
        run_id,
        after=after,
        limit=limit,
    )


@router.post("/analysis/reports/{report_id}/retry", status_code=202,
             response_model=RetriedReportResponse)
def retry_report(report_id: int, payload: RetryInput, request: Request) -> dict:
    return analysis_service(request).retry_report(
        report_id,
        module_keys=payload.module_keys,
        max_output_tokens=payload.max_output_tokens,
        timeout_seconds=payload.timeout_seconds,
        mode=payload.mode,
    )


@router.post("/analysis/reports/{report_id}/reviews", response_model=HumanReviewResponse,
             response_model_exclude_unset=True)
def review_record(report_id: int, payload: RecordReviewInput, request: Request) -> dict:
    return analysis_service(request).record_human_review(
        report_id, payload, actor=actor(request),
    )
