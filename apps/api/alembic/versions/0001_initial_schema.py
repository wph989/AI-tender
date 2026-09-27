"""初始表结构：设计文档 DDL 的可执行副本。

权威文档：docs/设计/03 第 5 节（核心表）、docs/质量/08 第 7 节（配置中心）、
docs/质量/09 第 10 节（回归回放）。本文件由文档抽取生成，逐字保留原文的列名、注释与索引；
tests/contract/test_ddl_matches_docs.py 盯着这份对应关系不漂移。

为什么用裸 SQL 而不是 SQLAlchemy Core 建模：DDL 的唯一权威是设计文档，
用 Core 再建模一遍等于把同一份结构维护两次，必然出现「文档里有、迁移里没有」。

三处必需的补充（原文按章节顺序直接执行会失败）：
1. `CREATE EXTENSION pg_trgm` —— element.text 的 gin_trgm_ops 索引依赖它，文档未写；
2. `field_instance.current_extraction_id` 的外键改在 extraction 建表后补 —— 它与
   `extraction.instance_id` 互相引用，PostgreSQL 要求被引用表在 CREATE 时已存在；
3. `config_release.regression_run_id` 同理（与 regression_run 互相引用）。

执行顺序按外键依赖排列，不按文档的章节顺序。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


_STATEMENTS: tuple[str, ...] = (
    """CREATE EXTENSION IF NOT EXISTS pg_trgm;""",
    """-- 文档（逻辑实体，代表"一份标书"）
CREATE TABLE document (
    id            BIGSERIAL PRIMARY KEY,
    title         TEXT         NOT NULL,          -- 初始取文件名，可人工修改
    project_no    TEXT,                            -- 招标编号，抽取后回填
    status        TEXT         NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ
);""",
    """-- 文档版本（溯源的根，由内容哈希唯一定位）
CREATE TABLE document_version (
    id                 BIGSERIAL PRIMARY KEY,
    document_id        BIGINT      NOT NULL REFERENCES document(id),
    version_no         INT         NOT NULL,
    sha256             CHAR(64)    NOT NULL,       -- 原始文件内容哈希
    mime               TEXT        NOT NULL,
    size_bytes         BIGINT      NOT NULL,
    original_key       TEXT        NOT NULL,       -- 原件对象存储 key
    -- 转换产物（PDF 直通时等于原件）
    pdf_key            TEXT        NOT NULL,       -- 坐标基座
    pdf_sha256         CHAR(64)    NOT NULL,
    is_converted       BOOLEAN     NOT NULL,       -- 是否经过格式转换
    converter          TEXT,                       -- 'gotenberg'
    converter_version  TEXT,                       -- GET /version 的结果
    page_count         INT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, version_no)
);
CREATE UNIQUE INDEX ux_version_sha ON document_version (sha256, converter_version);
CREATE INDEX ix_version_doc ON document_version (document_id, created_at DESC);""",
    """-- 解析运行（一次 MinerU 调用，记录全部环境信息以支持重放）
