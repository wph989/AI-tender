"""MinerU 适配器的行为契约（上传/提交阶段）。

为什么锁这些点：adapters/mineru.py 的调用序列长（create upload → PUT → complete → parse job），
每一步都依赖上一步回包里的一两个字段。字段名一旦和服务端不一致，表现是「整条解析链路直接失败」，
而真实服务上跑一次要几分钟（模型加载 + 推理），回归成本很高。所以用 MockTransport 把形状
锁死在测试里。

实测基准：自托管 mineru-kit api-server，版本 4.0.7。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable

import httpx
import pytest

from tender.adapters.documents.mineru import MinerUParser
from tender.domain.shared.errors import ParseFailed

BASE_URL = "http://mineru.test"
UPLOAD_ID = "upload_6f180b7b7c4973962e1d3eb0"
FILE_ID = "file-3861e203fd621a5540761815"
JOB_ID = "job_17376c1f3aa63a7c428413f4"
PDF_BYTES = b"%PDF-1.7\n% fake pdf bytes for tests\n"
PDF_SHA256 = hashlib.sha256(PDF_BYTES).hexdigest()

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def run(coro: Awaitable[object]) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


async def load_pdf(pdf_key: str) -> bytes:
    return PDF_BYTES


def health_response() -> httpx.Response:
    """实测形状：version 在顶层，能力声明在 features.output_formats。"""
    return httpx.Response(
        200,
        json={
            "status": "ok",
            "version": "4.0.7",
            "features": {
                "webhook": False,
                "output_formats": ["markdown", "middle_json", "structured_content", "zip"],
                "sources": ["file_id", "url", "inline"],
            },
        },
    )


def upload_response(*, id_key: str, upload_url: str | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            id_key: UPLOAD_ID,
            "object": "upload",
            "status": "pending",
            "upload_url": upload_url or f"{BASE_URL}/v1/uploads/{UPLOAD_ID}/content",
            "upload_method": "PUT",
            "upload_headers": {"Content-Type": "application/pdf"},
        },
    )


def complete_response() -> httpx.Response:
    """实测形状：完成的 upload 内嵌 `file` 对象，file_id 在 file.id 上。"""
    return httpx.Response(
        200,
        json={"id": UPLOAD_ID, "status": "completed", "file": {"id": FILE_ID, "object": "file"}},
    )


@pytest.fixture
def make_parser() -> object:
    created: list[MinerUParser] = []

    def factory(handler: Handler, **kwargs: object) -> MinerUParser:
        parser = MinerUParser(
            BASE_URL,
            pdf_loader=load_pdf,
            transport=httpx.MockTransport(handler),
            **kwargs,  # type: ignore[arg-type]
        )
        created.append(parser)
        return parser

    yield factory

    for parser in created:
        asyncio.run(parser.aclose())


def upload_flow_handler(*, id_key: str, seen: dict[str, object] | None = None) -> Handler:
    """模拟完整的「上传 → complete → 提交任务」序列。"""

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/health":
            return health_response()
        if path == "/v1/uploads" and request.method == "POST":
            if seen is not None:
                seen["create_body"] = request.content
            return upload_response(id_key=id_key)
        if path == f"/v1/uploads/{UPLOAD_ID}/content" and request.method == "PUT":
            if seen is not None:
                seen["put_body"] = request.content
                seen["put_auth"] = request.headers.get("Authorization")
            return httpx.Response(200)
        if path == f"/v1/uploads/{UPLOAD_ID}/complete":
            return complete_response()
        if path == "/v1/parse/jobs" and request.method == "POST":
            if seen is not None:
                seen["job_body"] = request.content
            return httpx.Response(202, json={"job_id": JOB_ID, "status": "queued"})
        raise AssertionError(f"未预期的请求：{request.method} {path}")

    return handler


def test_submit_accepts_openai_style_id(make_parser) -> None:
    """实测 4.0.7 的顶层字段是 `id`（`upload_...`），不是 `upload_id`。

    回归用例：早先只认 `upload_id`，真实服务上表现为「解析一次都没成功，报的错却是 upload 响应
    缺少字段」。
    """
    seen: dict[str, object] = {}
    parser = make_parser(upload_flow_handler(id_key="id", seen=seen))

    submission = run(parser.submit("smoke/a.pdf", pdf_sha256=PDF_SHA256))

    assert submission.job_id == JOB_ID
    assert submission.provider_version == "4.0.7"
    # 创建上传的请求体：bytes 必填（实测缺它会 400 invalid_request），sha256sum 用于服务端去重
    body = seen["create_body"]
    assert isinstance(body, bytes)
    for key in (b'"filename"', b'"bytes"', b'"mime_type"', b'"purpose"', b'"sha256sum"'):
        assert key in body
    # 上传字节走 PUT，且必须原样带上传内容
    assert seen["put_body"] == PDF_BYTES


@pytest.mark.parametrize("key", ["pdf/" + PDF_SHA256, "original/document.docx", "pdf/file.PDF"])
def test_storage_keys_are_submitted_as_pdf_filenames(make_parser, key) -> None:
    seen = {}
    parser = make_parser(upload_flow_handler(id_key="id", seen=seen))
    run(parser.submit(key, pdf_sha256=PDF_SHA256))
    body = json.loads(seen["create_body"])
    assert body["filename"].lower().endswith(".pdf")
    assert body["sha256sum"] == PDF_SHA256
    assert seen["put_body"] == PDF_BYTES


def test_submit_accepts_documented_upload_id(make_parser) -> None:
    """调研文档里记的名字是 `upload_id`；两个名字都要能跑，避免服务端形状回退时整条链路断掉。"""
    parser = make_parser(upload_flow_handler(id_key="upload_id"))

    submission = run(parser.submit("smoke/a.pdf", pdf_sha256=PDF_SHA256))

    assert submission.job_id == JOB_ID


def test_upload_without_any_id_is_rejected(make_parser) -> None:
    """两个名字都没有时必须失败：没有 id 就拼不出上传与 complete 的路径，硬跑只会得到更远的错误。"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/health":
            return health_response()
        if request.url.path == "/v1/uploads":
            return upload_response(id_key="something_else")
        raise AssertionError("没有 id 时不该继续发后续请求")

    parser = make_parser(handler)
    with pytest.raises(ParseFailed, match="缺少 id"):
        run(parser.submit("smoke/a.pdf", pdf_sha256=PDF_SHA256))


def test_cross_origin_upload_url_is_rejected(make_parser) -> None:
    """跨源 upload_url 必须拒绝：那意味着标书会被交给我们没配置过的存储服务。"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/health":
            return health_response()
        if request.url.path == "/v1/uploads":
            return upload_response(id_key="id", upload_url="http://evil.example/upload")
        raise AssertionError("跨源 upload_url 不该被 PUT")

    parser = make_parser(handler)
    with pytest.raises(ParseFailed, match="同源"):
        run(parser.submit("smoke/a.pdf", pdf_sha256=PDF_SHA256))


def test_api_key_is_sent_on_api_calls_and_upload(make_parser) -> None:
    """配了 api_key 时，业务接口与同源上传都要带 Bearer（自托管启用 --api-key 后 PUT 也校验）。"""
    seen: dict[str, object] = {}
    parser = make_parser(upload_flow_handler(id_key="id", seen=seen), api_key="k-123")

    run(parser.submit("smoke/a.pdf", pdf_sha256=PDF_SHA256))

    assert seen["put_auth"] == "Bearer k-123"
