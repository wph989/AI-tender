"""配置审计与影响清单确认（设计文档 08 第 6、7 节）。

审计写入只接受白名单里的 action：任何绕过 `write_audit` 的配置改动都意味着
"改了之后说不清"，所以发布路径的每个动作都必须先想清楚它对应哪个 action。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import Connection, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tender.adapters.pg.models import ConfigAck, ConfigAudit
from tender.config.gate import ImpactItem

AUDIT_ACTIONS = frozenset({"create", "acknowledge", "activate", "rollback", "force_activate"})


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
        insert(ConfigAudit).values(
            release_id=release_id,
            actor=actor,
            action=action,
            diff=dict(diff),
            reason=reason,
        )
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
            pg_insert(ConfigAck)
            .values(
                release_id=release_id,
                item_kind=entry.kind,
                item_ref=entry.ref,
                actor=actor,
                comment=comment,
            )
            .on_conflict_do_nothing(index_elements=["release_id", "item_kind", "item_ref"])
            .returning(ConfigAck.item_kind, ConfigAck.item_ref)
        ).first()
        if row is not None:
            inserted.append((entry.kind, entry.ref))
    return inserted


def load_acks(connection: Connection, release_id: int) -> list[tuple[str, str]]:
    rows = connection.execute(
        select(ConfigAck.item_kind, ConfigAck.item_ref).where(ConfigAck.release_id == release_id)
    ).all()
    return [(str(row[0]), str(row[1])) for row in rows]
