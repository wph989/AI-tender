"""基于本地文件系统的 BlobStore 实现。"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
from collections.abc import Buffer
from datetime import UTC, datetime
from io import BufferedReader, RawIOBase
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from tender.ports.storage.blob_store import BlobMetadata, BlobNotFound, BlobObject, BlobStoreError


class _RangeReader(RawIOBase):
    """让缓冲流在闭区间末尾读到 EOF，避免响应体超过 Content-Length。"""

    def __init__(self, stream: BufferedReader, size: int) -> None:
        super().__init__()
        self._stream = stream
        self._remaining = size

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Buffer) -> int:
        if not self._remaining:
            return 0
        count = self._stream.readinto(memoryview(buffer).cast("B")[:self._remaining])
        self._remaining -= count
        return count

    def close(self) -> None:
        try:
            self._stream.close()
        finally:
            super().close()


class LocalBlobStore:
    """将对象键映射为共享目录中的文件，并保留响应所需的 MIME 元数据。"""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._metadata_root = self._root / ".blob-metadata"

    def close(self) -> None:
        """本地文件句柄由各次操作自行关闭，保留统一的装配生命周期接口。"""

    def put(self, key: str, content: bytes, *, content_type: str) -> None:
        path = self._object_path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._assert_inside_root(path)
            # 原子替换可避免并发读取者看到尚未写完的对象。
            self._write_atomic(path, content)
            # MIME 类型无法从内容寻址键名还原，因此随对象保存在独立元数据目录。
            metadata = json.dumps(
                {
                    "content_type": content_type,
                    "etag": f'"{hashlib.sha256(content).hexdigest()}"',
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self._metadata_root.mkdir(parents=True, exist_ok=True)
            self._write_atomic(self._metadata_path(key), metadata)
        except OSError as exc:
            raise BlobStoreError(f"写入本地存储失败：{exc}") from exc

    def head(self, key: str) -> BlobMetadata:
        path = self._object_path(key)
        try:
            stat = path.stat()
        except FileNotFoundError as exc:
            raise BlobNotFound(key) from exc
        except OSError as exc:
            raise BlobStoreError(f"读取本地对象元数据失败：{exc}") from exc

        metadata = self._read_metadata(key)
        content_type = metadata.get("content_type") or (
            mimetypes.guess_type(key)[0] or "application/octet-stream"
        )
        return BlobMetadata(
            size_bytes=stat.st_size,
            content_type=content_type,
            etag=metadata.get("etag"),
            last_modified=datetime.fromtimestamp(stat.st_mtime, UTC),
        )

    def open(self, key: str, *, byte_range: tuple[int, int] | None = None) -> BlobObject:
        path = self._object_path(key)
        metadata = self.head(key)
        start, end = byte_range or (0, metadata.size_bytes - 1)
        if byte_range is not None and (
            start < 0 or end < start or start >= metadata.size_bytes
        ):
            raise ValueError("对象字节范围无效")
        end = min(end, metadata.size_bytes - 1)
        try:
            file_stream = path.open("rb")
        except FileNotFoundError as exc:
            raise BlobNotFound(key) from exc
        except OSError as exc:
            raise BlobStoreError(f"打开本地对象失败：{exc}") from exc

        stream: BinaryIO = file_stream
        size_bytes = metadata.size_bytes
        if byte_range is not None:
            size_bytes = end - start + 1
            try:
                file_stream.seek(start)
                stream = BufferedReader(_RangeReader(file_stream, size_bytes))
            except OSError as exc:
                file_stream.close()
                raise BlobStoreError(f"打开本地对象范围失败：{exc}") from exc
        return BlobObject(
            stream=stream,
            size_bytes=size_bytes,
            content_type=metadata.content_type,
            etag=metadata.etag,
            last_modified=metadata.last_modified,
            content_range=(
                f"bytes {start}-{end}/{metadata.size_bytes}" if byte_range is not None else None
            ),
        )

    def read(self, key: str) -> bytes:
        blob = self.open(key)
        try:
            return blob.stream.read()
        except OSError as exc:
            raise BlobStoreError(f"读取本地对象内容失败：{exc}") from exc
        finally:
            blob.stream.close()

    def _object_path(self, key: str) -> Path:
        pure = PurePosixPath(key)
        parts = key.split("/")
        if (
            not key
            or pure.is_absolute()
            or "\\" in key
            or any(part in {"", ".", ".."} for part in parts)
            or parts[0] == ".blob-metadata"
        ):
            raise BlobStoreError("本地存储对象键无效")
        path = self._root.joinpath(*parts)
        self._assert_inside_root(path)
        return path

    def _assert_inside_root(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self._root)
        except ValueError as exc:
            raise BlobStoreError("本地存储对象路径超出配置目录") from exc

    def _metadata_path(self, key: str) -> Path:
        return self._metadata_root / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"

    def _read_metadata(self, key: str) -> dict[str, str]:
        try:
            value = json.loads(self._metadata_path(key).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            raise BlobStoreError(f"读取本地对象元数据失败：{exc}") from exc
        if not isinstance(value, dict):
            raise BlobStoreError("本地对象元数据格式无效")
        return {
            field: value[field]
            for field in ("content_type", "etag")
            if isinstance(value.get(field), str)
        }

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            try:
                os.replace(temporary_path, path)
            except PermissionError:
                # Windows 上打开的下载流可能阻止替换。只在现有文件内容相同时视为写入成功。
                with path.open("rb") as existing:
                    if hashlib.file_digest(existing, "sha256").digest() != hashlib.sha256(
                        content
                    ).digest():
                        raise
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
