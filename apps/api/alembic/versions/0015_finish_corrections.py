"""登记收尾纠正额度，避免隐含的两轮限制早于用户配置的运行预算终止。"""

import sqlalchemy as sa
from alembic import op

revision = "0015_finish_corrections"
down_revision = "0014_analysis_retrieval"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.max_finish_corrections', 'L1', 'int', '2'::jsonb, '进入收尾后允许的连续无进展纠正轮数，耗尽时保留已核实成果并终止', false);""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # 只删除页面登记项，历史运行快照里的纠正额度仍须保留。
    op.execute(sa.text("DELETE FROM config_item WHERE key='analysis.max_finish_corrections';"))
