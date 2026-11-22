"""锚点格式为``p{page}b{block}``，页码和块序号均从1开始。

为什么需要一个独立类型而不是到处传字符串：锚点是证据与原文之间唯一的连接点，
格式漂一个字符前端就点不到任何位置，而这类错误不会抛异常，只会静默定位失败。
因此解析入口只允许一个，且失败必须抛错。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from tender.domain.shared.errors import AnchorFormatError, AnchorSequenceError

# 只接受规范形式，因此不放行前导零（p01b1）：
# 否则 p1b1 与 p01b1 会变成两个字符串指向同一个块，
# 去重与反查都会出现「看起来对、实际查不到」的情况。
_ANCHOR_RE = re.compile(r"^p([1-9]\d*)b([1-9]\d*)$")


@dataclass(frozen=True, slots=True)
class Anchor:
    page_no: int
    block_no: int

    def __post_init__(self) -> None:
        # 直接构造也要挡住 0：否则 Anchor(0, 1) 能存在却无法被 parse 还原，
        # 等于造出一个「系统内部合法、对外不可读」的值。
        if self.page_no < 1 or self.block_no < 1:
            raise AnchorSequenceError(f"锚点序号必须从 1 开始：p{self.page_no}b{self.block_no}")

    @classmethod
    def parse(cls, raw: str) -> Anchor:
        """解析锚点，失败抛 AnchorFormatError（绝不返回 None）。"""
        matched = _ANCHOR_RE.match(raw) if isinstance(raw, str) else None
        if matched is None:
            raise AnchorFormatError(f"锚点格式非法：{raw!r}")
        return cls(page_no=int(matched.group(1)), block_no=int(matched.group(2)))

    def __str__(self) -> str:
        return f"p{self.page_no}b{self.block_no}"
