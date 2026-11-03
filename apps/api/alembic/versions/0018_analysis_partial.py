"""模块运行账接受 partial 终态：校验不可用时部分发布已核实成果。"""

import sqlalchemy as sa
from alembic import op

revision = "0018_analysis_partial"
down_revision = "0017_document_recovery"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """ALTER TABLE agent_module_run DROP CONSTRAINT agent_module_run_status_check,
        ADD CONSTRAINT agent_module_run_status_check CHECK (
            status IN ('pending','running','completed','failed','canceled','partial')
        );""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # 先回填不可识别状态，避免旧约束拒绝已有行；partial 运行已发布成果仍可读取。
    op.execute(sa.text(
        "UPDATE agent_module_run SET status='failed' WHERE status='partial'"
    ))
    op.execute(sa.text(
        """ALTER TABLE agent_module_run DROP CONSTRAINT agent_module_run_status_check,
        ADD CONSTRAINT agent_module_run_status_check CHECK (
            status IN ('pending','running','completed','failed','canceled')
        );"""
    ))
