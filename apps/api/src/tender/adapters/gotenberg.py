"""Gotenberg 适配器：Office → PDF（接口契约见 docs/调研/02 第 6 节）。

这一层只做三件事：把字节发出去、把 PDF 收回来、把第三方错误翻译成领域错误。
但有两个细节必须在这里兜住，否则上层拿到的是「看起来成功的坏数据」：

1. **先取版本、再发转换**。`converter_version` 要写进 `document_version`——
   日后溯源有争议时必须能回答「当时是哪个版本转的」。`/version` 是廉价 GET，
   失败时让整次转换直接可重试失败，比「转换花了半分钟、拿到 PDF 之后才发现记不了版本」划算；
   版本在进程内缓存，正常运行时每次转换不会多出这次往返。
2. **响应必须回传同一个 `Gotenberg-Trace`**。转换是无状态 HTTP，并发下拿到别人请求的响应
   （串包）是真实存在的失败模式；trace 不符时按「可重试失败」处理，而不是把陌生 PDF 交给上层。

转换参数是**冻结取值**（docs/调研/02 第 3.2 节）：它们会改变分页，而分页一变溯源就废了。
因此不做成配置项——改参数必须走评审，而不是在页面上顺手调一下。
"""

from __future__ import annotations

import asyncio
import mimetypes
import re
import time
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from typing import BinaryIO

import httpx

from tender.domain.errors import ConversionFailed, ConversionUnavailable
from tender.ports.converter import ConvertResult

_CONVERT_PATH = "/forms/libreoffice/convert"
_VERSION_PATH = "/version"
_HEALTH_PATH = "/health"

# 我们的固定取值（docs/调研/02 第 3.2 节）。
_CONVERT_OPTIONS: dict[str, str] = {
    "exportBookmarks": "true",  # 保留 Word 大纲 → PDF 书签，供章节树交叉校验
    "exportBookmarksToPdfDestination": "true",  # 导出为命名目标，前端可按标题跳转
    "exportFormFields": "false",  # 控件转静态：避免 fallback 字体测量导致的裁切
    "updateIndexes": "true",  # 更新目录页码
    "exportNotes": "false",  # 标书不需要批注
}

# 5xx 多是上游瞬时状态（LibreOffice 崩溃重启、内存压力、代理抖动），退避重试有意义；
# 4xx 是「这次请求本身有问题」，重试只会再烧一次转换预算。
_RETRY_STATUSES = frozenset({500, 502, 503, 504})
_MAX_ATTEMPTS = 3


_ASCII_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _output_stem(filename: str) -> str:
    """把输出文件名压成 ASCII。

    HTTP 头只能带 ASCII 字节，而招标文件几乎清一色是中文名——直接把「招标文件」塞进
    `Gotenberg-Output-Filename` 会在 httpx 里抛 UnicodeEncodeError，转换根本发不出去。
    响应里的 Content-Disposition 我们并不使用（归档键由自有存储布局决定，见 docs/设计/03），
    所以这里只保留可读的 ASCII 部分；全被剥光时退回 "document"。
    原始文件名仍完整保留在 multipart 里，上游按它判断类型与展示。
    """
    stem = PurePosixPath(filename).stem
    safe = _ASCII_UNSAFE.sub("-", stem).strip("-._")
    return safe or "document"


def _rewind(src: BinaryIO) -> None:
    """重试前把输入流退回起点。

    第一次请求已经把流读完；不回退的重试会发出一个 0 字节文件，
    上游只会报一个更难查的 400——那比直接说「流不可回退」难查十倍。
    """
    if not src.seekable():
        raise ConversionUnavailable("输入流不可回退，无法安全重试转换请求")
    src.seek(0)


