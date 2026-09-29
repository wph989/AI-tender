"""配置审计与影响清单确认（设计文档 08 第 6、7 节）。

审计写入只接受白名单里的 action：任何绕过 `write_audit` 的配置改动都意味着
"改了之后说不清"，所以发布路径的每个动作都必须先想清楚它对应哪个 action。
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import Connection, text

from tender.config.gate import ImpactItem

AUDIT_ACTIONS = frozenset({"create", "acknowledge", "activate", "rollback", "force_activate"})

_AUDIT_SQL = """
    INSERT INTO config_audit (release_id, actor, action, diff, reason)
    VALUES (:release_id, :actor, :action, CAST(:diff AS JSONB), :reason)
"""

_ACK_SQL = """
    INSERT INTO config_ack (release_id, item_kind, item_ref, actor, comment)
    VALUES (:release_id, :item_kind, :item_ref, :actor, :comment)
    ON CONFLICT (release_id, item_kind, item_ref) DO NOTHING
    RETURNING item_kind, item_ref
"""

_LOAD_ACKS_SQL = """
    SELECT item_kind, item_ref FROM config_ack WHERE release_id = :release_id
"""


def write_audit(
    connection: Connection,
    *,
    release_id: int,
    actor: str,
    action: str,
    diff: Mapping[str, Any],
    reason: str | None = None,
) -> None:
    if action not in AUDIT_ACTIONS:
        raise ValueError(f"未登记的审计动作：{action}")
    connection.execute(
        text(_AUDIT_SQL),
        {
            "release_id": release_id,
            "actor": actor,
            "action": action,
            "diff": json.dumps(dict(diff), ensure_ascii=False),
            "reason": reason,
        },
    )


def insert_acks(
    connection: Connection,
    *,
    release_id: int,
    actor: str,
    items: Iterable[ImpactItem],
    comment: str | None = None,
) -> list[tuple[str, str]]:
    """逐条确认；重复确认不报错（幂等），返回本次真正新插入的条目。"""
    inserted: list[tuple[str, str]] = []
    for entry in items:
        row = connection.execute(
            text(_ACK_SQL),
            {
                "release_id": release_id,
                "item_kind": entry.kind,
                "item_ref": entry.ref,
                "actor": actor,
                "comment": comment,
            },
        ).first()
        if row is not None:
            inserted.append((entry.kind, entry.ref))
    return inserted


def load_acks(connection: Connection, release_id: int) -> list[tuple[str, str]]:
    rows = connection.execute(text(_LOAD_ACKS_SQL), {"release_id": release_id}).all()
    return [(str(row[0]), str(row[1])) for row in rows]
