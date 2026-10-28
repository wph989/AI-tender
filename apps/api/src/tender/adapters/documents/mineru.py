"""MinerU 4.x V1 HTTP 适配器，第三方协议细节在此收口。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from pathlib import PurePosixPath
from typing import cast
from urllib.parse import quote, urljoin, urlsplit

import httpx

from tender.domain.shared.errors import (
    ParseFailed,
    ParseSubmissionUnknown,
    ParseUnavailable,
    ServiceRestarted,
    UploadSizeMismatch,
)
from tender.ports.documents.parser import (
    MiddleJson,
    ParseConfigSnapshot,
    ParseJobState,
    ParseJobStatus,
    ParseProgress,
    ParseSubmission,
)

_HEALTH_PATH = "/v1/health"
_UPLOADS_PATH = "/v1/uploads"
_PARSE_JOBS_PATH = "/v1/parse/jobs"
_FILES_PATH = "/v1/files"
_PAGE_RANGE = "all"
_OUTPUT_FORMATS = ("middle_json", "zip")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TIERS = frozenset({"flash", "basic", "standard", "advanced"})
_OCR_MODES = frozenset({"auto", "txt", "ocr"})
_JOB_STATES = frozenset({"queued", "running", "completed", "partial", "failed", "canceled"})

PdfLoader = Callable[[str], Awaitable[bytes]]


class _UploadedFileMissing(Exception):
    """文件索引在上传与解析提交之间失效；可重建上传后安全重试。"""


class MinerUParser:
    """通过 MinerU 自托管 V1 API 解析 PDF。"""

    def __init__(
        self,
        base_url: str,
        *,
        pdf_loader: PdfLoader,
        api_key: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 180.0,
    ) -> None:
        normalized_url = base_url.rstrip("/")
        parsed = urlsplit(normalized_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("MinerU URL 必须是有效的 HTTP 或 HTTPS 基址")

        self._base_url = normalized_url
        self._origin = _origin(normalized_url)
        self._pdf_loader = pdf_loader
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._client = httpx.AsyncClient(
            base_url=normalized_url,
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            transport=transport,
            # 招标文件不能被开发机继承的 HTTP_PROXY 环境变量转发到内网之外。
            trust_env=False,
        )

    async def aclose(self) -> None:
        """调用方在 Worker 退出时关闭连接池，避免滚动重启遗留连接。"""
        await self._client.aclose()

    async def health(self) -> bool:
        """健康探针只检查 HTTP 状态码；MinerU 的 503 代表模型未就绪。"""
        try:
            response = await self._client.get(_HEALTH_PATH)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def submit(
        self,
        pdf_key: str,
        *,
        pdf_sha256: str,
        ocr_mode: str = "auto",
        tier: str = "standard",
    ) -> ParseSubmission:
        sha256 = _validated_sha256(pdf_sha256)
        _validate_config(tier, ocr_mode)
        if not pdf_key.strip():
            raise ParseFailed("PDF 存储键不能为空")

        filename = PurePosixPath(pdf_key.replace("\\", "/")).name or "document.pdf"
        # 对象存储按哈希寻址，键名未必带扩展名；MinerU 按文件名判断类型，MIME 不足以替代后缀。
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        provider_job_id, provider_version = await self._start_job(
            pdf_key,
            filename,
            sha256,
            tier=tier,
            ocr_mode=ocr_mode,
        )

        return ParseSubmission(
            job_id=provider_job_id,
            provider_version=provider_version,
            config_snapshot=_config_snapshot(tier, ocr_mode),
        )

    async def poll(self, job_id: str) -> ParseJobStatus:
        if not job_id.strip():
            raise ParseFailed("MinerU job_id 不能为空")
        response = await self._request_api(
            "GET",
            f"{_PARSE_JOBS_PATH}/{quote(job_id, safe='')}",
        )
        if response.status_code == 404:
            # 任务 ID 只在 MinerU 进程内有效；由用例层从 document_version 取 PDF key/hash 重提。
            raise ServiceRestarted("MinerU 任务索引已失效，需按 PDF SHA-256 重新提交")
        if response.status_code != 200:
            _raise_api_failure(response, "读取解析任务")

        payload = _json_object(response, "解析任务状态")
        raw_status = payload.get("status")
        if not isinstance(raw_status, str) or raw_status not in _JOB_STATES:
            raise ParseFailed(f"MinerU 返回未知任务状态：{raw_status!r}")

        state = cast(ParseJobState, raw_status)
        middle_json_file_id, file_error_code, file_error_message = _middle_json_output(payload)
        error_code, error_message = _error_details(payload)
        return ParseJobStatus(
            job_id=job_id,
            status=state,
            progress=_progress(payload.get("progress")),
            has_middle_json=middle_json_file_id is not None,
            error_code=error_code or file_error_code,
            error_message=error_message or file_error_message,
        )

    async def fetch_middle_json(self, job_id: str) -> MiddleJson:
        job_path = f"{_PARSE_JOBS_PATH}/{quote(job_id, safe='')}"
        job_response = await self._request_api("GET", job_path)
        if job_response.status_code == 404:
            raise ServiceRestarted("MinerU 任务索引已失效，需按 PDF SHA-256 重新提交")
        if job_response.status_code != 200:
            _raise_api_failure(job_response, "读取 MiddleJson 任务")
        job = _json_object(job_response, "MiddleJson 任务状态")
        if job.get("status") not in {"completed", "partial"}:
            raise ParseFailed("MinerU 任务尚未完成或没有可用的 MiddleJson")
        middle_json_file_id, _, _ = _middle_json_output(job)
        if not middle_json_file_id:
            raise ParseFailed("MinerU 任务没有可下载的 MiddleJson")

        path = f"{_FILES_PATH}/{quote(middle_json_file_id, safe='')}/content"
        response = await self._request_api("GET", path)
        if response.status_code == 404:
            raise ServiceRestarted("MinerU 产物索引已失效，需按 PDF SHA-256 重新提交")
        if response.status_code != 200:
            _raise_api_failure(response, "下载 MiddleJson")

        try:
            payload = json.loads(response.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ParseFailed("MinerU MiddleJson 不是有效的 UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise ParseFailed("MinerU MiddleJson 顶层必须是 JSON 对象")

        schema_version = payload.get("schema_version")
        # 不把数值 2.0 强制转成字符串，避免宽松转换掩盖上游 schema 契约变化。
        if not isinstance(schema_version, str) or schema_version != "2.0":
            received = (
                schema_version if isinstance(schema_version, str) and schema_version else "missing"
            )
            raise ParseFailed(f"不支持的 MiddleJson schema_version：{received}")
        pages = payload.get("pages")
        if not isinstance(pages, list) or any(not isinstance(page, dict) for page in pages):
            raise ParseFailed("MinerU MiddleJson 必须包含对象数组 pages")

        backend_value = payload.get("backend")
        backend = backend_value if isinstance(backend_value, str) else None
        return MiddleJson(
            raw_bytes=response.content,
            payload=cast(dict[str, object], payload),
            schema_version=schema_version,
            backend=backend,
        )

    async def _version(self) -> str:
        # 每次提交都取版本，避免服务升级后仍把旧版本写进 parse_run 快照。
        try:
            response = await self._client.get(_HEALTH_PATH)
        except httpx.HTTPError as exc:
            raise ParseUnavailable(f"MinerU 版本读取失败：{exc}") from exc
        if response.status_code != 200:
            raise ParseUnavailable(
                f"MinerU 版本读取失败：HTTP {response.status_code} {_body_snippet(response)}"
            )
        payload = _json_object(response, "MinerU health")
        version = str(payload.get("version") or "").strip()
        if not version:
            raise ParseFailed("MinerU health 响应里没有 version 字段")

        features = payload.get("features")
        formats = features.get("output_formats") if isinstance(features, dict) else None
        if not isinstance(formats, list) or not all(
            output_format in formats for output_format in _OUTPUT_FORMATS
        ):
            raise ParseFailed("MinerU health 未声明 middle_json 与 zip 输出能力")
        return version

    async def _ensure_file(self, pdf_key: str, filename: str, sha256: str) -> str:
        content = await self._pdf_loader(pdf_key)
        if not isinstance(content, bytes) or not content:
            raise ParseFailed("PDF 存储内容为空或不是 bytes")
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != sha256:
            raise ParseFailed(f"PDF 内容 SHA-256 不匹配：期望 {sha256}，实际 {actual_sha256}")

        for attempt in range(2):
            payload = await self._post_json(
                _UPLOADS_PATH,
                {
                    "filename": filename,
                    "bytes": len(content),
                    "mime_type": "application/pdf",
                    "purpose": "parse",
                    "sha256sum": sha256,
                },
                operation="创建 MinerU 上传",
            )
            status = payload.get("status")
            if status == "completed":
                return _file_id(payload)
            if status in {"cancelled", "expired"}:
                if attempt == 1:
                    raise ParseUnavailable(f"MinerU upload 已是 {status} 状态，无法取得可用文件")
                continue
            if status != "pending":
                raise ParseFailed(f"MinerU 返回不支持的 upload 状态：{status!r}")

            upload_id = _upload_id(payload)
            upload_url = _required_string(payload, "upload_url", "MinerU upload 响应")
            upload_method = _required_string(payload, "upload_method", "MinerU upload 响应")
            upload_headers = _string_headers(payload.get("upload_headers"))
            if upload_method.upper() != "PUT":
                raise ParseFailed(f"MinerU 返回不支持的上传方法：{upload_method!r}")

            absolute_upload_url = urljoin(f"{self._base_url}/", upload_url)
            _validate_upload_url(absolute_upload_url)
            if _origin(absolute_upload_url) != self._origin:
                # 自托管 API 返回同源上传路径；拒绝其它主机，防止标书转交给未配置的存储服务。
                raise ParseFailed("自托管 MinerU upload_url 必须与 API 同源")
            if self._api_key:
                upload_headers["Authorization"] = f"Bearer {self._api_key}"
            try:
                upload_response = await self._client.request(
                    upload_method,
                    absolute_upload_url,
                    content=content,
                    headers=upload_headers,
                )
            except httpx.HTTPError as exc:
                raise ParseUnavailable(f"MinerU 文件上传失败：{exc}") from exc
            if upload_response.status_code != 200:
                _raise_api_failure(upload_response, "上传 PDF 字节")

            complete_path = f"{_UPLOADS_PATH}/{quote(upload_id, safe='')}/complete"
            complete_response = await self._request_api("POST", complete_path)
            if complete_response.status_code == 200:
                completed = _json_object(complete_response, "完成 MinerU 上传")
                completed_file_id = _optional_file_id(completed)
                if completed_file_id:
                    return completed_file_id
            elif (
                complete_response.status_code == 409
                and _error_code(complete_response) == "upload_already_terminal"
            ):
                terminal_file_id = _optional_file_id(_safe_json_object(complete_response))
                if terminal_file_id:
                    return terminal_file_id
            else:
                _raise_api_failure(complete_response, "完成 MinerU 上传")

            # complete 响应丢失 file_id 时，按 SHA-256 再查一次已完成文件。
            if attempt == 1:
                raise ParseUnavailable("MinerU 上传已结束，但无法确认对应 file_id")

        raise ParseUnavailable("MinerU 上传状态无法确认")

    async def _post_json(
        self,
        path: str,
        body: Mapping[str, object],
        *,
        operation: str,
    ) -> dict[str, object]:
        response = await self._request_api("POST", path, json_body=body)
        if response.status_code != 200:
            _raise_api_failure(response, operation)
        return _json_object(response, operation)

    async def _create_parse_job(self, file_id: str, *, tier: str, ocr_mode: str) -> str:
        request_body: dict[str, object] = {
            "files": [
                {
                    "source": {"type": "file_id", "file_id": file_id},
                    "page_range": _PAGE_RANGE,
                }
            ],
            "tier": tier,
            "ocr_mode": ocr_mode,
            "output_formats": list(_OUTPUT_FORMATS),
        }
        try:
            response = await self._request_api(
                "POST",
                _PARSE_JOBS_PATH,
                json_body=request_body,
            )
        except ParseUnavailable as exc:
            # MinerU 没有幂等键；网络超时、HTTP 408 或 5xx 后不能确认任务是否已创建。
            raise ParseSubmissionUnknown(
                "MinerU 解析提交结果未知；先核对任务状态，不能盲目重放"
            ) from exc

        if response.status_code == 202:
            try:
                payload = _json_object(response, "创建解析任务")
            except ParseFailed as exc:
                raise ParseSubmissionUnknown(
                    "MinerU 已接受解析任务，但响应缺少可用 job_id"
                ) from exc
            provider_job_id = payload.get("job_id")
            if isinstance(provider_job_id, str) and provider_job_id:
                return provider_job_id
            raise ParseSubmissionUnknown("MinerU 已接受解析任务，但响应缺少可用 job_id")

        code = _error_code(response)
        if response.status_code == 404:
            raise _UploadedFileMissing
        if response.status_code == 408 or (
            response.status_code >= 500 and code != "quality_tier_unavailable"
        ):
            raise ParseSubmissionUnknown(
                f"MinerU 解析提交状态未知：HTTP {response.status_code} {_body_snippet(response)}"
            )
        _raise_api_failure(response, "提交 MinerU 解析任务")
        raise AssertionError("unreachable")

    async def _request_api(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, object] | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else None
        try:
            return await self._client.request(
                method,
                path,
                headers=headers,
                json=json_body,
            )
        except httpx.HTTPError as exc:
            raise ParseUnavailable(f"MinerU HTTP 请求失败：{exc}") from exc

    async def _start_job(
        self,
        pdf_key: str,
        filename: str,
        sha256: str,
        *,
        tier: str,
        ocr_mode: str,
    ) -> tuple[str, str]:
        # 服务可能在 complete 与 parse/jobs 之间重启；明确的 404 可按哈希重建文件后再试。
        for attempt in range(2):
            provider_version = await self._version()
            file_id = await self._ensure_file(pdf_key, filename, sha256)
            try:
                provider_job_id = await self._create_parse_job(
                    file_id,
                    tier=tier,
                    ocr_mode=ocr_mode,
                )
            except _UploadedFileMissing as exc:
                if attempt == 1:
                    raise ParseFailed("MinerU 重新上传后仍找不到文件索引") from exc
                continue
            return provider_job_id, provider_version
        raise AssertionError("unreachable")


def _config_snapshot(tier: str, ocr_mode: str) -> ParseConfigSnapshot:
    return ParseConfigSnapshot(
        tier=tier,
        ocr_mode=ocr_mode,
        page_range=_PAGE_RANGE,
        output_formats=_OUTPUT_FORMATS,
    )


def _validate_config(tier: str, ocr_mode: str) -> None:
    if tier not in _TIERS:
        raise ParseFailed(f"不支持的 MinerU tier：{tier!r}")
    if ocr_mode not in _OCR_MODES:
        raise ParseFailed(f"不支持的 MinerU ocr_mode：{ocr_mode!r}")


def _validated_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if not _SHA256.fullmatch(normalized):
        raise ParseFailed("pdf_sha256 必须是 64 位十六进制 SHA-256")
    return normalized


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"无效 URL：{url!r}")
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port or default_port


def _validate_upload_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ParseFailed("MinerU upload_url 必须是绝对 HTTP(S) URL")


def _required_string(payload: Mapping[str, object], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ParseFailed(f"{context}缺少 {key}")
    return value


def _upload_id(payload: Mapping[str, object]) -> str:
    """上传资源的 id。

    实测自托管 4.0.7 返回的是 OpenAI 风格的顶层 `id`（形如 `upload_xxx`），而调研文档里记的是
    `upload_id`。两个名字都认：字段名差异不该让整条解析链路直接失败。缺了必须报错——没有它
    拼不出「上传字节」与「complete」的路径。
    """
    for key in ("upload_id", "id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    raise ParseFailed("MinerU upload 响应缺少 id")


def _string_headers(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(header, str) for key, header in value.items()
    ):
        raise ParseFailed("MinerU upload_headers 必须是字符串键值对象")
    return dict(value)


def _file_id(payload: Mapping[str, object]) -> str:
    file_id = _optional_file_id(payload)
    if not file_id:
        raise ParseFailed("MinerU completed upload 响应缺少 file_id")
    return file_id


def _optional_file_id(payload: Mapping[str, object]) -> str | None:
    direct = payload.get("file_id")
    if isinstance(direct, str) and direct:
        return direct
    file_object = payload.get("file")
    if isinstance(file_object, dict):
        for key in ("file_id", "id"):
            value = file_object.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _middle_json_output(
    payload: Mapping[str, object],
) -> tuple[str | None, str | None, str | None]:
    files = payload.get("files")
    if not isinstance(files, list):
        return None, None, None
    objects = [item for item in files if isinstance(item, dict)]
    if len(objects) != 1:
        return None, None, None

    file_result = objects[0]
    output_files = file_result.get("output_files")
    middle_json_file_id: str | None = None
    if isinstance(output_files, dict):
        middle_json = output_files.get("middle_json")
        if isinstance(middle_json, dict):
            value = middle_json.get("file_id")
            if isinstance(value, str) and value:
                middle_json_file_id = value
    error_code, error_message = _error_details(file_result)
    return middle_json_file_id, error_code, error_message


def _progress(value: object) -> ParseProgress | None:
    if not isinstance(value, dict):
        return None
    total = _nonnegative_int(value.get("total"))
    completed = _nonnegative_int(value.get("completed"))
    failed = _nonnegative_int(value.get("failed"))
    if total is None or completed is None or failed is None:
        return None
    return ParseProgress(total=total, completed=completed, failed=failed)


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _safe_json_object(response: httpx.Response) -> dict[str, object]:
    try:
        value = response.json()
    except ValueError:
        return {}
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _json_object(response: httpx.Response, context: str) -> dict[str, object]:
    try:
        value = response.json()
    except ValueError as exc:
        raise ParseFailed(f"{context}响应不是有效 JSON") from exc
    if not isinstance(value, dict):
        raise ParseFailed(f"{context}响应顶层必须是 JSON 对象")
    return cast(dict[str, object], value)


def _error_code(response: httpx.Response) -> str | None:
    payload = _safe_json_object(response)
    containers = [payload]
    for key in ("error", "detail"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            containers.append(cast(dict[str, object], nested))
    for container in containers:
        code = container.get("code")
        if isinstance(code, str) and code:
            return code
    return None


def _error_details(payload: Mapping[str, object]) -> tuple[str | None, str | None]:
    error = payload.get("error")
    candidates: list[Mapping[str, object]] = [payload]
    if isinstance(error, dict):
        candidates.insert(0, cast(dict[str, object], error))
    code: str | None = None
    message: str | None = None
    for candidate in candidates:
        if code is None:
            value = candidate.get("code") or candidate.get("error_code")
            if isinstance(value, str) and value:
                code = value
        if message is None:
            value = candidate.get("message") or candidate.get("detail")
            if isinstance(value, str) and value:
                message = value
    return code, message


def _raise_api_failure(response: httpx.Response, operation: str) -> None:
    code = _error_code(response)
    message = (
        f"{operation}失败：HTTP {response.status_code}"
        + (f" {code}" if code else "")
        + f" {_body_snippet(response)}"
    )
    if code in {"bytes_mismatch", "upload_size_mismatch"} or response.status_code == 413:
        raise UploadSizeMismatch(message)
    if code == "quality_tier_unavailable":
        raise ParseFailed(message)
    if response.status_code >= 500 or response.status_code in {408, 429}:
        raise ParseUnavailable(message)
    raise ParseFailed(message)


def _body_snippet(response: httpx.Response) -> str:
    return response.text.strip().replace("\n", " ")[:300]
