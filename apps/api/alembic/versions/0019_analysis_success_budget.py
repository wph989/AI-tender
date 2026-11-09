"""成功额度与调用窗口单独持久化，避免恢复和回执重放重新扣费或重获额度。"""

import sqlalchemy as sa
from alembic import op

revision = "0019_analysis_success_budget"
down_revision = "0018_analysis_partial"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """ALTER TABLE agent_module_run
    ADD COLUMN successful_model_calls INT CHECK (successful_model_calls >= 0),
    ADD COLUMN successful_tool_calls INT CHECK (successful_tool_calls >= 0);""",
    """CREATE TABLE agent_call_attempt (
    run_id INT NOT NULL REFERENCES agent_module_run(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('model','tool')),
    call_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','ok','error','unknown','skipped')),
    detail JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id,kind,call_key)
    );
    CREATE INDEX ix_agent_call_pending ON agent_call_attempt (run_id,kind,status);""",
    """CREATE TABLE agent_model_invocation (
    run_id INT NOT NULL REFERENCES agent_module_run(id) ON DELETE CASCADE,
    call_key TEXT NOT NULL,
    progress JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id,call_key)
    );""",
    """INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
    ('analysis.max_model_calls', 'L1', 'int', '40'::jsonb, '每模块每次运行的成功模型请求上限，含摘要，协议失败不扣次数', false),
    ('analysis.max_tool_calls', 'L1', 'int', '48'::jsonb, '每模块每次运行的成功工具执行上限', false),
    ('analysis.max_review_repairs', 'L1', 'int', '1'::jsonb, '完整审查后的自动修复及定向复核上限，0表示不自动修复', false),
    ('analysis.review_max_input_tokens', 'L1', 'int', '12000'::jsonb, '审查单包完整输入的估算token上限，包含规则、正文、引文及依赖', false)
    ON CONFLICT (key) DO UPDATE SET description=EXCLUDED.description;""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    raise RuntimeError("调用结算记录不可丢弃，请从备份回滚")
