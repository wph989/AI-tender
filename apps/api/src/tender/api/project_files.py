"""项目文件上传、替换、元数据修改与软删除。"""

from __future__ import annotations

import asyncio
import hashlib
import io
import mimetypes
import zipfile
from pathlib import PurePosixPath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, insert, select, update
from starlette.responses import Response

from tender.adapters.pg.models import Job, Project, ProjectFile
from tender.adapters.pg.repositories.knowledge import sync_sources
from tender.api.common import blobs, engine, project_file_row
from tender.api.errors import ApiProblem
from tender.api.storage import stream_object
from tender.config.schema import parse_options
from tender.core import settings
from tender.domain.errors import TenderError
from tender.ports.blob_store import BlobStoreError

router = APIRouter(prefix="/api/v1/projects/{project_id}/files", tags=["project-files"])

_MAX_UPLOAD_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
_MAX_ARCHIVE_EXPANDED_BYTES = 512 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 500
_MAX_COMPRESSION_RATIO = 200
_ALLOWED_ROLES = frozenset(
    {"main", "clarification", "addendum", "boq", "drawing", "format", "other"}
)
_PARSEABLE_ROLES = _ALLOWED_ROLES
_PARSEABLE_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".odt",
        ".rtf",
        ".ppt",
        ".pptx",
        ".odp",
        ".xls",
        ".xlsx",
        ".xlsm",
        ".ods",
        ".csv",
        ".txt",
    }
)
_BOQ_EXTENSIONS = frozenset({".xls", ".xlsx", ".xlsm", ".ods"})
_DRAWING_EXTENSIONS = frozenset({".dwg", ".dxf", ".vsd", ".vsdx"})


class ProjectFilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=500)
    role: str | None = None
    sort_no: int | None = Field(default=None, ge=0)


class FileInput:
    def __init__(self, name: str, content: bytes) -> None:
        self.name = name
        self.content = content


@router.post("", status_code=202)
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
    _ensure_project(project_id, request)
    _validate_parse_config(tier, ocr_mode)
    uploads = files or []
    if len(uploads) > 100:
        raise ApiProblem(413, "too_many_files", "单次最多上传 100 个文件")
    known_sizes = [upload.size or 0 for upload in uploads]
    if archive is not None:
        known_sizes.append(archive.size or 0)
    if sum(known_sizes) > 1024 * 1024 * 1024:
        raise ApiProblem(413, "upload_too_large", "单次上传总量不能超过 1 GiB")
    items = [await _read_upload(upload, _MAX_UPLOAD_BYTES) for upload in uploads]
    skipped: list[dict[str, str]] = []
    if archive is not None:
        archive_input = await _read_upload(archive, _MAX_ARCHIVE_BYTES)
        extracted, archive_skipped = _read_archive(archive_input.content)
        items.extend(extracted)
        skipped.extend(archive_skipped)
    if not items:
        raise ApiProblem(400, "invalid_argument", "至少需要上传一个文件")

    added: list[dict[str, object]] = []
    jobs: list[str] = []
    retryable_failure = False
    for item in items:
        file_role = _validate_role(role) if role else _infer_role(item.name)
        try:
            result = await _add_project_file(
                request,
                project_id=project_id,
                item=item,
                role=file_role,
                auto_parse=auto_parse,
                tier=tier,
                ocr_mode=ocr_mode,
                replaces_id=None,
            )
        except ApiProblem as exc:
            skipped.append({"name": item.name, "reason": str(exc)})
            continue
        except TenderError as exc:
            skipped.append({"name": item.name, "reason": str(exc)})
            retryable_failure = retryable_failure or exc.retryable
            continue
        except BlobStoreError as exc:
            skipped.append({"name": item.name, "reason": str(exc)})
            retryable_failure = True
            continue
        added.append(result)
        if result["job_id"] is not None:
            jobs.append(str(result["job_id"]))

    if not added:
        raise ApiProblem(
            503 if retryable_failure else 422,
            "ingest_unavailable" if retryable_failure else "upload_failed",
            "没有文件成功入库",
            retryable=retryable_failure,
            detail={"skipped": skipped},
        )
    return {"added": added, "jobs": jobs, "skipped": skipped}


