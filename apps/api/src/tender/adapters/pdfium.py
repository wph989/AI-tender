"""pypdfium2 页面几何适配器；尺寸从 MediaBox 读出，旋转单独保存。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import BinaryIO

import pypdfium2 as pdfium
from pypdfium2._helpers.misc import PdfiumError


@dataclass(frozen=True, slots=True)
class ProbedPage:
    page_no: int
    width_pt: Decimal
    height_pt: Decimal
    rotation: int
    has_text_layer: bool


@dataclass(frozen=True, slots=True)
class PdfInspection:
    page_count: int
    pages: tuple[ProbedPage, ...]


class InvalidPdfError(ValueError):
    """文件不是可读取的 PDF，或页面几何缺失。"""


def inspect_pdf(source: bytes | BinaryIO) -> PdfInspection:
    """读取未旋转 MediaBox 与原生文本；空白页会保留 has_text_layer=false。"""
    try:
        with pdfium.PdfDocument(source) as document:
            pages: list[ProbedPage] = []
            for index in range(len(document)):
                page = document[index]
                try:
                    media_box = page.get_mediabox(fallback_ok=False)
                    if media_box is None:
                        raise InvalidPdfError(f"PDF 第 {index + 1} 页没有 MediaBox")
                    left, bottom, right, top = media_box
                    width = Decimal(str(right - left)).quantize(Decimal("0.001"))
                    height = Decimal(str(top - bottom)).quantize(Decimal("0.001"))
                    rotation = int(page.get_rotation())
                    if width <= 0 or height <= 0 or rotation not in {0, 90, 180, 270}:
                        raise InvalidPdfError(f"PDF 第 {index + 1} 页几何无效")

                    text_page = page.get_textpage()
                    try:
                        has_text = bool(text_page.get_text_range().strip())
                    finally:
                        text_page.close()
                    pages.append(
                        ProbedPage(
                            page_no=index + 1,
                            width_pt=width,
                            height_pt=height,
                            rotation=rotation,
                            has_text_layer=has_text,
                        )
                    )
                finally:
                    page.close()
    except (PdfiumError, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, InvalidPdfError):
            raise
        raise InvalidPdfError(f"PDF 无法读取：{exc}") from exc

    if not pages:
        raise InvalidPdfError("PDF 至少需要包含一页")
    return PdfInspection(page_count=len(pages), pages=tuple(pages))
