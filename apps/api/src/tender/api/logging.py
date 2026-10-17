"""请求级日志入口，不读取请求体，也不要求业务端点逐个埋点。"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from threading import Lock
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tender.core.logging import bind_context, get_logger
from tender.core.logging.context import valid_identifier

logger = get_logger(__name__)
_ACCESS_LOG_INTERVAL_ATTR = "_tender_access_log_interval"


def throttle_access_log[Endpoint: Callable[..., object]](
    interval_seconds: int = 60,
) -> Callable[[Endpoint], Endpoint]:
    """仅为选中的接口标记访问日志窗口；0 关闭，不影响接口执行和业务日志。"""
    if interval_seconds < 0:
        raise ValueError("访问日志窗口不能小于 0 秒")

    def decorate(endpoint: Endpoint) -> Endpoint:
        # 返回原函数，避免包装器破坏 FastAPI 参数解析、异步识别或同步线程池调度。
        setattr(endpoint, _ACCESS_LOG_INTERVAL_ATTR, interval_seconds)
        return endpoint

    return decorate


class _AccessLogWindow:
    def __init__(self, interval_seconds: int):
        self.interval = interval_seconds
        self._recent: OrderedDict[tuple[str, str, int], tuple[float, int]] = OrderedDict()
        self._lock = Lock()

    def sample(self, key: tuple[str, str, int]) -> int | None:
        """首条立即记录；窗口从输出时算起，重复请求不能让持续轮询永远静默。"""
        with self._lock:
            now = time.monotonic()
            previous = self._recent.get(key)
            # 按上次输出时间清理过期分组；提前淘汰有效分组会让同一窗口重复输出。
            # 被压缩的请求不改变顺序，因此只需检查队首，不必每次扫描全部路径。
            while self._recent:
                emitted_at, _ = next(iter(self._recent.values()))
                if now - emitted_at < self.interval:
                    break
                self._recent.popitem(last=False)
            if previous is not None and now - previous[0] < self.interval:
                self._recent[key] = (previous[0], previous[1] + 1)
                return None
            self._recent[key] = (now, 0)
            return previous[1] if previous is not None else 0


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        # 不同装饰器窗口各自清理缓存，短窗口不能提前清掉长窗口的有效分组。
        self._windows: dict[int, _AccessLogWindow] = {}

    def _sample(self, scope: Scope, status: int) -> int | None:
        interval = getattr(scope.get("endpoint"), _ACCESS_LOG_INTERVAL_ATTR, 0)
        if interval <= 0:
            return 0
        window = self._windows.get(interval)
        if window is None:
            window = self._windows.setdefault(interval, _AccessLogWindow(interval))
        return window.sample((scope["method"], scope["path"], status))

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
                # 已发出 200 响应头也可能断流或取消，不能按成功（尤其健康检查）降级。
                failed = status >= 500 or outcome != "completed"
                level = "error" if failed else "warning" if status >= 400 else "info"
                if route == "/api/v1/healthz" and status < 400 and not failed:
                    level = "debug"
                # 仅装饰器选中的接口压缩正常访问摘要；异常、断流与 4xx/5xx 始终保留。
                # 路径只用于进程内区分资源，不写入日志；查询参数不参与分组以压住轮询。
                suppressed = 0 if status >= 400 or outcome != "completed" else self._sample(
                    scope, status,
                )
                if suppressed is not None:
                    getattr(logger, level)(
                        "http_request_finished",
                        method=scope["method"],
                        route=route,
                        status_code=status,
                        duration_ms=round((time.perf_counter() - started) * 1000, 3),
                        outcome=outcome,
                        suppressed_count=suppressed,
                    )
