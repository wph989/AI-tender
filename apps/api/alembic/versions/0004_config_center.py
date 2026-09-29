"""配置中心：配置项种子、基线 release 与调度器所需的 job 列（设计文档 08）。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_config_center"
down_revision = "0003_llm_management"
branch_labels = None
depends_on = None


_SEED_ITEMS = """INSERT INTO config_item
    (key, layer, value_type, default_value, description, requires_gate)
VALUES
    ('convert.max_inflight', 'L1', 'int', '4'::jsonb, '同时在途的 Gotenberg 转换请求数', false),
    ('parse.max_inflight', 'L1', 'int', '2'::jsonb, 'MinerU 侧同时处于 queued+running 的 job 数上限，建议不超过 GPU 数 x2', false),
    ('extract.max_inflight', 'L1', 'int', '8'::jsonb, '同时在途的 LLM 抽取请求数', false),
    ('dispatch.interval_seconds', 'L1', 'int', '5'::jsonb, '调度器派发间隔；这就是配置改完多久生效的上限', false),
    ('job.poll.initial_interval_ms', 'L1', 'int', '2000'::jsonb, 'MinerU 轮询初始间隔（毫秒）', false),
    ('job.poll.max_interval_ms', 'L1', 'int', '30000'::jsonb, 'MinerU 轮询最大间隔（毫秒）', false),
    ('job.poll.max_attempts', 'L1', 'int', '180'::jsonb, '轮询次数上限，超出视为超时', false),
    ('job.timeout.convert_minutes', 'L1', 'int', '10'::jsonb, '转换超时（分钟）', false),
    ('job.timeout.parse_minutes', 'L1', 'int', '60'::jsonb, '解析超时（分钟）', false),
    ('job.retry.convert_500', 'L1', 'int', '3'::jsonb, 'Gotenberg 5xx 重试次数（400 不重试）', false),
    ('queue.priority.batch', 'L1', 'string', '"low"'::jsonb, '回归回放与批量任务的队列优先级', false),
    ('mineru.tier', 'L2', 'string', '"standard"'::jsonb, 'MinerU 生产固定档；advanced 建议仅由人工对单文档触发', true),
    ('mineru.ocr_mode', 'L2', 'string', '"auto"'::jsonb, '逐页自适应；扫描件占比高时可评估改 ocr', true),
    ('mineru.output_formats', 'L2', 'json', '["middle_json", "zip"]'::jsonb, '需要的输出格式；ZIP 默认不下载，按需获取', true),
    ('mineru.page_range', 'L2', 'string', '"all"'::jsonb, '解析页码范围，必须为 all，否则 title_leveling 失效', true),
    ('render.crop_dpi', 'L2', 'int', '300'::jsonb, '多模态字段裁剪图 DPI', true),
    ('llm_aided.title_leveling', 'L2', 'bool', 'true'::jsonb, '章节树构建依赖的标题分级', true),
    ('llm_aided.cross_page_table_cell_merge', 'L2', 'bool', 'true'::jsonb, '跨页表格单元格合并', true),
    ('preprocess.deskew', 'L2', 'bool', 'true'::jsonb, '扫描件纠偏', true),
    ('preprocess.denoise', 'L2', 'bool', 'true'::jsonb, '扫描件去噪', true),
    ('preprocess.min_dpi', 'L2', 'int', '300'::jsonb, '低于此值的扫描件先升采样', true),
    ('extract.strategy.dual_route', 'L3', 'bool', 'true'::jsonb, '规则 + LLM 双路投票', true),
    ('extract.strategy.second_pass', 'L3', 'bool', 'true'::jsonb, '低置信字段二次抽取', true),
    ('extract.strategy.multimodal', 'L3', 'bool', 'false'::jsonb, '多模态直读开关（仅表格类字段与扫描件生效）', true),
    ('extract.scope.per_lot', 'L3', 'bool', 'true'::jsonb, '按标段分组输出适用范围', true),
    ('extract.rerun.hide_threshold', 'L3', 'number', '0.10'::jsonb, '第 2 次机器结果的救回率低于此值时收起重跑按钮', true),
    ('extract.rerun.min_sample', 'L3', 'int', '30'::jsonb, '判定重跑按钮所需的最小样本量', true)
ON CONFLICT (key) DO NOTHING;"""

# 基线 release 让"激活之前创建的任务"也有 release 可挂快照；
# values 为空对象表示全部取 config_item 的默认值（解析规则见 tender/config/schema.resolve_values）。
_SEED_BASELINE = """INSERT INTO config_release
    (company_id, version_no, values, status, note, created_by)
SELECT 1, 1, '{}'::jsonb, 'active', '初始化基线（全部取默认值）', 'system:seed'
WHERE NOT EXISTS (SELECT 1 FROM config_release WHERE company_id = 1);"""

_STATEMENTS: tuple[str, ...] = (
    """ALTER TABLE job ADD COLUMN dispatched_at TIMESTAMPTZ;""",
    """ALTER TABLE job ADD COLUMN config_snapshot_id BIGINT REFERENCES job_config_snapshot(id);""",
    """CREATE INDEX ix_job_dispatch ON job (stage, created_at)
WHERE dispatched_at IS NULL AND status = 'pending';""",
    _SEED_ITEMS,
    _SEED_BASELINE,
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_job_dispatch"))
    op.execute(sa.text("ALTER TABLE job DROP COLUMN IF EXISTS config_snapshot_id"))
    op.execute(sa.text("ALTER TABLE job DROP COLUMN IF EXISTS dispatched_at"))
    # 种子数据保留：job_config_snapshot 可能已引用基线 release，删掉会让历史任务失去配置归属；
    # config_item 只是元数据，留着不影响旧代码。
