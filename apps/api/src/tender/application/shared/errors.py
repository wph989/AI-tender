"""服务层错误。

服务层不直接依赖 FastAPI，也不应该知道具体 HTTP 状态码，
因此用 ``kind`` 表达错误类别，由 ``api.errors`` 统一映射为 HTTP 响应。
"""

from __future__ import annotations

from typing import Any, ClassVar


class ServiceError(Exception):
    """业务用例可预期的失败；未知异常仍交给全局 500 处理。"""

    kind: ClassVar[str] = "invalid"
    code: ClassVar[str] = "invalid_argument"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool = False,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.retryable = retryable
        self.detail = detail


class InvalidArgument(ServiceError):
    """请求语义不合法，但格式本身已通过 DTO 校验。"""


class Forbidden(ServiceError):
    kind = "forbidden"
    code = "forbidden"


class NotFound(ServiceError):
    kind = "not_found"
    code = "not_found"


class Gone(ServiceError):
    """资源曾经存在但已失效，例如超过保留期的测试预览。"""

    kind = "gone"
    code = "gone"


class Conflict(ServiceError):
    kind = "conflict"
    code = "version_conflict"


class PreconditionFailed(ServiceError):
    kind = "precondition_failed"
    code = "version_conflict"


class Unprocessable(ServiceError):
    kind = "unprocessable"
    code = "invalid_argument"


class PayloadTooLarge(ServiceError):
    kind = "payload_too_large"
    code = "upload_too_large"


class Unavailable(ServiceError):
    kind = "unavailable"
    code = "service_unavailable"
