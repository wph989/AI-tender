"""阶段 1 API 所需的对象元数据与持久解析任务。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_storage_and_jobs"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


_STATEMENTS: tuple[str, ...] = (
    """ALTER TABLE project_file ADD COLUMN original_key TEXT;""",
    """ALTER TABLE project_file ADD COLUMN sha256 CHAR(64);""",
    """ALTER TABLE project_file ADD COLUMN mime TEXT;""",
    """ALTER TABLE project_file ADD COLUMN size_bytes BIGINT;""",
    """UPDATE project_file AS pf
SET original_key = dv.original_key,
    sha256 = dv.sha256,
    mime = dv.mime,
    size_bytes = dv.size_bytes
FROM document_version AS dv
WHERE pf.version_id = dv.id
  AND pf.original_key IS NULL;""",
    """ALTER TABLE parse_run ADD COLUMN provider_job_id TEXT;""",
    """ALTER TABLE parse_run ADD COLUMN config_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;""",
    """CREATE UNIQUE INDEX ux_run_request_id ON parse_run (request_id)
WHERE request_id IS NOT NULL;""",
    """CREATE TABLE job (
    id              TEXT PRIMARY KEY,
    company_id      BIGINT      NOT NULL DEFAULT 1,
    project_id      BIGINT      NOT NULL REFERENCES project(id),
    project_file_id BIGINT      NOT NULL REFERENCES project_file(id),
    version_id      BIGINT      REFERENCES document_version(id),
    run_id          BIGINT      REFERENCES parse_run(id),
    status          TEXT        NOT NULL DEFAULT 'pending',
    stage           TEXT        NOT NULL,
    progress        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    config_snapshot JSONB       NOT NULL DEFAULT '{}'::jsonb,
    error_code      TEXT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);""",
    """CREATE INDEX ix_job_project ON job (project_id, created_at DESC);""",
    """CREATE INDEX ix_job_active ON job (status, created_at)
WHERE status IN ('pending','submitting','running');""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_job_active"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_job_project"))
    op.execute(sa.text("DROP TABLE IF EXISTS job"))
    op.execute(sa.text("DROP INDEX IF EXISTS ux_run_request_id"))
    op.execute(sa.text("ALTER TABLE parse_run DROP COLUMN IF EXISTS config_snapshot"))
    op.execute(sa.text("ALTER TABLE parse_run DROP COLUMN IF EXISTS provider_job_id"))
    op.execute(sa.text("ALTER TABLE project_file DROP COLUMN IF EXISTS size_bytes"))
    op.execute(sa.text("ALTER TABLE project_file DROP COLUMN IF EXISTS mime"))
    op.execute(sa.text("ALTER TABLE project_file DROP COLUMN IF EXISTS sha256"))
    op.execute(sa.text("ALTER TABLE project_file DROP COLUMN IF EXISTS original_key"))
