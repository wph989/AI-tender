"""页面几何：pt 尺寸 + 原始 ``/Rotate`` + 视口与坐标换算（见 docs/设计/03 第 3.3、3.4 节）。

为什么把 rotation 放在领域层而不是渲染层：旋转决定「视觉方向」的含义，而 bbox 契约写的正是视觉方向。
留在渲染层就会出现前后端各按各的理解换算，表现为 90 度页面上的高亮横竖颠倒——
只在旋转页（扫描件常见）复现，测试最容易漏掉。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from tender.domain.documents.bbox import Bbox
from tender.domain.shared.errors import InvalidRotationError

_VALID_ROTATIONS = (0, 90, 180, 270)
_ONE = Decimal(1)


@dataclass(frozen=True, slots=True)
class PageGeometry:
    page_no: int
    width_pt: Decimal
    height_pt: Decimal
    rotation: int  # 原始 /Rotate

    def __post_init__(self) -> None:
        if self.rotation not in _VALID_ROTATIONS:
            raise InvalidRotationError(f"/Rotate 只能是 0/90/180/270，收到 {self.rotation}")

    def viewport_size(self) -> tuple[Decimal, Decimal]:
        """视觉方向的页面尺寸：90/270 度时宽高互换。

        前端算虚拟滚动占位高度、后端算裁剪区域，用的是同一个换算；
        两者不一致时占位高度与真实渲染高度不符，滚动位置会在渲染完成的瞬间跳动。
        """
        if self.rotation in (90, 270):
            return self.height_pt, self.width_pt
        return self.width_pt, self.height_pt

    def to_visual(self, bbox: Bbox) -> Bbox:
        """把「页面方向」的 bbox 换算成「视觉方向」。

        前提：入参已按 docs/设计/03 第 3.2 节做过原点翻转，
        即「归一化 + 左上原点 + 未旋转的页面方向」。
        `/Rotate` 的含义是按该角度**顺时针**显示，
        所以 90 度时原页面的左上角会落到视觉页面的右上角；
        x/y 与 1-x/1-y 的互换会让两个角的大小关系反转，因此每一项都要重新取 min/max。

        扫描件常见的 90/270 度如果不做这一步，高亮会整体横过来——这是本系统最难排查的一类 bug。
        """
        if self.rotation == 90:
            # u' = 1 - v, v' = u
            return Bbox(x0=_ONE - bbox.y1, y0=bbox.x0, x1=_ONE - bbox.y0, y1=bbox.x1)
        if self.rotation == 180:
            # u' = 1 - u, v' = 1 - v
            return Bbox(x0=_ONE - bbox.x1, y0=_ONE - bbox.y1, x1=_ONE - bbox.x0, y1=_ONE - bbox.y0)
        if self.rotation == 270:
            # u' = v, v' = 1 - u
            return Bbox(x0=bbox.y0, y0=_ONE - bbox.x1, x1=bbox.y1, y1=_ONE - bbox.x0)
        return bbox
