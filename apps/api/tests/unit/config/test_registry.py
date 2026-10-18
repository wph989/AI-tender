"""活动配置读取：缓存优先、refresh 写缓存并广播（设计文档 08 第 8 节）。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tender.config.registry import ActiveConfig, ConfigRegistry


class _ForbiddenEngine:
    """缓存命中时不该回源；一旦被调用说明读路径绕过缓存了。"""

    def connect(self) -> Any:
        raise AssertionError("缓存命中时不应回源数据库")


class _EmptyResult:
    def mappings(self) -> _EmptyResult:
        return self

    def first(self) -> None:
        return None


class _EmptyConnection:
    def __enter__(self) -> _EmptyConnection:
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def execute(self, *_: object, **__: object) -> _EmptyResult:
        return _EmptyResult()


class _EmptyEngine:
    """模拟"迁移还没跑"：任何查询都查不到行。"""

    def connect(self) -> _EmptyConnection:
        return _EmptyConnection()


class _FakeCache:
    def __init__(self, payload: Mapping[str, Any] | None = None) -> None:
        self.payload = payload
        self.published: list[int] = []
        self.closed = False

    def get_active(self, company_id: int) -> Mapping[str, Any] | None:
        return self.payload

    def set_active(self, company_id: int, payload: Mapping[str, Any]) -> None:
        self.payload = payload

    def publish_invalidate(self, company_id: int) -> None:
        self.published.append(company_id)

    def close(self) -> None:
        self.closed = True


def test_active_reads_from_cache_and_resolves_defaults() -> None:
    cache = _FakeCache({"release_id": 7, "version_no": 3, "values": {"convert.max_inflight": 6}})
    registry = ConfigRegistry(_ForbiddenEngine(), cache)  # type: ignore[arg-type]
    active = registry.active(1)
    assert active is not None
    assert active.release_id == 7
    assert active.resolved["convert.max_inflight"] == 6
    assert active.resolved["parse.max_inflight"] == 2


def test_missing_active_release_falls_back_to_defaults() -> None:
    registry = ConfigRegistry(_EmptyEngine(), _FakeCache())  # type: ignore[arg-type]
    assert registry.active(1) is None
    assert registry.resolved(1)["analysis.max_inflight"] == 2


def test_refresh_writes_cache_and_broadcasts() -> None:
    cache = _FakeCache()
    registry = ConfigRegistry(_ForbiddenEngine(), cache)  # type: ignore[arg-type]
    registry.refresh(
        1,
        ActiveConfig(
            release_id=9,
            version_no=4,
            values={"mineru.tier": "basic"},
            resolved={"mineru.tier": "basic"},
        ),
    )
    assert cache.payload == {
        "release_id": 9,
        "version_no": 4,
        "values": {"mineru.tier": "basic"},
    }
    assert cache.published == [1]


def test_snapshot_without_active_release_is_skipped() -> None:
    """迁移没跑时任务仍要能创建：宁可不写快照，也不写一个错的 release_id。"""
    registry = ConfigRegistry(_EmptyEngine(), _FakeCache())  # type: ignore[arg-type]
    assert registry.snapshot_for_job(None, company_id=1) is None  # type: ignore[arg-type]


def test_close_closes_cache() -> None:
    cache = _FakeCache()
    ConfigRegistry(_EmptyEngine(), cache).close()  # type: ignore[arg-type]
    assert cache.closed is True


def test_explicit_absent_config_does_not_read_again_inside_transaction(monkeypatch):
    from tender.config.registry import ConfigRegistry

    registry = ConfigRegistry(None)
    monkeypatch.setattr(
        registry, "active", lambda *_: (_ for _ in ()).throw(
            AssertionError("事务内不应回源读取更晚的配置")
        )
    )
    assert registry.snapshot_for_job(None, None) is None
