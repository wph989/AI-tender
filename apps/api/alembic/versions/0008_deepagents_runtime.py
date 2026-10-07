"""DeepAgents 运行记录与隔离的 checkpoint 空间；不改写历史报告快照。"""

import sqlalchemy as sa
from alembic import op

revision = "0008_deepagents_runtime"
down_revision = "0007_model_inputs"
branch_labels = None
depends_on = None

_STATEMENTS = (
    "CREATE SCHEMA agent_runtime;",
    "REVOKE ALL ON SCHEMA agent_runtime FROM PUBLIC;",
    """ALTER TABLE analysis_report
    ADD COLUMN runtime_version TEXT NOT NULL DEFAULT 'legacy',
    ADD COLUMN runtime_settings JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN reference_snapshot JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN summary JSONB NOT NULL DEFAULT '[]';""",
    """CREATE TABLE agent_module_run (
    id SERIAL PRIMARY KEY,
    module_id BIGINT NOT NULL REFERENCES analysis_module(id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL,
    attempt INT NOT NULL DEFAULT 1 CHECK (attempt > 0),
    thread_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','completed','failed','canceled')),
    owner UUID,
    lease_until TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    deadline_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    model_calls INT NOT NULL DEFAULT 0 CHECK (model_calls >= 0),
    tool_calls INT NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
    prompt_tokens BIGINT NOT NULL DEFAULT 0,
    completion_tokens BIGINT NOT NULL DEFAULT 0,
    limits JSONB NOT NULL,
    state JSONB NOT NULL DEFAULT '{}',
    error_message TEXT,
    UNIQUE (module_id, attempt)
);
CREATE INDEX ix_agent_module_run_active ON agent_module_run (company_id, status, lease_until);""",
    """CREATE TABLE agent_run_event (
    id BIGSERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES agent_module_run(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_run_event_run ON agent_run_event (run_id, id);""",
    """INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.max_inflight', 'L1', 'int', '2'::jsonb, '同公司所有报告共享的 DeepAgents 子代理并发上限', false),
('analysis.max_model_calls', 'L1', 'int', '32'::jsonb, '每模块每次运行的实际模型请求上限，含重试和摘要', false),
('analysis.max_tool_calls', 'L1', 'int', '48'::jsonb, '每模块每次运行的工具调用上限', false),
('analysis.timeout_seconds', 'L1', 'int', '900'::jsonb, '模块从首次执行开始的总时限，恢复不重置', false),
('analysis.context_tokens', 'L1', 'int', '24000'::jsonb, '模块上下文预算，达到百分之八十时压缩', false),
('analysis.max_output_tokens', 'L1', 'int', '4096'::jsonb, '模块单次模型输出上限', false);""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    raise RuntimeError("运行与证据账不可丢弃，请从备份回滚")