CREATE TABLE parse_run (
    id                 BIGSERIAL PRIMARY KEY,
    version_id         BIGINT      NOT NULL REFERENCES document_version(id),
    provider           TEXT        NOT NULL DEFAULT 'mineru',
    provider_version   TEXT        NOT NULL,       -- MinerU 版本
    tier               TEXT        NOT NULL,       -- flash|basic|standard|advanced
    backend            TEXT,                       -- pipeline|vlm|hybrid，来自产物
    schema_version     TEXT        NOT NULL,       -- MiddleJson schema_version
    status             TEXT        NOT NULL,       -- pending|running|completed|partial|failed|canceled
    request_id         TEXT,                       -- Gotenberg-Trace 风格的自有 job id
    raw_middle_key     TEXT,                       -- MiddleJson 原始产物存档
    raw_content_key    TEXT,                       -- Content List 存档
    page_count         INT,
    elapsed_ms         INT,
    error_code         TEXT,
    error_message      TEXT,
    started_at         TIMESTAMPTZ,
    finished_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_run_version ON parse_run (version_id, created_at DESC);
CREATE INDEX ix_run_status ON parse_run (status) WHERE status IN ('pending','running');""",
    """-- 页面
CREATE TABLE page (
    id            BIGSERIAL PRIMARY KEY,
    version_id    BIGINT      NOT NULL REFERENCES document_version(id),
    page_no       INT         NOT NULL,            -- 1-based 物理页
    width_pt      NUMERIC(10,3),                   -- PDF 用户空间尺寸
    height_pt     NUMERIC(10,3),
    rotation      SMALLINT    NOT NULL DEFAULT 0,  -- 原始 /Rotate
    image_key     TEXT,                            -- 预留：本期不生成整页图（预览由前端 pdf.js 渲染）
    image_px_w    INT,                             -- 预留
    image_px_h    INT,                             -- 预留
    text_layer    BOOLEAN     NOT NULL DEFAULT false, -- 是否存在原生文本层
    UNIQUE (version_id, page_no)
);""",
    """-- 元素（块）：锚点的物理落点
CREATE TABLE element (
    id             BIGSERIAL PRIMARY KEY,
    version_id     BIGINT      NOT NULL REFERENCES document_version(id),
    run_id         BIGINT      NOT NULL REFERENCES parse_run(id),
    page_no        INT         NOT NULL,
    order_no       INT         NOT NULL,           -- 页内块序，仅对参与编号的块连续
    anchor         TEXT        NOT NULL,           -- 'p12b5'
    type           TEXT        NOT NULL,           -- title|text|table|figure|header|footer|list|equation
    level          INT,                            -- 标题层级（title_leveling 产出）
    parent_id      BIGINT      REFERENCES element(id),
    bbox_x0        NUMERIC(7,6),                   -- 0-1，左上原点
    bbox_y0        NUMERIC(7,6),
    bbox_x1        NUMERIC(7,6),
    bbox_y1        NUMERIC(7,6),
    text           TEXT,                            -- 纯文本，用于校验与检索
    html           TEXT,                            -- 表格为 HTML 结构
    source         TEXT        NOT NULL DEFAULT 'native', -- native|ocr
    continues_prev BOOLEAN     NOT NULL DEFAULT false,    -- 跨页块延续标记
    mineru_locator TEXT,                            -- 派生引用，仅用于复现
    UNIQUE (run_id, page_no, order_no)          -- 锚点唯一范围 = 一次 parse_run，不是整个版本
);
CREATE INDEX ix_element_anchor ON element (run_id, anchor);   -- 锚点按 run 查询；跨 run 查同一锚点没有意义
CREATE INDEX ix_element_page ON element (version_id, page_no, order_no);
-- 文本检索（校验层与人工检索用）
CREATE INDEX ix_element_text_trgm ON element USING gin (text gin_trgm_ops);""",
    """-- 表格单元格（二期，一期只到块级）
CREATE TABLE table_cell (
    id          BIGSERIAL PRIMARY KEY,
    element_id  BIGINT NOT NULL REFERENCES element(id),
    row_no      INT    NOT NULL,
    col_no      INT    NOT NULL,
    rowspan     INT    NOT NULL DEFAULT 1,
    colspan     INT    NOT NULL DEFAULT 1,
    bbox_x0     NUMERIC(7,6),
    bbox_y0     NUMERIC(7,6),
    bbox_x1     NUMERIC(7,6),
    bbox_y1     NUMERIC(7,6),
    text        TEXT,
    UNIQUE (element_id, row_no, col_no)
);""",
    """CREATE TABLE project (
    id          BIGSERIAL PRIMARY KEY,
    company_id  BIGINT      NOT NULL DEFAULT 1,      -- 多租户预留，本期恒为 1
    name        TEXT        NOT NULL,
    project_no  TEXT,
    owner       TEXT,
    status      TEXT        NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);""",
    """-- 项目内文件：可增删改；软删除 + 替代关系
CREATE TABLE project_file (
    id           BIGSERIAL PRIMARY KEY,
    project_id   BIGINT      NOT NULL REFERENCES project(id),
    version_id   BIGINT      REFERENCES document_version(id),  -- 只存不解析的附件可为空
    role         TEXT        NOT NULL,   -- main|clarification|addendum|boq|drawing|format|other
    display_name TEXT        NOT NULL,
    is_parseable BOOLEAN     NOT NULL DEFAULT true,
    replaces_id  BIGINT      REFERENCES project_file(id),  -- 换内容时指向被替代项
    sort_no      INT         NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at   TIMESTAMPTZ
);
CREATE INDEX ix_project_file ON project_file (project_id, sort_no) WHERE deleted_at IS NULL;""",
    """-- 标段
CREATE TABLE lot (
    id         BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES project(id),
    code       TEXT,                     -- '一包' / 'A标段'
    name       TEXT,
    sort_no    INT    NOT NULL DEFAULT 0
);""",
    """-- 字段实例：跨尝试不变的稳定身份
CREATE TABLE field_instance (
    id            BIGSERIAL PRIMARY KEY,
    version_id    BIGINT      NOT NULL REFERENCES document_version(id),
    field_key     TEXT        NOT NULL,
    lot_id        BIGINT      REFERENCES lot(id),          -- NULL = 全文适用
    -- 当前展示哪一次结果；由应用在新尝试落库后更新（唯一 current 约束在 extraction 上）
    current_extraction_id BIGINT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, field_key, lot_id)
);""",
    """-- 抽取尝试：一次抽取 / 重跑 / 人工修正 = 一行，append-only 永不覆盖（field_instance 见 5.3 节）
