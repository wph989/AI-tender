"""移除预算人工上限，并登记可调整的分析证据块预算。"""

import sqlalchemy as sa
from alembic import op

revision = "0012_config_limits"
down_revision = "0011_analysis_data"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """ALTER TABLE llm_model DROP CONSTRAINT llm_model_extra_retries_check,
        ADD CONSTRAINT llm_model_extra_retries_check CHECK (extra_retries >= 0);""",
    """ALTER TABLE llm_feature DROP CONSTRAINT llm_feature_max_total_requests_check,
        DROP CONSTRAINT llm_feature_deadline_seconds_check,
        ADD CONSTRAINT llm_feature_max_total_requests_check CHECK (max_total_requests >= 1),
        ADD CONSTRAINT llm_feature_deadline_seconds_check CHECK (deadline_seconds >= 1);""",
    """INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.max_evidence_blocks', 'L1', 'int', '160'::jsonb, '每模块保留的原文证据块上限', false);""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # 发布和运行快照可能已引用新键或大预算，自动收窄会破坏历史可复现性。
    raise RuntimeError("新配置可能已被发布引用，请从备份回滚")
