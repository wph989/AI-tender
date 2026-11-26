"""配置中心 HTTP 入口：运行与解析配置的读写、发布、确认与回滚。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from tender.api.shared.common import actor, configs, engine, role
from tender.api.shared.responses import (
    ConfigAcknowledgeResponse,
    ConfigAuditResponse,
    ConfigItemsResponse,
    ConfigReleaseListResponse,
    ConfigReleaseResponse,
)
from tender.application.configuration.service import ConfigService
from tender.core import settings
from tender.core.di import create_config_service

router = APIRouter(prefix="/api/v1/config", tags=["config"])


class ReleaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=1000)
    based_on: int | None = None


class ImpactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=100)
    ref: str = Field(min_length=1, max_length=500)


class AcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ImpactRef] = Field(min_length=1, max_length=500)
    comment: str | None = Field(default=None, max_length=1000)


class ActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000)


def _service(request: Request) -> ConfigService:
    return create_config_service(engine(request), settings.company_id(), configs(request))


@router.get("/items", response_model=ConfigItemsResponse, response_model_exclude_unset=True)
def list_items(request: Request) -> dict[str, Any]:
    return _service(request).list_items(role(request))


@router.get("/releases", response_model=ConfigReleaseListResponse)
def list_releases(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return _service(request).list_releases(status, limit)


@router.post("/releases", status_code=201, response_model=ConfigReleaseResponse,
             response_model_exclude_unset=True)
def create_release(payload: ReleaseCreate, request: Request) -> dict[str, Any]:
    return _service(request).create_release(
        values=payload.values,
        note=payload.note,
        based_on=payload.based_on,
        role=role(request),
        actor=actor(request),
    )


@router.get("/releases/{release_id}", response_model=ConfigReleaseResponse,
            response_model_exclude_unset=True)
def get_release(release_id: int, request: Request) -> dict[str, Any]:
    return _service(request).get_release(release_id)


@router.post("/releases/{release_id}/acknowledge", response_model=ConfigAcknowledgeResponse)
def acknowledge_release(
    release_id: int,
    payload: AcknowledgeRequest,
    request: Request,
) -> dict[str, Any]:
    return _service(request).acknowledge(
        release_id,
        items=[(item.kind, item.ref) for item in payload.items],
        comment=payload.comment,
        role=role(request),
        actor=actor(request),
    )


@router.post("/releases/{release_id}/activate", response_model=ConfigReleaseResponse,
             response_model_exclude_unset=True)
def activate_release(
    release_id: int,
    payload: ActivateRequest,
    request: Request,
) -> dict[str, Any]:
    return _service(request).activate(
        release_id,
        reason=payload.reason,
        role=role(request),
        actor=actor(request),
    )


@router.post("/releases/{release_id}/rollback", response_model=ConfigReleaseResponse,
             response_model_exclude_unset=True)
def rollback_release(
    release_id: int,
    payload: RollbackRequest,
    request: Request,
) -> dict[str, Any]:
    return _service(request).rollback(
        release_id,
        reason=payload.reason,
        role=role(request),
        actor=actor(request),
    )


@router.get("/audit", response_model=ConfigAuditResponse)
def list_audit(
    request: Request,
    release_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return _service(request).list_audit(release_id, limit)
