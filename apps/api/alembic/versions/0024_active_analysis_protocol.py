"""将活跃报告的唯一性限定在同一执行协议内，保留退役报告原状。"""

from alembic import op

revision = "0024_active_analysis_protocol"
down_revision = "0023_reviewed_analysis"
branch_labels = None
depends_on = None


_STATEMENTS = (
    # 退役协议可能留下活跃状态，同一项目仍可发起当前协议的分析。
    "DROP INDEX ux_analysis_report_active;",
    """
        CREATE UNIQUE INDEX ux_analysis_report_active ON analysis_report
        (project_id, runtime_version, (coalesce(skill_snapshot ->> '__analysis_flow_version__', '')))
        WHERE status IN ('waiting', 'pending', 'running');
    """,
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    raise RuntimeError("不同协议可能已有并行历史记录，请使用升级前备份恢复")
