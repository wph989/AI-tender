# 12 · LLM 管理与模型路由

## 1. 目标与边界

把模型接入信息从部署参数（`apps/api/.env`）搬进数据库，由页面维护，并按功能选择模型、按优先级故障转移。

本期只做三件事：管理供应商与模型、给功能绑定模型并排优先级、按优先级调用并在失败时降级。不做配额、成本统计、多协议适配与向量模型；这些等出现真实消费者再加。

协议只支持 OpenAI Chat Completions 兼容（含 Azure 这类兼容变体）。**配置中心落地后，`extract.model` 这类"选哪个模型"的值引用本模块的模型行，不再复制连接信息。**

## 2. 三层结构

| 层 | 职责 | 不负责 |
| --- | --- | --- |
| 供应商 `llm_provider` | 一次连接所需的全部信息：`base_url`、加密后的密钥、启用状态 | 具体模型、优先级 |
| 模型 `llm_model` | 供应商下的具体模型与推理参数（超时、温度、max tokens） | 优先级、功能归属 |
| 功能绑定 `llm_feature_model` | 功能（`extract` / `retry`）与模型的多对多关系，**只有这一层带 `priority`** | 连接信息、推理参数 |

优先级与模型解耦是刻意的：同一个模型可以在不同功能里处于不同等级，运营商换模型时只动绑定层，不动模型行。

## 3. 优先级规则

- 取值范围 1–10，数字越小越优先；同一功能内唯一且连续（`1..N`）。
- **整表提交**：客户端提交有序的 `model_ids`，服务端按数组位置写 `1..N`；不做单行改级接口，避免出现空洞与同级。
- 页面上的"设为 N 级、其余自动降级"由前端计算后整表提交：把目标模型从原位置摘出，插入到第 N 位，原来的第 N 位及其后顺延一位。
- 新增第 11 个模型直接拒绝（`priority_limit_exceeded`），不静默挤掉最低级：静默丢模型会让线上配置无声变化。
- 目标位置超出范围时夹到 `1..数量+1`，不保留空洞；空洞级别没有可解释语义。

## 4. 故障转移

- 每个功能有 `failover_limit`（1–10，默认 3），实际生效值夹到该功能已绑定模型数量以内。
- 按 `1..failover_limit` 依次调用；连接失败、超时、HTTP 4xx/5xx、响应不是可解析 JSON 都算失败，降到下一级。
- 模型返回了结果但置信度低**不算失败**：继续走既有的双轮复抽与规则投票。
- 同一模型不原地重试，避免最坏耗时翻倍（超时上限 90 秒 × 候选数）。
- 候选耗尽后，该字段落 `need_review` 并记录失败链；全部失败属于内部重试，不占机器解析序号。
- 若所有候选的失败都是"暂时不可用"（网络、限流、5xx），向上抛 `ExtractionUnavailable`，让 worker 退避后整任务重试；只要有一个是明确拒绝（4xx、响应结构错误），就按字段失败处理。

## 5. 密钥与回退

- 密钥用 Fernet（AES-128-CBC + HMAC-SHA256）加密后存 `api_key_ciphertext`，同时存后 4 位提示 `api_key_hint`。
- 主密钥来自环境变量 `LLM_SECRET_KEYS`：逗号分隔，第一个用于加密，其余用于解密，支持轮换。未配置主密钥时**禁止保存密钥**，其余功能正常运行。
- 页面只写不回显；已有密钥显示为 `****后四位` 与更新时间。
- 取密钥的回退顺序：库内密文 → `.env` 的 `LLM_API_KEY`。注册表里没有可用模型时，整体回退到现有 `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` 单模型逻辑，保证已部署环境不因本模块失效。

## 6. 数据模型

DDL 以本节为权威，`alembic/versions/0003_llm_management.py` 是可执行副本，由契约测试盯住两侧不漂移。

