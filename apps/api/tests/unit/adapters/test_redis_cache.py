"""Redis 配置缓存：序列化、TTL 与降级（设计文档 08 第 8 节）。"""

from __future__ import annotations

import json

from tender.adapters.redis_cache import INVALIDATE_CHANNEL, RedisConfigCache


class _FakeClient:
    def __init__(self) -> None:
        self.store: dict[str, object] = {}
        self.expirations: dict[str, int | None] = {}
        self.published: list[tuple[str, str]] = []
        self.closed = False
        self.fail = False

    def get(self, key: str) -> object:
        if self.fail:
            raise ConnectionError("redis down")
        return self.store.get(key)

    def set(self, key: str, value: object, *, ex: int | None = None) -> None:
        if self.fail:
            raise ConnectionError("redis down")
        self.store[key] = value
        self.expirations[key] = ex

    def publish(self, channel: str, message: str) -> None:
        if self.fail:
            raise ConnectionError("redis down")
        self.published.append((channel, message))

    def close(self) -> None:
        self.closed = True


def test_set_and_get_round_trip() -> None:
    client = _FakeClient()
    cache = RedisConfigCache("redis://unused", client=client)
    cache.set_active(1, {"release_id": 7, "version_no": 3, "values": {"mineru.tier": "basic"}})
    assert cache.get_active(1) == {
        "release_id": 7,
        "version_no": 3,
        "values": {"mineru.tier": "basic"},
    }
    assert client.expirations["config:active:1"] == 60
    assert json.loads(client.store["config:active:1"])["release_id"] == 7


def test_cache_is_partitioned_by_company() -> None:
    client = _FakeClient()
    cache = RedisConfigCache("redis://unused", client=client)
    cache.set_active(1, {"release_id": 1, "version_no": 1, "values": {}})
    assert cache.get_active(2) is None


def test_publish_invalidate_carries_company_id() -> None:
    client = _FakeClient()
    cache = RedisConfigCache("redis://unused", client=client)
    cache.publish_invalidate(9)
    assert client.published == [(INVALIDATE_CHANNEL, "9")]


def test_broken_cache_degrades_instead_of_raising() -> None:
    """Redis 抖动只该让配置多回源几次数据库，不能把读配置变成 500。"""
    client = _FakeClient()
    cache = RedisConfigCache("redis://unused", client=client)
    client.fail = True
    assert cache.get_active(1) is None
    cache.set_active(1, {"release_id": 1, "version_no": 1, "values": {}})
    cache.publish_invalidate(1)
    cache.close()
    assert client.closed is True


def test_invalid_json_is_treated_as_miss() -> None:
    client = _FakeClient()
    cache = RedisConfigCache("redis://unused", client=client)
    client.store["config:active:1"] = b"not-json"
    assert cache.get_active(1) is None


def test_custom_ttl_is_honored() -> None:
    client = _FakeClient()
    cache = RedisConfigCache("redis://unused", client=client, ttl_seconds=15)
    cache.set_active(1, {"release_id": 1, "version_no": 1, "values": {}})
    assert client.expirations["config:active:1"] == 15