CREATE TABLE extraction (
    id            BIGSERIAL PRIMARY KEY,
    instance_id   BIGINT      NOT NULL REFERENCES field_instance(id),  -- 跨尝试不变的稳定身份
    version_id    BIGINT      NOT NULL REFERENCES document_version(id),
    run_id        BIGINT      REFERENCES parse_run(id),
    attempt_no         INT    NOT NULL,            -- 时间线序号：每次留档 +1，含人工修正
    machine_attempt_no INT,                        -- 机器解析序号：仅 first / *_rerun / reparse 计数；manual_edit 为空
    trigger       TEXT        NOT NULL,            -- first|hinted_rerun|user_rerun|param_rerun|reparse|manual_edit
    hint          TEXT,                            -- 带提示重跑时用户填的提示原文
    field_key     TEXT        NOT NULL,            -- bid_bond_amount 等
    group_key     TEXT,                            -- basic_info|qualification|scoring|risk
    value_json    JSONB,                           -- 结构化值（含单位、币种）
    value_text    TEXT,                            -- 展示用文本
    confidence    NUMERIC(4,3),                    -- 0-1
    status        TEXT        NOT NULL,            -- auto|need_review|verified|rejected|conflict|not_found
    strategy      TEXT        NOT NULL,            -- rule|llm|rule+llm
    evidence_count INT        NOT NULL DEFAULT 0,  -- 冗余计数，避免列表页 N+1
    supersedes_id BIGINT      REFERENCES extraction(id),   -- 被本次取代的尝试
    is_current    BOOLEAN     NOT NULL DEFAULT false,
    created_by    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (instance_id, attempt_no)
);
-- 机器解析序号在同一 parse_run 内唯一；换 run 后从 1 重新计数（见 2.1 节与 09 第 2 节）
CREATE UNIQUE INDEX ux_extraction_machine_no ON extraction (instance_id, run_id, machine_attempt_no)
    WHERE machine_attempt_no IS NOT NULL;
-- 每个实例最多一条 current：把"哪条是当前值"变成数据库约束，而不是应用层约定
CREATE UNIQUE INDEX ux_extraction_current ON extraction (instance_id) WHERE is_current;
CREATE INDEX ix_extraction_version ON extraction (version_id, group_key, field_key);
CREATE INDEX ix_extraction_review ON extraction (version_id) WHERE status = 'need_review';
CREATE INDEX ix_extraction_trigger ON extraction (trigger, created_at DESC);""",
    """ALTER TABLE field_instance ADD CONSTRAINT fk_field_instance_current_extraction FOREIGN KEY (current_extraction_id) REFERENCES extraction(id);""",
    """-- 证据（核心表）
