"""供应商429冷却跨模块和进程共享，避免多个Agent同时撞限流。"""

import sqlalchemy as sa
from alembic import op

revision = "0009_provider_cooldown"
down_revision = "0008_deepagents_runtime"
branch_labels = None
depends_on = None

_STATEMENTS = (
    "ALTER TABLE llm_provider ADD COLUMN rate_limited_until TIMESTAMPTZ;",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE llm_provider DROP COLUMN rate_limited_until"))
