"""``ports/repository`` 的 PostgreSQL 实现（docs/工程/10-技术选型与工程结构.md）。

这个包是「业务库取数」这一可替换细节的唯一落点：上层按 ``ports/repository`` 里的
``Protocol`` 编程，装配点（``core.di``、API 路由、worker 任务）在这里取具体实现。
所以裸 SQL 只应该出现在这个包里，或者出现在 SQLAlchemy 无法表达的系统目录/锁函数上
（``information_schema``、``pg_locks``、``pg_advisory_*``）——那些也一律写明理由。

放这里而不是 ``application``：``application`` 与 ``adapters`` 必须互不引用，
否则换存储实现时要动用例层（``pyproject.toml`` 的 import-linter 契约）。
"""
