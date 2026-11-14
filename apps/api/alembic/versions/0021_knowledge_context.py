"""知识切片入库前合并为条款大块，保存其真实页码和坐标。"""

import sqlalchemy as sa
from alembic import op

revision = "0021_knowledge_context"
down_revision = "0020_llm_response_timeout"
branch_labels = None
depends_on = None

_STATEMENTS = (
    "ALTER TABLE knowledge_chunk ADD COLUMN locations JSONB;",
    """COMMENT ON COLUMN knowledge_chunk.locations IS
    '入库时合并的大块页码、坐标及页内字符范围；模型只使用大块ID';""",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE knowledge_chunk DROP COLUMN locations"))
