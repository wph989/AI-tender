"""checkpoint DDL 只由部署命令初始化，worker 无隐式建表路径。"""

import asyncio
import sys

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.conninfo import make_conninfo
from sqlalchemy.engine import make_url

from tender.core import settings


def checkpoint_dsn() -> str:
    url = make_url(settings.database_url())
    return make_conninfo(
        host=url.host,
        port=url.port or 5432,
        dbname=url.database,
        user=url.username,
        password=url.password,
        options="-c search_path=agent_runtime",
        connect_timeout=10,
    )


async def setup_checkpoints() -> None:
    async with AsyncPostgresSaver.from_conn_string(checkpoint_dsn()) as saver:
        # setup 含 CREATE INDEX CONCURRENTLY，需要 autocommit；独立命令避免破坏 Alembic 事务。
        await saver.conn.execute("SELECT pg_advisory_lock(16843008, 0)")
        try:
            await saver.setup()
        finally:
            await saver.conn.execute("SELECT pg_advisory_unlock(16843008, 0)")


def run_async(coroutine):
    # Windows 默认 Proactor 不支持 psycopg；只调整此任务的 loop，不改变全进程策略。
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    return asyncio.run(coroutine, loop_factory=factory)


if __name__ == "__main__":
    run_async(setup_checkpoints())
