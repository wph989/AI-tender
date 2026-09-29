"""Gotenberg 适配器的行为契约。

为什么用 MockTransport 而不是起真容器：这里要锁的是**客户端行为**——重试次数、
退避节奏、Trace 串包判定、错误码翻译、版本缓存。真容器只能证明「网络通」，
证明不了重试分支，而且要几十秒才能跑一次，没人会在提交前跑它。
"""

from __future__ import annotations

import asyncio
import base64
import io
from collections.abc import Awaitable, Callable

import httpx
import pytest

from tender.adapters.gotenberg import GotenbergConverter, _output_stem
from tender.domain.errors import ConversionFailed, ConversionUnavailable

PDF_BYTES = b"%PDF-1.7\n% fake pdf bytes for tests\n"

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]


def run(coro: Awaitable[object]) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


def pdf_response(request: httpx.Request, *, trace: str | None = None) -> httpx.Response:
    """正常成功响应：回传同一个 Trace，Content-Type 是 PDF。"""
    return httpx.Response(
        200,
        content=PDF_BYTES,
        headers={
            "Content-Type": "application/pdf",
            "Gotenberg-Trace": trace if trace is not None else request.headers["Gotenberg-Trace"],
        },
    )


def version_response() -> httpx.Response:
    return httpx.Response(200, json={"version": "8.34.0"})


@pytest.fixture
def make_converter() -> object:
    """工厂 + 统一收尾：适配器持有连接池，测试结束必须关掉，否则会有未关闭客户端的告警。"""
    created: list[GotenbergConverter] = []

    def factory(handler: Handler, **kwargs: object) -> tuple[GotenbergConverter, list[float]]:
        sleeps: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            # 真实退避会拖慢测试；这里只记录节奏，验证指数退避确实按 0.5 → 1.0 走
            sleeps.append(seconds)

        converter = GotenbergConverter(
            "http://gotenberg.test",
            transport=httpx.MockTransport(handler),
            sleep=fake_sleep,
            **kwargs,  # type: ignore[arg-type]
        )
        created.append(converter)
        return converter, sleeps

    yield factory

    for converter in created:
        asyncio.run(converter.aclose())


def test_to_pdf_sends_frozen_options_and_returns_result(make_converter) -> None:
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return version_response()
        assert request.method == "POST"
        assert request.url.path == "/forms/libreoffice/convert"
        # 中文名不能进 HTTP 头（头只能 ASCII）：输出名退化为 document，
        # 原始中文名仍完整保留在 multipart 里（见下面的 body 断言）
        assert request.headers["Gotenberg-Output-Filename"] == "document"
        assert request.headers["Gotenberg-Trace"] == "job_01"
        await request.aread()
        seen["body"] = request.content
        return pdf_response(request)

    converter, sleeps = make_converter(handler)
    result = run(
        converter.to_pdf(io.BytesIO(b"docx-bytes"), filename="招标文件.docx", trace_id="job_01")
    )

    assert result.pdf_bytes == PDF_BYTES
    assert (result.converter, result.converter_version, result.trace_id) == (
        "gotenberg",
        "8.34.0",
        "job_01",
    )
    assert result.elapsed_ms >= 0
    assert sleeps == []

    body = seen["body"]
    assert isinstance(body, bytes)
    # 冻结参数一个都不能少：分页语义就是靠它们锁住的（docs/调研/02 第 3.2 节）
    for key, value in {
        "exportBookmarks": "true",
        "exportBookmarksToPdfDestination": "true",
        "exportFormFields": "false",
        "updateIndexes": "true",
        "exportNotes": "false",
    }.items():
        assert f'name="{key}"'.encode() in body
        assert value.encode() in body
    assert b'filename="\xe6\x8b\x9b\xe6\xa0\x87\xe6\x96\x87\xe4\xbb\xb6.docx"' in body
    assert b"docx-bytes" in body


def test_version_is_cached_across_conversions(make_converter) -> None:
    version_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal version_calls
        if request.url.path == "/version":
            version_calls += 1
            return version_response()
        return pdf_response(request)

    converter, _ = make_converter(handler)
    for index in range(2):
        run(converter.to_pdf(io.BytesIO(b"x"), filename="a.docx", trace_id=f"t{index}"))

    assert version_calls == 1


def test_version_failure_blocks_conversion(make_converter) -> None:
    convert_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal convert_calls
        if request.url.path == "/version":
            return httpx.Response(503, text="models are still loading")
        convert_calls += 1
        return pdf_response(request)

    converter, _ = make_converter(handler)
    with pytest.raises(ConversionUnavailable) as excinfo:
        run(converter.to_pdf(io.BytesIO(b"x"), filename="a.docx", trace_id="t"))

    assert excinfo.value.retryable is True
    assert convert_calls == 0, "版本读不到就不该把贵重的转换请求发出去"


