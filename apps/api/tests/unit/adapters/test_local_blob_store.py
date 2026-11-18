from __future__ import annotations

from pathlib import Path

import pytest

from tender.adapters.storage.local import LocalBlobStore
from tender.ports.storage.blob_store import BlobNotFound, BlobStoreError


def test_local_blob_store_round_trips_metadata_and_byte_ranges(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path / "objects")
    store.put("original/ab/file", b"abcdef", content_type="text/plain")

    metadata = store.head("original/ab/file")
    assert metadata.size_bytes == 6
    assert metadata.content_type == "text/plain"
    assert metadata.etag
    assert metadata.last_modified is not None

    blob = store.open("original/ab/file", byte_range=(1, 3))
    try:
        assert blob.size_bytes == 3
        assert blob.content_range == "bytes 1-3/6"
        assert blob.stream.read(2) == b"bc"
        assert blob.stream.read(64 * 1024) == b"d"
        assert blob.stream.read() == b""
    finally:
        blob.stream.close()

    assert store.read("original/ab/file") == b"abcdef"


def test_local_blob_store_can_repeat_upload_while_object_is_open(tmp_path: Path) -> None:
    # Windows 的普通读取句柄打开时不能替换文件。两个实例模拟 API 和 Worker 共用目录。
    root = tmp_path / "objects"
    first = LocalBlobStore(root)
    second = LocalBlobStore(root)
    first.put("original/ab/file", b"abcdef", content_type="text/plain")

    with first.open("original/ab/file").stream as reader:
        second.put("original/ab/file", b"abcdef", content_type="text/plain")
        assert reader.read() == b"abcdef"
    assert second.read("original/ab/file") == b"abcdef"


def test_local_blob_store_reports_missing_objects(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path / "objects")

    with pytest.raises(BlobNotFound):
        store.head("missing/object")


@pytest.mark.parametrize("key", ["../outside", "a/../../outside", r"a\..\outside", "/absolute"])
def test_local_blob_store_rejects_paths_outside_its_root(tmp_path: Path, key: str) -> None:
    store = LocalBlobStore(tmp_path / "objects")

    with pytest.raises(BlobStoreError):
        store.put(key, b"unsafe", content_type="text/plain")

    assert not (tmp_path / "outside").exists()