class GotenbergConverter:
    """`OfficeConverter` 的 Gotenberg 实现（同步 HTTP + 在途上限由调度侧控制）。"""

    def __init__(
        self,
        base_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 180.0,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        # transport 只给测试注入：有了它，重试、串包、版本缓存这些分支不用起真服务就能覆盖
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            auth=(username, password) if username and password else None,
            transport=transport,
            # 内网转换服务与 MinerU 保持一致，避免启动终端的代理把标书和健康探针转发出去。
            trust_env=False,
        )
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._version: str | None = None

    async def aclose(self) -> None:
        """调用方负责在 worker 退出时关闭连接池；不关会在滚动重启时留下 TIME_WAIT 堆积。"""
        await self._client.aclose()

    async def version(self) -> str:
        """Gotenberg 版本，进程内缓存。

        拿不到版本必须失败而不是降级成 "unknown"：converter_version 是溯源记录的一部分，
        一个写不出「当时用哪个版本」的结果，等于没有溯源（docs/调研/02 第 7 节第 5 条）。
        """
        if self._version is not None:
            return self._version
        try:
            response = await self._client.get(_VERSION_PATH)
        except httpx.HTTPError as exc:
            raise ConversionUnavailable(f"Gotenberg 版本读取失败：{exc}") from exc
        if response.status_code != 200:
            raise ConversionUnavailable(
                f"Gotenberg 版本读取失败：HTTP {response.status_code} {_body_snippet(response)}"
            )
        # 实测 Gotenberg 8.37.0 的 /version 返回的是**纯文本**版本号（"8.37.0"，Content-Type 是
        # text/plain），不是 JSON。早先只按 JSON 解析，真实部署里表现成「一次转换都没成功，
        # 报的错却是版本读取失败」，从日志看不出是响应形状的问题。这里两种形状都接受：先试
        # JSON，不是 JSON 就把整段文本当版本号——版本号马上要写进 document_version，在适配器里
        # 多这几行比每次升级 Gotenberg 都重踩一遍强。
        text = response.text.strip()
        try:
            payload = response.json()
        except ValueError:
            # 纯文本可能被引号包着（有的网关会这么转发），去掉首尾引号再取
            version = text.strip('"').strip()
        else:
            version = str(payload.get("version") or "").strip() if isinstance(payload, dict) else ""
        if not version:
            raise ConversionUnavailable(
                f"Gotenberg 版本响应无法解析（期望纯文本或含 version 字段的 JSON）：{text[:200]!r}"
            )
        self._version = version
        return version

    async def health(self) -> bool:
        """健康检查按「非 200 即不健康」判定（503 = 依赖模块未就绪），且不抛异常。

        调用方要的是状态而不是异常——健康探针抛错会把「不健康」与「探针本身写错了」混在一起。
        """
        try:
            response = await self._client.get(_HEALTH_PATH)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def to_pdf(self, src: BinaryIO, *, filename: str, trace_id: str) -> ConvertResult:
        version = await self.version()
        started = time.perf_counter()

        # Gotenberg 会在给定名字后追加扩展名：去掉原扩展名，否则得到 tender.docx.pdf
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        headers = {"Gotenberg-Output-Filename": _output_stem(filename), "Gotenberg-Trace": trace_id}

        response = await self._post_with_retry(src, filename, content_type, headers, trace_id)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if not response.content.startswith(b"%PDF-"):
            # 单文件请求正常只可能回 PDF；回到别的类型说明上游行为变了（例如回成 ZIP），
            # 此时宁可显式失败，也不能把一段不是 PDF 的字节当成 PDF 存进基座
            raise ConversionFailed(
                f"Gotenberg 返回的不是 PDF（Content-Type: {response.headers.get('content-type')}）"
            )

        return ConvertResult(
            pdf_bytes=response.content,
            converter="gotenberg",
            converter_version=version,
            trace_id=trace_id,
            elapsed_ms=elapsed_ms,
        )

    async def _post_with_retry(
        self,
        src: BinaryIO,
        filename: str,
        content_type: str,
        headers: dict[str, str],
        trace_id: str,
    ) -> httpx.Response:
        last_error: ConversionUnavailable | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            if attempt > 1:
                _rewind(src)
            try:
                response = await self._client.post(
                    _CONVERT_PATH,
                    files={"files": (filename, src, content_type)},
                    data=_CONVERT_OPTIONS,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                # 网络层失败（连不上、读超时）算上游不可用；读超时可能意味着服务端还在转换，
                # 重试有重复转换的成本，但比「让用户重新上传」小得多
                last_error = ConversionUnavailable(f"Gotenberg 请求失败：{exc}")
            else:
                if response.status_code == 200:
                    # 串包校验：响应必须带同一个 trace，否则这不是我们那次转换的结果
                    echoed = response.headers.get("Gotenberg-Trace")
                    if echoed == trace_id:
                        return response
                    last_error = ConversionUnavailable(
                        f"Gotenberg 响应 Trace 不一致：期望 {trace_id!r}，收到 {echoed!r}"
                    )
                elif response.status_code in _RETRY_STATUSES:
                    last_error = ConversionUnavailable(
                        f"Gotenberg 暂时不可用：HTTP {response.status_code} "
                        f"{_body_snippet(response)}"
                    )
                else:
                    # 4xx 与其它非预期状态：文件本身或请求有问题，重试没有意义
                    raise ConversionFailed(
                        f"转换失败：HTTP {response.status_code} {_body_snippet(response)}"
                    )

            if attempt < _MAX_ATTEMPTS:
                await self._sleep(self._backoff_seconds * 2 ** (attempt - 1))

        assert last_error is not None  # 循环里每条失败路径都会赋值，这里只为类型收窄
        raise last_error


def _body_snippet(response: httpx.Response) -> str:
    """把上游响应体的前 200 字符带进错误信息：排障时最有用的往往就是这句话本身。"""
    text = response.text.strip().replace("\n", " ")
    return text[:200]
