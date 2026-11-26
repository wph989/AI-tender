"""所有 JSON API 成功响应都进入 Pydantic/OpenAPI 契约。"""

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from tender.api.app import app
from tender.api.knowledge import routes as knowledge
from tender.api.shared.errors import install_error_handlers
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


@pytest.mark.parametrize("status", ["pending", "failed", "completed"])
def test_answer_http_preserves_display_contract_and_excludes_execution_snapshot(
    monkeypatch, status,
):
    from types import SimpleNamespace

    source = {"source_id": 1, "collection_id": 1, "project_id": 1, "project_file_id": 1,
              "version_id": 1, "parse_run_id": 1, "element_id": 1, "anchor": "p1b1",
              "page_no": 1, "bbox": None, "file_name": "招标文件.pdf", "purpose": "tender",
              "quote": "甲级资质", "block_id": "s1r1c0"}
    payload = {
        "id": 1, "status": status, "question": "资质要求", "company_id": 7,
        "error_message": "模型不可用" if status == "failed" else None,
        "snapshot": {"sources": [source], "mode": "hybrid", "warning": "部分资料无语义索引",
                     "graph_used": True, "no_evidence": False, "retrieved_blocks": 40},
        "items": [{"id": "r", "field": "资格", "group": "资质", "sort_order": 0,
                   "note": "", "verification": "supported", "internal": "不属于展示契约",
                   "values": [{"value": "甲级资质", "citations": [source]}]}],
        "relations": [{"subject": "资格", "predicate": "requires", "object": "证明",
                       "scope": "公共要求", "condition": "", "citations": [source]}],
    }
    monkeypatch.setattr(knowledge, "knowledge_service", lambda request: SimpleNamespace(
        get_answer=lambda answer_id: payload,
    ))
    instance = FastAPI()
    instance.include_router(knowledge.router)
    install_error_handlers(instance)
    with TestClient(instance) as client:
        response = client.get("/api/v1/knowledge/answers/1")
    assert response.status_code == 200
    wire = response.json()
    assert wire["error_message"] == payload["error_message"]
    assert wire["snapshot"] == {
        "mode": "hybrid", "warning": "部分资料无语义索引", "graph_used": True,
        "no_evidence": False,
    }
    assert "company_id" not in wire and "internal" not in wire["items"][0]
    assert wire["items"][0]["values"][0]["citations"][0]["block_id"] == "s1r1c0"
    schemas = instance.openapi()["components"]["schemas"]
    assert {"snapshot", "error_message", "items", "relations"} <= (
        schemas["KnowledgeAnswerResponse"]["properties"].keys()
    )
    assert schemas["KnowledgeValueResponse"]["properties"]["citations"]["items"] == {
        "$ref": "#/components/schemas/AnalysisEvidenceResponse",
    }
