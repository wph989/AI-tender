"""解析后的元素值对象；用例和仓储共用，避免数据契约依赖处理流程。"""

from dataclasses import dataclass

from tender.domain.documents.bbox import Bbox


@dataclass(frozen=True, slots=True)
class NormalizedElement:
    page_no: int
    order_no: int
    anchor: str
    element_type: str
    level: int | None
    parent_index: int | None
    bbox: Bbox | None
    text: str | None
    html: str | None
    source: str
    continues_prev: bool
    mineru_locator: str
