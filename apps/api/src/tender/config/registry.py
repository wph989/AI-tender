"""活动配置读取：Redis 缓存 → 数据库回源 → 解析成完整值（设计文档 08 第 8 节）。

读取路径刻意做成两个方法：`active()` 给"现在生效的配置"，`refresh()` 给发布路径
在激活/回滚后立刻写缓存并广播失效。写入一律先落库再调 refresh——缓存里出现数据库没有的值
比缓存过期难查得多。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, Engine, text

from tender.config import schema
from tender.config.snapshot import save_snapshot
from tender.core import settings
from tender.ports.config_cache import ConfigCache

_ACTIVE_SQL = """
    SELECT id, version_no, values
    FROM config_release
    WHERE company_id = :company_id AND status = 'active'
    ORDER BY id DESC
    LIMIT 1
"""


@dataclass(frozen=True, slots=True)
class ActiveConfig:
    release_id: int
    version_no: int
    values: Mapping[str, Any]
    resolved: Mapping[str, Any]

    def cache_payload(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "version_no": self.version_no,
            "values": dict(self.values),
        }


def _payload_to_active(payload: Mapping[str, Any]) -> ActiveConfig:
    values = dict(payload.get("values") or {})
    return ActiveConfig(
        release_id=int(payload["release_id"]),
        version_no=int(payload.get("version_no") or 0),
        values=values,
        resolved=schema.resolve_values(values),
    )


class ConfigRegistry:
    def __init__(self, engine: Engine, cache: ConfigCache | None = None) -> None:
        self._engine = engine
        self._cache = cache

    def active(self, company_id: int | None = None) -> ActiveConfig | None:
        cid = settings.company_id() if company_id is None else company_id
        if self._cache is not None:
            cached = self._cache.get_active(cid)
            if cached is not None:
                return _payload_to_active(cached)
        payload = self._load(cid)
        if payload is None:
            return None
        if self._cache is not None:
            self._cache.set_active(cid, payload)
        return _payload_to_active(payload)

    def resolved(self, company_id: int | None = None) -> Mapping[str, Any]:
        """读完整配置值；没有 active release（迁移还没跑）时退回代码默认值。"""
        active = self.active(company_id)
        return active.resolved if active is not None else schema.default_values()

    def refresh(self, company_id: int, active: ActiveConfig) -> None:
        """发布路径专用：写缓存 + 广播失效，让各进程 5 秒内看到新配置。"""
        if self._cache is None:
            return
        self._cache.set_active(company_id, active.cache_payload())
        self._cache.publish_invalidate(company_id)

    def snapshot_for_job(
        self,
        connection: Connection,
        active: ActiveConfig | None = None,
        *,
        company_id: int | None = None,
    ) -> int | None:
        """在创建任务的同一个事务里写配置快照，返回快照 ID。

        调用方先 `active(...)` 再开事务，避免事务里等 Redis；没有 active release
        （迁移还没跑）时返回 None，任务行上的 config_snapshot_id 为空就是证据。
        """
        target = active if active is not None else self.active(company_id)
        if target is None:
            return None
        return save_snapshot(
            connection,
            release_id=target.release_id,
            resolved=target.resolved,
        )

    def close(self) -> None:
        if self._cache is not None:
            self._cache.close()

    def _load(self, company_id: int) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(text(_ACTIVE_SQL), {"company_id": company_id}).mappings().first()
            )
        if row is None:
            return None
        return {
            "release_id": int(row["id"]),
            "version_no": int(row["version_no"]),
            "values": dict(row["values"] or {}),
        }
