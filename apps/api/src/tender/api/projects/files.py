"""项目文件上传、替换、元数据修改与软删除接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import Response

from tender.api.shared.common import actor, blobs, configs, engine
from tender.api.shared.errors import as_api_problem
from tender.api.shared.responses import ProjectFileResponse, ReplaceFileResponse, UploadResponse
from tender.api.shared.storage import stream_object
from tender.application.projects.files import (
    MAX_ARCHIVE_BYTES,
    MAX_UPLOAD_BYTES,
    MAX_UPLOAD_TOTAL_BYTES,
    FileInput,
    ProjectFileService,
    safe_filename,
    validate_upload_limits,
)
from tender.application.shared.errors import InvalidArgument, PayloadTooLarge, ServiceError
from tender.core import settings
from tender.core.di import create_project_file_service

router = APIRouter(prefix="/api/v1/projects/{project_id}/files", tags=["project-files"])

class ProjectFilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=500)
    role: str | None = None
    sort_no: int | None = Field(default=None, ge=0)


def _service(request: Request) -> ProjectFileService:
    return create_project_file_service(
        engine(request),
        settings.company_id(),
        blobs(request),
        configs(request),
    )


@router.post("", status_code=202, response_model=UploadResponse)
async def upload_files(
    project_id: int,
    request: Request,
    files: Annotated[list[UploadFile] | None, File()] = None,
    archive: Annotated[UploadFile | None, File()] = None,
    auto_parse: Annotated[bool, Form()] = True,
    tier: Annotated[str | None, Form()] = None,
    ocr_mode: Annotated[str | None, Form()] = None,
    role: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    try:
        incoming = files or []
        known_total = sum(upload.size or 0 for upload in incoming)
        if archive is not None:
            known_total += archive.size or 0
        validate_upload_limits(len(incoming), known_total)
        uploads = []
        total_bytes = 0
        for upload in incoming:
            item = await _read_upload(upload, MAX_UPLOAD_BYTES, total_bytes=total_bytes)
            uploads.append(item)
            total_bytes += len(item.content)
        archive_input = (
            await _read_upload(archive, MAX_ARCHIVE_BYTES, total_bytes=total_bytes)
            if archive is not None else None
        )
        return await _service(request).upload(
            project_id=project_id,
            files=uploads,
            archive=archive_input,
            auto_parse=auto_parse,
            tier=tier,
            ocr_mode=ocr_mode,
            role=role,
            actor=actor(request),
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc

@router.patch("/{file_id}", response_model=ProjectFileResponse)
def patch_file(
    project_id: int,
    file_id: int,
    payload: ProjectFilePatch,
    request: Request,
) -> dict[str, object]:
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}
    try:
        return _service(request).patch(project_id, file_id, changes)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.post("/{file_id}/replace", status_code=202, response_model=ReplaceFileResponse)
async def replace_file(
    project_id: int,
    file_id: int,
    request: Request,
    file: Annotated[UploadFile, File()],
    auto_parse: Annotated[bool, Form()] = True,
    tier: Annotated[str | None, Form()] = None,
    ocr_mode: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    try:
        item = await _read_upload(file, MAX_UPLOAD_BYTES)
        return await _service(request).replace(
            project_id=project_id,
            file_id=file_id,
            item=item,
            auto_parse=auto_parse,
            tier=tier,
            ocr_mode=ocr_mode,
            actor=actor(request),
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc


@router.delete("/{file_id}", status_code=204, response_model=None)
def delete_file(project_id: int, file_id: int, request: Request) -> Response:
    try:
        _service(request).delete(project_id, file_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc
    return Response(status_code=204)


@router.get("/{file_id}/original", response_model=None)
def get_original(project_id: int, file_id: int, request: Request) -> Response:
    try:
        original = _service(request).original(project_id, file_id)
    except ServiceError as exc:
        raise as_api_problem(exc) from exc
    return stream_object(
        blobs(request),
        original["key"],
        original["filename"],
        original["content_type"],
        request.headers.get("range"),
        inline=False,
    )


async def _read_upload(
    upload: UploadFile, max_bytes: int, *, total_bytes: int = 0,
) -> FileInput:
    name = safe_filename(upload.filename or "")
    # 元数据可能没有大小；每次最多读剩余额度加一个探测字节，避免超限后才分配大块内存。
    read_limit = min(max_bytes, MAX_UPLOAD_TOTAL_BYTES - total_bytes)
    try:
        content = await upload.read(read_limit + 1)
    finally:
        await upload.close()
    if len(content) > max_bytes:
        raise PayloadTooLarge(f"文件超过 {max_bytes} 字节限制")
    validate_upload_limits(0, total_bytes + len(content))
    if not content:
        raise InvalidArgument("不能上传空文件")
    return FileInput(name, content)


async def _add_project_file(
    request: Request,
    *,
    project_id: int,
    item: FileInput,
    role: str,
    auto_parse: bool,
    tier: str | None,
    ocr_mode: str | None,
    replaces_id: int | None,
    sort_no: int | None = None,
    display_name: str | None = None,
) -> dict[str, object]:
    """保留旧入口给内部调用与回归测试；实际逻辑在服务层。"""
    try:
        return await _service(request).add_project_file(
            project_id=project_id,
            item=item,
            role=role,
            auto_parse=auto_parse,
            tier=tier,
            ocr_mode=ocr_mode,
            replaces_id=replaces_id,
            actor=actor(request),
            sort_no=sort_no,
            display_name=display_name,
        )
    except ServiceError as exc:
        raise as_api_problem(exc) from exc
