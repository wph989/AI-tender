// 由 scripts/generate-api-types.py 从 FastAPI OpenAPI 生成。
export interface ApiSchemas {
  "AcknowledgeRequest": { "comment"?: (string | null); "items": Array<ApiSchemas["ImpactRef"]>; };
  "ActivateRequest": { "reason"?: (string | null); };
  "AgentProgressResponse": { "activity"?: (string | null); "draft_count": number; "protocol": "skill-agent-v1"; "reviewed_count": number; "unresolved_issues": number; };
  "AnalysisContextResponse": { "facts": Array<Record<string, unknown>>; "format_nodes": Array<Record<string, unknown>>; "gaps": Array<Record<string, unknown>>; "lot_id": (number | null); "next_offset": (number | null); "purpose": string; "readiness": string; "references": Array<Record<string, unknown>>; "relations": Array<Record<string, unknown>>; "requirement_manifest": Array<string>; "requirements": Array<Record<string, unknown>>; "schema_version": string; "snapshot_id": number; "total_requirements": number; "unresolved": Array<Record<string, unknown>>; };
  "AnalysisDataResponse": { "data": ApiSchemas["AnalysisDatasetResponse"]; "report_id": number; "revision": number; "schema_version": string; "snapshot_id": number; "stale": boolean; };
  "AnalysisDatasetResponse": { "facts": Array<ApiSchemas["AnalysisRecordResponse"]>; "format_nodes": Array<ApiSchemas["AnalysisRecordResponse"]>; "gaps": Array<Record<string, unknown>>; "lots": Array<Record<string, unknown>>; "quality_issues"?: Array<Record<string, unknown>>; "quality_status": "self_check_passed" | "needs_review" | "needs_input" | "unknown"; "readiness": string; "references"?: Array<Record<string, unknown>>; "relations": Array<ApiSchemas["AnalysisRecordResponse"]>; "requirements": Array<ApiSchemas["AnalysisRecordResponse"]>; "schema_version": string; };
  "AnalysisEventsResponse": { "events": Array<Record<string, unknown>>; "next_after": number; };
  "AnalysisFieldResponse": { "field": string; "group": string; "id": string; "note": string; "output"?: (Record<string, unknown> | null); "record"?: (ApiSchemas["AnalysisRecordResponse"] | null); "sort_order": number; "values": Array<Record<string, unknown>>; "verification": string; };
  "AnalysisInput": { "allow_partial"?: boolean; };
  "AnalysisModuleResponse": { "error_message"?: (string | null); "id": number; "items": Array<ApiSchemas["AnalysisFieldResponse"]>; "module_key": string; "progress"?: (ApiSchemas["AgentProgressResponse"] | null); "quality_issues"?: Array<Record<string, unknown>>; "quality_status"?: ("self_check_passed" | "needs_review" | "needs_input" | "unknown" | null); "runs"?: Array<Record<string, unknown>>; "status": string; "title": string; };
  "AnalysisRecordResponse": { "human_review"?: (Record<string, unknown> | null); "human_review_status"?: ("pending" | "confirmed" | "corrected" | "rejected" | "outdated" | null); "id": string; "key"?: (string | null); "kind"?: (string | null); "module_key"?: (string | null); "text"?: (string | null); "title"?: (string | null); "verification"?: (string | null); };
  "AnalysisReportResponse": { "allow_partial": boolean; "category": string; "coverage": Record<string, unknown>; "created_at": string; "data_schema_version"?: (string | null); "error_message"?: (string | null); "finished_at"?: (string | null); "id": number; "modules": Array<ApiSchemas["AnalysisModuleResponse"]>; "project_id": number; "quality_status": string; "runtime_version": string; "stale": boolean; "status": string; "summary": Array<Record<string, unknown>>; "topics": Array<string>; };
  "AnalysisReportSummary": { "allow_partial"?: boolean; "created_at": string; "finished_at"?: (string | null); "id": number; "status": string; };
  "AnalysisSettings": { "category": "engineering" | "goods" | "service"; "lots"?: Array<ApiSchemas["LotSettings"]>; "topics"?: Array<string>; };
  "AnalysisStartResponse": { "id": number; "project_id": number; "status": string; };
  "AnalysisStatusResponse": { "analysis_category": (string | null); "analysis_topics": Array<string>; "categories": Record<string, unknown>; "lots": Array<Record<string, unknown>>; "reports": Array<ApiSchemas["AnalysisReportSummary"]>; "sources": Array<ApiSchemas["KnowledgeSourceResponse"]>; "topics": Record<string, unknown>; };
  "AnchorResolveRequest": { "anchors": Array<string>; "parse_run_id"?: (number | null); };
  "AnchorResponse": { "anchor": string; "bbox": (Array<number> | null); "page_no": number; "run_id": (number | null); "text": string; "type": string; };
  "AnchorsResponse": { "items": Array<ApiSchemas["AnchorResponse"]>; "missing": Array<string>; "run_id": (number | null); };
  "AskInput": { "collection_ids"?: Array<number>; "question": string; };
  "BindingsRequest": { "failover_limit"?: (number | null); "max_total_requests"?: (number | null); "model_ids"?: Array<number>; "revision": number; };
  "Body_replace_file_api_v1_projects__project_id__files__file_id__replace_post": { "auto_parse"?: boolean; "file": string; "ocr_mode"?: (string | null); "tier"?: (string | null); };
  "Body_upload_files_api_v1_projects__project_id__files_post": { "archive"?: (string | null); "auto_parse"?: boolean; "files"?: (Array<string> | null); "ocr_mode"?: (string | null); "role"?: (string | null); "tier"?: (string | null); };
  "CancelReportResponse": { "canceling": boolean; "status": string; };
  "CapabilityTestResponse": { "capability": string; "created_at": string; "error_message": (string | null); "expires_at": (string | null); "finished_at": (string | null); "id": number; "latency_ms": (number | null); "model_id"?: (number | null); "result": Record<string, unknown>; "status": string; "validity": string; };
  "CitationInput": { "anchor": string; "collection_id": number; "element_id": number; "parse_run_id": number; "project_file_id": number; "project_id": number; "source_id": number; "version_id": number; };
  "CitationResolutionResponse": { "anchor": string; "bbox": (Array<number> | null); "collection_id": number; "content"?: (string | null); "element_id": number; "file_name": string; "page_no": number; "parse_run_id": number; "project_file_id": number; "project_id": number; "quote"?: (string | null); "source_id": number; "version_id": number; };
  "CollectionInput": { "name": string; "purpose": "tender" | "company" | "history" | "reference"; };
  "CollectionResponse": { "embedding_configured"?: (boolean | null); "embedding_model"?: (string | null); "file_count"?: (number | null); "id": number; "is_project"?: (boolean | null); "name": string; "purpose": string; "sources"?: (Array<ApiSchemas["KnowledgeSourceResponse"]> | null); "upload_project_id"?: (number | null); };
  "ConfigAcknowledgeResponse": { "acked": Array<Record<string, string>>; "id": number; "impact": Array<Record<string, unknown>>; };
  "ConfigAuditResponse": { "items": Array<Record<string, unknown>>; };
  "ConfigItemsResponse": { "active": (Record<string, number> | null); "items": Array<Record<string, unknown>>; "role": string; };
  "ConfigReleaseListResponse": { "items": Array<Record<string, unknown>>; };
  "ConfigReleaseResponse": { "audit"?: (Array<Record<string, unknown>> | null); "changed"?: Record<string, unknown>; "gate"?: (Record<string, unknown> | null); "gated"?: Array<string>; "id": number; "impact"?: (Array<Record<string, unknown>> | null); "overrides"?: (Record<string, unknown> | null); "status"?: (string | null); "values"?: (Record<string, unknown> | null); "version_no"?: (number | null); };
  "ContextInput": { "limit"?: number; "lot_id"?: (number | null); "offset"?: number; "purpose": "outline" | "content" | "check"; "requirement_ids"?: Array<string>; "snapshot_id": number; };
  "DeleteResponse": { "deleted": boolean; };
  "ElementResponse": { "anchor": string; "bbox": (Array<number> | null); "continues_prev": boolean; "id"?: (number | null); "level"?: (number | null); "order_no": number; "page_no": number; "parent_id"?: (number | null); "source": string; "text": string; "type": string; };
  "ElementsResponse": { "elements": Array<ApiSchemas["ElementResponse"]>; "page_no"?: (number | null); "run_id"?: (number | null); };
  "EmbeddingTestResponse": { "dimension": number; "model": string; "status": string; };
  "FeaturePatch": { "failover_limit": number; "max_total_requests"?: number; "revision": number; };
  "HTTPValidationError": { "detail"?: Array<ApiSchemas["ValidationError"]>; };
  "HealthResponse": { "status": "ok"; };
  "HumanReviewResponse": { "actor": string; "corrected_text": (string | null); "created_at": string; "decision": string; "id": number; "note": string; "record_id": string; "snapshot_id": number; };
  "IdStatusResponse": { "id"?: (number | string | null); "job_id"?: (string | null); "status"?: (string | null); "test_id"?: (number | null); };
  "ImpactRef": { "kind": string; "ref": string; };
  "ImportRequest": { "api_mode"?: "chat_completions" | "responses" | "messages" | "generate_content" | "embeddings" | "rerank" | "image_generation"; "capabilities"?: Array<string>; "display_name"?: (string | null); "enabled"?: boolean; "extra_retries"?: number; "kind"?: "language" | "embedding" | "rerank" | "image_generation"; "max_tokens"?: (number | null); "model_id"?: string; "model_ids": Array<string>; "parameters"?: Record<string, unknown>; "provider_id"?: number; "supported_parameters"?: (Array<string> | null); "temperature"?: (number | null); "timeout_seconds"?: number; "total_timeout_seconds"?: (number | null); };
  "JobResponse": { "created_at"?: (string | null); "error_code"?: (string | null); "error_message"?: (string | null); "finished_at"?: (string | null); "id": string; "progress"?: (Record<string, unknown> | null); "run_id"?: (number | null); "stage"?: (string | null); "status": string; "updated_at"?: (string | null); "version_id"?: (number | null); };
  "KnowledgeAnswerResponse": { "id": number; "items": Array<Record<string, unknown>>; "question": string; "relations": Array<Record<string, unknown>>; "status": string; };
  "KnowledgeCollectionListResponse": { "items": Array<ApiSchemas["CollectionResponse"]>; };
  "KnowledgeSearchResponse": { "items": Array<Record<string, unknown>>; "warning"?: (string | null); };
  "KnowledgeSourceResponse": { "collection_id": number; "embedding_model_id"?: (number | null); "error_message": (string | null); "file_name": string; "index_error": (string | null); "index_status": (string | null); "needs_reindex"?: (boolean | null); "parse_run_id": (number | null); "project_file_id": number; "project_id": number; "purpose": string; "semantic_ready"?: (boolean | null); "source_id": number; "state": string; "version_id": (number | null); };
  "KnowledgeSourcesResponse": { "collection_id": number; "linked_collection_ids": Array<number>; "sources": Array<ApiSchemas["KnowledgeSourceResponse"]>; };
  "LinkedCollections": { "collection_ids": Array<number>; };
  "LinkedCollectionsResponse": { "linked_collection_ids": Array<number>; };
  "LlmCallsResponse": { "items": Array<Record<string, unknown>>; "total": number; };
  "LlmEntityResponse": { "id"?: (number | null); "key"?: (string | null); "model_id"?: (string | null); "name"?: (string | null); "status"?: (string | null); };
  "LlmListResponse": { "items": Array<Record<string, unknown>>; };
  "LlmSettingsResponse": { "adapter_profiles": Array<Record<string, unknown>>; "default_max_total_requests": number; "feature_fields": Record<string, unknown>; "max_bindings": number; "model_fields": Record<string, unknown>; "secret_key_ready": boolean; "test_valid_seconds": number; };
  "LotSettings": { "category"?: ("engineering" | "goods" | "service" | null); "id": number; "topics"?: (Array<string> | null); };
  "ModelCreate": { "api_mode"?: "chat_completions" | "responses" | "messages" | "generate_content" | "embeddings" | "rerank" | "image_generation"; "capabilities"?: Array<string>; "display_name"?: (string | null); "enabled"?: boolean; "extra_retries"?: number; "kind"?: "language" | "embedding" | "rerank" | "image_generation"; "max_tokens"?: (number | null); "model_id": string; "parameters"?: Record<string, unknown>; "provider_id": number; "supported_parameters"?: (Array<string> | null); "temperature"?: (number | null); "timeout_seconds"?: number; "total_timeout_seconds"?: (number | null); };
  "ModelImportResponse": { "created": number; "imported": number; "skipped": number; };
  "ModelPatch": { "api_mode"?: ("chat_completions" | "responses" | "messages" | "generate_content" | "embeddings" | "rerank" | "image_generation" | null); "capabilities"?: (Array<string> | null); "display_name"?: (string | null); "enabled"?: (boolean | null); "extra_retries"?: (number | null); "kind"?: ("language" | "embedding" | "rerank" | "image_generation" | null); "max_tokens"?: (number | null); "parameters"?: (Record<string, unknown> | null); "revision"?: (number | null); "supported_parameters"?: (Array<string> | null); "temperature"?: (number | null); "timeout_seconds"?: (number | null); "total_timeout_seconds"?: (number | null); };
  "ModelTestResponse": { "error"?: (string | null); "http_status"?: (number | null); "latency_ms": number; "status": string; "test_id": number; };
  "ModuleRecordsResponse": { "evidence": Record<string, unknown>; "module_key": string; "output_schema": Record<string, unknown>; "quality_issues": Array<Record<string, unknown>>; "quality_status": string; "records": Array<ApiSchemas["AnalysisRecordResponse"]>; "schema_version": string; "status": string; };
  "OutlineResponse": { "items": Array<Record<string, unknown>>; "run_id": (number | null); };
  "PageMetadata": { "has_text_layer": boolean; "height_pt": number; "page_no": number; "rotation": number; "width_pt": number; };
  "PagesResponse": { "page_count": number; "pages": Array<ApiSchemas["PageMetadata"]>; "total": number; };
  "ParseJobCreatedResponse": { "force": boolean; "job_id": string; "run_id": (number | null); "status": string; "version_id": number; };
  "ParseRequest": { "force"?: boolean; "ocr_mode"?: (string | null); "reason"?: (string | null); "tier"?: (string | null); };
  "ProjectCreate": { "name": string; "owner"?: (string | null); "project_no"?: (string | null); };
  "ProjectDetailFileResponse": { "created_at": string; "display_name": string; "is_parseable": boolean; "latest_job"?: (Record<string, unknown> | null); "latest_run_id"?: (number | null); "mime": (string | null); "page_count"?: (number | null); "parse_ocr_mode"?: (string | null); "parse_status"?: (string | null); "parse_tier"?: (string | null); "project_file_id": number; "project_id": number; "replaced_by_id"?: (number | null); "replaces_id"?: (number | null); "role": string; "sha256": string; "size_bytes": number; "sort_no": number; "version_id": (number | null); };
  "ProjectDetailResponse": { "company_id": number; "created_at": string; "failed_count"?: (number | null); "file_count"?: (number | null); "files": Array<ApiSchemas["ProjectDetailFileResponse"]>; "id": number; "last_activity_at"?: (string | null); "lots": Array<ApiSchemas["ProjectLotResponse"]>; "name": string; "owner": (string | null); "project_no": (string | null); "status": string; };
  "ProjectFilePatch": { "display_name"?: (string | null); "role"?: (string | null); "sort_no"?: (number | null); };
  "ProjectFileResponse": { "display_name": string; "is_parseable": boolean; "mime": (string | null); "project_file_id": number; "project_id": number; "role": string; "sha256": string; "size_bytes": number; "sort_no": number; "version_id": (number | null); };
  "ProjectListResponse": { "items": Array<ApiSchemas["ProjectResponse"]>; "limit": number; "offset": number; };
  "ProjectLotResponse": { "code": (string | null); "id": number; "name": string; "sort_no": number; };
  "ProjectPatch": { "name"?: (string | null); "owner"?: (string | null); "project_no"?: (string | null); };
  "ProjectResponse": { "company_id": number; "created_at": string; "failed_count"?: (number | null); "file_count"?: (number | null); "id": number; "last_activity_at"?: (string | null); "name": string; "owner": (string | null); "project_no": (string | null); "status": string; };
  "ProviderCreate": { "api_key"?: (string | null); "auth_mode"?: "api_key" | "none"; "base_url": string; "enabled"?: boolean; "name": string; "protocol"?: "openai_compatible" | "openai" | "anthropic" | "gemini" | "rerank_http"; };
  "ProviderPatch": { "api_key"?: (string | null); "auth_mode"?: ("api_key" | "none" | null); "base_url"?: (string | null); "clear_api_key"?: boolean; "enabled"?: (boolean | null); "name"?: (string | null); "revision"?: (number | null); };
  "QueuedCountResponse": { "queued_count": number; };
  "ReadinessResponse": { "checks": Record<string, boolean>; "status": "ready" | "not_ready"; };
  "RecordReviewInput": { "corrected_text"?: (string | null); "decision": "confirmed" | "corrected" | "rejected"; "note"?: string; "previous_review_id": (number | null); "record_id": string; "snapshot_id": number; };
  "ReleaseCreate": { "based_on"?: (number | null); "note"?: (string | null); "values"?: Record<string, unknown>; };
  "RemoteModelsResponse": { "items": Array<string>; };
  "ReplaceFileResponse": { "added": ApiSchemas["UploadedFileResponse"]; "jobs": Array<string>; };
  "RetriedReportResponse": { "id": number; "status": string; };
  "RetryInput": { "max_output_tokens"?: (number | null); "mode"?: ("restart" | "resume" | null); "module_keys"?: Array<string>; "timeout_seconds"?: (number | null); };
  "RollbackRequest": { "reason"?: (string | null); };
  "TestRequest": { "capability"?: ("text" | "vision" | "embedding" | "multimodal_embedding" | "rerank" | "image_generation" | null); };
  "UploadResponse": { "added": Array<ApiSchemas["UploadedFileResponse"]>; "jobs": Array<string>; "skipped": Array<Record<string, string>>; };
  "UploadedFileResponse": { "display_name": string; "is_parseable": boolean; "job_id": (string | null); "project_file_id": number; "role": string; "version_id": (number | null); };
  "ValidationError": { "ctx"?: Record<string, unknown>; "input"?: unknown; "loc": Array<(string | number)>; "msg": string; "type": string; };
  "VersionResponse": { "converter": (string | null); "converter_version": (string | null); "created_at": string; "document_id": number; "id": number; "is_converted": boolean; "mime": (string | null); "page_count": (number | null); "parse_runs": Array<Record<string, unknown>>; "pdf_sha256": (string | null); "project_id": number; "sha256": string; "size_bytes": number; "title": string; "version_no": number; };
}

