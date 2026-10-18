"""在接触文件内容前拒绝超限批次，大小未知时也不能无界读入内存。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tender.api.projects import files as routes
from tender.api.shared.errors import ApiProblem
from tender.application.projects import files as policy


class Upload:
    def __init__(self, content=b"x", *, size=None, name="sample.txt"):
        self.content = content
        self.size = size
        self.filename = name
        self.read_sizes = []

    async def read(self, size):
        self.read_sizes.append(size)
        return self.content[:size]

    async def close(self):
        pass


@pytest.fixture
def service(monkeypatch):
    value = SimpleNamespace(upload=AsyncMock(return_value={"added": []}))
    monkeypatch.setattr(routes, "_service", lambda _: value)
    return value


def upload(files, archive=None):
    return asyncio.run(
        routes.upload_files(1, SimpleNamespace(headers={}), files=files, archive=archive)
    )


def test_too_many_files_are_rejected_without_reading(service):
    files = [Upload(size=1) for _ in range(101)]
    with pytest.raises(ApiProblem) as caught:
        upload(files)
    assert (caught.value.status_code, caught.value.code) == (413, "too_many_files")
    assert all(not file.read_sizes for file in files)
    service.upload.assert_not_awaited()


@pytest.mark.parametrize("include_archive", [False, True])
def test_known_total_is_rejected_without_reading(service, include_archive):
    # 仅用元数据表达大文件，回归验证不实际分配 GiB 内存。
    mib = 1024 * 1024
    files = [Upload(size=500 * mib), Upload(size=500 * mib)]
    extra = Upload(size=32 * mib)
    archive = extra if include_archive else None
    if archive is None:
        files.append(extra)
    with pytest.raises(ApiProblem) as caught:
        upload(files, archive)
    assert (caught.value.status_code, caught.value.code) == (413, "upload_too_large")
    assert all(not file.read_sizes for file in [*files, extra])
    service.upload.assert_not_awaited()


@pytest.mark.parametrize("include_archive", [False, True])
@pytest.mark.parametrize("declared_size", [None, 0])
def test_reading_is_bounded_by_remaining_total(
    monkeypatch, service, include_archive, declared_size,
):
    # 缩小相同规则的预算，检查读请求本身受限，不能读完整个文件后才检查。
    monkeypatch.setattr(policy, "MAX_UPLOAD_TOTAL_BYTES", 10)
    monkeypatch.setattr(routes, "MAX_UPLOAD_TOTAL_BYTES", 10)
    first = Upload(b"123456", size=declared_size)
    overflow = Upload(b"abcdef", size=declared_size)
    later = Upload(b"later", size=declared_size)
    files = [first] if include_archive else [first, overflow, later]
    with pytest.raises(ApiProblem) as caught:
        upload(files, overflow if include_archive else None)
    assert (caught.value.status_code, caught.value.code) == (413, "upload_too_large")
    assert first.read_sizes == [11]
    assert overflow.read_sizes == [5]
    assert later.read_sizes == []
    service.upload.assert_not_awaited()


def test_exact_total_remains_accepted(monkeypatch, service):
    monkeypatch.setattr(policy, "MAX_UPLOAD_TOTAL_BYTES", 10)
    monkeypatch.setattr(routes, "MAX_UPLOAD_TOTAL_BYTES", 10)
    upload([Upload(b"123456"), Upload(b"abcd")])
    service.upload.assert_awaited_once()
    assert [item.content for item in service.upload.await_args.kwargs["files"]] == [
        b"123456", b"abcd",
    ]


@pytest.mark.parametrize("replace", [False, True])
@pytest.mark.parametrize(("content", "status", "code"), [
    (b"", 400, "invalid_argument"),
    (b"1234", 413, "upload_too_large"),
])
def test_single_file_errors_keep_http_mapping(
    monkeypatch, service, replace, content, status, code,
):
    monkeypatch.setattr(routes, "MAX_UPLOAD_BYTES", 3)
    file = Upload(content)
    with pytest.raises(ApiProblem) as caught:
        if replace:
            asyncio.run(routes.replace_file(1, 2, SimpleNamespace(headers={}), file))
        else:
            upload([file])
    assert (caught.value.status_code, caught.value.code) == (status, code)
    service.upload.assert_not_awaited()
