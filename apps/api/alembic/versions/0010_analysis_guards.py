"""解析防循环配置；只增加配置定义，不覆盖活动发布或历史运行快照。"""

import sqlalchemy as sa
from alembic import op

revision = "0010_analysis_guards"
down_revision = "0009_provider_cooldown"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.max_tool_failures', 'L1', 'int', '3'::jsonb, '工具连续失败上限，按工具及全局分别计数', false),
('analysis.max_no_progress_rounds', 'L1', 'int', '3'::jsonb, '无新增证据或有效成果的轮数，达到后收尾', false),
('analysis.max_identical_tool_calls', 'L1', 'int', '3'::jsonb, '同一工具与参数的累计调用上限', false),
('analysis.max_validation_failures', 'L1', 'int', '3'::jsonb, '同一事实校验失败上限，含首次失败', false),
('analysis.max_subagent_retries', 'L1', 'int', '2'::jsonb, '子Agent本地执行故障的自动恢复上限', false);""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # 已发布版本和历史运行可能引用这些键，删除会破坏审计与重放。
    raise RuntimeError("解析护栏配置可能已被发布引用，请从备份回滚")
