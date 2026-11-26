"""真实同步、异步和SSE建流入口统一映射业务错误，路由无需再包装异常。"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tender.api.jobs import routes as jobs
from tender.api.knowledge import routes as knowledge
from tender.api.projects import routes as projects
from tender.api.shared.errors import install_error_handlers
from tender.application.shared import errors


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("kind,status", [
    ("InvalidArgument", 400), ("Forbidden", 403), ("NotFound", 404), ("Conflict", 409),
    ("Gone", 410), ("PreconditionFailed", 412), ("PayloadTooLarge", 413),
    ("Unprocessable", 422), ("Unavailable", 503),
])
def test_service_errors_use_one_http_mapping(monkeypatch, asynchronous, kind, status):
    failure = getattr(errors, kind)(
        "业务失败", code="fixture_error", retryable=True, detail={"field": "name"},
    )

    def fail(*args, **kwargs):
        raise failure

    async def async_fail(*args, **kwargs):
        raise failure

    app = FastAPI()
    install_error_handlers(app)
    if asynchronous:
        monkeypatch.setattr(knowledge, "knowledge_service", lambda request: SimpleNamespace(
            search_collection=async_fail,
        ))
        app.include_router(knowledge.router)
    else:
        monkeypatch.setattr(projects, "_service", lambda request: SimpleNamespace(create=fail))
        app.include_router(projects.router)
    with TestClient(app) as client:
        response = (client.get("/api/v1/knowledge/collections/1/search?q=资质")
                    if asynchronous else client.post("/api/v1/projects", json={"name": "项目"}))
    assert response.status_code == status
    assert response.json()["error"] == {
        "code": "fixture_error", "message": "业务失败", "retryable": True,
        "detail": {"field": "name"},
    }


@pytest.mark.parametrize("suffix", ["", "/events"])
def test_job_query_and_sse_authorize_before_stream(monkeypatch, suffix):
    def payload(job_id):
        raise errors.NotFound("任务不存在")

    monkeypatch.setattr(jobs, "_service", lambda request: SimpleNamespace(payload=payload))
    app = FastAPI()
    app.include_router(jobs.router)
    install_error_handlers(app)
    with TestClient(app) as client:
        response = client.get("/api/v1/jobs/missing" + suffix)
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
