"""PDF 页面探测数据契约；仓储只依赖页面数据，不依赖 PDFium 引擎。"""

from dataclasses import dataclass
from decimal import Decimal


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
