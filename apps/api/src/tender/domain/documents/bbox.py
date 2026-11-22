"""坐标契约：0–1 归一化、左上原点、视觉方向（见 docs/设计/03-数据模型与溯源设计.md）。

为什么用 Decimal 而不是 float：归一化坐标要落 NUMERIC(7,6) 并参与相等比较，
float 的舍入会让「同一条证据」在两次读取中不相等。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from tender.domain.shared.errors import BboxFormatError

# 外部数值的统一入口类型：MiddleJson 给 JSON number，数据库给 Decimal，共享向量文件给字符串。
RawNumber = int | float | str | Decimal


def to_decimal(value: RawNumber) -> Decimal:
    """把外部数值转成 Decimal，必须走 str。

    ``Decimal(0.1)`` 会把 float 的二进制误差原样固化（0.1000000000000000055511151231257827），
    再落进 NUMERIC(7,6) 就成了一个「看起来是 0.1、实际不是」的值；
    `Decimal("0.1")` 才是十进制 0.1。
    """
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True, slots=True)
class PixelBox:
    """像素坐标盒。

    字段是 Decimal 而不是 int：换算本身不做取整——是向下取整还是向外扩张取决于用途
    （裁剪宁可多含一点，画调试框宁可贴合），纯函数不该替调用方决定。
    """

    x0: Decimal
    y0: Decimal
    x1: Decimal
    y1: Decimal


@dataclass(frozen=True, slots=True)
class Bbox:
    x0: Decimal
    y0: Decimal
    x1: Decimal
    y1: Decimal

    @classmethod
    def from_raw(cls, values: Sequence[RawNumber]) -> Bbox:
        """从 bbox 数组 ``[x0, y0, x1, y1]`` 构造（MinerU 的原始结构）。

        长度不是 4 直接抛错：缺字段时静默补 0 会产出一个「结构合法但数值错误」的坐标，
        恰好是这套系统里最贵的错误类型。
        """
        if len(values) != 4:
            raise BboxFormatError(f"bbox 必须是 4 个元素，收到 {len(values)} 个")
        return cls(*(to_decimal(value) for value in values))

    def is_valid(self) -> bool:
        """``0 <= x0 < x1 <= 1`` 且 ``0 <= y0 < y1 <= 1``。

        零面积盒（x0 == x1）判为无效：它画不出任何高亮，前端只能显示一个看不见的框，
        而用户会以为「系统没定位到」，排查方向完全错。
        """
        return 0 <= self.x0 < self.x1 <= 1 and 0 <= self.y0 < self.y1 <= 1

    def to_pixels(self, width_px: int, height_px: int) -> PixelBox:
        return PixelBox(
            x0=self.x0 * width_px,
            y0=self.y0 * height_px,
            x1=self.x1 * width_px,
            y1=self.y1 * height_px,
        )

    @classmethod
    def from_pixels(cls, box: PixelBox, width_px: int, height_px: int) -> Bbox:
        return cls(
            x0=box.x0 / width_px,
            y0=box.y0 / height_px,
            x1=box.x1 / width_px,
            y1=box.y1 / height_px,
        )

    def union(self, other: Bbox) -> Bbox:
        """合并两个定位区域，使同页多块原文有统一的外接矩形。"""
        return Bbox(
            x0=min(self.x0, other.x0),
            y0=min(self.y0, other.y0),
            x1=max(self.x1, other.x1),
            y1=max(self.y1, other.y1),
        )
