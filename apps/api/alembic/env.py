"""当前空库基线的执行环境，连接地址由应用设置统一读取。

物理结构由 SQL 基线表达；ORM 映射和文档表清单由契约测试核对，
因此不启用 autogenerate。日志沿用应用配置，避免初始化时另起一套。
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from tender.core.settings import database_url

target_metadata = None


def run_migrations_offline() -> None:
    """离线模式（``alembic upgrade head --sql``）：只渲染 SQL，不连库。

    离线渲染检查命令生成，SQL、事务和约束还须通过 PostgreSQL 集成验证。
    """
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