CREATE TABLE evidence (
    id            BIGSERIAL PRIMARY KEY,
    extraction_id BIGINT      NOT NULL REFERENCES extraction(id) ON DELETE CASCADE,
    version_id    BIGINT      NOT NULL REFERENCES document_version(id),
    seq           INT         NOT NULL DEFAULT 1,  -- 多证据排序
    anchor        TEXT        NOT NULL,            -- 'p12b5'
    element_id    BIGINT      REFERENCES element(id),
    page_no       INT         NOT NULL,            -- 冗余，便于按页聚合
    bbox_x0       NUMERIC(7,6),                    -- 冗余自 element，允许独立修正
    bbox_y0       NUMERIC(7,6),
    bbox_x1       NUMERIC(7,6),
    bbox_y1       NUMERIC(7,6),
    char_start    INT,                             -- 块内 0-based 字符区间
    char_end      INT,
    quote         TEXT        NOT NULL,            -- 原文片段（LLM 必须逐字复制）
    quote_source  TEXT        NOT NULL,            -- native|ocr
    match_type    TEXT        NOT NULL,            -- exact|normalized|page_fallback|manual
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_evidence_extraction ON evidence (extraction_id, seq);
CREATE INDEX ix_evidence_version_page ON evidence (version_id, page_no);""",
    """-- 复核动作：事实标准的生产记录（每次确认/修正/补充各一行，只增不改）
CREATE TABLE review_action (
    id          BIGSERIAL PRIMARY KEY,
    instance_id BIGINT      NOT NULL REFERENCES field_instance(id),
    attempt_id  BIGINT      NOT NULL REFERENCES extraction(id),  -- 被核对的机器尝试
    -- correct/supplement 产生的人工结果快照；confirm/reject 时为空
    result_attempt_id BIGINT REFERENCES extraction(id),
    action      TEXT        NOT NULL,       -- confirm|correct|supplement|reject
    review_mode TEXT        NOT NULL,       -- item（逐条）|batch（批量勾选）|spot_check（抽检）
    old_value   JSONB,                      -- correct 时保留原值，供统计与回归
    new_value   JSONB,
    evidence    JSONB,                      -- 用户框选的锚点，correct/supplement 必填
    actor       TEXT        NOT NULL,
    comment     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_review_action_instance ON review_action (instance_id, created_at DESC);
CREATE INDEX ix_review_action_mode ON review_action (review_mode, created_at DESC);""",
    """-- 复核队列（待办）。与 review_action 职责不同：这里只记"要做什么"，判断结果记在 review_action
CREATE TABLE review_task (
    id                 BIGSERIAL PRIMARY KEY,
    extraction_id      BIGINT      NOT NULL REFERENCES extraction(id) ON DELETE CASCADE,
    reason             TEXT        NOT NULL,   -- no_evidence|low_confidence|rule_conflict|bad_quote|spot_check
    status             TEXT        NOT NULL DEFAULT 'open',  -- open|resolved|dismissed
    assignee           TEXT,
    resolved_action_id BIGINT      REFERENCES review_action(id),  -- 指向真正的事实标准记录
    resolved_at        TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_review_open ON review_task (status) WHERE status = 'open';""",
    """-- 回归集条目：由 correct / supplement 快照而来，与生产数据物理隔离
CREATE TABLE gold_item (
    id                 BIGSERIAL PRIMARY KEY,
    source_instance_id BIGINT,                -- 只留血缘，不设外键（理由见下）
    version_id         BIGINT      NOT NULL,
    field_key          TEXT        NOT NULL,
    expected           JSONB       NOT NULL,
    expected_anchors   TEXT[]      NOT NULL,  -- 必须非空：gold 一定带锚点
    origin             TEXT        NOT NULL,  -- correct|supplement
    param_snapshot     JSONB       NOT NULL,  -- 产出这条 gold 时的参数，回放时用于分层
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_gold_field ON gold_item (field_key);""",
    """-- 跨文件/多值冲突组（见 4.4、4.5 节）
CREATE TABLE extraction_conflict (
    id            BIGSERIAL PRIMARY KEY,
    project_id    BIGINT NOT NULL REFERENCES project(id),
    field_key     TEXT   NOT NULL,
    lot_id        BIGINT REFERENCES lot(id),
    candidate_ids BIGINT[] NOT NULL,                  -- 参与冲突的 extraction.id
    resolved_id   BIGINT REFERENCES extraction(id),   -- 人工裁定后指向胜出项
    status        TEXT   NOT NULL DEFAULT 'open',     -- open|resolved|dismissed
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_conflict_open ON extraction_conflict (project_id, field_key) WHERE status = 'open';""",
    """ALTER TABLE document         ADD COLUMN company_id BIGINT NOT NULL DEFAULT 1;""",
    """ALTER TABLE document_version ADD COLUMN company_id BIGINT NOT NULL DEFAULT 1;""",
    """-- 适用范围：NULL = 全文适用（见 4.4 节）
ALTER TABLE extraction ADD COLUMN lot_id BIGINT REFERENCES lot(id);""",
    """-- 产生该结果时所用的字段定义版本；字段定义变更后结果不可直接比较（见 08 文档第 3 节）
ALTER TABLE extraction ADD COLUMN field_def_version INT NOT NULL DEFAULT 1;""",
    """-- 配置项定义（元数据：类型、默认值、是否受门禁约束）
CREATE TABLE config_item (
    key            TEXT PRIMARY KEY,          -- 'mineru.tier'
    layer          TEXT NOT NULL,             -- L1|L2|L3
    value_type     TEXT NOT NULL,             -- int|bool|string|json|secret
    default_value  JSONB NOT NULL,
    description    TEXT NOT NULL,
    requires_gate  BOOLEAN NOT NULL DEFAULT false,   -- 是否受回归门禁约束
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);""",
    """-- 配置版本（一次提交 = 一个 release）
CREATE TABLE config_release (
    id             BIGSERIAL PRIMARY KEY,
    company_id     BIGINT      NOT NULL DEFAULT 1,   -- 多租户预留；本期恒为 1
    version_no     INT         NOT NULL,
    values         JSONB       NOT NULL,             -- 全量值（非 diff），保证可独立回放
    status         TEXT        NOT NULL,             -- draft|active|archived|rolled_back
    based_on       BIGINT      REFERENCES config_release(id),
    regression_run_id BIGINT,   -- 见 09 第 10 节
    note           TEXT,
    created_by     TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_release_active ON config_release (company_id) WHERE status = 'active';""",
    """ALTER TABLE config_release ADD CONSTRAINT fk_config_release_regression_run FOREIGN KEY (regression_run_id) REFERENCES regression_run(id);""",
    """-- 任务级配置快照（不可变）
CREATE TABLE job_config_snapshot (
    id           BIGSERIAL PRIMARY KEY,
    release_id   BIGINT      NOT NULL REFERENCES config_release(id),
    resolved     JSONB       NOT NULL,       -- 解析后的完整配置值
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);""",
    """-- 变更审计
CREATE TABLE config_audit (
    id          BIGSERIAL PRIMARY KEY,
    release_id  BIGINT      NOT NULL REFERENCES config_release(id),
    actor       TEXT        NOT NULL,
    action      TEXT        NOT NULL,        -- create|acknowledge|activate|rollback|force_activate
    diff        JSONB       NOT NULL,        -- {key: {old, new}}
    reason      TEXT,                        -- 强制激活时必填
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);""",
    """-- 变更影响清单的逐条确认记录（门禁要能回答「谁在何时确认了哪一条影响」）
CREATE TABLE config_ack (
    id         BIGSERIAL PRIMARY KEY,
    release_id BIGINT      NOT NULL REFERENCES config_release(id),
    item_kind  TEXT        NOT NULL,     -- field_def_changed|regression_failure|field_removed
    item_ref   TEXT        NOT NULL,     -- 如 'bid_bond_amount@p12b5'
    actor      TEXT        NOT NULL,
    comment    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (release_id, item_kind, item_ref)
);""",
    """-- 回归回放（一次参数变更的回放报告）
CREATE TABLE regression_run (
    id                BIGSERIAL PRIMARY KEY,
    release_id        BIGINT      NOT NULL REFERENCES config_release(id),
    gold_total        INT         NOT NULL,
    pass_count        INT         NOT NULL,
    fail_count        INT         NOT NULL,
    baseline_rate     NUMERIC(5,4),                          -- 当前 active 的回归集通过率，用于比较
    anchor_hit        NUMERIC(5,4),
    by_field          JSONB,                                 -- 逐字段通过率
    failures          JSONB,                                 -- 失败明细（含 gold 锚点，便于跳原文）
    impact_items      JSONB,                                 -- 变更影响清单（逐条 confirmation 状态）
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ
);""",
)

# 逆序删表；pg_trgm 不删——同一数据库里可能有别的 schema 在用
_TABLES_IN_DROP_ORDER: tuple[str, ...] = (
    "regression_run",
    "config_ack",
    "config_audit",
    "job_config_snapshot",
    "config_release",
    "config_item",
    "extraction_conflict",
    "gold_item",
    "review_task",
    "review_action",
    "evidence",
    "extraction",
    "field_instance",
    "lot",
    "project_file",
    "project",
    "table_cell",
    "element",
    "page",
    "parse_run",
    "document_version",
    "document",
)


def _statement_without_trailing_semicolon(statement: str) -> str:
    # 文档原文每条 DDL 都以分号结尾，而 alembic 在 as_sql 模式下渲染时会自己再补一个分号，
    # 于是 `alembic upgrade head --sql` 的产物里出现 "...;;"。去掉原文末尾的分号：
    # 执行语义完全不变，但产物能被评审人读懂，也能被「按分号切分」的简单工具安全处理。
    stripped = statement.strip()
    while stripped.endswith(";"):
        stripped = stripped[:-1].rstrip()
    return stripped


def upgrade() -> None:
    for statement in _STATEMENTS:
        op.execute(sa.text(_statement_without_trailing_semicolon(statement)))


def downgrade() -> None:
    for table in _TABLES_IN_DROP_ORDER:
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))
