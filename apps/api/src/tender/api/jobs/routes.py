"""持久任务查询与 SSE 进度流；数据读取委托服务层。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from tender.api.shared.common import engine
from tender.api.shared.logging import throttle_access_log
from tender.api.shared.responses import JobResponse
from tender.application.jobs.service import JobService
from tender.application.shared.errors import ServiceError
from tender.core import settings
from tender.core.di import create_job_service

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _service(request: Request) -> JobService:
    return create_job_service(engine(request), settings.company_id())


def _payload(request: Request, job_id: str) -> dict[str, object] | None:
    try:
        return _service(request).payload(job_id)
    except ServiceError:
        return None


@router.get("/{job_id}", response_model=JobResponse)
# 前端等待解析时每秒查询，只压缩重复访问摘要。
@throttle_access_log()
def get_job(job_id: str, request: Request) -> dict[str, object]:
    # 普通查询和建流前核验共用权限与错误转换，避免两处口径漂移。
    return _payload_or_raise(request, job_id)


@router.get("/{job_id}/events", response_model=None)
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    _payload_or_raise(request, job_id)

    async def events() -> AsyncIterator[str]:
        last_sent: str | None = None
        heartbeat_at = asyncio.get_running_loop().time()
        while not await request.is_disconnected():
            payload = await asyncio.to_thread(_payload, request, job_id)
            if payload is None:
                yield 'event: error\ndata: {"code":"not_found"}\n\n'
                return
            data = json.dumps(payload, ensure_ascii=False, default=str)
            if data != last_sent:
                updated_at = payload["updated_at"]
                event_id = (
                    int(updated_at.timestamp() * 1000) if hasattr(updated_at, "timestamp") else 0
                )
                event_type = "done" if _service(request).is_terminal(payload) else "progress"
                yield f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"
                last_sent = data
            if _service(request).is_terminal(payload):
                return
            now = asyncio.get_running_loop().time()
            if now - heartbeat_at >= 15:
                yield ": heartbeat\n\n"
                heartbeat_at = now
            await asyncio.sleep(1)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _payload_or_raise(request: Request, job_id: str) -> dict[str, object]:
    return _service(request).payload(job_id)


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str, request: Request) -> dict[str, object]:
    """取消任务；已终态的任务返回 409，避免给出「取消成功」的假象。"""
    return _service(request).cancel(job_id)
