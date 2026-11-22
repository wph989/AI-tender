"""HTTP 成功响应的线格式模型；额外字段暂时透传，稳定字段由 OpenAPI 明确约束。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class IdStatusResponse(ApiResponse):
    id: int | str | None = None
    status: str | None = None
    job_id: str | None = None
    test_id: int | None = None


class ItemsResponse(ApiResponse):
    items: list[Any]


class ProjectResponse(ApiResponse):
    id: int
    company_id: int
    name: str
    project_no: str | None
    owner: str | None
    status: str
    created_at: datetime
    file_count: int | None = None
    failed_count: int | None = None
    last_activity_at: datetime | None = None


class ProjectListResponse(ApiResponse):
    items: list[ProjectResponse]
    offset: int
    limit: int


class ProjectFileResponse(ApiResponse):
    project_file_id: int
    project_id: int
    version_id: int | None
    role: str
    display_name: str
    is_parseable: bool
    sort_no: int
    sha256: str
    mime: str | None
    size_bytes: int


class ProjectDetailFileResponse(ProjectFileResponse):
    replaces_id: int | None = None
    created_at: datetime
    page_count: int | None = None
    parse_status: str | None = None
    parse_tier: str | None = None
    parse_ocr_mode: str | None = None
    latest_run_id: int | None = None
    replaced_by_id: int | None = None
    latest_job: dict[str, Any] | None = None


class ProjectLotResponse(ApiResponse):
    id: int
    code: str | None
    name: str
    sort_no: int


class UploadedFileResponse(ApiResponse):
    project_file_id: int
    display_name: str
    role: str
    is_parseable: bool
    version_id: int | None
    job_id: str | None


class ProjectDetailResponse(ProjectResponse):
    files: list[ProjectDetailFileResponse]
    lots: list[ProjectLotResponse]


class UploadResponse(ApiResponse):
    added: list[UploadedFileResponse]
    jobs: list[str]
    skipped: list[dict[str, str]]


class ReplaceFileResponse(ApiResponse):
    added: UploadedFileResponse
    jobs: list[str]


class JobResponse(ApiResponse):
    id: str
    status: str
    stage: str | None = None
    progress: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    version_id: int | None = None
    run_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    finished_at: datetime | None = None


class JobCreatedResponse(ApiResponse):
    job_id: str
    status: str


class ParseJobCreatedResponse(JobCreatedResponse):
    version_id: int
    run_id: int | None
    force: bool


class PageMetadata(ApiResponse):
    page_no: int
    width_pt: float
    height_pt: float
    rotation: int
    has_text_layer: bool


class PagesResponse(ApiResponse):
    total: int
    page_count: int
    pages: list[PageMetadata]


class ElementResponse(ApiResponse):
    id: int | None = None
    parent_id: int | None = None
    anchor: str
    type: str
    level: int | None = None
    page_no: int
    order_no: int
    bbox: list[float] | None
    text: str
    source: str
    continues_prev: bool


class ElementsResponse(ApiResponse):
    run_id: int | None = None
    elements: list[ElementResponse]
    page_no: int | None = None


class AnchorResponse(ApiResponse):
    anchor: str
    run_id: int | None
    page_no: int
    bbox: list[float] | None
    text: str
    type: str


class AnchorsResponse(ApiResponse):
    run_id: int | None
    items: list[AnchorResponse]
    missing: list[str]


class VersionResponse(ApiResponse):
    id: int
    document_id: int
    project_id: int
    version_no: int
    title: str
    sha256: str
    pdf_sha256: str | None
    mime: str | None
    size_bytes: int
    is_converted: bool
    converter: str | None
    converter_version: str | None
    page_count: int | None
    created_at: datetime
    parse_runs: list[dict[str, Any]]


class OutlineResponse(ApiResponse):
    run_id: int | None
    items: list[dict[str, Any]]


class KnowledgeSourceResponse(ApiResponse):
    source_id: int
    collection_id: int
    project_id: int
    project_file_id: int
    file_name: str
    version_id: int | None
    parse_run_id: int | None
    state: str
    purpose: str
    index_status: str | None
    index_error: str | None
    error_message: str | None
    semantic_ready: bool | None = None
    needs_reindex: bool | None = None
    embedding_model_id: int | None = None


class CollectionResponse(ApiResponse):
    id: int
    name: str
    purpose: str
    upload_project_id: int | None = None
    is_project: bool | None = None
    file_count: int | None = None
    sources: list[KnowledgeSourceResponse] | None = None
    embedding_configured: bool | None = None
    embedding_model: str | None = None


class KnowledgeCollectionListResponse(ApiResponse):
    items: list[CollectionResponse]


class KnowledgeSourcesResponse(ApiResponse):
    collection_id: int
    linked_collection_ids: list[int]
    sources: list[KnowledgeSourceResponse]


class KnowledgeSearchResponse(ApiResponse):
    items: list[dict[str, Any]]
    warning: str | None = None


class KnowledgeAnswerResponse(ApiResponse):
    id: int
    status: str
    question: str
    items: list[dict[str, Any]]
    relations: list[dict[str, Any]]


class CitationResolutionResponse(ApiResponse):
    source_id: int
    collection_id: int
    project_id: int
    project_file_id: int
    version_id: int
    parse_run_id: int
    element_id: int
    anchor: str
    page_no: int
    bbox: list[float] | None
    file_name: str
    quote: str | None = None
    content: str | None = None


class LlmEntityResponse(ApiResponse):
    id: int | None = None
    status: str | None = None
    key: str | None = None
    name: str | None = None
    model_id: str | None = None


class CapabilityTestResponse(ApiResponse):
    id: int
    model_id: int | None = None
    capability: str
    status: str
    validity: str
    latency_ms: int | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    result: dict[str, Any]


class ConfigItemsResponse(ApiResponse):
    role: str
    items: list[dict[str, Any]]
    active: dict[str, int] | None


class ConfigReleaseListResponse(ApiResponse):
    items: list[dict[str, Any]]


class ConfigReleaseResponse(ApiResponse):
    id: int
    version_no: int | None = None
    status: str | None = None
    changed: dict[str, Any] = Field(default_factory=dict)
    gated: list[str] = Field(default_factory=list)
    overrides: dict[str, Any] | None = None
    values: dict[str, Any] | None = None
    impact: list[dict[str, Any]] | None = None
    gate: dict[str, Any] | None = None
    audit: list[dict[str, Any]] | None = None


class ConfigAcknowledgeResponse(ApiResponse):
    id: int
    acked: list[dict[str, str]]
    impact: list[dict[str, Any]]


class ConfigAuditResponse(ApiResponse):
    items: list[dict[str, Any]]


class AnalysisReportSummary(ApiResponse):
    id: int
    status: str
    created_at: datetime
    finished_at: datetime | None = None
    allow_partial: bool = False


class AnalysisStatusResponse(ApiResponse):
    analysis_category: str | None
    analysis_topics: list[str]
    lots: list[dict[str, Any]]
    reports: list[AnalysisReportSummary]
    sources: list[KnowledgeSourceResponse]
    categories: dict[str, Any]
    topics: dict[str, Any]


class AnalysisStartResponse(ApiResponse):
    id: int
    project_id: int
    status: str


class AnalysisRecordResponse(ApiResponse):
    id: str
    module_key: str | None = None
    key: str | None = None
    kind: str | None = None
    title: str | None = None
    text: str | None = None
    verification: str | None = None
    human_review_status: Literal[
        "pending", "confirmed", "corrected", "rejected", "outdated",
    ] | None = None
    human_review: dict[str, Any] | None = None


class AnalysisFieldResponse(ApiResponse):
    id: str
    field: str
    group: str
    sort_order: int
    values: list[dict[str, Any]]
    note: str
    verification: str
    record: AnalysisRecordResponse | None = None
    output: dict[str, Any] | None = None


class AgentProgressResponse(ApiResponse):
    protocol: Literal["skill-agent-v1"]
    activity: str | None = None
    draft_count: int
    reviewed_count: int
    unresolved_issues: int


class AnalysisModuleResponse(ApiResponse):
    id: int
    module_key: str
    title: str
    status: str
    items: list[AnalysisFieldResponse]
    error_message: str | None = None
    quality_status: Literal[
        "self_check_passed", "needs_review", "needs_input", "unknown",
    ] | None = None
    quality_issues: list[dict[str, Any]] = Field(default_factory=list)
    runs: list[dict[str, Any]] = Field(default_factory=list)
    progress: AgentProgressResponse | None = None


class AnalysisReportResponse(ApiResponse):
    id: int
    project_id: int
    status: str
    category: str
    topics: list[str]
    allow_partial: bool
    created_at: datetime
    finished_at: datetime | None = None
    stale: bool
    runtime_version: str
    data_schema_version: str | None = None
    quality_status: str
    modules: list[AnalysisModuleResponse]
    summary: list[dict[str, Any]]
    coverage: dict[str, Any]
    error_message: str | None = None


class ModuleRecordsResponse(ApiResponse):
    schema_version: str
    module_key: str
    status: str
    quality_status: str
    quality_issues: list[dict[str, Any]]
    records: list[AnalysisRecordResponse]
    evidence: dict[str, Any]
    output_schema: dict[str, Any]


class AnalysisDataResponse(ApiResponse):
    report_id: int
    snapshot_id: int
    revision: int
    schema_version: str
    stale: bool
    data: AnalysisDatasetResponse


class AnalysisDatasetResponse(ApiResponse):
    schema_version: str
    lots: list[dict[str, Any]]
    facts: list[AnalysisRecordResponse]
    requirements: list[AnalysisRecordResponse]
    format_nodes: list[AnalysisRecordResponse]
    relations: list[AnalysisRecordResponse]
    gaps: list[dict[str, Any]]
    quality_status: Literal[
        "self_check_passed", "needs_review", "needs_input", "unknown",
    ]
    quality_issues: list[dict[str, Any]] = Field(default_factory=list)
    readiness: str
    references: list[dict[str, Any]] = Field(default_factory=list)


class AnalysisEventsResponse(ApiResponse):
    events: list[dict[str, Any]]
    next_after: int


class RetriedReportResponse(ApiResponse):
    id: int
    status: str


class CancelReportResponse(ApiResponse):
    status: str
    canceling: bool


class HumanReviewResponse(ApiResponse):
    id: int
    snapshot_id: int
    record_id: str
    decision: str
    actor: str
    note: str
    corrected_text: str | None
    created_at: datetime


class ModelTestResponse(ApiResponse):
    test_id: int
    status: str
    latency_ms: int
    http_status: int | None = None
    error: str | None = None


class LlmListResponse(ApiResponse):
    items: list[dict[str, Any]]


class LlmCallsResponse(ApiResponse):
    items: list[dict[str, Any]]
    total: int


class DeleteResponse(ApiResponse):
    deleted: bool


class QueuedCountResponse(ApiResponse):
    queued_count: int


class EmbeddingTestResponse(ApiResponse):
    status: str
    model: str
    dimension: int


class LinkedCollectionsResponse(ApiResponse):
    linked_collection_ids: list[int]


class LlmSettingsResponse(ApiResponse):
    secret_key_ready: bool
    adapter_profiles: list[dict[str, Any]]
    test_valid_seconds: int
    max_bindings: int
    model_fields_value: dict[str, Any] = Field(
        alias="model_fields", serialization_alias="model_fields",
    )
    feature_fields: dict[str, Any]
    default_max_total_requests: int


class RemoteModelsResponse(ApiResponse):
    items: list[str]


class ModelImportResponse(ApiResponse):
    created: int
    imported: int
    skipped: int


class AnalysisContextResponse(ApiResponse):
    schema_version: str
    snapshot_id: int
    purpose: str
    lot_id: int | None
    facts: list[dict[str, Any]]
    requirements: list[dict[str, Any]]
    format_nodes: list[dict[str, Any]]
    unresolved: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    gaps: list[dict[str, Any]]
    readiness: str
    references: list[dict[str, Any]]
    requirement_manifest: list[str]
    total_requirements: int
    next_offset: int | None


class ReviewRowsResponse(ApiResponse):
    items: list[dict[str, Any]]