export interface ApiPaths {
  "/api/v1/analysis/reports/{report_id}": {
    get: { response: ApiSchemas["AnalysisReportResponse"] };
  };
  "/api/v1/analysis/reports/{report_id}/cancel": {
    post: { response: ApiSchemas["CancelReportResponse"] };
  };
  "/api/v1/analysis/reports/{report_id}/context": {
    post: { request: ApiSchemas["ContextInput"]; response: ApiSchemas["AnalysisContextResponse"] };
  };
  "/api/v1/analysis/reports/{report_id}/data": {
    get: { response: ApiSchemas["AnalysisDataResponse"] };
  };
  "/api/v1/analysis/reports/{report_id}/modules/{module_key}/records": {
    get: { response: ApiSchemas["ModuleRecordsResponse"] };
  };
  "/api/v1/analysis/reports/{report_id}/retry": {
    post: { request: ApiSchemas["RetryInput"]; response: ApiSchemas["RetriedReportResponse"] };
  };
  "/api/v1/analysis/reports/{report_id}/reviews": {
    post: { request: ApiSchemas["RecordReviewInput"]; response: ApiSchemas["HumanReviewResponse"] };
  };
  "/api/v1/analysis/reports/{report_id}/runs/{run_id}/events": {
    get: { response: ApiSchemas["AnalysisEventsResponse"] };
  };
  "/api/v1/config/audit": {
    get: { response: ApiSchemas["ConfigAuditResponse"] };
  };
  "/api/v1/config/items": {
    get: { response: ApiSchemas["ConfigItemsResponse"] };
  };
  "/api/v1/config/releases": {
    get: { response: ApiSchemas["ConfigReleaseListResponse"] };
    post: { request: ApiSchemas["ReleaseCreate"]; response: ApiSchemas["ConfigReleaseResponse"] };
  };
  "/api/v1/config/releases/{release_id}": {
    get: { response: ApiSchemas["ConfigReleaseResponse"] };
  };
  "/api/v1/config/releases/{release_id}/acknowledge": {
    post: { request: ApiSchemas["AcknowledgeRequest"]; response: ApiSchemas["ConfigAcknowledgeResponse"] };
  };
  "/api/v1/config/releases/{release_id}/activate": {
    post: { request: ApiSchemas["ActivateRequest"]; response: ApiSchemas["ConfigReleaseResponse"] };
  };
  "/api/v1/config/releases/{release_id}/rollback": {
    post: { request: ApiSchemas["RollbackRequest"]; response: ApiSchemas["ConfigReleaseResponse"] };
  };
  "/api/v1/healthz": {
    get: { response: ApiSchemas["HealthResponse"] };
  };
  "/api/v1/jobs/{job_id}": {
    get: { response: ApiSchemas["JobResponse"] };
  };
  "/api/v1/jobs/{job_id}/cancel": {
    post: { response: ApiSchemas["JobResponse"] };
  };
  "/api/v1/jobs/{job_id}/events": {
    get: { response: unknown };
  };
  "/api/v1/knowledge/answers/{answer_id}": {
    get: { response: ApiSchemas["KnowledgeAnswerResponse"] };
  };
  "/api/v1/knowledge/citations/resolve": {
    post: { request: ApiSchemas["CitationInput"]; response: ApiSchemas["CitationResolutionResponse"] };
  };
  "/api/v1/knowledge/collections": {
    get: { response: ApiSchemas["KnowledgeCollectionListResponse"] };
    post: { request: ApiSchemas["CollectionInput"]; response: ApiSchemas["CollectionResponse"] };
  };
  "/api/v1/knowledge/collections/{collection_id}": {
    delete: { response: ApiSchemas["DeleteResponse"] };
    get: { response: ApiSchemas["CollectionResponse"] };
    patch: { request: ApiSchemas["CollectionInput"]; response: ApiSchemas["CollectionResponse"] };
  };
  "/api/v1/knowledge/collections/{collection_id}/ask": {
    post: { request: ApiSchemas["AskInput"]; response: ApiSchemas["IdStatusResponse"] };
  };
  "/api/v1/knowledge/collections/{collection_id}/reindex": {
    post: { response: ApiSchemas["QueuedCountResponse"] };
  };
  "/api/v1/knowledge/collections/{collection_id}/search": {
    get: { response: ApiSchemas["KnowledgeSearchResponse"] };
  };
  "/api/v1/knowledge/embedding/test": {
    post: { response: ApiSchemas["EmbeddingTestResponse"] };
  };
  "/api/v1/knowledge/sources/{source_id}/process": {
    post: { response: ApiSchemas["IdStatusResponse"] };
  };
  "/api/v1/llm/calls": {
    get: { response: ApiSchemas["LlmCallsResponse"] };
  };
  "/api/v1/llm/features": {
    get: { response: ApiSchemas["LlmListResponse"] };
  };
  "/api/v1/llm/features/{feature_key}": {
    patch: { request: ApiSchemas["FeaturePatch"]; response: ApiSchemas["LlmEntityResponse"] };
  };
  "/api/v1/llm/features/{feature_key}/models": {
    put: { request: ApiSchemas["BindingsRequest"]; response: ApiSchemas["LlmEntityResponse"] };
  };
  "/api/v1/llm/models": {
    get: { response: ApiSchemas["LlmListResponse"] };
    post: { request: ApiSchemas["ModelCreate"]; response: ApiSchemas["LlmEntityResponse"] };
  };
  "/api/v1/llm/models/{model_id}": {
    delete: { response: ApiSchemas["IdStatusResponse"] };
    patch: { request: ApiSchemas["ModelPatch"]; response: ApiSchemas["LlmEntityResponse"] };
  };
  "/api/v1/llm/models/{model_id}/test": {
    post: { request: (ApiSchemas["TestRequest"] | null); response: ApiSchemas["ModelTestResponse"] };
  };
  "/api/v1/llm/models/{model_id}/tests": {
    post: { request: (ApiSchemas["TestRequest"] | null); response: ApiSchemas["IdStatusResponse"] };
  };
  "/api/v1/llm/providers": {
    get: { response: ApiSchemas["LlmListResponse"] };
    post: { request: ApiSchemas["ProviderCreate"]; response: ApiSchemas["LlmEntityResponse"] };
  };
  "/api/v1/llm/providers/{provider_id}": {
    delete: { response: ApiSchemas["IdStatusResponse"] };
    patch: { request: ApiSchemas["ProviderPatch"]; response: ApiSchemas["LlmEntityResponse"] };
  };
  "/api/v1/llm/providers/{provider_id}/models/import": {
    post: { request: ApiSchemas["ImportRequest"]; response: ApiSchemas["ModelImportResponse"] };
  };
  "/api/v1/llm/providers/{provider_id}/remote-models": {
    get: { response: ApiSchemas["RemoteModelsResponse"] };
  };
  "/api/v1/llm/providers/{provider_id}/test": {
    post: { response: ApiSchemas["ModelTestResponse"] };
  };
  "/api/v1/llm/settings": {
    get: { response: ApiSchemas["LlmSettingsResponse"] };
  };
  "/api/v1/llm/tests": {
    get: { response: ApiSchemas["LlmListResponse"] };
  };
  "/api/v1/llm/tests/{test_id}": {
    get: { response: ApiSchemas["CapabilityTestResponse"] };
  };
  "/api/v1/llm/tests/{test_id}/preview": {
    get: { response: unknown };
  };
  "/api/v1/projects": {
    get: { response: ApiSchemas["ProjectListResponse"] };
    post: { request: ApiSchemas["ProjectCreate"]; response: ApiSchemas["ProjectResponse"] };
  };
  "/api/v1/projects/{project_id}": {
    get: { response: ApiSchemas["ProjectDetailResponse"] };
    patch: { request: ApiSchemas["ProjectPatch"]; response: ApiSchemas["ProjectDetailResponse"] };
  };
  "/api/v1/projects/{project_id}/analysis": {
    get: { response: ApiSchemas["AnalysisStatusResponse"] };
    post: { request: ApiSchemas["AnalysisInput"]; response: ApiSchemas["AnalysisStartResponse"] };
  };
  "/api/v1/projects/{project_id}/analysis/settings": {
    put: { request: ApiSchemas["AnalysisSettings"]; response: ApiSchemas["AnalysisStatusResponse"] };
  };
  "/api/v1/projects/{project_id}/files": {
    post: { response: ApiSchemas["UploadResponse"] };
  };
  "/api/v1/projects/{project_id}/files/{file_id}": {
    patch: { request: ApiSchemas["ProjectFilePatch"]; response: ApiSchemas["ProjectFileResponse"] };
  };
  "/api/v1/projects/{project_id}/files/{file_id}/original": {
    get: { response: unknown };
  };
  "/api/v1/projects/{project_id}/files/{file_id}/replace": {
    post: { response: ApiSchemas["ReplaceFileResponse"] };
  };
  "/api/v1/projects/{project_id}/knowledge": {
    get: { response: ApiSchemas["KnowledgeSourcesResponse"] };
  };
  "/api/v1/projects/{project_id}/knowledge/ask": {
    post: { request: ApiSchemas["AskInput"]; response: ApiSchemas["IdStatusResponse"] };
  };
  "/api/v1/projects/{project_id}/knowledge/collections": {
    put: { request: ApiSchemas["LinkedCollections"]; response: ApiSchemas["LinkedCollectionsResponse"] };
  };
  "/api/v1/readyz": {
    get: { response: ApiSchemas["ReadinessResponse"] };
  };
  "/api/v1/versions/{version_id}": {
    get: { response: ApiSchemas["VersionResponse"] };
  };
  "/api/v1/versions/{version_id}/anchors/resolve": {
    post: { request: ApiSchemas["AnchorResolveRequest"]; response: ApiSchemas["AnchorsResponse"] };
  };
  "/api/v1/versions/{version_id}/anchors/{anchor}": {
    get: { response: ApiSchemas["AnchorResponse"] };
  };
  "/api/v1/versions/{version_id}/elements": {
    get: { response: ApiSchemas["ElementsResponse"] };
  };
  "/api/v1/versions/{version_id}/file": {
    get: { response: unknown };
  };
  "/api/v1/versions/{version_id}/original": {
    get: { response: unknown };
  };
  "/api/v1/versions/{version_id}/outline": {
    get: { response: ApiSchemas["OutlineResponse"] };
  };
  "/api/v1/versions/{version_id}/pages": {
    get: { response: ApiSchemas["PagesResponse"] };
  };
  "/api/v1/versions/{version_id}/pages/{page_no}/elements": {
    get: { response: ApiSchemas["ElementsResponse"] };
  };
  "/api/v1/versions/{version_id}/parse": {
    post: { request: ApiSchemas["ParseRequest"]; response: ApiSchemas["ParseJobCreatedResponse"] };
  };
  "/api/v1/versions/{version_id}/reparse": {
    post: { request: ApiSchemas["ParseRequest"]; response: ApiSchemas["ParseJobCreatedResponse"] };
  };
}

export type ApiResult<P extends keyof ApiPaths, M extends keyof ApiPaths[P]> =
  ApiPaths[P][M] extends { response: infer R } ? R : never;
