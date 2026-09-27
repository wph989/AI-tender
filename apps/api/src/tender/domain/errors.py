"""领域错误基类。

`code` 与 docs/设计/05 第 5 节的错误码表同名，但领域层不认识 HTTP：
TenderError → HTTP 状态码 + 响应体的映射只允许出现在 api/errors.py 一处
（见 docs/工程/11 第 5.1 节），
散落各处会让同一个错误在不同接口返回不同状态码，前端只能靠猜。
"""

from __future__ import annotations

from typing import ClassVar


class TenderError(Exception):
    """领域层唯一基类。带机器可读的 code，前端据此决定重试按钮是否可用。"""

    code: ClassVar[str] = "invalid_argument"

    def __init__(self, message: str = "") -> None:
        super().__init__(message or self.code)


class AnchorFormatError(TenderError):
    """锚点字符串非法：格式不对、带前导零、序号为 0 等。

    典型来源是 LLM 复述锚点时写错，由「校验①锚点存在性」拦截并丢弃该条证据。
    它必须抛错而不是返回 None——否则「锚点坏了」会被静默当成「这条结果没有锚点」，
    表现为一次看似正常的 not_found。
    """


class BboxFormatError(TenderError):
    """bbox 结构非法（长度不是 4）。数值越界不在此列，越界由 ``Bbox.is_valid()`` 判定。"""


class InvalidRotationError(TenderError):
    """``/Rotate`` 不是 0/90/180/270。"""


class AnchorSequenceError(TenderError):
    """锚点序号不是从 1 开始。"""
