"""保存任务创建时的生效配置及发布来源，便于审计和复盘。

任务行保存执行参数，本快照保留完整配置来源；创建时与任务同事务写入。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection, insert

from tender.adapters.pg.models import JobConfigSnapshot


def save_snapshot(
    connection: Connection,
    *,
    release_id: int | None,
    resolved: Mapping[str, Any],
) -> int | None:
    """在创建任务的同一个事务里写快照，返回快照 ID；没有 active release 时返回 None。

    返回 None 而不是报错：迁移没跑或冷启动时任务仍要能创建，
    任务行上的 `config_snapshot_id` 为空本身就是"这次没有配置快照"的证据。
    """
    if release_id is None:
        return None
    return int(
        connection.execute(
            insert(JobConfigSnapshot)
            .values(release_id=release_id, resolved=dict(resolved))
            .returning(JobConfigSnapshot.id)
        ).scalar_one()
    )
