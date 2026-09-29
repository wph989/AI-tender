"""对象存储端口：业务代码只依赖字节与流，不暴露 boto3 类型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class BlobMetadata:
    size_bytes: int
    content_type: str
    etag: str | None
    last_modified: datetime | None


@dataclass(slots=True)
class BlobObject:
    stream: BinaryIO
    size_bytes: int
    content_type: str
    etag: str | None
    last_modified: datetime | None
    content_range: str | None


class BlobNotFound(Exception):
    """对象不存在；由 HTTP 层映射为不泄露存储细节的 404。"""


class BlobStoreError(Exception):
    """对象存储暂时不可用；调用方可按 retryable 错误处理。"""


class BlobStore(Protocol):
    def put(self, key: str, content: bytes, *, content_type: str) -> None:
        """按内容寻址写入对象；重复写入同一 key 必须幂等。"""
        ...

    def head(self, key: str) -> BlobMetadata:
        """仅读取对象元数据，用于校验 Range 与生成响应头。"""
        ...

    def open(self, key: str, *, byte_range: tuple[int, int] | None = None) -> BlobObject:
        """打开完整对象或一个闭区间字节范围。调用方负责关闭流。"""
        ...

    def read(self, key: str) -> bytes:
        """读取完整对象；仅供解析适配器等确实需要完整字节的路径使用。"""
        ...
