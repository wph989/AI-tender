"""LLM 供应商、模型、功能绑定与调用记录（设计文档 12 第 6 节）。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_llm_management"
down_revision = "0002_storage_and_jobs"
branch_labels = None
depends_on = None


# DDL 与 docs/设计/12-LLM管理与模型路由.md 第 6 节逐字对应；
# 契约测试 tests/contract/test_ddl_matches_docs.py 比对的是这里的字符串。
_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE llm_provider (
    id                 BIGSERIAL PRIMARY KEY,
    name               TEXT        NOT NULL,
    base_url           TEXT        NOT NULL,
    api_key_ciphertext TEXT,
    api_key_hint       TEXT,
    enabled            BOOLEAN     NOT NULL DEFAULT true,
    last_test_status   TEXT,
    last_test_at       TIMESTAMPTZ,
    last_test_error    TEXT,
    deleted_at         TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);""",
    """CREATE UNIQUE INDEX ux_llm_provider_name ON llm_provider (name) WHERE deleted_at IS NULL;""",
    """CREATE TABLE llm_model (
    id               BIGSERIAL PRIMARY KEY,
    provider_id      BIGINT       NOT NULL REFERENCES llm_provider(id),
    model_id         TEXT         NOT NULL,
    display_name     TEXT         NOT NULL,
    timeout_seconds  NUMERIC(6,1) NOT NULL DEFAULT 90,
    temperature      NUMERIC(3,2),
    max_tokens       INT,
    enabled          BOOLEAN      NOT NULL DEFAULT true,
    last_test_status TEXT,
    last_test_at     TIMESTAMPTZ,
    last_test_error  TEXT,
    deleted_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (provider_id, model_id)
);""",
    """CREATE TABLE llm_feature (
    key            TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    failover_limit INT  NOT NULL DEFAULT 3 CHECK (failover_limit BETWEEN 1 AND 10),
    description    TEXT NOT NULL DEFAULT '',
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);""",
    """CREATE TABLE llm_feature_model (
    id          BIGSERIAL PRIMARY KEY,
    feature_key TEXT   NOT NULL REFERENCES llm_feature(key),
    model_id    BIGINT NOT NULL REFERENCES llm_model(id),
    priority    INT    NOT NULL CHECK (priority BETWEEN 1 AND 10),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (feature_key, model_id),
    UNIQUE (feature_key, priority)
);""",
    """CREATE TABLE llm_call_log (
    id                BIGSERIAL PRIMARY KEY,
    provider_id       BIGINT REFERENCES llm_provider(id),
    model_id          BIGINT REFERENCES llm_model(id),
    feature_key       TEXT,
    purpose           TEXT NOT NULL,
    status            TEXT NOT NULL,
    http_status       INT,
    latency_ms        INT  NOT NULL,
    prompt_tokens     INT,
    completion_tokens INT,
    error_message     TEXT,
    extraction_id     BIGINT REFERENCES extraction(id),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);""",
    """CREATE INDEX ix_llm_call_created ON llm_call_log (created_at DESC);""",
    """CREATE INDEX ix_llm_call_feature ON llm_call_log (feature_key, created_at DESC);""",
    """CREATE INDEX ix_llm_call_model ON llm_call_log (model_id, created_at DESC);""",
    """ALTER TABLE extraction ADD COLUMN llm_model_id BIGINT REFERENCES llm_model(id);""",
    """ALTER TABLE extraction ADD COLUMN llm_model_name TEXT;""",
    # 功能清单是代码枚举（设计文档 12 第 1 节），种子只是让页面一打开就有可绑定的功能；
    # 消费者在 application/llm_routing.py，页面不能新增功能。
    """INSERT INTO llm_feature (key, name, failover_limit, description)
VALUES ('extract', '字段抽取', 3, '首次抽取与低置信复抽'),
       ('retry', '重跑与带提示重跑', 3, '人工触发的单字段重跑')
ON CONFLICT (key) DO NOTHING;""",
)

# 删表必须严格逆序：llm_call_log 引用 llm_model / llm_provider，先删会被外键挡住。
_TABLES_IN_DROP_ORDER: tuple[str, ...] = (
    "llm_call_log",
    "llm_feature_model",
    "llm_feature",
    "llm_model",
    "llm_provider",
)


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(statement))


def downgrade() -> None:
    # 先摘掉 extraction 上的两列，再删被它们引用的 llm_model。
    op.execute(sa.text("ALTER TABLE extraction DROP COLUMN IF EXISTS llm_model_name"))
    op.execute(sa.text("ALTER TABLE extraction DROP COLUMN IF EXISTS llm_model_id"))
    for table in _TABLES_IN_DROP_ORDER:
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
