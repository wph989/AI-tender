"""统一导出日志公共接口，让调用方不依赖内部文件划分。"""

from tender.core.logging.context import bind_context, clear_context, get_context
from tender.core.logging.setup import configure_logging, get_logger, shutdown_logging

__all__ = [
    "bind_context", "clear_context", "configure_logging", "get_context",
    "get_logger", "shutdown_logging",
]
