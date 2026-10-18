"""锚点单测。全量合法/非法样例在共享向量里，这里只覆盖向量表达不了的部分。"""

from __future__ import annotations

import pytest

from tender.domain.documents.anchor import Anchor
from tender.domain.shared.errors import AnchorFormatError, AnchorSequenceError


def test_parse_and_str_round_trip() -> None:
    anchor = Anchor.parse("p12b5")
    assert (anchor.page_no, anchor.block_no) == (12, 5)
    assert str(anchor) == "p12b5"


def test_parse_rejects_non_string() -> None:
    # LLM 偶尔会把锚点写成数字或 null。让它抛领域错误，而不是在 re.match 上崩成 AttributeError——
    # 前者能被「校验①」按条丢弃，后者会让整份文档的抽取失败。
    with pytest.raises(AnchorFormatError):
        Anchor.parse(None)  # type: ignore[arg-type]


def test_direct_construction_rejects_zero() -> None:
    # 构造与 parse 必须用同一套约束，否则内部能造出 parse 不认的值，两端行为分叉
    with pytest.raises(AnchorSequenceError):
        Anchor(page_no=0, block_no=1)
    with pytest.raises(AnchorSequenceError):
        Anchor(page_no=1, block_no=0)
