"""说明关键词与语义检索的独立召回规则，保留现有阈值与配置发布。"""

import sqlalchemy as sa
from alembic import op

revision = "0022_retrieval_semantics"
down_revision = "0021_knowledge_context"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate)
VALUES
('analysis.similarity_threshold', 'L1', 'number', '0.6'::jsonb, '专题语义检索的最低余弦相似度（0到1）；关键词独立召回，按命中数参与融合排序', false)
ON CONFLICT (key) DO UPDATE SET description=EXCLUDED.description;""",
)


def upgrade() -> None:
    # 只更新说明，用户已发布的阈值、模型及配额全部沿用。
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text("""UPDATE config_item SET description=
'专题检索最低相关度（0到1），有向量时用余弦相似度，否则用检索词命中比例'
WHERE key='analysis.similarity_threshold';"""))
