"""HTTP 文件响应与单段 Range 解析。"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from fastapi.responses import Response, StreamingResponse

from tender.ports.storage.blob_store import BlobMetadata, BlobObject, BlobStore

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$", re.IGNORECASE)


def parse_range(value: str, size: int) -> tuple[int, int]:
    match = _RANGE_RE.fullmatch(value.strip())
    if match is None or size <= 0:
        raise ValueError
    start_raw, end_raw = match.groups()
    if not start_raw and not end_raw:
        raise ValueError
    if not start_raw:
        suffix_length = int(end_raw)
        if suffix_length <= 0:
            raise ValueError
        return max(0, size - suffix_length), size - 1
    start = int(start_raw)
    end = int(end_raw) if end_raw else size - 1
    if start >= size or end < start:
        raise ValueError
    return start, min(end, size - 1)


def stream_object(
    blobs: BlobStore,
    key: str,
    filename: str,
    fallback_type: str,
    range_header: str | None,
    *,
    inline: bool,
) -> Response:
    metadata: BlobMetadata = blobs.head(key)
    byte_range: tuple[int, int] | None = None
    if range_header:
        try:
            byte_range = parse_range(range_header, metadata.size_bytes)
        except ValueError:
            return Response(
                status_code=416,
                headers={
                    "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes */{metadata.size_bytes}",
                    "Content-Length": "0",
                },
            )

    blob: BlobObject = blobs.open(key, byte_range=byte_range)
    status_code = 206 if byte_range is not None else 200
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(blob.size_bytes),
        "Content-Type": blob.content_type or fallback_type,
        "Content-Disposition": content_disposition(filename, inline=inline),
    }
    if blob.etag:
        headers["ETag"] = blob.etag
    if blob.last_modified:
        headers["Last-Modified"] = blob.last_modified.strftime("%a, %d %b %Y %H:%M:%S GMT")
    if byte_range is not None:
        start, end = byte_range
        headers["Content-Range"] = blob.content_range or (
            f"bytes {start}-{end}/{metadata.size_bytes}"
        )

    def body() -> Any:
        try:
            while chunk := blob.stream.read(64 * 1024):
                yield chunk
        finally:
            blob.stream.close()

    return StreamingResponse(body(), status_code=status_code, headers=headers)


def content_disposition(filename: str, *, inline: bool) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "document"
    disposition = "inline" if inline else "attachment"
    return f"{disposition}; filename=\"{safe_name}\"; filename*=UTF-8''{quote(filename, safe='')}"
