"""基于 PostgreSQL 会话锁的任务互斥；进程退出后连接释放锁。"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine

from tender.adapters.pg.locks import acquire_lock, release_lock, try_acquire_lock


class TaskLocks:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def lock(self, key: str, *, wait: bool = False) -> Iterator[bool]:
        with self.engine.connect() as connection:
            if wait:
                acquire_lock(connection, key)
                acquired = True
            else:
                acquired = try_acquire_lock(connection, key)
            # 会话锁跨事务存活，先结束取锁事务，避免外部调用期间持有普通事务。
            connection.commit()
            try:
                yield acquired
            finally:
                if acquired:
                    release_lock(connection, key)
                    connection.commit()
