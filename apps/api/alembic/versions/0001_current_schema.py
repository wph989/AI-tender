"""当前空库基线：直接创建现行表、约束、索引与种子，不重放退役设计。"""

from alembic import op

revision = "0001_current_schema"
down_revision = None
branch_labels = None
depends_on = None

# SQL 保留数据库约束与索引，不能用不包含这些约束的 ORM 元数据代替。
_STATEMENTS: tuple[str, ...] = (
    """
CREATE SCHEMA agent_runtime;
    """.strip(),
    """
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;
    """.strip(),
    """
COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';
    """.strip(),
    """
CREATE TABLE agent_call_attempt (
    run_id integer NOT NULL,
    kind text NOT NULL,
    call_key text NOT NULL,
    status text NOT NULL,
    detail jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT agent_call_attempt_kind_check CHECK ((kind = ANY (ARRAY['model'::text, 'tool'::text]))),
    CONSTRAINT agent_call_attempt_status_check CHECK ((status = ANY (ARRAY['running'::text, 'ok'::text, 'error'::text, 'unknown'::text, 'skipped'::text])))
);
    """.strip(),
    """
CREATE TABLE agent_model_invocation (
    run_id integer NOT NULL,
    call_key text NOT NULL,
    progress jsonb DEFAULT '{}'::jsonb NOT NULL
);
    """.strip(),
    """
CREATE TABLE agent_module_run (
    id integer NOT NULL,
    module_id bigint NOT NULL,
    company_id bigint NOT NULL,
    attempt integer DEFAULT 1 NOT NULL,
    thread_id text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    owner uuid,
    lease_until timestamp with time zone,
    started_at timestamp with time zone,
    deadline_at timestamp with time zone,
    finished_at timestamp with time zone,
    model_calls integer DEFAULT 0 NOT NULL,
    tool_calls integer DEFAULT 0 NOT NULL,
    prompt_tokens bigint DEFAULT 0 NOT NULL,
    completion_tokens bigint DEFAULT 0 NOT NULL,
    limits jsonb NOT NULL,
    state jsonb DEFAULT '{}'::jsonb NOT NULL,
    error_message text,
    successful_model_calls integer,
    successful_tool_calls integer,
    CONSTRAINT agent_module_run_attempt_check CHECK ((attempt > 0)),
    CONSTRAINT agent_module_run_model_calls_check CHECK ((model_calls >= 0)),
    CONSTRAINT agent_module_run_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'running'::text, 'completed'::text, 'failed'::text, 'canceled'::text, 'partial'::text]))),
    CONSTRAINT agent_module_run_successful_model_calls_check CHECK ((successful_model_calls >= 0)),
    CONSTRAINT agent_module_run_successful_tool_calls_check CHECK ((successful_tool_calls >= 0)),
    CONSTRAINT agent_module_run_tool_calls_check CHECK ((tool_calls >= 0))
);
    """.strip(),
    """
CREATE SEQUENCE agent_module_run_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE agent_module_run_id_seq OWNED BY agent_module_run.id;
    """.strip(),
    """
CREATE TABLE agent_run_event (
    id bigint NOT NULL,
    run_id integer NOT NULL,
    kind text NOT NULL,
    detail jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE agent_run_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE agent_run_event_id_seq OWNED BY agent_run_event.id;
    """.strip(),
    """
CREATE TABLE analysis_data_snapshot (
    id bigint NOT NULL,
    report_id bigint NOT NULL,
    revision integer NOT NULL,
    schema_version text NOT NULL,
    manifest_hash text NOT NULL,
    input_snapshot jsonb NOT NULL,
    data jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE analysis_data_snapshot_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE analysis_data_snapshot_id_seq OWNED BY analysis_data_snapshot.id;
    """.strip(),
    """
CREATE TABLE analysis_module (
    id bigint NOT NULL,
    report_id bigint NOT NULL,
    module_key text NOT NULL,
    title text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    items jsonb DEFAULT '[]'::jsonb NOT NULL,
    trace jsonb DEFAULT '[]'::jsonb NOT NULL,
    error_message text,
    business_data jsonb DEFAULT '{}'::jsonb NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE analysis_module_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE analysis_module_id_seq OWNED BY analysis_module.id;
    """.strip(),
    """
CREATE TABLE analysis_record_review (
    id bigint NOT NULL,
    snapshot_id bigint NOT NULL,
    record_id text NOT NULL,
    actor text NOT NULL,
    decision text NOT NULL,
    note text NOT NULL,
    corrected_text text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT analysis_record_review_check CHECK (((decision = 'corrected'::text) = (corrected_text IS NOT NULL))),
    CONSTRAINT analysis_record_review_decision_check CHECK ((decision = ANY (ARRAY['confirmed'::text, 'corrected'::text, 'rejected'::text])))
);
    """.strip(),
    """
CREATE SEQUENCE analysis_record_review_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE analysis_record_review_id_seq OWNED BY analysis_record_review.id;
    """.strip(),
    """
CREATE TABLE analysis_report (
    id bigint NOT NULL,
    project_id bigint NOT NULL,
    company_id bigint NOT NULL,
    status text DEFAULT 'waiting'::text NOT NULL,
    lease_until timestamp with time zone,
    allow_partial boolean DEFAULT false NOT NULL,
    category text NOT NULL,
    topics jsonb DEFAULT '[]'::jsonb NOT NULL,
    lot_settings jsonb DEFAULT '[]'::jsonb NOT NULL,
    source_snapshot jsonb DEFAULT '[]'::jsonb NOT NULL,
    coverage jsonb DEFAULT '{}'::jsonb NOT NULL,
    skill_version text NOT NULL,
    skill_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    runtime_version text DEFAULT 'deepagents-0.7.22-v6-records'::text NOT NULL,
    runtime_settings jsonb DEFAULT '{}'::jsonb NOT NULL,
    reference_snapshot jsonb DEFAULT '[]'::jsonb NOT NULL,
    summary jsonb DEFAULT '[]'::jsonb NOT NULL,
    derived_lot_ids bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    snapshot_pending boolean DEFAULT false NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE analysis_report_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE analysis_report_id_seq OWNED BY analysis_report.id;
    """.strip(),
    """
CREATE TABLE config_ack (
    id bigint NOT NULL,
    release_id bigint NOT NULL,
    item_kind text NOT NULL,
    item_ref text NOT NULL,
    actor text NOT NULL,
    comment text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE config_ack_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE config_ack_id_seq OWNED BY config_ack.id;
    """.strip(),
    """
CREATE TABLE config_audit (
    id bigint NOT NULL,
    release_id bigint NOT NULL,
    actor text NOT NULL,
    action text NOT NULL,
    diff jsonb NOT NULL,
    reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE config_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE config_audit_id_seq OWNED BY config_audit.id;
    """.strip(),
    """
CREATE TABLE config_item (
    key text NOT NULL,
    layer text NOT NULL,
    value_type text NOT NULL,
    default_value jsonb NOT NULL,
    description text NOT NULL,
    requires_gate boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);
    """.strip(),
    """
CREATE TABLE config_release (
    id bigint NOT NULL,
    company_id bigint DEFAULT 1 NOT NULL,
    version_no integer NOT NULL,
    "values" jsonb NOT NULL,
    status text NOT NULL,
    based_on bigint,
    note text,
    created_by text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE config_release_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE config_release_id_seq OWNED BY config_release.id;
    """.strip(),
    """
CREATE TABLE document (
    id bigint NOT NULL,
    title text NOT NULL,
    project_no text,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    company_id bigint DEFAULT 1 NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE document_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE document_id_seq OWNED BY document.id;
    """.strip(),
    """
CREATE TABLE document_version (
    id bigint NOT NULL,
    document_id bigint NOT NULL,
    version_no integer NOT NULL,
    sha256 character(64) NOT NULL,
    mime text NOT NULL,
    size_bytes bigint NOT NULL,
    original_key text NOT NULL,
    pdf_key text NOT NULL,
    pdf_sha256 character(64) NOT NULL,
    is_converted boolean NOT NULL,
    converter text,
    converter_version text,
    page_count integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    company_id bigint DEFAULT 1 NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE document_version_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE document_version_id_seq OWNED BY document_version.id;
    """.strip(),
    """
CREATE TABLE element (
    id bigint NOT NULL,
    version_id bigint NOT NULL,
    run_id bigint NOT NULL,
    page_no integer NOT NULL,
    order_no integer NOT NULL,
    anchor text NOT NULL,
    type text NOT NULL,
    level integer,
    parent_id bigint,
    bbox_x0 numeric(7,6),
    bbox_y0 numeric(7,6),
    bbox_x1 numeric(7,6),
    bbox_y1 numeric(7,6),
    text text,
    html text,
    source text DEFAULT 'native'::text NOT NULL,
    continues_prev boolean DEFAULT false NOT NULL,
    mineru_locator text
);
    """.strip(),
    """
CREATE SEQUENCE element_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE element_id_seq OWNED BY element.id;
    """.strip(),
    """
CREATE TABLE job (
    id text NOT NULL,
    company_id bigint DEFAULT 1 NOT NULL,
    project_id bigint NOT NULL,
    project_file_id bigint NOT NULL,
    version_id bigint,
    run_id bigint,
    status text DEFAULT 'pending'::text NOT NULL,
    stage text NOT NULL,
    progress jsonb DEFAULT '{}'::jsonb NOT NULL,
    config_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    error_code text,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    dispatched_at timestamp with time zone,
    config_snapshot_id bigint,
    next_attempt_at timestamp with time zone,
    dispatch_lease_until timestamp with time zone
);
    """.strip(),
    """
CREATE TABLE job_config_snapshot (
    id bigint NOT NULL,
    release_id bigint NOT NULL,
    resolved jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE job_config_snapshot_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE job_config_snapshot_id_seq OWNED BY job_config_snapshot.id;
    """.strip(),
    """
CREATE TABLE knowledge_answer (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    project_id bigint,
    collection_ids jsonb NOT NULL,
    question text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    lease_until timestamp with time zone,
    items jsonb DEFAULT '[]'::jsonb NOT NULL,
    relations jsonb DEFAULT '[]'::jsonb NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone
);
    """.strip(),
    """
CREATE SEQUENCE knowledge_answer_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE knowledge_answer_id_seq OWNED BY knowledge_answer.id;
    """.strip(),
    """
CREATE TABLE knowledge_chunk (
    id bigint NOT NULL,
    index_id bigint NOT NULL,
    element_id bigint NOT NULL,
    ordinal integer NOT NULL,
    char_start integer NOT NULL,
    char_end integer NOT NULL,
    chapter text DEFAULT ''::text NOT NULL,
    content text NOT NULL,
    embedding double precision[],
    locations jsonb
);
    """.strip(),
    """
COMMENT ON COLUMN knowledge_chunk.locations IS '入库时合并的大块页码、坐标及页内字符范围；模型只使用大块ID';
    """.strip(),
    """
CREATE SEQUENCE knowledge_chunk_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE knowledge_chunk_id_seq OWNED BY knowledge_chunk.id;
    """.strip(),
    """
CREATE TABLE knowledge_collection (
    id bigint NOT NULL,
    company_id bigint NOT NULL,
    name text NOT NULL,
    purpose text NOT NULL,
    upload_project_id bigint NOT NULL,
    is_project boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT knowledge_collection_purpose_check CHECK ((purpose = ANY (ARRAY['tender'::text, 'company'::text, 'history'::text, 'reference'::text])))
);
    """.strip(),
    """
CREATE SEQUENCE knowledge_collection_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE knowledge_collection_id_seq OWNED BY knowledge_collection.id;
    """.strip(),
    """
CREATE TABLE knowledge_index (
    id bigint NOT NULL,
    source_id bigint NOT NULL,
    version_id bigint NOT NULL,
    run_id bigint NOT NULL,
    embedding_model_id bigint,
    embedding_signature text,
    dimension integer,
    chunk_version text DEFAULT '1'::text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    lease_until timestamp with time zone,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone
);
    """.strip(),
    """
CREATE SEQUENCE knowledge_index_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE knowledge_index_id_seq OWNED BY knowledge_index.id;
    """.strip(),
    """
CREATE TABLE knowledge_relation (
    id bigint NOT NULL,
    report_id bigint NOT NULL,
    module_id bigint NOT NULL,
    subject text NOT NULL,
    predicate text NOT NULL,
    object text NOT NULL,
    scope text DEFAULT ''::text NOT NULL,
    condition text DEFAULT ''::text NOT NULL,
    citations jsonb NOT NULL,
    verified boolean DEFAULT false NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE knowledge_relation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE knowledge_relation_id_seq OWNED BY knowledge_relation.id;
    """.strip(),
    """
CREATE TABLE knowledge_source (
    id bigint NOT NULL,
    collection_id bigint NOT NULL,
    project_file_id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE knowledge_source_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE knowledge_source_id_seq OWNED BY knowledge_source.id;
    """.strip(),
    """
CREATE TABLE llm_call_log (
    id bigint NOT NULL,
    provider_id bigint,
    model_id bigint,
    feature_key text,
    purpose text NOT NULL,
    status text NOT NULL,
    http_status integer,
    latency_ms integer NOT NULL,
    prompt_tokens integer,
    completion_tokens integer,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    invocation_id uuid,
    candidate_ordinal integer,
    retry_ordinal integer,
    request_ordinal integer,
    model_name_snapshot text,
    provider_name_snapshot text,
    model_key_snapshot text,
    vector_count integer,
    document_count integer,
    image_count integer
);
    """.strip(),
    """
CREATE SEQUENCE llm_call_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE llm_call_log_id_seq OWNED BY llm_call_log.id;
    """.strip(),
    """
CREATE TABLE llm_feature (
    key text NOT NULL,
    name text NOT NULL,
    failover_limit integer DEFAULT 3 NOT NULL,
    description text DEFAULT ''::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    max_total_requests integer DEFAULT 6 NOT NULL,
    revision integer DEFAULT 1 NOT NULL,
    CONSTRAINT llm_feature_failover_limit_check CHECK (((failover_limit >= 1) AND (failover_limit <= 10))),
    CONSTRAINT llm_feature_max_total_requests_check CHECK ((max_total_requests >= 1))
);
    """.strip(),
    """
CREATE TABLE llm_feature_model (
    id bigint NOT NULL,
    feature_key text NOT NULL,
    model_id bigint NOT NULL,
    priority integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT llm_feature_model_priority_check CHECK (((priority >= 1) AND (priority <= 10)))
);
    """.strip(),
    """
CREATE SEQUENCE llm_feature_model_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE llm_feature_model_id_seq OWNED BY llm_feature_model.id;
    """.strip(),
    """
CREATE TABLE llm_model (
    id bigint NOT NULL,
    provider_id bigint NOT NULL,
    model_id text NOT NULL,
    display_name text NOT NULL,
    timeout_seconds double precision DEFAULT 90 NOT NULL,
    temperature numeric(3,2),
    max_tokens integer,
    enabled boolean DEFAULT true NOT NULL,
    last_test_status text,
    last_test_at timestamp with time zone,
    last_test_error text,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    kind text DEFAULT 'language'::text NOT NULL,
    api_mode text DEFAULT 'chat_completions'::text NOT NULL,
    capabilities jsonb DEFAULT '["text_input", "json_output"]'::jsonb NOT NULL,
    extra_retries integer DEFAULT 1 NOT NULL,
    revision integer DEFAULT 1 NOT NULL,
    config_revision integer DEFAULT 1 NOT NULL,
    last_test_config_revision integer,
    last_test_provider_revision integer,
    last_test_id bigint,
    parameters jsonb DEFAULT '{}'::jsonb NOT NULL,
    supported_parameters jsonb,
    embedding_space_id uuid,
    total_timeout_seconds double precision,
    CONSTRAINT llm_model_check CHECK (((total_timeout_seconds IS NULL) OR ((total_timeout_seconds > (0)::double precision) AND (total_timeout_seconds < 'Infinity'::double precision) AND (kind = 'language'::text)))),
    CONSTRAINT llm_model_extra_retries_check CHECK ((extra_retries >= 0)),
    CONSTRAINT llm_model_kind_check CHECK ((kind = ANY (ARRAY['language'::text, 'embedding'::text, 'rerank'::text, 'image_generation'::text]))),
    CONSTRAINT llm_model_parameters_check CHECK ((jsonb_typeof(parameters) = 'object'::text)),
    CONSTRAINT llm_model_timeout_seconds_check CHECK (((timeout_seconds > (0)::double precision) AND (timeout_seconds < 'Infinity'::double precision)))
);
    """.strip(),
    """
COMMENT ON COLUMN llm_model.timeout_seconds IS '文本模型为有效增量响应间隔；非文本模型仍为请求总超时。已有数值保持，新文本模型由应用默认10秒';
    """.strip(),
    """
COMMENT ON COLUMN llm_model.total_timeout_seconds IS '文本模型单次请求总时限，NULL表示关闭';
    """.strip(),
    """
CREATE SEQUENCE llm_model_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE llm_model_id_seq OWNED BY llm_model.id;
    """.strip(),
    """
CREATE TABLE llm_provider (
    id bigint NOT NULL,
    name text NOT NULL,
    base_url text NOT NULL,
    api_key_ciphertext text,
    api_key_hint text,
    enabled boolean DEFAULT true NOT NULL,
    last_test_status text,
    last_test_at timestamp with time zone,
    last_test_error text,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    protocol text DEFAULT 'openai_compatible'::text NOT NULL,
    auth_mode text DEFAULT 'api_key'::text NOT NULL,
    revision integer DEFAULT 1 NOT NULL,
    config_revision integer DEFAULT 1 NOT NULL,
    credential_revision integer DEFAULT 1 NOT NULL,
    api_key_updated_at timestamp with time zone,
    last_test_config_revision integer,
    last_test_id bigint,
    rate_limited_until timestamp with time zone,
    CONSTRAINT llm_provider_auth_mode_check CHECK ((auth_mode = ANY (ARRAY['api_key'::text, 'none'::text])))
);
    """.strip(),
    """
CREATE SEQUENCE llm_provider_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE llm_provider_id_seq OWNED BY llm_provider.id;
    """.strip(),
    """
CREATE TABLE llm_test (
    id bigint NOT NULL,
    provider_id bigint NOT NULL,
    model_id bigint,
    capability text NOT NULL,
    provider_revision integer NOT NULL,
    model_revision integer,
    status text DEFAULT 'running'::text NOT NULL,
    latency_ms integer,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    call_log_id bigint,
    timeout_seconds double precision DEFAULT 90 NOT NULL,
    result jsonb DEFAULT '{}'::jsonb NOT NULL,
    preview_data bytea,
    preview_mime text,
    invalidated_at timestamp with time zone,
    heartbeat_at timestamp with time zone
);
    """.strip(),
    """
CREATE SEQUENCE llm_test_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE llm_test_id_seq OWNED BY llm_test.id;
    """.strip(),
    """
CREATE TABLE lot (
    id bigint NOT NULL,
    project_id bigint NOT NULL,
    code text,
    name text,
    sort_no integer DEFAULT 0 NOT NULL,
    analysis_category text,
    analysis_topics jsonb
);
    """.strip(),
    """
CREATE SEQUENCE lot_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE lot_id_seq OWNED BY lot.id;
    """.strip(),
    """
CREATE TABLE page (
    id bigint NOT NULL,
    version_id bigint NOT NULL,
    page_no integer NOT NULL,
    width_pt numeric(10,3),
    height_pt numeric(10,3),
    rotation smallint DEFAULT 0 NOT NULL,
    image_key text,
    image_px_w integer,
    image_px_h integer,
    text_layer boolean DEFAULT false NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE page_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE page_id_seq OWNED BY page.id;
    """.strip(),
    """
CREATE TABLE parse_run (
    id bigint NOT NULL,
    version_id bigint NOT NULL,
    provider text DEFAULT 'mineru'::text NOT NULL,
    provider_version text NOT NULL,
    tier text NOT NULL,
    backend text,
    schema_version text NOT NULL,
    status text NOT NULL,
    request_id text,
    raw_middle_key text,
    raw_content_key text,
    page_count integer,
    elapsed_ms integer,
    error_code text,
    error_message text,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    provider_job_id text,
    config_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL
);
    """.strip(),
    """
CREATE SEQUENCE parse_run_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE parse_run_id_seq OWNED BY parse_run.id;
    """.strip(),
    """
CREATE TABLE project (
    id bigint NOT NULL,
    company_id bigint DEFAULT 1 NOT NULL,
    name text NOT NULL,
    project_no text,
    owner text,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    kind text DEFAULT 'project'::text NOT NULL,
    analysis_category text,
    analysis_topics jsonb DEFAULT '[]'::jsonb NOT NULL
);
    """.strip(),
    """
CREATE TABLE project_file (
    id bigint NOT NULL,
    project_id bigint NOT NULL,
    version_id bigint,
    role text NOT NULL,
    display_name text NOT NULL,
    is_parseable boolean DEFAULT true NOT NULL,
    replaces_id bigint,
    sort_no integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    original_key text,
    sha256 character(64),
    mime text,
    size_bytes bigint
);
    """.strip(),
    """
CREATE SEQUENCE project_file_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE project_file_id_seq OWNED BY project_file.id;
    """.strip(),
    """
CREATE SEQUENCE project_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE project_id_seq OWNED BY project.id;
    """.strip(),
    """
CREATE TABLE project_knowledge_collection (
    project_id bigint NOT NULL,
    collection_id bigint NOT NULL
);
    """.strip(),
    """
CREATE TABLE table_cell (
    id bigint NOT NULL,
    element_id bigint NOT NULL,
    row_no integer NOT NULL,
    col_no integer NOT NULL,
    rowspan integer DEFAULT 1 NOT NULL,
    colspan integer DEFAULT 1 NOT NULL,
    bbox_x0 numeric(7,6),
    bbox_y0 numeric(7,6),
    bbox_x1 numeric(7,6),
    bbox_y1 numeric(7,6),
    text text
);
    """.strip(),
    """
CREATE SEQUENCE table_cell_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
    """.strip(),
    """
ALTER SEQUENCE table_cell_id_seq OWNED BY table_cell.id;
    """.strip(),
    """
ALTER TABLE agent_module_run ALTER COLUMN id SET DEFAULT nextval('agent_module_run_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE agent_run_event ALTER COLUMN id SET DEFAULT nextval('agent_run_event_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE analysis_data_snapshot ALTER COLUMN id SET DEFAULT nextval('analysis_data_snapshot_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE analysis_module ALTER COLUMN id SET DEFAULT nextval('analysis_module_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE analysis_record_review ALTER COLUMN id SET DEFAULT nextval('analysis_record_review_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE analysis_report ALTER COLUMN id SET DEFAULT nextval('analysis_report_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE config_ack ALTER COLUMN id SET DEFAULT nextval('config_ack_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE config_audit ALTER COLUMN id SET DEFAULT nextval('config_audit_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE config_release ALTER COLUMN id SET DEFAULT nextval('config_release_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE document ALTER COLUMN id SET DEFAULT nextval('document_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE document_version ALTER COLUMN id SET DEFAULT nextval('document_version_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE element ALTER COLUMN id SET DEFAULT nextval('element_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE job_config_snapshot ALTER COLUMN id SET DEFAULT nextval('job_config_snapshot_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE knowledge_answer ALTER COLUMN id SET DEFAULT nextval('knowledge_answer_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE knowledge_chunk ALTER COLUMN id SET DEFAULT nextval('knowledge_chunk_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE knowledge_collection ALTER COLUMN id SET DEFAULT nextval('knowledge_collection_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE knowledge_index ALTER COLUMN id SET DEFAULT nextval('knowledge_index_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE knowledge_relation ALTER COLUMN id SET DEFAULT nextval('knowledge_relation_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE knowledge_source ALTER COLUMN id SET DEFAULT nextval('knowledge_source_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE llm_call_log ALTER COLUMN id SET DEFAULT nextval('llm_call_log_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE llm_feature_model ALTER COLUMN id SET DEFAULT nextval('llm_feature_model_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE llm_model ALTER COLUMN id SET DEFAULT nextval('llm_model_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE llm_provider ALTER COLUMN id SET DEFAULT nextval('llm_provider_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE llm_test ALTER COLUMN id SET DEFAULT nextval('llm_test_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE lot ALTER COLUMN id SET DEFAULT nextval('lot_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE page ALTER COLUMN id SET DEFAULT nextval('page_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE parse_run ALTER COLUMN id SET DEFAULT nextval('parse_run_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE project ALTER COLUMN id SET DEFAULT nextval('project_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE project_file ALTER COLUMN id SET DEFAULT nextval('project_file_id_seq'::regclass);
    """.strip(),
    """
ALTER TABLE table_cell ALTER COLUMN id SET DEFAULT nextval('table_cell_id_seq'::regclass);
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.max_inflight', 'L1', 'int', '2', '同公司所有报告共享的 DeepAgents 子代理并发上限', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.max_model_calls', 'L1', 'int', '40', '每模块每次运行的成功模型请求上限，含摘要，协议失败不扣次数', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.max_tool_calls', 'L1', 'int', '48', '每模块每次运行的成功工具执行上限', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.max_evidence_blocks', 'L1', 'int', '160', '每模块保留的原文证据块上限', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.similarity_threshold', 'L1', 'number', '0.6', '专题语义检索的最低余弦相似度（0到1）；关键词独立召回，按命中数参与融合排序', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.max_search_results', 'L1', 'int', '6', '每次专题检索通过阈值后返回的证据块上限', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.rate_limit_backoff_seconds', 'L1', 'int', '30', '上游429未给出恢复时间时的首次等待秒数，后续按倍数递增', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.rate_limit_max_wait_seconds', 'L1', 'int', '600', '单个模块内为上游限流累计等待的上限秒数，超出后按可补跑失败收尾', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.max_subagent_retries', 'L1', 'int', '2', '子Agent本地执行故障的自动恢复上限', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.timeout_seconds', 'L1', 'int', '1800', '单个模块的总时限（非单次请求），恢复不重置', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.context_tokens', 'L1', 'int', '24000', '模块上下文预算，达到百分之八十时压缩', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('analysis.max_output_tokens', 'L1', 'int', '8192', '模块单次模型输出上限', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('convert.max_inflight', 'L1', 'int', '4', '同时在途的 Gotenberg 转换请求数', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('parse.max_inflight', 'L1', 'int', '2', 'MinerU 侧同时处于 queued+running 的 job 数上限，建议不超过 GPU 数 x2', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('dispatch.interval_seconds', 'L1', 'int', '5', '调度器派发间隔；这就是配置改完多久生效的上限', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('job.poll.initial_interval_ms', 'L1', 'int', '2000', 'MinerU 轮询初始间隔（毫秒）', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('job.poll.max_interval_ms', 'L1', 'int', '30000', 'MinerU 轮询最大间隔（毫秒）', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('job.poll.max_attempts', 'L1', 'int', '180', '轮询次数上限，超出视为超时', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('job.timeout.convert_minutes', 'L1', 'int', '10', '转换超时（分钟）', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('job.timeout.parse_minutes', 'L1', 'int', '60', '解析超时（分钟）', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('job.retry.convert_500', 'L1', 'int', '3', 'Gotenberg 5xx 重试次数（400 不重试）', false, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('mineru.tier', 'L2', 'string', '"standard"', 'MinerU 生产固定档；advanced 建议仅由人工对单文档触发', true, now());
    """.strip(),
    """
INSERT INTO config_item (key, layer, value_type, default_value, description, requires_gate, updated_at) VALUES ('mineru.ocr_mode', 'L2', 'string', '"auto"', '逐页自适应；扫描件占比高时可评估改 ocr', true, now());
    """.strip(),
    """
INSERT INTO config_release (id, company_id, version_no, "values", status, based_on, note, created_by, created_at) VALUES (1, 1, 1, '{}', 'active', NULL, '初始化基线（全部取默认值）', 'system:seed', now());
    """.strip(),
    """
INSERT INTO llm_feature (key, name, failover_limit, description, updated_at, max_total_requests, revision) VALUES ('analysis', '智能分析', 3, '', now(), 6, 1);
    """.strip(),
    """
INSERT INTO llm_feature (key, name, failover_limit, description, updated_at, max_total_requests, revision) VALUES ('knowledge_ask', '知识问答', 3, '', now(), 6, 1);
    """.strip(),
    """
INSERT INTO llm_feature (key, name, failover_limit, description, updated_at, max_total_requests, revision) VALUES ('embedding', '语义检索向量', 3, '', now(), 6, 1);
    """.strip(),
    """
INSERT INTO llm_feature (key, name, failover_limit, description, updated_at, max_total_requests, revision) VALUES ('rerank', '检索重排', 3, '对检索候选进行专用重排；未配置时保留混合检索顺序', now(), 6, 1);
    """.strip(),
    """
INSERT INTO llm_feature (key, name, failover_limit, description, updated_at, max_total_requests, revision) VALUES ('image_generation', '图片生成', 3, '图片模型管理、功能绑定与显式测试；不自动生成业务素材', now(), 6, 1);
    """.strip(),
    """
SELECT pg_catalog.setval('agent_module_run_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('agent_run_event_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('analysis_data_snapshot_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('analysis_module_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('analysis_record_review_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('analysis_report_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('config_ack_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('config_audit_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('config_release_id_seq', 1, true);
    """.strip(),
    """
SELECT pg_catalog.setval('document_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('document_version_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('element_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('job_config_snapshot_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('knowledge_answer_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('knowledge_chunk_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('knowledge_collection_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('knowledge_index_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('knowledge_relation_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('knowledge_source_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('llm_call_log_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('llm_feature_model_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('llm_model_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('llm_provider_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('llm_test_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('lot_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('page_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('parse_run_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('project_file_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('project_id_seq', 1, false);
    """.strip(),
    """
SELECT pg_catalog.setval('table_cell_id_seq', 1, false);
    """.strip(),
    """
ALTER TABLE agent_call_attempt
    ADD CONSTRAINT agent_call_attempt_pkey PRIMARY KEY (run_id, kind, call_key);
    """.strip(),
    """
ALTER TABLE agent_model_invocation
    ADD CONSTRAINT agent_model_invocation_pkey PRIMARY KEY (run_id, call_key);
    """.strip(),
    """
ALTER TABLE agent_module_run
    ADD CONSTRAINT agent_module_run_module_id_attempt_key UNIQUE (module_id, attempt);
    """.strip(),
    """
ALTER TABLE agent_module_run
    ADD CONSTRAINT agent_module_run_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE agent_module_run
    ADD CONSTRAINT agent_module_run_thread_id_key UNIQUE (thread_id);
    """.strip(),
    """
ALTER TABLE agent_run_event
    ADD CONSTRAINT agent_run_event_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE analysis_data_snapshot
    ADD CONSTRAINT analysis_data_snapshot_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE analysis_data_snapshot
    ADD CONSTRAINT analysis_data_snapshot_report_id_revision_key UNIQUE (report_id, revision);
    """.strip(),
    """
ALTER TABLE analysis_module
    ADD CONSTRAINT analysis_module_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE analysis_module
    ADD CONSTRAINT analysis_module_report_id_module_key_key UNIQUE (report_id, module_key);
    """.strip(),
    """
ALTER TABLE analysis_record_review
    ADD CONSTRAINT analysis_record_review_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE analysis_report
    ADD CONSTRAINT analysis_report_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE config_ack
    ADD CONSTRAINT config_ack_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE config_ack
    ADD CONSTRAINT config_ack_release_id_item_kind_item_ref_key UNIQUE (release_id, item_kind, item_ref);
    """.strip(),
    """
ALTER TABLE config_audit
    ADD CONSTRAINT config_audit_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE config_item
    ADD CONSTRAINT config_item_pkey PRIMARY KEY (key);
    """.strip(),
    """
ALTER TABLE config_release
    ADD CONSTRAINT config_release_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE document
    ADD CONSTRAINT document_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE document_version
    ADD CONSTRAINT document_version_document_id_version_no_key UNIQUE (document_id, version_no);
    """.strip(),
    """
ALTER TABLE document_version
    ADD CONSTRAINT document_version_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE element
    ADD CONSTRAINT element_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE element
    ADD CONSTRAINT element_run_id_page_no_order_no_key UNIQUE (run_id, page_no, order_no);
    """.strip(),
    """
ALTER TABLE job_config_snapshot
    ADD CONSTRAINT job_config_snapshot_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE job
    ADD CONSTRAINT job_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE knowledge_answer
    ADD CONSTRAINT knowledge_answer_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE knowledge_chunk
    ADD CONSTRAINT knowledge_chunk_index_id_ordinal_key UNIQUE (index_id, ordinal);
    """.strip(),
    """
ALTER TABLE knowledge_chunk
    ADD CONSTRAINT knowledge_chunk_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE knowledge_collection
    ADD CONSTRAINT knowledge_collection_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE knowledge_collection
    ADD CONSTRAINT knowledge_collection_upload_project_id_key UNIQUE (upload_project_id);
    """.strip(),
    """
ALTER TABLE knowledge_index
    ADD CONSTRAINT knowledge_index_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE knowledge_relation
    ADD CONSTRAINT knowledge_relation_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE knowledge_source
    ADD CONSTRAINT knowledge_source_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE knowledge_source
    ADD CONSTRAINT knowledge_source_project_file_id_key UNIQUE (project_file_id);
    """.strip(),
    """
ALTER TABLE llm_call_log
    ADD CONSTRAINT llm_call_log_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE llm_feature_model
    ADD CONSTRAINT llm_feature_model_feature_key_model_id_key UNIQUE (feature_key, model_id);
    """.strip(),
    """
ALTER TABLE llm_feature_model
    ADD CONSTRAINT llm_feature_model_feature_key_priority_key UNIQUE (feature_key, priority);
    """.strip(),
    """
ALTER TABLE llm_feature_model
    ADD CONSTRAINT llm_feature_model_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE llm_feature
    ADD CONSTRAINT llm_feature_pkey PRIMARY KEY (key);
    """.strip(),
    """
ALTER TABLE llm_model
    ADD CONSTRAINT llm_model_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE llm_provider
    ADD CONSTRAINT llm_provider_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE llm_test
    ADD CONSTRAINT llm_test_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE lot
    ADD CONSTRAINT lot_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE page
    ADD CONSTRAINT page_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE page
    ADD CONSTRAINT page_version_id_page_no_key UNIQUE (version_id, page_no);
    """.strip(),
    """
ALTER TABLE parse_run
    ADD CONSTRAINT parse_run_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE project_file
    ADD CONSTRAINT project_file_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE project_knowledge_collection
    ADD CONSTRAINT project_knowledge_collection_pkey PRIMARY KEY (project_id, collection_id);
    """.strip(),
    """
ALTER TABLE project
    ADD CONSTRAINT project_pkey PRIMARY KEY (id);
    """.strip(),
    """
ALTER TABLE table_cell
    ADD CONSTRAINT table_cell_element_id_row_no_col_no_key UNIQUE (element_id, row_no, col_no);
    """.strip(),
    """
ALTER TABLE table_cell
    ADD CONSTRAINT table_cell_pkey PRIMARY KEY (id);
    """.strip(),
    """
CREATE INDEX ix_agent_call_pending ON agent_call_attempt USING btree (run_id, kind, status);
    """.strip(),
    """
CREATE INDEX ix_agent_module_run_active ON agent_module_run USING btree (company_id, status, lease_until);
    """.strip(),
    """
CREATE INDEX ix_agent_run_event_run ON agent_run_event USING btree (run_id, id);
    """.strip(),
    """
CREATE INDEX ix_analysis_data_snapshot_manifest ON analysis_data_snapshot USING btree (report_id, manifest_hash, id DESC);
    """.strip(),
    """
CREATE INDEX ix_analysis_data_snapshot_report ON analysis_data_snapshot USING btree (report_id, id DESC);
    """.strip(),
    """
CREATE INDEX ix_analysis_record_review_latest ON analysis_record_review USING btree (snapshot_id, record_id, id DESC);
    """.strip(),
    """
CREATE INDEX ix_analysis_report_project ON analysis_report USING btree (project_id, id DESC);
    """.strip(),
    """
CREATE INDEX ix_analysis_report_snapshot_pending ON analysis_report USING btree (company_id, id);
    """.strip(),
    """
CREATE INDEX ix_element_anchor ON element USING btree (run_id, anchor);
    """.strip(),
    """
CREATE INDEX ix_element_page ON element USING btree (version_id, page_no, order_no);
    """.strip(),
    """
CREATE INDEX ix_element_text_trgm ON element USING gin (text gin_trgm_ops);
    """.strip(),
    """
CREATE INDEX ix_job_active ON job USING btree (status, created_at) WHERE (status = ANY (ARRAY['pending'::text, 'submitting'::text, 'running'::text]));
    """.strip(),
    """
CREATE INDEX ix_job_dispatch ON job USING btree (stage, created_at) WHERE ((dispatched_at IS NULL) AND (status = 'pending'::text));
    """.strip(),
    """
CREATE INDEX ix_job_project ON job USING btree (project_id, created_at DESC);
    """.strip(),
    """
CREATE INDEX ix_job_recovery ON job USING btree (company_id, next_attempt_at, dispatch_lease_until) WHERE ((finished_at IS NULL) AND (dispatched_at IS NOT NULL));
    """.strip(),
    """
CREATE INDEX ix_knowledge_chunk_index ON knowledge_chunk USING btree (index_id);
    """.strip(),
    """
CREATE INDEX ix_knowledge_chunk_text ON knowledge_chunk USING gin (content gin_trgm_ops);
    """.strip(),
    """
CREATE INDEX ix_knowledge_collection_company ON knowledge_collection USING btree (company_id, id);
    """.strip(),
    """
CREATE INDEX ix_knowledge_index_source ON knowledge_index USING btree (source_id, id DESC);
    """.strip(),
    """
CREATE INDEX ix_knowledge_relation_report ON knowledge_relation USING btree (report_id);
    """.strip(),
    """
CREATE INDEX ix_llm_call_created ON llm_call_log USING btree (created_at DESC);
    """.strip(),
    """
CREATE INDEX ix_llm_call_feature ON llm_call_log USING btree (feature_key, created_at DESC);
    """.strip(),
    """
CREATE UNIQUE INDEX ix_llm_call_invocation ON llm_call_log USING btree (invocation_id, request_ordinal);
    """.strip(),
    """
CREATE INDEX ix_llm_call_model ON llm_call_log USING btree (model_id, created_at DESC);
    """.strip(),
    """
CREATE INDEX ix_llm_test_model ON llm_test USING btree (model_id, created_at DESC);
    """.strip(),
    """
CREATE INDEX ix_project_file ON project_file USING btree (project_id, sort_no) WHERE (deleted_at IS NULL);
    """.strip(),
    """
CREATE INDEX ix_run_status ON parse_run USING btree (status) WHERE (status = ANY (ARRAY['pending'::text, 'running'::text]));
    """.strip(),
    """
CREATE INDEX ix_run_version ON parse_run USING btree (version_id, created_at DESC);
    """.strip(),
    """
CREATE INDEX ix_version_doc ON document_version USING btree (document_id, created_at DESC);
    """.strip(),
    """
CREATE UNIQUE INDEX ux_analysis_report_active ON analysis_report USING btree (project_id) WHERE (status = ANY (ARRAY['waiting'::text, 'pending'::text, 'running'::text]));
    """.strip(),
    """
CREATE UNIQUE INDEX ux_llm_model_active ON llm_model USING btree (provider_id, model_id) WHERE (deleted_at IS NULL);
    """.strip(),
    """
CREATE UNIQUE INDEX ux_llm_provider_name ON llm_provider USING btree (name) WHERE (deleted_at IS NULL);
    """.strip(),
    """
CREATE UNIQUE INDEX ux_release_active ON config_release USING btree (company_id) WHERE (status = 'active'::text);
    """.strip(),
    """
CREATE UNIQUE INDEX ux_run_request_id ON parse_run USING btree (request_id) WHERE (request_id IS NOT NULL);
    """.strip(),
    """
CREATE UNIQUE INDEX ux_version_sha ON document_version USING btree (sha256, converter_version);
    """.strip(),
    """
ALTER TABLE agent_call_attempt
    ADD CONSTRAINT agent_call_attempt_run_id_fkey FOREIGN KEY (run_id) REFERENCES agent_module_run(id) ON DELETE CASCADE;
    """.strip(),
    """
ALTER TABLE agent_model_invocation
    ADD CONSTRAINT agent_model_invocation_run_id_fkey FOREIGN KEY (run_id) REFERENCES agent_module_run(id) ON DELETE CASCADE;
    """.strip(),
    """
ALTER TABLE agent_module_run
    ADD CONSTRAINT agent_module_run_module_id_fkey FOREIGN KEY (module_id) REFERENCES analysis_module(id) ON DELETE CASCADE;
    """.strip(),
    """
ALTER TABLE agent_run_event
    ADD CONSTRAINT agent_run_event_run_id_fkey FOREIGN KEY (run_id) REFERENCES agent_module_run(id) ON DELETE CASCADE;
    """.strip(),
    """
ALTER TABLE analysis_data_snapshot
    ADD CONSTRAINT analysis_data_snapshot_report_id_fkey FOREIGN KEY (report_id) REFERENCES analysis_report(id) ON DELETE CASCADE;
    """.strip(),
    """
ALTER TABLE analysis_module
    ADD CONSTRAINT analysis_module_report_id_fkey FOREIGN KEY (report_id) REFERENCES analysis_report(id) ON DELETE CASCADE;
    """.strip(),
    """
ALTER TABLE analysis_record_review
    ADD CONSTRAINT analysis_record_review_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES analysis_data_snapshot(id) ON DELETE CASCADE;
    """.strip(),
    """
ALTER TABLE analysis_report
    ADD CONSTRAINT analysis_report_project_id_fkey FOREIGN KEY (project_id) REFERENCES project(id);
    """.strip(),
    """
ALTER TABLE config_ack
    ADD CONSTRAINT config_ack_release_id_fkey FOREIGN KEY (release_id) REFERENCES config_release(id);
    """.strip(),
    """
ALTER TABLE config_audit
    ADD CONSTRAINT config_audit_release_id_fkey FOREIGN KEY (release_id) REFERENCES config_release(id);
    """.strip(),
    """
ALTER TABLE config_release
    ADD CONSTRAINT config_release_based_on_fkey FOREIGN KEY (based_on) REFERENCES config_release(id);
    """.strip(),
    """
ALTER TABLE document_version
    ADD CONSTRAINT document_version_document_id_fkey FOREIGN KEY (document_id) REFERENCES document(id);
    """.strip(),
    """
ALTER TABLE element
    ADD CONSTRAINT element_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES element(id);
    """.strip(),
    """
ALTER TABLE element
    ADD CONSTRAINT element_run_id_fkey FOREIGN KEY (run_id) REFERENCES parse_run(id);
    """.strip(),
    """
ALTER TABLE element
    ADD CONSTRAINT element_version_id_fkey FOREIGN KEY (version_id) REFERENCES document_version(id);
    """.strip(),
    """
ALTER TABLE job
    ADD CONSTRAINT job_config_snapshot_id_fkey FOREIGN KEY (config_snapshot_id) REFERENCES job_config_snapshot(id);
    """.strip(),
    """
ALTER TABLE job_config_snapshot
    ADD CONSTRAINT job_config_snapshot_release_id_fkey FOREIGN KEY (release_id) REFERENCES config_release(id);
    """.strip(),
    """
ALTER TABLE job
    ADD CONSTRAINT job_project_file_id_fkey FOREIGN KEY (project_file_id) REFERENCES project_file(id);
    """.strip(),
    """
ALTER TABLE job
    ADD CONSTRAINT job_project_id_fkey FOREIGN KEY (project_id) REFERENCES project(id);
    """.strip(),
    """
ALTER TABLE job
    ADD CONSTRAINT job_run_id_fkey FOREIGN KEY (run_id) REFERENCES parse_run(id);
    """.strip(),
    """
ALTER TABLE job
    ADD CONSTRAINT job_version_id_fkey FOREIGN KEY (version_id) REFERENCES document_version(id);
    """.strip(),
    """
ALTER TABLE knowledge_answer
    ADD CONSTRAINT knowledge_answer_project_id_fkey FOREIGN KEY (project_id) REFERENCES project(id);
    """.strip(),
    """
ALTER TABLE knowledge_chunk
    ADD CONSTRAINT knowledge_chunk_element_id_fkey FOREIGN KEY (element_id) REFERENCES element(id);
    """.strip(),
    """
ALTER TABLE knowledge_chunk
    ADD CONSTRAINT knowledge_chunk_index_id_fkey FOREIGN KEY (index_id) REFERENCES knowledge_index(id) ON DELETE CASCADE;
    """.strip(),
    """
ALTER TABLE knowledge_collection
    ADD CONSTRAINT knowledge_collection_upload_project_id_fkey FOREIGN KEY (upload_project_id) REFERENCES project(id);
    """.strip(),
    """
ALTER TABLE knowledge_index
    ADD CONSTRAINT knowledge_index_embedding_model_id_fkey FOREIGN KEY (embedding_model_id) REFERENCES llm_model(id);
    """.strip(),
    """
ALTER TABLE knowledge_index
    ADD CONSTRAINT knowledge_index_run_id_fkey FOREIGN KEY (run_id) REFERENCES parse_run(id);
    """.strip(),
    """
ALTER TABLE knowledge_index
    ADD CONSTRAINT knowledge_index_source_id_fkey FOREIGN KEY (source_id) REFERENCES knowledge_source(id);
    """.strip(),
    """
ALTER TABLE knowledge_index
    ADD CONSTRAINT knowledge_index_version_id_fkey FOREIGN KEY (version_id) REFERENCES document_version(id);
    """.strip(),
    """
ALTER TABLE knowledge_relation
    ADD CONSTRAINT knowledge_relation_module_id_fkey FOREIGN KEY (module_id) REFERENCES analysis_module(id) ON DELETE CASCADE;
    """.strip(),
    """
ALTER TABLE knowledge_relation
    ADD CONSTRAINT knowledge_relation_report_id_fkey FOREIGN KEY (report_id) REFERENCES analysis_report(id) ON DELETE CASCADE;
    """.strip(),
    """
ALTER TABLE knowledge_source
    ADD CONSTRAINT knowledge_source_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES knowledge_collection(id);
    """.strip(),
    """
ALTER TABLE knowledge_source
    ADD CONSTRAINT knowledge_source_project_file_id_fkey FOREIGN KEY (project_file_id) REFERENCES project_file(id);
    """.strip(),
    """
ALTER TABLE llm_call_log
    ADD CONSTRAINT llm_call_log_model_id_fkey FOREIGN KEY (model_id) REFERENCES llm_model(id);
    """.strip(),
    """
ALTER TABLE llm_call_log
    ADD CONSTRAINT llm_call_log_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES llm_provider(id);
    """.strip(),
    """
ALTER TABLE llm_feature_model
    ADD CONSTRAINT llm_feature_model_feature_key_fkey FOREIGN KEY (feature_key) REFERENCES llm_feature(key);
    """.strip(),
    """
ALTER TABLE llm_feature_model
    ADD CONSTRAINT llm_feature_model_model_id_fkey FOREIGN KEY (model_id) REFERENCES llm_model(id);
    """.strip(),
    """
ALTER TABLE llm_model
    ADD CONSTRAINT llm_model_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES llm_provider(id);
    """.strip(),
    """
ALTER TABLE llm_test
    ADD CONSTRAINT llm_test_call_log_id_fkey FOREIGN KEY (call_log_id) REFERENCES llm_call_log(id);
    """.strip(),
    """
ALTER TABLE llm_test
    ADD CONSTRAINT llm_test_model_id_fkey FOREIGN KEY (model_id) REFERENCES llm_model(id);
    """.strip(),
    """
ALTER TABLE llm_test
    ADD CONSTRAINT llm_test_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES llm_provider(id);
    """.strip(),
    """
ALTER TABLE lot
    ADD CONSTRAINT lot_project_id_fkey FOREIGN KEY (project_id) REFERENCES project(id);
    """.strip(),
    """
ALTER TABLE page
    ADD CONSTRAINT page_version_id_fkey FOREIGN KEY (version_id) REFERENCES document_version(id);
    """.strip(),
    """
ALTER TABLE parse_run
    ADD CONSTRAINT parse_run_version_id_fkey FOREIGN KEY (version_id) REFERENCES document_version(id);
    """.strip(),
    """
ALTER TABLE project_file
    ADD CONSTRAINT project_file_project_id_fkey FOREIGN KEY (project_id) REFERENCES project(id);
    """.strip(),
    """
ALTER TABLE project_file
    ADD CONSTRAINT project_file_replaces_id_fkey FOREIGN KEY (replaces_id) REFERENCES project_file(id);
    """.strip(),
    """
ALTER TABLE project_file
    ADD CONSTRAINT project_file_version_id_fkey FOREIGN KEY (version_id) REFERENCES document_version(id);
    """.strip(),
    """
ALTER TABLE project_knowledge_collection
    ADD CONSTRAINT project_knowledge_collection_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES knowledge_collection(id);
    """.strip(),
    """
ALTER TABLE project_knowledge_collection
    ADD CONSTRAINT project_knowledge_collection_project_id_fkey FOREIGN KEY (project_id) REFERENCES project(id);
    """.strip(),
    """
ALTER TABLE table_cell
    ADD CONSTRAINT table_cell_element_id_fkey FOREIGN KEY (element_id) REFERENCES element(id);
    """.strip(),
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    raise RuntimeError("数据库基线回退请恢复备份")
