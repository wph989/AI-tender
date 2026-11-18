from pathlib import Path

import pytest

from tender.core import settings
from tender.core.di import create_blob_store_factory
from tender.ports.storage.blob_store import BlobNotFound


def test_worker_factory_keeps_the_storage_chosen_at_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    monkeypatch.setattr(settings, "_ENV_FILE", env_file)
    monkeypatch.delenv("BLOB_STORE_BACKEND", raising=False)
    monkeypatch.delenv("LOCAL_STORAGE_ROOT", raising=False)
    env_file.write_text("BLOB_STORE_BACKEND=local\nLOCAL_STORAGE_ROOT=first\n", encoding="utf-8")
    running_factory = create_blob_store_factory()
    running_factory().put("original/ab/file", b"abc", content_type="text/plain")

    env_file.write_text("BLOB_STORE_BACKEND=local\nLOCAL_STORAGE_ROOT=second\n", encoding="utf-8")
    assert running_factory().read("original/ab/file") == b"abc"
    with pytest.raises(BlobNotFound):
        create_blob_store_factory()().read("original/ab/file")
