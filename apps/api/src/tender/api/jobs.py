"""持久任务查询、导出下载与 SSE 进度流。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from tender.api.common import engine
from tender.api.errors import ApiProblem
from tender.core import settings

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
_TERMINAL = frozenset({"completed", "partial", "failed", "canceled"})


def _payload(request: Request, job_id: str) -> dict[str, object] | None:
    with engine(request).connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT id, status, stage, progress, error_code, error_message,
                          version_id, run_id, created_at, updated_at, finished_at
                   FROM job WHERE id = :job_id AND company_id = :company_id"""
                ),
                {"job_id": job_id, "company_id": settings.company_id()},
            )
            .mappings()
            .first()
        )
    return dict(row) if row is not None else None


@router.get("/{job_id}")
def get_job(job_id: str, request: Request) -> dict[str, object]:
    payload = _payload(request, job_id)
    if payload is None:
        raise ApiProblem(404, "not_found", "任务不存在")
    return payload


@router.get("/{job_id}/download")
def download_export(job_id: str, request: Request) -> StreamingResponse:
    payload = _payload(request, job_id)
    if payload is None:
        raise ApiProblem(404, "not_found", "任务不存在")
    if payload["stage"] != "exporting" or payload["status"] != "completed":
        raise ApiProblem(409, "export_not_ready", "导出文件尚未生成")
    progress = payload.get("progress")
    key = progress.get("output_key") if isinstance(progress, dict) else None
    if not isinstance(key, str) or not key:
        raise ApiProblem(409, "export_not_ready", "导出文件地址尚未写入")
    blob = request.app.state.components.blobs.open(key)

    def body() -> Iterator[bytes]:
        try:
            while chunk := blob.stream.read(64 * 1024):
                yield chunk
        finally:
            blob.stream.close()

    return StreamingResponse(
        body(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=export.xlsx",
            "Content-Length": str(blob.size_bytes),
        },
    )


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    if _payload(request, job_id) is None:
        raise ApiProblem(404, "not_found", "任务不存在")

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
                event_type = "done" if payload["status"] in _TERMINAL else "progress"
                yield f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"
                last_sent = data
            if payload["status"] in _TERMINAL:
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


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, request: Request) -> dict[str, object]:
    """取消任务；已终态的任务返回 409，避免给出「取消成功」的假象。

    worker 侧的状态写入都拒绝把 canceled 改回去，所以取消后的任务不会再被在途任务复活。
    """
    db = engine(request)
    with db.begin() as connection:
        canceled = connection.execute(
            text(
                """UPDATE job
                   SET status = 'canceled', error_code = 'canceled_by_user',
                       error_message = '任务已由用户取消', finished_at = now(), updated_at = now()
                   WHERE id = :job_id AND company_id = :company_id
                     AND status NOT IN ('completed','partial','failed','canceled')
                   RETURNING id"""
            ),
            {"job_id": job_id, "company_id": settings.company_id()},
        ).scalar_one_or_none()
        if canceled is None:
            current = connection.execute(
                text("SELECT status FROM job WHERE id = :job_id AND company_id = :company_id"),
                {"job_id": job_id, "company_id": settings.company_id()},
            ).scalar_one_or_none()
            if current is None:
                raise ApiProblem(404, "not_found", "任务不存在")
            raise ApiProblem(409, "job_not_cancelable", f"任务已处于终态：{current}")
    payload = _payload(request, job_id)
    if payload is None:
        raise ApiProblem(404, "not_found", "任务不存在")
    return payload