```sql
CREATE TABLE llm_provider (
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
);
CREATE UNIQUE INDEX ux_llm_provider_name ON llm_provider (name) WHERE deleted_at IS NULL;

CREATE TABLE llm_model (
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
);

CREATE TABLE llm_feature (
    key            TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    failover_limit INT  NOT NULL DEFAULT 3 CHECK (failover_limit BETWEEN 1 AND 10),
    description    TEXT NOT NULL DEFAULT '',
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE llm_feature_model (
    id          BIGSERIAL PRIMARY KEY,
    feature_key TEXT   NOT NULL REFERENCES llm_feature(key),
    model_id    BIGINT NOT NULL REFERENCES llm_model(id),
    priority    INT    NOT NULL CHECK (priority BETWEEN 1 AND 10),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (feature_key, model_id),
    UNIQUE (feature_key, priority)
);

CREATE TABLE llm_call_log (
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
);
CREATE INDEX ix_llm_call_created ON llm_call_log (created_at DESC);
CREATE INDEX ix_llm_call_feature ON llm_call_log (feature_key, created_at DESC);
CREATE INDEX ix_llm_call_model ON llm_call_log (model_id, created_at DESC);

ALTER TABLE extraction ADD COLUMN llm_model_id BIGINT REFERENCES llm_model(id);
ALTER TABLE extraction ADD COLUMN llm_model_name TEXT;
```

`llm_model_name` 是快照列：模型改名或停用后，历史抽取记录仍要能读回"当时用的是哪个模型"。

迁移里另外写入两条功能种子（`extract`、`retry`，默认 `failover_limit = 3`），种子不是结构，契约测试不比对。

## 7. 接口

全部挂在 `/api/v1/llm` 下，错误响应沿用 `05` 第 5 节的统一格式。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/providers` | 供应商列表与新建 |
| PATCH/DELETE | `/providers/{id}` | 修改与软删除；仍被功能绑定时拒绝删除 |
| POST | `/providers/{id}/test` | 调 `GET /v1/models` 测连通性，写 `last_test_*` |
| GET | `/providers/{id}/remote-models` | 返回远端模型列表供勾选，不落库 |
| POST | `/providers/{id}/models/import` | 按勾选的模型 id 建 `llm_model`，已存在则跳过 |
| GET/POST | `/models` | 模型列表与新建 |
| PATCH/DELETE | `/models/{id}` | 修改与软删除；仍被绑定时拒绝删除 |
| POST | `/models/{id}/test` | 最小 chat 请求验证可用性，写 `last_test_*` |
| GET | `/features` | 功能列表（含绑定与 `failover_limit`） |
| PATCH | `/features/{key}` | 改 `failover_limit` |
| PUT | `/features/{key}/models` | 整表提交有序 `model_ids` |
| GET | `/calls` | 调用记录分页查询，可按功能、模型、状态过滤 |

新增错误码：

| code | HTTP | retryable | 说明 |
| --- | --- | --- | --- |
| `priority_limit_exceeded` | 400 | 否 | 一个功能最多绑定 10 个模型 |
| `model_in_use` | 409 | 否 | 模型或供应商仍被功能绑定，不能删除 |
| `secret_key_unavailable` | 503 | 否 | 未配置 `LLM_SECRET_KEYS`，无法保存密钥 |

连通性测试接口即使失败也返回 200，响应体里给 `status`、`latency_ms`、`error`，便于页面直接展示；只有参数错误才返回 4xx。

## 8. 前端

新增 `/settings/models` 路由与顶部导航（工作台 / 模型管理）。页面三块：供应商（含测试与拉取导入）、模型（含参数与测试）、功能绑定（选功能、排序、改深度、整表保存）。密钥输入框只写不回显。

## 9. 不做什么

- 不做自动同步：远端删了模型，本地记录保留，避免历史调用记录失去引用。
- 不做调用日志自动清理；按每天一万次调用估算，一年不到 1 GB，等有量了再归档。
- 不做按字段绑定、多模型投票、配额与成本统计。
- 不做页面直接改密钥以外的加密轮换入口；轮换通过更换 `LLM_SECRET_KEYS` 顺序完成。