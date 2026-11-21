"""进程存活不依赖就绪依赖；readyz 单独报告数据库、Redis 与存储状态。"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from tender.api.app import create_app


class _Runtime:
    def __init__(self, *, postgres: bool, redis: bool, storage: bool) -> None:
        self.postgres = postgres
        self.configs = SimpleNamespace(health=lambda: redis)
        self.blobs = SimpleNamespace(health=lambda: storage)

    def postgres_healthy(self):
        if not self.postgres:
            raise ConnectionError("postgresql unavailable")
        return True

    async def aclose(self) -> None:
        return None


def test_liveness_remains_ok_when_readiness_dependencies_are_down() -> None:
    app = create_app(_Runtime(postgres=False, redis=False, storage=True))

    with TestClient(app) as client:
        live = client.get("/api/v1/healthz")
        ready = client.get("/api/v1/readyz")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 503
    assert ready.json() == {
        "status": "not_ready",
        "checks": {"postgresql": False, "redis": False, "storage": True},
    }


def test_readiness_checks_only_infrastructure_dependencies() -> None:
    app = create_app(_Runtime(postgres=True, redis=True, storage=True))

    with TestClient(app) as client:
        ready = client.get("/api/v1/readyz")

    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "checks": {"postgresql": True, "redis": True, "storage": True},
    }
