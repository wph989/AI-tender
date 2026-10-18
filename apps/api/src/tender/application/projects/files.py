"""项目文件上传、替换、元数据与原件访问的业务编排。"""

from __future__ import annotations

import asyncio
import hashlib
import io
import mimetypes
import zipfile
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from tender.application.shared.errors import (
    InvalidArgument,
    NotFound,
    PayloadTooLarge,
    ServiceError,
    Unavailable,
    Unprocessable,
)
from tender.config.schema import document_execution_snapshot, parse_options
from tender.domain.shared.errors import TenderError
from tender.ports.configuration.registry import ConfigReader
from tender.ports.repository.projects.files import ProjectFileRepository
from tender.ports.storage.blob_store import BlobStore, BlobStoreError

MAX_UPLOAD_FILES = 100
MAX_UPLOAD_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 500
MAX_COMPRESSION_RATIO = 200
ALLOWED_ROLES = frozenset(
    {"main", "clarification", "addendum", "boq", "drawing", "format", "other"}
)
PARSEABLE_ROLES = ALLOWED_ROLES
PARSEABLE_EXTENSIONS = frozenset(
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
BOQ_EXTENSIONS = frozenset({".xls", ".xlsx", ".xlsm", ".ods"})
DRAWING_EXTENSIONS = frozenset({".dwg", ".dxf", ".vsd", ".vsdx"})


class FileInput:
    def __init__(self, name: str, content: bytes) -> None:
        self.name = name
        self.content = content


def validate_upload_limits(file_count: int, total_bytes: int) -> None:
    """入口预检和用例复用同一规则，避免文件已读入内存才发现批次超限。"""
    if file_count > MAX_UPLOAD_FILES:
        raise PayloadTooLarge("单次最多上传 100 个文件", code="too_many_files")
    if total_bytes > MAX_UPLOAD_TOTAL_BYTES:
        raise PayloadTooLarge("单次上传总量不能超过 1 GiB")


def safe_filename(raw_name: str) -> str:
    name = PurePosixPath(raw_name.replace(chr(92), "/")).name.replace(chr(0), "").strip()
    return name[:500] if name and name not in {".", ".."} else "document"


def infer_role(filename: str) -> str:
    extension = PurePosixPath(filename.lower()).suffix
    if extension in BOQ_EXTENSIONS:
        return "boq"
    if extension in DRAWING_EXTENSIONS:
        return "drawing"
    return "main"


def validate_role(role: str | None) -> str:
    value = (role or "").strip()
    if value not in ALLOWED_ROLES:
        raise InvalidArgument("文件 role 不受支持")
    return value


def role_is_parseable(role: str, extension: str) -> bool:
    return role in PARSEABLE_ROLES and extension.lower() in PARSEABLE_EXTENSIONS


def validate_parse_config(tier: str | None, ocr_mode: str | None) -> None:
    if tier is not None and tier not in {"flash", "basic", "standard", "advanced"}:
        raise InvalidArgument("tier 不受支持")
    if ocr_mode is not None and ocr_mode not in {"auto", "txt", "ocr"}:
        raise InvalidArgument("ocr_mode 不受支持")


def read_archive(content: bytes) -> tuple[list[FileInput], list[dict[str, str]]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (OSError, zipfile.BadZipFile) as exc:
        raise InvalidArgument("压缩包不是有效 ZIP 文件") from exc

    items: list[FileInput] = []
    skipped: list[dict[str, str]] = []
    try:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > MAX_ARCHIVE_MEMBERS:
            raise PayloadTooLarge("ZIP 文件内项目数量超过限制", code="archive_too_large")
        total_unpacked = 0
        for info in infos:
            normalized = info.filename.replace(chr(92), "/")
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
            if total_unpacked > MAX_ARCHIVE_EXPANDED_BYTES:
                raise PayloadTooLarge("ZIP 解压后总大小超过限制", code="archive_too_large")
            if info.file_size and not info.compress_size:
                raise Unprocessable("ZIP 压缩比例异常", code="invalid_archive")
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise Unprocessable("ZIP 压缩比例超过限制", code="invalid_archive")
            try:
                member = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                skipped.append({"name": info.filename, "reason": f"无法读取：{exc}"})
                continue
            items.append(FileInput(safe_filename(path.name), member))
    finally:
        archive.close()
    return items, skipped


class ProjectFileService:
    def __init__(
        self,
        repository: ProjectFileRepository,
        company_id: int,
        blobs: BlobStore,
        configs: ConfigReader,
    ) -> None:
        self.repository = repository
        self.company_id = company_id
        self.blobs = blobs
        self.configs = configs

    def ensure_project(self, project_id: int) -> None:
        if not self.repository.project_exists(project_id):
            raise NotFound("项目不存在")

    async def upload(
        self,
        *,
        project_id: int,
        files: list[FileInput],
        archive: FileInput | None,
        auto_parse: bool,
        tier: str | None,
        ocr_mode: str | None,
        role: str | None,
        actor: str,
    ) -> dict[str, Any]:
        self.ensure_project(project_id)
        validate_parse_config(tier, ocr_mode)
        known_sizes = [len(item.content) for item in files]
        if archive is not None:
            known_sizes.append(len(archive.content))
        validate_upload_limits(len(files), sum(known_sizes))
        items = list(files)
        skipped: list[dict[str, str]] = []
        if archive is not None:
            extracted, archive_skipped = read_archive(archive.content)
            items.extend(extracted)
            skipped.extend(archive_skipped)
        if not items:
            raise InvalidArgument("至少需要上传一个文件")

        added: list[dict[str, object]] = []
        jobs: list[str] = []
        retryable_failure = False
        for item in items:
            file_role = validate_role(role) if role else infer_role(item.name)
            try:
                result = await self.add_project_file(
                    project_id=project_id,
                    item=item,
                    role=file_role,
                    auto_parse=auto_parse,
                    tier=tier,
                    ocr_mode=ocr_mode,
                    replaces_id=None,
                    actor=actor,
                )
            except (ServiceError, TenderError) as exc:
                skipped.append({"name": item.name, "reason": str(exc)})
                retryable_failure = retryable_failure or exc.retryable
                continue
            except BlobStoreError as exc:
                # 单个文件存储失败不能丢掉已经提交的成功回执，也不能阻断后续文件。
                skipped.append({"name": item.name, "reason": str(exc)})
                retryable_failure = True
                continue
            added.append(result)
            if result["job_id"]:
                jobs.append(str(result["job_id"]))
        if not added:
            if retryable_failure:
                raise Unavailable(
                    "没有文件成功入库",
                    code="ingest_unavailable",
                    retryable=True,
                    detail={"skipped": skipped},
                )
            raise Unprocessable(
                "没有文件成功入库",
                code="upload_failed",
                detail={"skipped": skipped},
            )
        return {"added": added, "jobs": jobs, "skipped": skipped}

    async def add_project_file(
        self,
        *,
        project_id: int,
        item: FileInput,
        role: str,
        auto_parse: bool,
        tier: str | None,
        ocr_mode: str | None,
        replaces_id: int | None,
        actor: str,
        sort_no: int | None = None,
        display_name: str | None = None,
    ) -> dict[str, object]:
        name = display_name or item.name
        extension = PurePosixPath(name.lower()).suffix
        parseable = role_is_parseable(role, extension)
        if parseable and extension == ".pdf" and not item.content.startswith(b"%PDF-"):
            raise Unprocessable("PDF 文件头无效", code="invalid_pdf")

        original_sha = hashlib.sha256(item.content).hexdigest()
        raw_mime = (
            "application/pdf"
            if extension == ".pdf"
            else (mimetypes.guess_type(name)[0] or "application/octet-stream")
        )
        original_key = f"original/{original_sha[:2]}/{original_sha}"
        await asyncio.to_thread(
            self.blobs.put,
            original_key,
            item.content,
            content_type=raw_mime,
        )

        # 活动配置可能走 Redis 缓存，必须在数据库事务之外读取，避免持锁等网络。
        active_config = self.configs.active(self.company_id)
        try:
            options = parse_options(
                active_config.resolved if active_config is not None else {}, tier, ocr_mode
            )
        except ValueError as exc:
            raise InvalidArgument(str(exc)) from exc

        job_id: str | None = None
        with self.repository.transaction() as tx:
            if not tx.lock_project(project_id):
                raise NotFound("项目不存在")
            if replaces_id is not None and not tx.replacement_exists(project_id, replaces_id):
                raise NotFound("待替换文件不存在")
            if sort_no is None:
                sort_no = tx.next_sort_no(project_id)
            project_file_id = tx.insert_file(
                {
                    "project_id": project_id,
                    "version_id": None,
                    "role": role,
                    "display_name": name,
                    "is_parseable": parseable,
                    "replaces_id": replaces_id,
                    "sort_no": sort_no,
                    "original_key": original_key,
                    "sha256": original_sha,
                    "mime": raw_mime,
                    "size_bytes": len(item.content),
                }
            )
            tx.sync_sources(project_id)
            if parseable:
                job_id = f"job_{uuid4().hex}"
                stage = "probing" if extension == ".pdf" else "converting"
                snapshot_id = tx.snapshot_for_job(active_config)
                tx.insert_job(
                    {
                        "id": job_id,
                        "company_id": self.company_id,
                        "project_id": project_id,
                        "project_file_id": project_file_id,
                        "version_id": None,
                        "status": "pending",
                        "stage": stage,
                        "progress": {},
                        "config_snapshot": {
                            **options,
                            "auto_parse": auto_parse,
                            "execution": document_execution_snapshot(
                                active_config.resolved if active_config is not None else None
                            ),
                            "execution_origin": "created",
                        },
                        "config_snapshot_id": snapshot_id,
                    }
                )

        return {
            "project_file_id": project_file_id,
            "display_name": name,
            "role": role,
            "is_parseable": parseable,
            "version_id": None,
            "job_id": job_id,
        }

    async def replace(
        self,
        *,
        project_id: int,
        file_id: int,
        item: FileInput,
        auto_parse: bool,
        tier: str | None,
        ocr_mode: str | None,
        actor: str,
    ) -> dict[str, object]:
        validate_parse_config(tier, ocr_mode)
        old = self.require_file(project_id, file_id)
        result = await self.add_project_file(
            project_id=project_id,
            item=item,
            role=str(old["role"]),
            auto_parse=auto_parse,
            tier=tier,
            ocr_mode=ocr_mode,
            replaces_id=file_id,
            actor=actor,
            sort_no=int(old["sort_no"]),
            display_name=str(old["display_name"]),
        )
        jobs = [str(result["job_id"])] if result["job_id"] else []
        return {"added": result, "jobs": jobs}

    def require_file(self, project_id: int, file_id: int) -> dict[str, Any]:
        row = self.repository.row(project_id, file_id)
        if row is None:
            raise NotFound("项目文件不存在")
        return row

    def patch(self, project_id: int, file_id: int, changes: dict[str, object]) -> dict[str, object]:
        if not changes:
            raise InvalidArgument("至少需要修改一个文件字段")
        self.require_file(project_id, file_id)
        values: dict[str, object] = {}
        if "display_name" in changes:
            name = str(changes["display_name"] or "").strip()
            if not name:
                raise InvalidArgument("显示名称不能为空")
            values["display_name"] = name
        if "role" in changes:
            values["role"] = validate_role(str(changes["role"]))
        if "sort_no" in changes:
            values["sort_no"] = changes["sort_no"]
        if not self.repository.update(project_id, file_id, values):
            raise NotFound("项目文件不存在")
        row = self.require_file(project_id, file_id)
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

    def delete(self, project_id: int, file_id: int) -> None:
        if not self.repository.soft_delete(project_id, file_id):
            raise NotFound("项目文件不存在")

    def original(self, project_id: int, file_id: int) -> dict[str, Any]:
        row = self.require_file(project_id, file_id)
        key = row["original_key"] or row["version_original_key"]
        if not key:
            raise NotFound("原件对象不存在")
        return {
            "key": str(key),
            "filename": str(row["display_name"]),
            "content_type": str(row["mime"] or "application/octet-stream"),
        }
