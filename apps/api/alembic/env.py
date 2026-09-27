"""Alembic 运行环境。

三个刻意的选择：

1. 连接串走 `tender.core.settings.database_url()`，不写进 alembic.ini —— 迁移脚本里内嵌地址，
   等于把「哪个库是生产」这件事藏在版本库里。取值优先级（环境变量 > .env > 默认值）
   和「改哪里」都写在 settings.py 里，这里不重复一遍。
2. `target_metadata = None`：本项目 DDL 的权威是设计文档，迁移用裸 SQL 表达（见 0001 迁移的说明），
   因此不支持 autogenerate。新增迁移用 `alembic revision -m "..."` 手写，
   文档与本目录的一致性由 tests/contract/test_ddl_matches_docs.py 负责盯住。
3. 不调用 logging.fileConfig：日志由应用侧统一配置（core/logging.py），迁移不该另起一套。

跑法：在 apps/api 目录下执行——alembic 只在当前目录找 alembic.ini。
（tender 已 editable 装进 .venv，不再依赖 `prepend_sys_path` 找包；那一行留着只是为了
让人不 sync 也能跑迁移。）
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from tender.core.settings import database_url

target_metadata = None


def run_migrations_offline() -> None:
    """离线模式（``alembic upgrade head --sql``）：只渲染 SQL，不连库。

    这条路径是 CI 里验证迁移的主要手段——没有数据库也能证明「迁移能被渲染成合法 SQL」。
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
