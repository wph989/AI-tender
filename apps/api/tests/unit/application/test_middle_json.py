"""MiddleJson 归一化：空白页不能被判成解析失败。

MinerU 用 exclude_defaults 序列化 MiddleJson，PageInfo.blocks 的默认值（空列表）会被整体省略，
所以「整页无块」的空白页在 JSON 里只剩 page_idx，没有 blocks 键（实测 137 页样本第 10 页即如此）。
如果这里把「缺字段」当成数据损坏，一份含空白页的正常文档就会整份解析失败。
"""

from __future__ import annotations

from typing import Any

import pytest

from tender.application.documents.middle_json import NormalizedElement, normalize_middle_json
from tender.domain.shared.errors import ParseFailed


def _text_block(text: str) -> dict[str, Any]:
    # 形状取自实测样本：块级 content 是 InlineSpan 列表，文字在 span 的 content 字段里。
    return {
        "type": "text",
        "index": 0,
        "bbox": [0.1, 0.1, 0.9, 0.2],
        "content": [{"type": "text", "content": text}],
    }


def _normalize(pages: list[dict[str, Any]]) -> list[NormalizedElement]:
    page_count = len(pages)
    return normalize_middle_json(
        {"pages": pages},
        expected_page_count=page_count,
        # 页面几何来自我们自己的 PDF 引擎（MiddleJson 不含 page_size），这里给全页 0 度。
        page_rotations=dict.fromkeys(range(1, page_count + 1), 0),
        page_has_text_layer=dict.fromkeys(range(1, page_count + 1), True),
        bbox_origin="top_left",
        bbox_rotation="visual",
        require_all_pages=True,
    )


def test_blank_page_without_blocks_key_produces_no_elements() -> None:
    elements = _normalize(
        [
            {"page_idx": 0, "blocks": [_text_block("首页正文")]},
            {"page_idx": 1},
        ]
    )

    assert [element.anchor for element in elements] == ["p1b1"]


def test_page_after_blank_page_keeps_one_based_anchors() -> None:
    elements = _normalize(
        [
            {"page_idx": 0},
            {"page_idx": 1, "blocks": [_text_block("空白页之后的正文")]},
        ]
    )

    assert [(element.page_no, element.anchor) for element in elements] == [(2, "p2b1")]


def test_blocks_that_is_not_an_array_still_fails() -> None:
    with pytest.raises(ParseFailed, match="blocks 必须是数组"):
        _normalize([{"page_idx": 0, "blocks": {}}])
