"""任务级配置快照（设计文档 08 第 4 节）。

`job_config_snapshot` 与 `job.config_snapshot` 不是一回事：后者是"这个任务要干什么"
（阶段参数），前者是"这个任务当时的配置世界是什么样"，用于回放与追责。
快照只写不改——写入侧只有这一处，读侧将来要查"为什么这条抽错了"就靠它。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import Connection, text

_INSERT_SQL = """
    INSERT INTO job_config_snapshot (release_id, resolved)
    VALUES (:release_id, CAST(:resolved AS JSONB))
    RETURNING id
"""


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
            text(_INSERT_SQL),
            {
                "release_id": release_id,
                "resolved": json.dumps(dict(resolved), ensure_ascii=False),
            },
        ).scalar_one()
    )