@router.patch("/{file_id}")
def patch_file(
    project_id: int,
    file_id: int,
    payload: ProjectFilePatch,
    request: Request,
) -> dict[str, object]:
    fields = payload.model_fields_set
    if not fields:
        raise ApiProblem(400, "invalid_argument", "至少需要修改一个文件字段")
    project_file_row(engine(request), project_id, file_id)
    values: dict[str, object] = {}
    if "display_name" in fields:
        name = (payload.display_name or "").strip()
        if not name:
            raise ApiProblem(400, "invalid_argument", "显示名称不能为空")
        values["display_name"] = name
    if "role" in fields:
        values["role"] = _validate_role(payload.role)
    if "sort_no" in fields:
        values["sort_no"] = payload.sort_no
    # project 侧条件收窄租户：company_id 不在 project_file 上，只能经项目主键回连。
    owned_project = (
        select(Project.id)
        .where(
            Project.id == project_id,
            Project.company_id == settings.company_id(),
            Project.deleted_at.is_(None),
        )
        .scalar_subquery()
    )
    with engine(request).begin() as connection:
        updated = connection.execute(
            update(ProjectFile)
            .where(
                ProjectFile.project_id == owned_project,
                ProjectFile.id == file_id,
                ProjectFile.deleted_at.is_(None),
            )
            .values(**values)
        ).rowcount
    if not updated:
        raise ApiProblem(404, "not_found", "项目文件不存在")
    row = project_file_row(engine(request), project_id, file_id)
    return {
        "project_file_id": row["id"],
        "project_id": row["project_id"],
        "version_id": row["version_id"],
        "role": row["role"],
        "display_name": row["display_name"],
        "is_parseable": row["is_parseable"],
        "sort_no": row["sort_no"],
        "sha256": row["sha256"],
        "mime": row["mime"],
        "size_bytes": row["size_bytes"],
    }


@router.post("/{file_id}/replace", status_code=202)
async def replace_file(
    project_id: int,
    file_id: int,
    request: Request,
    file: Annotated[UploadFile, File()],
    auto_parse: Annotated[bool, Form()] = True,
    tier: Annotated[str | None, Form()] = None,
    ocr_mode: Annotated[str | None, Form()] = None,
) -> dict[str, object]:
    _validate_parse_config(tier, ocr_mode)
    old = project_file_row(engine(request), project_id, file_id)
    item = await _read_upload(file, _MAX_UPLOAD_BYTES)
    result = await _add_project_file(
        request,
        project_id=project_id,
        item=item,
        role=str(old["role"]),
        auto_parse=auto_parse,
        tier=tier,
        ocr_mode=ocr_mode,
        replaces_id=file_id,
        sort_no=int(old["sort_no"]),
        display_name=str(old["display_name"]),
    )
    jobs = [str(result["job_id"])] if result["job_id"] else []
    return {"added": result, "jobs": jobs}


@router.delete("/{file_id}", status_code=204)
def delete_file(project_id: int, file_id: int, request: Request) -> Response:
    owned_project = (
        select(Project.id)
        .where(
            Project.id == project_id,
            Project.company_id == settings.company_id(),
            Project.deleted_at.is_(None),
        )
        .scalar_subquery()
    )
    with engine(request).begin() as connection:
        updated = connection.execute(
            update(ProjectFile)
            .where(
                ProjectFile.project_id == owned_project,
                ProjectFile.id == file_id,
                ProjectFile.deleted_at.is_(None),
            )
            .values(deleted_at=func.now())
        ).rowcount
    if not updated:
        raise ApiProblem(404, "not_found", "项目文件不存在")
    return Response(status_code=204)


