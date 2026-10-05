"""模型能力、受限重试、配置版本与可追踪测试。"""

import sqlalchemy as sa
from alembic import op

revision = "0006_model_capabilities"
down_revision = "0005_knowledge_analysis"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """ALTER TABLE llm_provider
        ADD COLUMN protocol TEXT NOT NULL DEFAULT 'openai_compatible',
        ADD COLUMN auth_mode TEXT NOT NULL DEFAULT 'api_key' CHECK (auth_mode IN ('api_key','none')),
        ADD COLUMN revision INT NOT NULL DEFAULT 1,
        ADD COLUMN config_revision INT NOT NULL DEFAULT 1,
        ADD COLUMN credential_revision INT NOT NULL DEFAULT 1,
        ADD COLUMN api_key_updated_at TIMESTAMPTZ,
        ADD COLUMN last_test_config_revision INT,
        ADD COLUMN last_test_id BIGINT;""",
    # 已有匿名内网连接保留为显式匿名；不从环境变量复制任何凭证。
    """UPDATE llm_provider SET auth_mode = 'none' WHERE api_key_ciphertext IS NULL;""",
    """ALTER TABLE llm_model
        ADD COLUMN kind TEXT NOT NULL DEFAULT 'language' CHECK (kind IN ('language','embedding','rerank')),
        ADD COLUMN api_mode TEXT NOT NULL DEFAULT 'chat_completions',
        ADD COLUMN capabilities JSONB NOT NULL DEFAULT '["text_input","json_output"]',
        ADD COLUMN extra_retries INT NOT NULL DEFAULT 1 CHECK (extra_retries BETWEEN 0 AND 10),
        ADD COLUMN revision INT NOT NULL DEFAULT 1,
        ADD COLUMN config_revision INT NOT NULL DEFAULT 1,
        ADD COLUMN last_test_config_revision INT,
        ADD COLUMN last_test_provider_revision INT,
        ADD COLUMN last_test_id BIGINT;""",
    """ALTER TABLE llm_model DROP CONSTRAINT llm_model_provider_id_model_id_key;""",
    """CREATE UNIQUE INDEX ux_llm_model_active ON llm_model(provider_id,model_id) WHERE deleted_at IS NULL;""",
    """ALTER TABLE llm_feature
        ADD COLUMN max_total_requests INT NOT NULL DEFAULT 6 CHECK (max_total_requests BETWEEN 1 AND 20),
        ADD COLUMN deadline_seconds INT NOT NULL DEFAULT 600 CHECK (deadline_seconds BETWEEN 1 AND 86400),
        ADD COLUMN revision INT NOT NULL DEFAULT 1;""",
    """ALTER TABLE llm_call_log
        ADD COLUMN invocation_id UUID,
        ADD COLUMN candidate_ordinal INT,
        ADD COLUMN retry_ordinal INT,
        ADD COLUMN request_ordinal INT,
        ADD COLUMN model_name_snapshot TEXT,
        ADD COLUMN provider_name_snapshot TEXT,
        ADD COLUMN model_key_snapshot TEXT,
        ADD COLUMN vector_count INT,
        ADD COLUMN document_count INT;""",
    """CREATE UNIQUE INDEX ix_llm_call_invocation ON llm_call_log(invocation_id,request_ordinal);""",
    # 首次补齐能确认的历史名称，后续改名不再影响旧记录。
    """UPDATE llm_call_log c SET provider_name_snapshot=p.name
        FROM llm_provider p WHERE c.provider_id=p.id;""",
    """UPDATE llm_call_log c SET model_name_snapshot=m.display_name,model_key_snapshot=m.model_id
        FROM llm_model m WHERE c.model_id=m.id;""",
    """CREATE TABLE llm_test (
        id BIGSERIAL PRIMARY KEY,
        provider_id BIGINT NOT NULL REFERENCES llm_provider(id),
        model_id BIGINT REFERENCES llm_model(id),
        capability TEXT NOT NULL,
        provider_revision INT NOT NULL,
        model_revision INT,
        status TEXT NOT NULL DEFAULT 'running',
        latency_ms INT,
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at TIMESTAMPTZ
    );""",
    """CREATE INDEX ix_llm_test_model ON llm_test(model_id,created_at DESC);""",
    """INSERT INTO llm_feature(key,name,description) VALUES ('rerank','检索重排','对检索候选进行专用重排；未配置时保留混合检索顺序') ON CONFLICT DO NOTHING;""",
    # 用一次显式绑定迁移替代每次调用时隐式借用字段模型，之后清空即停止调用。
    """INSERT INTO llm_feature_model(feature_key,model_id,priority)
        SELECT f.key,fm.model_id,fm.priority FROM llm_feature f CROSS JOIN llm_feature_model fm
        WHERE f.key IN ('analysis','knowledge_ask') AND fm.feature_key='extract'
          AND NOT EXISTS (SELECT 1 FROM llm_feature_model existing WHERE existing.feature_key=f.key);""",
    # 旧表允许把同一模型用于语言与向量；迁移不能悄悄留下运行时必然失败的绑定。
    """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM llm_feature_model e JOIN llm_feature_model other
            ON e.model_id=other.model_id WHERE e.feature_key='embedding' AND other.feature_key<>'embedding')
        THEN RAISE EXCEPTION '同一模型同时绑定向量和语言功能，请先拆分模型登记后重新迁移';
        END IF;
        END $$;""",
    """UPDATE llm_model SET kind='embedding',api_mode='embeddings',
        capabilities='["text_input","embedding"]',temperature=NULL,max_tokens=NULL
        WHERE id IN (SELECT model_id FROM llm_feature_model WHERE feature_key='embedding');""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # 软删除后同名重建的数据无法无损恢复旧唯一约束，要求显式备份回滚。
    raise RuntimeError("该迁移需从备份回滚，不能丢弃模型测试与调用历史")
