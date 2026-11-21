"""按版本触发首次解析或管理员重新解析的 HTTP 入口。"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from tender.api.shared.common import actor, configs, engine
from tender.api.shared.errors import as_api_problem
from tender.api.shared.responses import ParseJobCreatedResponse
from tender.application.documents.parsing import ParseService
from tender.application.shared.errors import ServiceError
from tender.core import settings
from tender.core.di import create_parse_service

router = APIRouter(prefix="/api/v1/versions", tags=["parsing"])


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: str | None = None
    ocr_mode: str | None = None
    force: bool = False
    reason: str | None = Field(default=None, max_length=1000)


def _service(request: Request) -> ParseService:
    return create_parse_service(engine(request), settings.company_id(), configs(request))


def _validate(payload: ParseRequest) -> None:
    try:
        ParseService.validate(
            tier=payload.tier,
            ocr_mode=payload.ocr_mode,
            force=payload.force,
            reason=payload.reason,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


def _create_parse_job(
    version_id: int,
    payload: ParseRequest,
    request: Request,
    *,
    force: bool,
) -> dict[str, object]:
    try:
        return _service(request).create_job(
            version_id,
            tier=payload.tier,
            ocr_mode=payload.ocr_mode,
            force=force,
            reason=payload.reason,
            actor=actor(request),
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/{version_id}/parse", status_code=202, response_model=ParseJobCreatedResponse)
def parse_version(
    version_id: int,
    request: Request,
    payload: ParseRequest,
) -> dict[str, object]:
    _validate(payload)
    return _create_parse_job(version_id, payload, request, force=payload.force)


@router.post("/{version_id}/reparse", status_code=202, response_model=ParseJobCreatedResponse)
def reparse_version(
    version_id: int,
    request: Request,
    payload: ParseRequest,
) -> dict[str, object]:
    forced = payload.model_copy(update={"force": True})
    _validate(forced)
    return _create_parse_job(version_id, forced, request, force=True)
