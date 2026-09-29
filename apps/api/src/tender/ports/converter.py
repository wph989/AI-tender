"""Office → PDF 转换端口（契约见 docs/调研/02 第 6 节）。

签名里刻意没有 Gotenberg 的概念：上层只应该知道「把这份文件给我换成 PDF」，
将来若换成 unoserver 或 JODConverter，用例层与 Worker 一行都不用改。

`ConvertResult` 放在端口而不是适配器：它是用例层要消费的返回值，
换个适配器也要原样返回，属于契约的一部分。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol


@dataclass(frozen=True, slots=True)
class ConvertResult:
    pdf_bytes: bytes
    # 转换器名（"gotenberg"）与版本要一起写进 document_version——
    # 日后任何一次溯源争议，都得能回答「当时是哪个版本转的」（docs/调研/02 第 7 节）。
    converter: str
    converter_version: str
    trace_id: str
    elapsed_ms: int


class OfficeConverter(Protocol):
    async def version(self) -> str:
        """读取转换器版本，供版本去重与溯源快照使用。"""
        ...

    async def to_pdf(self, src: BinaryIO, *, filename: str, trace_id: str) -> ConvertResult:
        """把 Office 文档转成 PDF。

        约定：一次只转换一个文件（多文件时 Gotenberg 会返回 ZIP，处理逻辑会分叉）；
        `filename` 只用于命名与 MIME 判定；`trace_id` 必须回传校验，防止并发下串包。
        """
        ...
