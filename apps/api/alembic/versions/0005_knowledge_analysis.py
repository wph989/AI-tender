"""知识集合、可版本化检索和项目综合报告；来源仍使用现有 PDF 坐标基座。"""

import sqlalchemy as sa
from alembic import op

revision = "0005_knowledge_analysis"
down_revision = "0004_config_center"
branch_labels = None
depends_on = None

_STATEMENTS = (
    "ALTER TABLE project ADD COLUMN kind TEXT NOT NULL DEFAULT 'project';",
    "ALTER TABLE project ADD COLUMN analysis_category TEXT;",
    "ALTER TABLE project ADD COLUMN analysis_topics JSONB NOT NULL DEFAULT '[]';",
    "ALTER TABLE lot ADD COLUMN analysis_category TEXT;",
    "ALTER TABLE lot ADD COLUMN analysis_topics JSONB;",
    """CREATE TABLE knowledge_collection (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('tender','company','history','reference')),
    upload_project_id BIGINT NOT NULL UNIQUE REFERENCES project(id),
    is_project BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX ix_knowledge_collection_company ON knowledge_collection (company_id, id);""",
    """CREATE TABLE project_knowledge_collection (
    project_id BIGINT NOT NULL REFERENCES project(id),
    collection_id BIGINT NOT NULL REFERENCES knowledge_collection(id),
    PRIMARY KEY (project_id, collection_id)
);""",
    """CREATE TABLE knowledge_source (
    id BIGSERIAL PRIMARY KEY,
    collection_id BIGINT NOT NULL REFERENCES knowledge_collection(id),
    project_file_id BIGINT NOT NULL UNIQUE REFERENCES project_file(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);""",
    """CREATE TABLE knowledge_index (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES knowledge_source(id),
    version_id BIGINT NOT NULL REFERENCES document_version(id),
    run_id BIGINT NOT NULL REFERENCES parse_run(id),
    embedding_model_id BIGINT REFERENCES llm_model(id),
    embedding_signature TEXT,
    dimension INT,
    chunk_version TEXT NOT NULL DEFAULT '1',
    status TEXT NOT NULL DEFAULT 'pending',
    lease_until TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX ix_knowledge_index_source ON knowledge_index (source_id, id DESC);""",
    """CREATE TABLE knowledge_chunk (
    id BIGSERIAL PRIMARY KEY,
    index_id BIGINT NOT NULL REFERENCES knowledge_index(id) ON DELETE CASCADE,
    element_id BIGINT NOT NULL REFERENCES element(id),
    ordinal INT NOT NULL,
    char_start INT NOT NULL,
    char_end INT NOT NULL,
    chapter TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    embedding DOUBLE PRECISION[],
    UNIQUE (index_id, ordinal)
);
CREATE INDEX ix_knowledge_chunk_index ON knowledge_chunk (index_id);
CREATE INDEX ix_knowledge_chunk_text ON knowledge_chunk USING gin (content gin_trgm_ops);""",
    """CREATE TABLE analysis_report (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES project(id),
    company_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'waiting',
    lease_until TIMESTAMPTZ,
    allow_partial BOOLEAN NOT NULL DEFAULT false,
    category TEXT NOT NULL,
    topics JSONB NOT NULL DEFAULT '[]',
    lot_settings JSONB NOT NULL DEFAULT '[]',
    source_snapshot JSONB NOT NULL DEFAULT '[]',
    coverage JSONB NOT NULL DEFAULT '{}',
    skill_version TEXT NOT NULL,
    skill_snapshot JSONB NOT NULL DEFAULT '{}',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX ix_analysis_report_project ON analysis_report (project_id, id DESC);
CREATE UNIQUE INDEX ux_analysis_report_active ON analysis_report (project_id)
WHERE status IN ('waiting','pending','running');""",
    """CREATE TABLE analysis_module (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL REFERENCES analysis_report(id) ON DELETE CASCADE,
    module_key TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    items JSONB NOT NULL DEFAULT '[]',
    trace JSONB NOT NULL DEFAULT '[]',
    error_message TEXT,
    UNIQUE (report_id, module_key)
);""",
    """CREATE TABLE knowledge_relation (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL REFERENCES analysis_report(id) ON DELETE CASCADE,
    module_id BIGINT NOT NULL REFERENCES analysis_module(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT '',
    condition TEXT NOT NULL DEFAULT '',
    citations JSONB NOT NULL,
    verified BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX ix_knowledge_relation_report ON knowledge_relation (report_id);""",
    """CREATE TABLE knowledge_answer (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL,
    project_id BIGINT REFERENCES project(id),
    collection_ids JSONB NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    snapshot JSONB NOT NULL DEFAULT '{}',
    lease_until TIMESTAMPTZ,
    items JSONB NOT NULL DEFAULT '[]',
    relations JSONB NOT NULL DEFAULT '[]',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);""",
    """INSERT INTO knowledge_collection (company_id, name, purpose, upload_project_id, is_project)
SELECT company_id, name, 'tender', id, true FROM project WHERE deleted_at IS NULL;
INSERT INTO knowledge_source (collection_id, project_file_id)
SELECT k.id, f.id FROM knowledge_collection k JOIN project_file f ON f.project_id = k.upload_project_id
WHERE f.deleted_at IS NULL;""",
    """INSERT INTO llm_feature (key, name) VALUES
('analysis', '智能分析'), ('knowledge_ask', '知识问答'), ('embedding', '语义检索向量')
ON CONFLICT (key) DO NOTHING;""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    for table in (
        "knowledge_answer",
        "knowledge_relation",
        "analysis_module",
        "analysis_report",
        "knowledge_chunk",
        "knowledge_index",
        "knowledge_source",
        "project_knowledge_collection",
        "knowledge_collection",
    ):
        op.execute(sa.text(f"DROP TABLE {table}"))
    for table, columns in (
        ("lot", ("analysis_category", "analysis_topics")),
        ("project", ("kind", "analysis_category", "analysis_topics")),
    ):
        for column in columns:
            op.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN {column}"))
    op.execute(
        sa.text("DELETE FROM llm_feature WHERE key IN ('analysis','knowledge_ask','embedding')")
    )
