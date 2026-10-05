"""HTTP 错误响应映射；领域层和适配器不认识状态码。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from tender.core.secrets import SecretKeyUnavailable
from tender.domain.errors import (
    ConversionFailed,
    ConversionUnavailable,
    ExtractionFailed,
    ExtractionUnavailable,
    ModelInUse,
    ParseFailed,
    ParseSubmissionUnknown,
    ParseUnavailable,
    ServiceRestarted,
    TenderError,
)
from tender.ports.blob_store import BlobNotFound, BlobStoreError

logger = logging.getLogger(__name__)


class ApiProblem(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        detail: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.detail = detail


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiProblem)
    async def api_problem_handler(_: Request, exc: ApiProblem) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.retryable, exc.detail)

    @app.exception_handler(TenderError)
    async def tender_error_handler(_: Request, exc: TenderError) -> JSONResponse:
        if isinstance(exc, (ConversionFailed, ExtractionFailed, ParseFailed)):
            status = 422
        elif isinstance(exc, (ServiceRestarted, ModelInUse)):
            status = 409
        elif isinstance(
            exc,
            (
                ConversionUnavailable,
                ExtractionUnavailable,
                ParseUnavailable,
                ParseSubmissionUnknown,
            ),
        ):
            status = 503
        else:
            status = 400
        return error_response(status, exc.code, str(exc), exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            400,
            "invalid_argument",
            "请求参数格式错误",
            # Pydantic 的 input/ctx 可能包含整份供应商请求和密钥，错误回包只保留定位信息。
            detail={
                "errors": [
                    {"loc": error["loc"], "type": error["type"], "msg": error["msg"]}
                    for error in exc.errors()
                ]
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = exc.status_code
        code = "not_found" if status == 404 else "invalid_argument"
        message = "资源不存在" if status == 404 else str(exc.detail)
        return error_response(status, code, message)

    @app.exception_handler(IntegrityError)
    async def integrity_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.info("数据库约束冲突", exc_info=exc)
        return error_response(409, "version_conflict", "数据已被并发修改")

    @app.exception_handler(SecretKeyUnavailable)
    async def secret_key_handler(_: Request, exc: SecretKeyUnavailable) -> JSONResponse:
        # 未配置主密钥或密文解不开：这是部署问题，不是请求问题，也不能重试。
        return error_response(503, "secret_key_unavailable", str(exc))

    @app.exception_handler(BlobNotFound)
    async def blob_not_found_handler(_: Request, __: BlobNotFound) -> JSONResponse:
        return error_response(404, "not_found", "文件不存在")

    @app.exception_handler(BlobStoreError)
    async def blob_error_handler(_: Request, exc: BlobStoreError) -> JSONResponse:
        logger.warning("对象存储暂时不可用：%s", exc)
        return error_response(503, "storage_unavailable", "对象存储暂时不可用", True)

    @app.exception_handler(Exception)
    async def unexpected_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("API 未处理异常", exc_info=exc)
        return error_response(500, "internal_error", "服务暂时无法处理请求")


def error_response(
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
    detail: dict[str, Any] | None = None,
) -> JSONResponse:
    error: dict[str, object] = {
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    if detail is not None:
        error["detail"] = detail
    return JSONResponse(status_code=status_code, content={"error": error})
