"""登记专题检索的相关度阈值与单次结果上限，历史配置快照保留原样。"""

import sqlalchemy as sa
from alembic import op

revision = "0014_analysis_retrieval"
down_revision = "0013_retire_extraction"
branch_labels = None
depends_on = None

_STATEMENTS = (
    """INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.similarity_threshold', 'L1', 'number', '0.6'::jsonb, '专题检索最低相关度（0到1），有向量时用余弦相似度，否则用检索词命中比例', false),
('analysis.max_search_results', 'L1', 'int', '6'::jsonb, '每次专题检索通过阈值后返回的证据块上限', false);""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # 删除登记项不改写历史版本和运行快照，避免丢失已执行分析的检索参数。
    op.execute(sa.text("""DELETE FROM config_item WHERE key IN
        ('analysis.similarity_threshold', 'analysis.max_search_results');"""))
