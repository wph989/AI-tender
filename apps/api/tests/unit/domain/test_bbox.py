"""bbox 单测。采样边界与四则运算在共享向量里覆盖，这里只测向量表达不了的精度与结构约束。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tender.domain.bbox import Bbox, PixelBox, to_decimal
from tender.domain.errors import BboxFormatError


def test_to_decimal_goes_through_str() -> None:
    # Decimal(0.1) 会把二进制误差固化下来，落库后与共享向量里的 "0.1" 不相等
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal(1) == Decimal("1")
    assert to_decimal("0.1") == Decimal("0.1")


def test_pixel_round_trip_is_exact() -> None:
    bbox = Bbox.from_raw(["0.25", "0.5", "0.75", "1"])
    pixels = bbox.to_pixels(width_px=1000, height_px=2000)
    assert pixels == PixelBox(x0=Decimal(250), y0=Decimal(1000), x1=Decimal(750), y1=Decimal(2000))
    # 换算不做取整，所以往返必须精确：一旦这里引入舍入，裁剪区域与高亮框就会悄悄错位
    assert Bbox.from_pixels(pixels, 1000, 2000) == bbox


def test_from_raw_rejects_wrong_length() -> None:
    with pytest.raises(BboxFormatError):
        Bbox.from_raw([0.1, 0.2, 0.3])
