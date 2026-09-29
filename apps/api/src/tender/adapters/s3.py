"""S3 / MinIO 对象存储适配器；第三方异常与响应形状在此收口。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from tender.core import settings
from tender.ports.blob_store import BlobMetadata, BlobNotFound, BlobObject, BlobStoreError


class S3BlobStore:
    """用内容键保存原件、PDF 基座和解析原始产物。"""

    def __init__(
        self,
        *,
        endpoint_url: str | None = None,
        bucket: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str | None = None,
        client: Any | None = None,
    ) -> None:
        self._bucket = bucket or settings.s3_bucket()
        self._client: Any = client or boto3.client(
            "s3",
            endpoint_url=endpoint_url or settings.s3_endpoint_url(),
            aws_access_key_id=access_key or settings.s3_access_key(),
            aws_secret_access_key=secret_key or settings.s3_secret_key(),
            region_name=region or settings.s3_region(),
            # 招标文件只能走配置的内网对象存储，不能继承开发机代理转发到外网。
            config=Config(
                proxies={},
                retries={"mode": "standard", "max_attempts": 3},
                max_pool_connections=50,
                s3={"addressing_style": "path"},
            ),
        )

    def close(self) -> None:
        self._client.close()

    def put(self, key: str, content: bytes, *, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentLength=len(content),
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise BlobStoreError(f"写入对象存储失败：{exc}") from exc

    def head(self, key: str) -> BlobMetadata:
        try:
            response = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _is_missing(exc):
                raise BlobNotFound(key) from exc
            raise BlobStoreError(f"读取对象元数据失败：{exc}") from exc
        except BotoCoreError as exc:
            raise BlobStoreError(f"读取对象元数据失败：{exc}") from exc

        return BlobMetadata(
            size_bytes=int(response["ContentLength"]),
            content_type=str(response.get("ContentType") or "application/octet-stream"),
            etag=_optional_string(response.get("ETag")),
            last_modified=_optional_datetime(response.get("LastModified")),
        )

    def open(self, key: str, *, byte_range: tuple[int, int] | None = None) -> BlobObject:
        request: dict[str, object] = {"Bucket": self._bucket, "Key": key}
        if byte_range is not None:
            start, end = byte_range
            request["Range"] = f"bytes={start}-{end}"
        try:
            response = self._client.get_object(**request)
        except ClientError as exc:
            if _is_missing(exc):
                raise BlobNotFound(key) from exc
            raise BlobStoreError(f"读取对象失败：{exc}") from exc
        except BotoCoreError as exc:
            raise BlobStoreError(f"读取对象失败：{exc}") from exc

        return BlobObject(
            stream=response["Body"],
            size_bytes=int(response["ContentLength"]),
            content_type=str(response.get("ContentType") or "application/octet-stream"),
            etag=_optional_string(response.get("ETag")),
            last_modified=_optional_datetime(response.get("LastModified")),
            content_range=_optional_string(response.get("ContentRange")),
        )

    def read(self, key: str) -> bytes:
        blob = self.open(key)
        try:
            return blob.stream.read()
        except (BotoCoreError, OSError) as exc:
            raise BlobStoreError(f"读取对象内容失败：{exc}") from exc
        finally:
            blob.stream.close()


def _is_missing(exc: ClientError) -> bool:
    response = exc.response
    code = str(response.get("Error", {}).get("Code", ""))
    status = int(response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
    return status == 404 or code in {"NoSuchKey", "NoSuchBucket", "NotFound"}


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None
