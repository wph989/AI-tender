"""共享坐标向量的消费端（后端）。

前端 apps/web/src/lib/coords/__tests__/vectors.test.ts 消费同一个文件：
任何一侧改了坐标规则而没更新向量，这里立刻变红——这是「两份实现必然漂移」的防漂移机制，
不是普通的回归测试（见 docs/工程/10 第 4.5 节）。
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from tender.domain.documents.anchor import Anchor
from tender.domain.documents.bbox import Bbox
from tender.domain.documents.page import PageGeometry
from tender.domain.shared.errors import AnchorFormatError

# 向量文件在仓库根的 packages/contract 下，不随包安装：它是两侧共用的开发期事实源
_VECTORS_PATH = (
    Path(__file__).resolve().parents[4] / "packages" / "contract" / "coords-vectors.json"
)
_VECTORS = json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))


def test_anchor_vectors() -> None:
    for case in _VECTORS["anchor"]["valid"]:
        anchor = Anchor.parse(case["text"])
        assert (anchor.page_no, anchor.block_no) == (case["pageNo"], case["blockNo"])
        assert str(anchor) == case["text"]

    for raw in _VECTORS["anchor"]["invalid"]:
        with pytest.raises(AnchorFormatError):
            Anchor.parse(raw)


def test_bbox_validity_vectors() -> None:
    for case in _VECTORS["bbox"]["validity"]:
        assert Bbox.from_raw(case["bbox"]).is_valid() is case["valid"]


def test_bbox_pixel_vectors() -> None:
    for case in _VECTORS["bbox"]["pixels"]:
        bbox = Bbox.from_raw(case["bbox"])
        pixels = bbox.to_pixels(case["widthPx"], case["heightPx"])
        assert [pixels.x0, pixels.y0, pixels.x1, pixels.y1] == [
            Decimal(value) for value in case["pixels"]
        ]
        assert Bbox.from_pixels(pixels, case["widthPx"], case["heightPx"]) == bbox


def test_bbox_union_vectors() -> None:
    for case in _VECTORS["bbox"]["union"]:
        merged = Bbox.from_raw(case["a"]).union(Bbox.from_raw(case["b"]))
        assert [merged.x0, merged.y0, merged.x1, merged.y1] == [
            Decimal(value) for value in case["expected"]
        ]


@pytest.mark.parametrize("case", _VECTORS["rotation"], ids=lambda case: case["label"])
def test_rotation_vectors(case: dict) -> None:
    page = PageGeometry(
        page_no=1,
        width_pt=Decimal(case["widthPt"]),
        height_pt=Decimal(case["heightPt"]),
        rotation=case["rotation"],
    )
    assert page.viewport_size() == (
        Decimal(case["viewport"]["width"]),
        Decimal(case["viewport"]["height"]),
    )
    visual = page.to_visual(Bbox.from_raw(case["bbox"]))
    assert [visual.x0, visual.y0, visual.x1, visual.y1] == [
        Decimal(value) for value in case["visual"]
    ]
