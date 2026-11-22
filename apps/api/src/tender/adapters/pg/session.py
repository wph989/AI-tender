"""集中创建业务和配额锁引擎，使连接参数在装配时保持一致。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

from tender.core import settings


def create_pg_engine(url: str | URL | None = None, **options: Any) -> Engine:
    """连接池取出连接前先探活，避免复用被网络设备断开的连接。"""
    options.setdefault("pool_pre_ping", True)
    return create_engine(url or settings.database_url(), **options)