def test_client_error_is_not_retried(make_converter) -> None:
    convert_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal convert_calls
        if request.url.path == "/version":
            return version_response()
        convert_calls += 1
        return httpx.Response(400, text="could not load document: password protected")

    converter, sleeps = make_converter(handler)
    with pytest.raises(ConversionFailed) as excinfo:
        run(converter.to_pdf(io.BytesIO(b"x"), filename="locked.docx", trace_id="t"))

    assert excinfo.value.code == "conversion_failed"
    assert excinfo.value.retryable is False
    assert "password protected" in str(excinfo.value)
    assert convert_calls == 1
    assert sleeps == []


def test_server_error_is_retried_and_stream_is_rewound(make_converter) -> None:
    bodies: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return version_response()
        await request.aread()
        bodies.append(request.content)
        if len(bodies) == 1:
            return httpx.Response(500, text="LibreOffice crashed")
        return pdf_response(request)

    converter, sleeps = make_converter(handler)
    result = run(converter.to_pdf(io.BytesIO(b"docx-bytes"), filename="a.docx", trace_id="t"))

    assert result.pdf_bytes == PDF_BYTES
    assert sleeps == [0.5]
    assert len(bodies) == 2
    # 第二次请求必须带全量文件字节：不回退输入流的话这里会是 0 字节
    assert b"docx-bytes" in bodies[1]
    assert len(bodies[0]) == len(bodies[1])


def test_server_errors_exhaust_retries(make_converter) -> None:
    convert_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal convert_calls
        if request.url.path == "/version":
            return version_response()
        convert_calls += 1
        return httpx.Response(503, text="conversion timed out")

    converter, sleeps = make_converter(handler)
    with pytest.raises(ConversionUnavailable) as excinfo:
        run(converter.to_pdf(io.BytesIO(b"x"), filename="a.docx", trace_id="t"))

    assert excinfo.value.retryable is True
    assert convert_calls == 3
    assert sleeps == [0.5, 1.0]


def test_trace_mismatch_is_retried_then_fails(make_converter) -> None:
    convert_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal convert_calls
        if request.url.path == "/version":
            return version_response()
        convert_calls += 1
        return pdf_response(request, trace="someone-elses-trace")

    converter, _ = make_converter(handler)
    with pytest.raises(ConversionUnavailable) as excinfo:
        run(converter.to_pdf(io.BytesIO(b"x"), filename="a.docx", trace_id="mine"))

    assert excinfo.value.retryable is True
    assert "someone-elses-trace" in str(excinfo.value)
    assert convert_calls == 3, "串包是瞬时故障，应当用满重试次数再放弃"


def test_non_pdf_success_body_is_rejected(make_converter) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/version":
            return version_response()
        return httpx.Response(
            200,
            content=b"PK\x03\x04 zip payload",
            headers={
                "Content-Type": "application/zip",
                "Gotenberg-Trace": request.headers["Gotenberg-Trace"],
            },
        )

    converter, _ = make_converter(handler)
    with pytest.raises(ConversionFailed):
        run(converter.to_pdf(io.BytesIO(b"x"), filename="a.docx", trace_id="t"))


def test_health_reflects_status_and_transport_errors(make_converter) -> None:
    async def healthy(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "up"})

    converter, _ = make_converter(healthy)
    assert run(converter.health()) is True

    async def degraded(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="dependency not ready")

    converter, _ = make_converter(degraded)
    assert run(converter.health()) is False

    async def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    converter, _ = make_converter(unreachable)
    assert run(converter.health()) is False


def test_basic_auth_is_sent_only_when_credentials_are_configured(make_converter) -> None:
    seen: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Authorization"))
        if request.url.path == "/version":
            return version_response()
        return pdf_response(request)

    with_auth, _ = make_converter(handler, username="user", password="secret")
    run(with_auth.to_pdf(io.BytesIO(b"x"), filename="a.docx", trace_id="t"))
    expected = "Basic " + base64.b64encode(b"user:secret").decode()
    assert seen[0] == expected

    without_auth, _ = make_converter(handler)
    run(without_auth.to_pdf(io.BytesIO(b"x"), filename="a.docx", trace_id="t"))
    assert seen[-1] is None


def test_output_stem_is_ascii_safe() -> None:
    """输出名要能发出去：HTTP 头只认 ASCII，中文名必须有确定的退化路径。"""
    assert _output_stem("tender-2026.docx") == "tender-2026"  # 去掉扩展名后原样保留
    assert _output_stem("招标文件.docx") == "document"  # 纯中文 → 兜底名
    assert _output_stem("v1.2 招标文件 final.docx") == "v1.2-final"  # 非 ASCII 段折叠成连字符
    assert _output_stem("...") == "document"  # 只剩标点时不能发出空文件名
