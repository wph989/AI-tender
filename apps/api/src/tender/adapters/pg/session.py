"""业务库引擎与会话工厂（docs/工程/10 第 4.2 节的 adapters/pg/session.py）。

历史代码在 api 装配点与多个 worker 模块各自 create_engine（同库、同参数），
迁往 ORM 时先收口到这一个入口：create_engine 不会发起连接，启动路径用它没有额外开销。

配额锁引擎（agent_runtime 的 NullPool 长事务持锁）是参数化例外，同样走这个入口传参；
application 层不能 import adapters（import-linter 契约），那里的替换要在装配点传入。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker

from tender.core import settings


def create_pg_engine(url: str | URL | None = None, **options: Any) -> Engine:
    """创建业务库引擎：全项目唯一的引擎构造入口。

    默认 pool_pre_ping=True：连接被网络设备静默掐断后，取下一条连接先探活
    （2026-10-12 连接池死连接导致 worker 反复 ConnectionError 的教训，见 HANDOOFF）。
    显式传 pool_pre_ping=False 可以关掉；传 poolclass=NullPool 时它无实际作用。
    """
    options.setdefault("pool_pre_ping", True)
    return create_engine(url or settings.database_url(), **options)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """绑定引擎的会话工厂；expire_on_commit=False，提交后对象仍可读（worker 常用模式）。"""
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def pg_session(factory: sessionmaker[Session]) -> Iterator[Session]:
    """短生命周期会话：正常提交、异常回滚、最后必然关闭。"""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
