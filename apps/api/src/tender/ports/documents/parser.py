"""文档解析端口：只表达系统需要的解析能力，不暴露 MinerU 的 HTTP 结构。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

ParseJobState = Literal["queued", "running", "completed", "partial", "failed", "canceled"]


@dataclass(frozen=True, slots=True)
class ParseConfigSnapshot:
    """描述一次解析的有效参数，供 parse_run 原样留档。"""

    tier: str
    ocr_mode: str
    page_range: str
    output_formats: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParseProgress:
    total: int
    completed: int
    failed: int


@dataclass(frozen=True, slots=True)
class ParseSubmission:
    """提交成功后需与配置快照一起持久化的解析任务引用。"""

    job_id: str
    provider_version: str
    config_snapshot: ParseConfigSnapshot


@dataclass(frozen=True, slots=True)
class ParseJobStatus:
    """一次轮询结果；has_middle_json 为真时可下载 MiddleJson。"""

    job_id: str
    status: ParseJobState
    progress: ParseProgress | None
    has_middle_json: bool
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class MiddleJson:
    """MiddleJson 原始字节与已校验的顶层元数据，原始字节用于审计存档。"""

    raw_bytes: bytes
    payload: dict[str, object]
    schema_version: str
    backend: str | None


class DocumentParser(Protocol):
    async def submit(
        self,
        pdf_key: str,
        *,
        pdf_sha256: str,
        ocr_mode: str = "auto",
        tier: str = "standard",
    ) -> ParseSubmission:
        """提交 PDF 并返回可持久化的任务引用与配置快照。"""
        ...

    async def poll(self, job_id: str) -> ParseJobStatus:
        """读取一次状态；服务索引丢失时抛出 ServiceRestarted。"""
        ...

    async def fetch_middle_json(self, job_id: str) -> MiddleJson:
        """用任务句柄查找并下载已完成任务的 MiddleJson。"""
        ...

    async def health(self) -> bool:
        """探测解析服务；任何非 200 响应都表示不健康。"""
        ...
