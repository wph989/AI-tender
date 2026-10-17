"""登记上游限流等待参数，避免固定30秒冷却撑不过供应商的分钟级配额窗口。"""

import sqlalchemy as sa
from alembic import op

revision = "0016_rate_limit_wait"
down_revision = "0015_finish_corrections"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.rate_limit_backoff_seconds', 'L1', 'int', '30'::jsonb, '上游429未给出恢复时间时的首次等待秒数，后续按倍数递增', false);""",
    """INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.rate_limit_max_wait_seconds', 'L1', 'int', '600'::jsonb, '单个模块内为上游限流累计等待的上限秒数，超出后按可补跑失败收尾', false);""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # 只删除页面登记项，历史运行快照里的等待上限仍须保留。
    op.execute(sa.text(
        "DELETE FROM config_item WHERE key IN ("
        "'analysis.rate_limit_backoff_seconds','analysis.rate_limit_max_wait_seconds');"
    ))
