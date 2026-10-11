"""业务解析成果与不可变快照；历史展示数据不作语义回填。"""

import sqlalchemy as sa
from alembic import op

revision = "0011_analysis_data"
down_revision = "0010_analysis_guards"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """ALTER TABLE analysis_module ADD COLUMN business_data JSONB NOT NULL DEFAULT '{}';""",
    """ALTER TABLE analysis_report ADD COLUMN derived_lot_ids BIGINT[] NOT NULL DEFAULT '{}';""",
    """CREATE TABLE analysis_data_snapshot (
    id BIGSERIAL PRIMARY KEY,
    report_id BIGINT NOT NULL REFERENCES analysis_report(id) ON DELETE CASCADE,
    revision INT NOT NULL,
    schema_version TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    input_snapshot JSONB NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_id, revision),
    UNIQUE (report_id, manifest_hash)
);
CREATE INDEX ix_analysis_data_snapshot_report ON analysis_data_snapshot (report_id, id DESC);""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    raise RuntimeError("解析数据快照可能已被下游引用，请从备份回滚")
