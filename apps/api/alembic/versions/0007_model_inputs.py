"""补齐四类模型配置、分能力测试结果和临时生图预览。"""

import sqlalchemy as sa
from alembic import op

revision = "0007_model_inputs"
down_revision = "0006_model_capabilities"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """ALTER TABLE llm_model DROP CONSTRAINT llm_model_kind_check;""",
    """ALTER TABLE llm_model ADD CONSTRAINT llm_model_kind_check
        CHECK (kind IN ('language','embedding','rerank','image_generation'));""",
    """ALTER TABLE llm_model
        ADD COLUMN parameters JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(parameters)='object'),
        ADD COLUMN supported_parameters JSONB,
        ADD COLUMN embedding_space_id UUID;""",
    # 空间由服务端分配；不能通过手填相同 ID 将两个未经验证的向量空间混用。
    """UPDATE llm_model SET embedding_space_id=gen_random_uuid() WHERE kind='embedding';""",
    """ALTER TABLE llm_test
        ADD COLUMN call_log_id BIGINT REFERENCES llm_call_log(id),
        ADD COLUMN timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 90,
        ADD COLUMN result JSONB NOT NULL DEFAULT '{}',
        ADD COLUMN preview_data BYTEA,
        ADD COLUMN preview_mime TEXT,
        ADD COLUMN invalidated_at TIMESTAMPTZ;""",
    """ALTER TABLE llm_call_log ADD COLUMN image_count INT;""",
    """INSERT INTO llm_feature(key,name,description) VALUES
        ('image_generation','图片生成','图片模型管理、功能绑定与显式测试；不自动生成业务素材')
        ON CONFLICT DO NOTHING;""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    raise RuntimeError("需要从备份回滚，不能丢弃模型参数、空间身份与测试历史")
