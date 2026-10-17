"""请求级日志入口，不读取请求体，也不要求业务端点逐个埋点。"""

from __future__ import annotations

import time
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tender.core.logging import bind_context, get_logger
from tender.core.logging.context import valid_identifier

logger = get_logger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = next(
            (value.decode("latin-1") for key, value in scope["headers"] if key == b"x-request-id"),
            None,
        )
        request_id = incoming if valid_identifier(incoming) else uuid4().hex
        scope.setdefault("state", {})["log_request_id"] = request_id
        started = time.perf_counter()
        status = 500
        outcome = "completed"

        async def send_response(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (key, value) for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                message = {
                    **message, "headers": [*headers, (b"x-request-id", request_id.encode("ascii"))]
                }
            await send(message)

        # 纯 ASGI 中间件保留流式响应与异步上下文，finally 覆盖断连和取消。
        with bind_context(request_id=request_id):
            try:
                await self.app(scope, receive, send_response)
            except BaseException:
                outcome = "interrupted"
                raise
            finally:
                route = getattr(scope.get("route"), "path", "<unmatched>")
                level = "error" if status >= 500 else "warning" if status >= 400 else "info"
                if route == "/api/v1/healthz" and status < 400:
                    level = "debug"
                getattr(logger, level)(
                    "http_request_finished",
                    method=scope["method"],
                    route=route,
                    status_code=status,
                    duration_ms=round((time.perf_counter() - started) * 1000, 3),
                    outcome=outcome,
                )
