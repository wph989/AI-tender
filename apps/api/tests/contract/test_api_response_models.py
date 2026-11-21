"""所有 JSON API 成功响应都进入 Pydantic/OpenAPI 契约。"""

from fastapi.routing import APIRoute
from pydantic import BaseModel

from tender.api.app import app

BODYLESS_ROUTES = {
    ("DELETE", "/api/v1/projects/{project_id}"),
    ("DELETE", "/api/v1/projects/{project_id}/files/{file_id}"),
    ("GET", "/api/v1/projects/{project_id}/files/{file_id}/original"),
    ("GET", "/api/v1/versions/{version_id}/file"),
    ("GET", "/api/v1/versions/{version_id}/original"),
    ("GET", "/api/v1/jobs/{job_id}/events"),
    ("GET", "/api/v1/llm/tests/{test_id}/preview"),
}


def test_json_routes_declare_pydantic_response_models():
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1/"):
            continue
        if any((method, route.path) in BODYLESS_ROUTES for method in route.methods or ()):
            continue
        if route.status_code == 204:
            continue
        model = route.response_model
        if not isinstance(model, type) or not issubclass(model, BaseModel):
            missing.append(route.path)
    assert missing == []


def test_openapi_exposes_liveness_readiness_and_quality_contracts():
    schema = app.openapi()
    assert schema["paths"]["/api/v1/healthz"]["get"]["responses"]["200"]
    assert schema["paths"]["/api/v1/readyz"]["get"]["responses"]["503"]
    quality = schema["components"]["schemas"]["AnalysisModuleResponse"]
    statuses = quality["properties"]["quality_status"]["anyOf"][0]["enum"]
    assert "self_check_passed" in statuses
    progress = schema["components"]["schemas"]["AgentProgressResponse"]["properties"]
    assert set(progress) == {
        "protocol", "activity", "draft_count", "reviewed_count", "unresolved_issues",
    }
