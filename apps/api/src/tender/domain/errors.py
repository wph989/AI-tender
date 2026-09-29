"""领域错误基类。

`code` 与 docs/设计/05 第 5 节的错误码表同名，但领域层不认识 HTTP：
TenderError → HTTP 状态码 + 响应体的映射只允许出现在 api/errors.py 一处
（见 docs/工程/11 第 5.1 节），
散落各处会让同一个错误在不同接口返回不同状态码，前端只能靠猜。
"""

from __future__ import annotations

from typing import ClassVar


class TenderError(Exception):
    """领域层唯一基类。带机器可读的 code 与 retryable 信号（见 docs/设计/05 第 5 节）。"""

    code: ClassVar[str] = "invalid_argument"
    retryable: ClassVar[bool] = False

    def __init__(self, message: str = "", *, http_status: int | None = None) -> None:
        super().__init__(message or self.code)
        # 网关返回的原始状态码：只用于调用记录与页面上的测试结果，不参与 HTTP 映射。
        self.http_status = http_status


class AnchorFormatError(TenderError):
    """锚点字符串非法：格式不对、带前导零、序号为 0 等。"""


class BboxFormatError(TenderError):
    """bbox 结构非法（长度不是 4）。"""


class InvalidRotationError(TenderError):
    """``/Rotate`` 不是 0/90/180/270。"""


class AnchorSequenceError(TenderError):
    """锚点序号不是从 1 开始。"""


class ConversionFailed(TenderError):
    """Gotenberg 判定文件有问题或响应不是 PDF。"""

    code: ClassVar[str] = "conversion_failed"


class ConversionUnavailable(TenderError):
    """Gotenberg 侧暂时不可用。"""

    code: ClassVar[str] = "conversion_unavailable"
    retryable: ClassVar[bool] = True


class ParseFailed(TenderError):
    """MinerU 明确拒绝请求，或返回不符合 MiddleJson 契约的数据。"""

    code: ClassVar[str] = "parse_failed"


class ParseUnavailable(TenderError):
    """MinerU 的安全读取或上传操作暂时失败，可退避后重试。"""

    code: ClassVar[str] = "parse_unavailable"
    retryable: ClassVar[bool] = True


class ParseSubmissionUnknown(TenderError):
    """创建解析任务的响应丢失，远端受理状态未知，不能盲目重放。"""

    code: ClassVar[str] = "parse_submission_unknown"


class UploadSizeMismatch(ParseFailed):
    """MinerU 的 400 bytes_mismatch 与 413 upload_size_mismatch 统一归类。"""

    code: ClassVar[str] = "upload_size_mismatch"


class ServiceRestarted(TenderError):
    """MinerU 进程内索引失效；调用方应从文档版本读取 PDF key 与 SHA-256 后重提。"""

    code: ClassVar[str] = "service_restarted"
    retryable: ClassVar[bool] = True


class PriorityLimitExceeded(TenderError):
    """一个功能最多绑定 10 个模型（设计文档 12 第 3 节）。"""

    code: ClassVar[str] = "priority_limit_exceeded"


class ModelInUse(TenderError):
    """模型或供应商仍被功能绑定，删除会破坏调用链。"""

    code: ClassVar[str] = "model_in_use"


class ExtractionFailed(TenderError):
    """模型返回非法结构或明确拒绝请求。"""

    code: ClassVar[str] = "extraction_failed"


class ExtractionUnavailable(TenderError):
    """模型网关网络、限流或服务端故障，可由 worker 退避重试。"""

    code: ClassVar[str] = "extraction_unavailable"
    retryable: ClassVar[bool] = True
