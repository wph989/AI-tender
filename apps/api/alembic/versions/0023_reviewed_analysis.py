"""让报告快照可补发，并保存与快照绑定的人工复核记录。"""

import sqlalchemy as sa
from alembic import op

revision = "0023_reviewed_analysis"
down_revision = "0022_retrieval_semantics"
branch_labels = None
depends_on = None

_STATEMENTS = (
    # 资料 A→B→A 也需新身份，防止复用第一次 A 的人工确认。
    """ALTER TABLE analysis_data_snapshot DROP CONSTRAINT analysis_data_snapshot_report_id_manifest_hash_key;""",
    """CREATE INDEX ix_analysis_data_snapshot_manifest ON analysis_data_snapshot (report_id, manifest_hash, id DESC);""",
    """ALTER TABLE analysis_report ADD COLUMN snapshot_pending BOOLEAN NOT NULL DEFAULT FALSE;""",
    """CREATE INDEX ix_analysis_report_snapshot_pending ON analysis_report (company_id, id);""",
    """CREATE TABLE analysis_record_review (
    id            BIGSERIAL PRIMARY KEY,
    snapshot_id   BIGINT NOT NULL REFERENCES analysis_data_snapshot(id) ON DELETE CASCADE,
    record_id     TEXT NOT NULL,
    actor         TEXT NOT NULL,
    decision      TEXT NOT NULL CHECK (decision IN ('confirmed', 'corrected', 'rejected')),
    note          TEXT NOT NULL,
    corrected_text TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((decision = 'corrected') = (corrected_text IS NOT NULL))
);""",
    """CREATE INDEX ix_analysis_record_review_latest ON analysis_record_review
(snapshot_id, record_id, id DESC);""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))
    # 旧版已经结束却没有快照的报告也进入补发扫描；已有快照仍保留历史身份。
    op.execute(sa.text("""UPDATE analysis_report AS r SET snapshot_pending = TRUE
WHERE r.runtime_version IN ('deepagents-0.7.22-v5-records', 'deepagents-0.7.22-v6-records')
  AND r.status IN ('completed', 'partial', 'failed', 'canceled')
  AND NOT EXISTS (SELECT 1 FROM analysis_data_snapshot s WHERE s.report_id = r.id);"""))


def downgrade() -> None:
    # 人工裁定没有等价的旧版存储，降级不能静默丢弃它们。
    raise RuntimeError("人工复核记录需保留，请使用升级前的备份恢复")