@router.get("/{file_id}/original")
def get_original(project_id: int, file_id: int, request: Request) -> Response:
    row = project_file_row(engine(request), project_id, file_id)
    key = row["original_key"] or row["version_original_key"]
    if not key:
        raise ApiProblem(404, "not_found", "原件对象不存在")
    return stream_object(
        blobs(request),
        str(key),
        str(row["display_name"]),
        str(row["mime"] or "application/octet-stream"),
        request.headers.get("range"),
        inline=False,
    )


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
    name = display_name or item.name
    extension = PurePosixPath(name.lower()).suffix
    parseable = _role_is_parseable(role, extension)
    if parseable and extension == ".pdf" and not item.content.startswith(b"%PDF-"):
        raise ApiProblem(422, "invalid_pdf", "PDF 文件头无效")

    original_sha = hashlib.sha256(item.content).hexdigest()
    raw_mime = (
        "application/pdf"
        if extension == ".pdf"
        else (mimetypes.guess_type(name)[0] or "application/octet-stream")
    )
    original_key = f"original/{original_sha[:2]}/{original_sha}"
    await asyncio.to_thread(
        blobs(request).put,
        original_key,
        item.content,
        content_type=raw_mime,
    )

    company = settings.company_id()
    # 先读活动配置（可能走 Redis 缓存）再开事务：不在事务里等网络。
    active_config = request.app.state.components.configs.active(company)
    try:
        options = parse_options(
            active_config.resolved if active_config is not None else {}, tier, ocr_mode
        )
    except ValueError as exc:
        raise ApiProblem(400, "invalid_argument", str(exc)) from exc
    job_id: str | None = None
    with engine(request).begin() as connection:
        project = connection.execute(
            select(Project.id)
            .where(
                Project.id == project_id,
                Project.company_id == company,
                Project.deleted_at.is_(None),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if project is None:
            raise ApiProblem(404, "not_found", "项目不存在")
        if replaces_id is not None:
            replaces = connection.execute(
                select(ProjectFile.id).where(
                    ProjectFile.id == replaces_id,
                    ProjectFile.project_id == project_id,
                    ProjectFile.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
            if replaces is None:
                raise ApiProblem(404, "not_found", "待替换文件不存在")

        if sort_no is None:
            sort_no = int(
                connection.execute(
                    select(func.coalesce(func.max(ProjectFile.sort_no), -1) + 1).where(
                        ProjectFile.project_id == project_id,
                        ProjectFile.deleted_at.is_(None),
                    )
                ).scalar_one()
            )
        project_file_id = int(
            connection.execute(
                insert(ProjectFile)
                .values(
                    project_id=project_id,
                    version_id=None,
                    role=role,
                    display_name=name,
                    is_parseable=parseable,
                    replaces_id=replaces_id,
                    sort_no=sort_no,
                    original_key=original_key,
                    sha256=original_sha,
                    mime=raw_mime,
                    size_bytes=len(item.content),
                )
                .returning(ProjectFile.id)
            ).scalar_one()
        )
        sync_sources(connection, project_id)
        if parseable:
            job_id = f"job_{uuid4().hex}"
            stage = "probing" if extension == ".pdf" else "converting"
            snapshot_id = request.app.state.components.configs.snapshot_for_job(
                connection, active_config
            )
            connection.execute(
                insert(Job).values(
                    id=job_id,
                    company_id=company,
                    project_id=project_id,
                    project_file_id=project_file_id,
                    version_id=None,
                    status="pending",
                    stage=stage,
                    progress={},
                    config_snapshot={**options, "auto_parse": auto_parse},
                    config_snapshot_id=snapshot_id,
                )
            )

    return {
        "project_file_id": project_file_id,
        "display_name": name,
        "role": role,
        "is_parseable": parseable,
        "version_id": None,
        "job_id": job_id,
    }


async def _read_upload(upload: UploadFile, max_bytes: int) -> FileInput:
    name = _safe_filename(upload.filename or "")
    content = await upload.read(max_bytes + 1)
    await upload.close()
    if len(content) > max_bytes:
        raise ApiProblem(413, "upload_too_large", f"文件超过 {max_bytes} 字节限制")
    if not content:
        raise ApiProblem(400, "invalid_argument", "不能上传空文件")
    return FileInput(name, content)


def _read_archive(content: bytes) -> tuple[list[FileInput], list[dict[str, str]]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ApiProblem(400, "invalid_argument", "压缩包不是有效 ZIP 文件") from exc

    items: list[FileInput] = []
    skipped: list[dict[str, str]] = []
    try:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > _MAX_ARCHIVE_MEMBERS:
            raise ApiProblem(413, "archive_too_large", "ZIP 文件内项目数量超过限制")
        total_unpacked = 0
        for info in infos:
            normalized = info.filename.replace("\\", "/")
            path = PurePosixPath(normalized)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.name
                or (path.parts and path.parts[0].endswith(":"))
            ):
                skipped.append({"name": info.filename, "reason": "压缩包路径无效"})
                continue
            if info.filename.startswith("__MACOSX/") or path.name == ".DS_Store":
                continue
            total_unpacked += info.file_size
            if total_unpacked > _MAX_ARCHIVE_EXPANDED_BYTES:
                raise ApiProblem(413, "archive_too_large", "ZIP 解压后总大小超过限制")
            if info.file_size and not info.compress_size:
                raise ApiProblem(422, "invalid_archive", "ZIP 压缩比例异常")
            if info.compress_size and info.file_size / info.compress_size > _MAX_COMPRESSION_RATIO:
                raise ApiProblem(422, "invalid_archive", "ZIP 压缩比例超过限制")
            try:
                member = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                skipped.append({"name": info.filename, "reason": f"无法读取：{exc}"})
                continue
            items.append(FileInput(_safe_filename(path.name), member))
    finally:
        archive.close()
    return items, skipped


def _ensure_project(project_id: int, request: Request) -> None:
    from tender.api.common import project_row

    project_row(engine(request), project_id)


def _infer_role(filename: str) -> str:
    extension = PurePosixPath(filename.lower()).suffix
    if extension in _BOQ_EXTENSIONS:
        return "boq"
    if extension in _DRAWING_EXTENSIONS:
        return "drawing"
    return "main"


def _validate_role(role: str | None) -> str:
    value = (role or "").strip()
    if value not in _ALLOWED_ROLES:
        raise ApiProblem(400, "invalid_argument", "文件 role 不受支持")
    return value


def _role_is_parseable(role: str, extension: str) -> bool:
    return role in _PARSEABLE_ROLES and extension.lower() in _PARSEABLE_EXTENSIONS


def _validate_parse_config(tier: str | None, ocr_mode: str | None) -> None:
    if tier is not None and tier not in {"flash", "basic", "standard", "advanced"}:
        raise ApiProblem(400, "invalid_argument", "tier 不受支持")
    if ocr_mode is not None and ocr_mode not in {"auto", "txt", "ocr"}:
        raise ApiProblem(400, "invalid_argument", "ocr_mode 不受支持")


def _safe_filename(raw_name: str) -> str:
    name = PurePosixPath(raw_name.replace("\\", "/")).name.replace("\x00", "").strip()
    return name[:500] if name and name not in {".", ".."} else "document"
