"""领域错误基类。

`code` 与 docs/设计/05 第 5 节的错误码表同名，但领域层不认识 HTTP：
TenderError → HTTP 状态码 + 响应体的映射只允许出现在 api/errors.py 一处
（见 docs/工程/11 第 5.1 节），
散落各处会让同一个错误在不同接口返回不同状态码，前端只能靠猜。
"""

from __future__ import annotations

from typing import ClassVar


class TenderError(Exception):
    """领域层唯一基类。带机器可读的 code 与 retryable 信号（见 docs/设计/05 第 5 节）。

    `retryable` 必须由错误类型自己声明，而不是让 API 层按 HTTP 状态码去猜：
    「错误该映射成哪个状态码」与「该不该给用户重试按钮」是两件事。
    """

    code: ClassVar[str] = "invalid_argument"
    retryable: ClassVar[bool] = False

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

class ConversionFailed(TenderError):
    """Gotenberg 判定「文件本身有问题」（400/422），或响应根本不是 PDF。

    重试无意义：同样的字节再转一次还是失败，只会再烧掉一次转换预算。
    """

    code: ClassVar[str] = "conversion_failed"


class ConversionUnavailable(TenderError):
    """Gotenberg 侧暂时不可用：5xx、网络错误、版本读不到、响应 Trace 串包。

    这类失败重试有意义；`retryable=True` 会让前端把「重试」按钮亮起来
    （见 docs/设计/05 第 5 节）。
    """

    code: ClassVar[str] = "conversion_unavailable"
    retryable: ClassVar[bool] = True
