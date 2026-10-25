"""文档任务的下一执行时间与消息租约；队列丢消息后仍能从数据库恢复。"""

import sqlalchemy as sa
from alembic import op

revision = "0017_document_recovery"
down_revision = "0016_rate_limit_wait"
branch_labels = None
depends_on = None

_STATEMENTS = (
    "ALTER TABLE job ADD COLUMN next_attempt_at TIMESTAMPTZ;",
    "ALTER TABLE job ADD COLUMN dispatch_lease_until TIMESTAMPTZ;",
    """CREATE INDEX ix_job_recovery ON job (company_id, next_attempt_at, dispatch_lease_until)
        WHERE finished_at IS NULL AND dispatched_at IS NOT NULL;""",
)


def upgrade() -> None:
    # 老任务没有消息租约，首次扫描即可恢复；活跃执行者仍由既有会话锁保护。
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.drop_index("ix_job_recovery", table_name="job")
    op.drop_column("job", "dispatch_lease_until")
    op.drop_column("job", "next_attempt_at")
