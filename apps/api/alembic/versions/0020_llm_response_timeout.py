"""文本生成按增量间隔计时，功能绑定只限制次数，模型测试按活性续租。"""

import sqlalchemy as sa
from alembic import op

revision = "0020_llm_response_timeout"
down_revision = "0019_analysis_success_budget"
branch_labels = None
depends_on = None

_STATEMENTS = (
    # 旧NUMERIC(6,1)会将较小正数舍入为0；用浮点存储统一接受有限正数。
    """ALTER TABLE llm_model ALTER COLUMN timeout_seconds TYPE DOUBLE PRECISION
    USING timeout_seconds::double precision;""",
    """ALTER TABLE llm_model ADD CONSTRAINT llm_model_timeout_seconds_check
    CHECK (timeout_seconds > 0 AND timeout_seconds < 'Infinity'::float8);""",
    """ALTER TABLE llm_model ADD COLUMN total_timeout_seconds DOUBLE PRECISION
    CHECK (total_timeout_seconds IS NULL OR
           (total_timeout_seconds > 0 AND total_timeout_seconds < 'Infinity'::float8
            AND kind = 'language'));""",
    """ALTER TABLE llm_feature DROP COLUMN deadline_seconds;""",
    """ALTER TABLE llm_test ADD COLUMN heartbeat_at TIMESTAMPTZ;""",
    """COMMENT ON COLUMN llm_model.timeout_seconds IS
    '文本模型为有效增量响应间隔；非文本模型仍为请求总超时。已有数值保持，新文本模型由应用默认10秒';""",
    """COMMENT ON COLUMN llm_model.total_timeout_seconds IS
    '文本模型单次请求总时限，NULL表示关闭';""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # 已删除的自定义窗口时限无法重建；回滚前须从部署备份恢复配置。
    raise RuntimeError("功能绑定旧时限已取消，请从部署备份回滚")
