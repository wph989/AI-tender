"""所有 JSON API 成功响应都进入 Pydantic/OpenAPI 契约。"""

import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel, ValidationError

from tender.api.app import app
from tender.api.shared.responses import AnalysisModuleRecordResponse, AnalysisRecordResponse

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
    assert {"input_changed", "research_summary", "runs"} <= quality["properties"].keys()
    assert "research_gaps" not in quality["properties"]


@pytest.mark.parametrize("missing", ["content", "scope", "evidence_ids"])
def test_module_response_rejects_missing_content_and_evidence_identity(missing):
    record = {
        "id": "r", "key": "r", "kind": "requirement", "title": "质保要求",
        "text": "内容：质保三年", "content": {"内容": "质保三年"},
        "scope": {"kind": "common", "lot_refs": []}, "evidence_ids": ["proof"],
        "module_key": "project_basic_info_parsing", "group": "项目基本信息",
        "sort_order": 0, "structuring": "complete", "verification": "supported",
    }
    del record[missing]
    with pytest.raises(ValidationError) as caught:
        AnalysisModuleRecordResponse.model_validate(record)
    assert missing in {issue["loc"][0] for issue in caught.value.errors()}


def test_snapshot_response_requires_resolved_scope_and_its_own_citations():
    record = {
        "id": "r", "key": "r", "kind": "requirement", "title": "质保要求",
        "text": "内容：质保三年", "content": {"内容": "质保三年"},
        "scope": {"kind": "common", "lot_refs": []}, "evidence_ids": ["proof"],
        "module_key": "project_basic_info_parsing", "group": "项目基本信息",
        "sort_order": 0, "structuring": "complete", "verification": "supported",
    }
    with pytest.raises(ValidationError) as caught:
        AnalysisRecordResponse.model_validate(record)
    assert {issue["loc"] for issue in caught.value.errors()} >= {
        ("scope", "lot_ids"), ("citations",),
    }
