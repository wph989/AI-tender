"""配置版本、审计与影响确认的数据库访问。

这里只负责 SQL、锁和事务边界；某个状态是否可激活、影响项是否合法等规则
由服务层判断，避免数据库层在查询后偷偷改变业务含义。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, Engine, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tender.adapters.pg.locks import acquire_xact_lock
from tender.adapters.pg.models import ConfigAck, ConfigAudit, ConfigRelease


class ConfigTransaction:
    def __init__(self, connection: Connection, company_id: int) -> None:
        self.connection = connection
        self.company_id = company_id

    def lock_company(self) -> None:
        acquire_xact_lock(self.connection, f"config-release:{self.company_id}")

    def release(self, release_id: int) -> dict[str, Any] | None:
        row = (
            self.connection.execute(
                select(ConfigRelease).where(
                    ConfigRelease.id == release_id,
                    ConfigRelease.company_id == self.company_id,
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def active_release(self) -> dict[str, Any] | None:
        row = (
            self.connection.execute(
                select(ConfigRelease)
                .where(
                    ConfigRelease.company_id == self.company_id,
                    ConfigRelease.status == "active",
                )
                .order_by(ConfigRelease.id.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def next_version_no(self) -> int:
        return int(
            self.connection.execute(
                select(func.coalesce(func.max(ConfigRelease.version_no), 0) + 1).where(
                    ConfigRelease.company_id == self.company_id
                )
            ).scalar_one()
        )

    def archive_active(self) -> None:
        self.connection.execute(
            update(ConfigRelease)
            .where(
                ConfigRelease.company_id == self.company_id,
                ConfigRelease.status == "active",
            )
            .values(status="archived")
        )

    def insert_release(self, values: Mapping[str, Any]) -> int:
        return int(
            self.connection.execute(
                insert(ConfigRelease).values(**dict(values)).returning(ConfigRelease.id)
            ).scalar_one()
        )

    def set_release_status(self, release_id: int, status: str) -> None:
        self.connection.execute(
            update(ConfigRelease).where(ConfigRelease.id == release_id).values(status=status)
        )

    def write_audit(
        self,
        *,
        release_id: int,
        actor: str,
        action: str,
        diff: Mapping[str, Any],
        reason: str | None,
    ) -> None:
        self.connection.execute(
            insert(ConfigAudit).values(
                release_id=release_id,
                actor=actor,
                action=action,
                diff=dict(diff),
                reason=reason,
            )
        )

    def insert_acks(
        self,
        *,
        release_id: int,
        actor: str,
        items: Iterable[Any],
        comment: str | None,
    ) -> list[tuple[str, str]]:
        inserted: list[tuple[str, str]] = []
        for entry in items:
            row = self.connection.execute(
                pg_insert(ConfigAck)
                .values(
                    release_id=release_id,
                    item_kind=entry.kind,
                    item_ref=entry.ref,
                    actor=actor,
                    comment=comment,
                )
                .on_conflict_do_nothing(
                    index_elements=["release_id", "item_kind", "item_ref"]
                )
                .returning(ConfigAck.item_kind, ConfigAck.item_ref)
            ).first()
            if row is not None:
                inserted.append((entry.kind, entry.ref))
        return inserted

    def load_acks(self, release_id: int) -> list[tuple[str, str]]:
        rows = self.connection.execute(
            select(ConfigAck.item_kind, ConfigAck.item_ref).where(
                ConfigAck.release_id == release_id
            )
        ).all()
        return [(str(row[0]), str(row[1])) for row in rows]

    def audit_rows(self, release_id: int, limit: int) -> list[dict[str, Any]]:
        statement = (
            select(
                ConfigAudit.id,
                ConfigAudit.release_id,
                ConfigAudit.actor,
                ConfigAudit.action,
                ConfigAudit.diff,
                ConfigAudit.reason,
                ConfigAudit.created_at,
                ConfigRelease.version_no,
            )
            .select_from(ConfigAudit)
            .join(ConfigRelease, ConfigRelease.id == ConfigAudit.release_id)
            .where(
                ConfigRelease.company_id == self.company_id,
                ConfigAudit.release_id == release_id,
            )
        )
        rows = self.connection.execute(
            statement.order_by(ConfigAudit.id.desc()).limit(limit)
        ).mappings().all()
        return [dict(row) for row in rows]


class ConfigRepository:
    def __init__(self, engine: Engine, company_id: int) -> None:
        self.engine = engine
        self.company_id = company_id

    @contextmanager
    def transaction(self) -> Iterator[ConfigTransaction]:
        with self.engine.begin() as connection:
            yield ConfigTransaction(connection, self.company_id)

    def release(self, release_id: int) -> dict[str, Any] | None:
        with self.transaction() as transaction:
            return transaction.release(release_id)

    def active_release(self) -> dict[str, Any] | None:
        with self.transaction() as transaction:
            return transaction.active_release()

    def list_releases(self, status: str | None, limit: int) -> list[dict[str, Any]]:
        statement = select(
            ConfigRelease.id,
            ConfigRelease.version_no,
            ConfigRelease.status,
            ConfigRelease.note,
            ConfigRelease.created_by,
            ConfigRelease.created_at,
            ConfigRelease.based_on,
        ).where(ConfigRelease.company_id == self.company_id)
        if status:
            statement = statement.where(ConfigRelease.status == status)
        with self.engine.connect() as connection:
            rows = connection.execute(
                statement.order_by(ConfigRelease.version_no.desc()).limit(limit)
            ).mappings().all()
        return [dict(row) for row in rows]

    def audit_rows(self, release_id: int | None, limit: int) -> list[dict[str, Any]]:
        statement = (
            select(
                ConfigAudit.id,
                ConfigAudit.release_id,
                ConfigAudit.actor,
                ConfigAudit.action,
                ConfigAudit.diff,
                ConfigAudit.reason,
                ConfigAudit.created_at,
                ConfigRelease.version_no,
            )
            .select_from(ConfigAudit)
            .join(ConfigRelease, ConfigRelease.id == ConfigAudit.release_id)
            .where(ConfigRelease.company_id == self.company_id)
        )
        if release_id is not None:
            statement = statement.where(ConfigAudit.release_id == release_id)
        with self.engine.connect() as connection:
            rows = connection.execute(
                statement.order_by(ConfigAudit.id.desc()).limit(limit)
            ).mappings().all()
        return [dict(row) for row in rows]
