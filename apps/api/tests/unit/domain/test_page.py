"""页面几何单测：旋转是坐标链路里最易出错、也最难在真实数据上复现的一段。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tender.domain.bbox import Bbox
from tender.domain.errors import InvalidRotationError
from tender.domain.page import PageGeometry


def _page(rotation: int) -> PageGeometry:
    return PageGeometry(
        page_no=1, width_pt=Decimal("600"), height_pt=Decimal("800"), rotation=rotation
    )


@pytest.mark.parametrize(
    ("rotation", "expected"),
    [
        (0, (Decimal("600"), Decimal("800"))),
        (90, (Decimal("800"), Decimal("600"))),
        (180, (Decimal("600"), Decimal("800"))),
        (270, (Decimal("800"), Decimal("600"))),
    ],
)
def test_viewport_size_swaps_on_quarter_turns(
    rotation: int, expected: tuple[Decimal, Decimal]
) -> None:
    assert _page(rotation).viewport_size() == expected


def test_to_visual_moves_page_top_left_to_visual_top_right_at_90() -> None:
    """页面左上角的块，顺时针 90 度后必须落到视觉页面的右上角。

    这条断言是旋转处理的核心：如果只机械地互换 x/y（漏掉 1 - v），
    高亮会跑到左上角——而且只在扫描件上复现，数字正文页永远测不出来。
    """
    top_left = Bbox.from_raw(["0", "0", "0.1", "0.1"])
    assert _page(90).to_visual(top_left) == Bbox(
        x0=Decimal("0.9"), y0=Decimal(0), x1=Decimal(1), y1=Decimal("0.1")
    )


def test_to_visual_is_identity_when_no_rotation() -> None:
    bbox = Bbox.from_raw(["0.2", "0.3", "0.5", "0.6"])
    assert _page(0).to_visual(bbox) == bbox


def test_rejects_rotation_outside_quarter_turns() -> None:
    with pytest.raises(InvalidRotationError):
        _page(45)
