"""PostgreSQL advisory lock 的唯一入口。

``pg_advisory_lock`` 系列是系统函数，没有也不该有 ORM 映射，typed declarative 表达能力
不到这里（与 ``knowledge.py`` 顶部对 ``information_schema`` 的取舍相同）。把裸 SQL 收敛
到本模块，其它层只表达「我要这把锁」，不再各自拼 ``hashtextextended``。

两类键刻意分开：字符串键走 ``hashtextextended``（作业、抽取、冲突等业务名），
整数键走 ``pg_advisory_xact_lock(id)``（项目、集合等业务主键），两者哈希空间不同，
不会因为 id 恰好等于某个业务名的哈希而误撞。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

_HASHED = "hashtextextended(:lock_key, 0)"


def acquire_lock(connection: Any, key: str) -> None:
    """取会话级锁，拿不到就阻塞等待；连接断开时 PostgreSQL 自动释放。"""
    connection.execute(
        text(f"SELECT pg_advisory_lock({_HASHED})"), {"lock_key": key}
    )


def try_acquire_lock(connection: Any, key: str) -> bool:
    """尝试取会话级锁；已被占用时立刻返回 ``False``。"""
    return bool(
        connection.execute(
            text(f"SELECT pg_try_advisory_lock({_HASHED})"), {"lock_key": key}
        ).scalar_one()
    )


def release_lock(connection: Any, key: str) -> None:
    """释放会话级锁；必须与 ``try_acquire_lock`` 用同一个键。"""
    connection.execute(
        text(f"SELECT pg_advisory_unlock({_HASHED})"), {"lock_key": key}
    )


def acquire_xact_lock(connection: Any, key: str) -> None:
    """取事务级锁：并发点在同一事务里串行化，提交/回滚即释放。"""
    connection.execute(
        text(f"SELECT pg_advisory_xact_lock({_HASHED})"), {"lock_key": key}
    )


def try_acquire_xact_lock(connection: Any, key: str) -> bool:
    """尝试取事务级锁；用于「正在停止，请稍后再试」这类需要立刻给结论的判断。"""
    return bool(
        connection.execute(
            text(f"SELECT pg_try_advisory_xact_lock({_HASHED})"), {"lock_key": key}
        ).scalar_one()
    )


def acquire_xact_lock_id(connection: Any, key: int) -> None:
    """按整数键取事务级锁（项目、集合等业务主键）。"""
    connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": key})
