"""下线字段抽取、复核与金标回放；历史迁移保留用于已有环境顺序升级。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_retire_extraction"
down_revision = "0012_config_limits"
branch_labels = None
depends_on = None

_STATEMENTS: tuple[str, ...] = (
    """UPDATE job SET status = 'canceled', error_code = 'feature_retired',
    error_message = '字段抽取流程已下线，请使用项目 Agent 分析',
    dispatched_at = NULL, finished_at = now(), updated_at = now()
WHERE stage IN ('extracting', 'exporting')
  AND status NOT IN ('completed', 'partial', 'failed', 'canceled');""",
    """DELETE FROM llm_feature_model WHERE feature_key IN ('extract', 'retry');""",
    """DELETE FROM llm_feature WHERE key IN ('extract', 'retry');""",
    """DELETE FROM config_item WHERE key LIKE 'extract.%';""",
    """INSERT INTO config_item
    (key, layer, value_type, default_value, description, requires_gate)
VALUES
    ('queue.priority.batch', 'L1', 'string', '"low"'::jsonb, '批量任务的队列优先级', false),
    ('render.crop_dpi', 'L2', 'int', '300'::jsonb, '页面裁剪图 DPI', true)
ON CONFLICT (key) DO UPDATE SET description = EXCLUDED.description;""",
    """ALTER TABLE llm_call_log DROP COLUMN extraction_id;""",
    """ALTER TABLE config_release DROP COLUMN regression_run_id;""",
    """ALTER TABLE field_instance DROP CONSTRAINT fk_field_instance_current_extraction;""",
    # 不使用 CASCADE：若现场还有未识别依赖，必须整笔回滚，不能误删其它业务。
    """DROP TABLE review_task;""",
    """DROP TABLE review_action;""",
    """DROP TABLE evidence;""",
    """DROP TABLE extraction_conflict;""",
    """DROP TABLE gold_item;""",
    """DROP TABLE extraction;""",
    """DROP TABLE field_instance;""",
    """DROP TABLE regression_run;""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # 重新建空表会伪装成可逆迁移，但无法还原复核记录；恢复必须使用迁移前备份。
    raise RuntimeError("字段抽取历史数据已移除，请使用迁移前数据库备份恢复")
