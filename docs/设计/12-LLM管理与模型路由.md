# 12 · LLM 管理与模型路由

## 1. 目标与边界

把模型接入信息从部署参数（`apps/api/.env`）搬进数据库，由页面维护，并按功能选择模型、按优先级故障转移。

2026-10-05：支持供应商、按能力登记模型、功能绑定、有限重试、测试有效性与调用记录。知识分析消费者增加后，已扩展语言、纯文本嵌入和专用重排。当前交付与后续边界见第 10 节。

协议由 `/llm/settings` 的 `adapter_profiles` 明确登记；兼容协议不等于所有品牌、认证方式和参数都已支持。**配置中心落地后，`extract.model` 这类"选哪个模型"的值引用本模块的模型行，不再复制连接信息。**

## 2. 三层结构

| 层 | 职责 | 不负责 |
| --- | --- | --- |
| 供应商 `llm_provider` | 一次连接所需的全部信息：`base_url`、加密后的密钥、启用状态 | 具体模型、优先级 |
| 模型 `llm_model` | 供应商下的具体模型与推理参数（超时、温度、max tokens） | 优先级、功能归属 |
| 功能绑定 `llm_feature_model` | 功能（`extract` / `retry`）与模型的多对多关系，**只有这一层带 `priority`** | 连接信息、推理参数 |

优先级与模型解耦是刻意的：同一个模型可以在不同功能里处于不同等级，运营商换模型时只动绑定层，不动模型行。

### 当前功能与配置入口（2026-10-12）

功能名称和说明由代码中的消费者清单返回，不再读取可能过期的数据库种子文案。

| 功能键 | 实际调用范围 |
| --- | --- |
| `analysis` | 13个招标专题解析、证据校验、上下文压缩，以及模块补跑和指定专题重新解析 |
| `knowledge_ask` | 项目问答、知识库问答与引用核对 |
| `embedding` | 知识库向量索引、专题解析和问答中的向量检索；单模型 |
| `rerank` | 专题解析与问答的检索候选重排；单模型 |
| `extract` | 文件流水线和配置回归回放中的首次字段抽取 |
| `retry` | 字段低置信复抽、人工重跑和带提示重跑，不用于专题补跑 |
| `image_generation` | 尚未接入业务，`binding_available=false`；只允许清理历史绑定，模型列表仍可显式测试图片生成 |

`analysis.*`、`llm_aided.*`、`extract.max_inflight`、`extract.strategy.*` 的编辑入口统一放在
「模型管理 → 分析参数」，配置中心保留其它运行与文件处理规则。底层配置键、范围元数据和版本链不变，
发布与回滚仍作用于整个版本。未接入的开关继续只读。向量与重排的路由预算不可编辑，因为当前消费者为单次调用。

## 3. 优先级规则

- 取值范围 1–10，数字越小越优先；同一功能内唯一且连续（`1..N`）。
- **整表提交**：客户端提交有序的 `model_ids`，服务端按数组位置写 `1..N`；不做单行改级接口，避免出现空洞与同级。
- 页面上的"设为 N 级、其余自动降级"由前端计算后整表提交：把目标模型从原位置摘出，插入到第 N 位，原来的第 N 位及其后顺延一位。
- 页面支持选择完整顺位、上移、下移、置顶、置底；顺位选择结束后再移动，避免输入两位数字时提前重排。切换功能保留独立草稿，保存仍使用原子整表提交及版本校验。
- 新增第 11 个模型直接拒绝（`priority_limit_exceeded`），不静默挤掉最低级：静默丢模型会让线上配置无声变化。
- 目标位置超出范围时夹到 `1..数量+1`，不保留空洞；空洞级别没有可解释语义。

## 4. 故障转移

- 每个功能有 `failover_limit`（1–10，默认 3），实际生效值夹到该功能已绑定模型数量以内。
- `failover_limit` 只计实际发送过请求的不同可用候选。语言模型暂时故障先按 `extra_retries` 退避；认证、参数或非法 JSON 不在原模型重复请求，模型明确拒绝与本地约束错误直接停止。
- 模型返回了结果但置信度低**不算失败**：继续走既有的双轮复抽与规则投票。
- 模型 `extra_retries` 为整数 ≥0，默认 1；功能 `max_total_requests` 为整数 ≥1，默认 6，`deadline_seconds` 为整数 ≥1，默认 600；这些预算无人工最大值。默认暂时故障顺序为 A/A/B/B/C/C，任何预算先到即停止。
- 候选耗尽后，该字段落 `need_review` 并记录失败链；全部失败属于内部重试，不占机器解析序号。
- 若所有候选的失败都是"暂时不可用"（网络、限流、5xx），向上抛 `ExtractionUnavailable`，让 worker 退避后整任务重试；只要有一个是明确拒绝（4xx、响应结构错误），就按字段失败处理。

## 5. 密钥与回退

- 密钥用 Fernet（AES-128-CBC + HMAC-SHA256）加密后存 `api_key_ciphertext`，同时存后 4 位提示 `api_key_hint`。
- 主密钥来自环境变量 `LLM_SECRET_KEYS`：逗号分隔，第一个用于加密，其余用于解密，支持轮换。未配置主密钥时**禁止保存密钥**，其余功能正常运行。
- 页面只写不回显；已有密钥显示为 `****后四位` 与更新时间。
- 模型、端点和供应商密钥只来自注册表。空绑定、缺密钥和数据库失败不回退 `.env` 的 `LLM_*` 模型配置。匿名连接必须显式声明 `auth_mode=none`，部署主密钥仍由 `LLM_SECRET_KEYS` 提供。

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

## 10. 2026-10-05 模型能力管理增量

根目录《11-AI模型管理详细设计.md》作为跨项目设计参考。本仓库沿用 Python、`/api/v1/llm`、snake_case、有序 model_ids、Fernet 及既有调用日志，未迁入 PPT 页面、Node 模块或工作区共享体系。

- 页面四个分类：供应商、模型、功能绑定、调用记录。通过 settings 提供的能力清单和参数范围渲染表单；语言协议为 OpenAI/兼容 Chat Completions、OpenAI Responses、Anthropic Messages、Gemini generate_content；嵌入只实现 OpenAI/兼容纯文本；重排为固定 `/rerank` 契约。
- 功能为 extract、retry、analysis、knowledge_ask、embedding、rerank。嵌入和重排暂只允许一个绑定，执行单次请求；重试和功能预算当前只用于语言调用，页面明确显示此边界。
- 新导入模型禁用，不覆盖已有模型、不自动绑定，最多 100 项并返回 created/skipped。目录列表不证明能力；专用重排不支持目录时明确返回 unsupported，仍允许手动登记和测试。
- 供应商/模型更新可传 revision 做 CAS；页面总是携带打开表单时的版本。为兼容既有客户端，省略版本仍可更新。功能排序和预算必须传 revision，在一次 PUT 事务保存，冲突 412；当前不是跨两次 HTTP 请求的原子操作。各功能分别保留草稿，刷新不覆盖草稿。
- 测试单次发起，不重试、不切换；持久 test_id 并可按 ID 查询。按模型种类选择探测。默认成功后 7 天过期；端点、认证与实质模型参数变化失效；相同值保存、改名、启停及额外重试数不使能力证明失效。旧配置或较早开始的测试只保留历史，不覆盖最新摘要。
- 调用列表按功能、模型、状态过滤并分页；invocation_id 查询按 request_ordinal 排序。每个语言调用发送前登记请求，回写同一条记录；显示模型/供应商名称快照、重试与用量。测试记录也保存名称快照及向量/重排数量，未知用量保留 null。历史记录软删除后仍保留。
- 2026-10-17：失败详情保留上游 HTTP 状态和响应正文（JSON、文本或 HTML），列表展开及调用链均保留换行、按文本展示。Agent SDK 只读取实际响应或已解析的错误 body，不拼接含请求的异常文本；语言、目录、嵌入、重排、生图的 HTTP 失败共用此处理。已知 API Key 和常见凭证字段在记录前隐藏；error_message 上限为16000字符，超长内容明确标记截断，接口读取不再截掉HTTP状态后的正文。旧记录若未保存正文，无法恢复；此改动不需要数据库迁移。
- 按 `Retry-After` 和指数随机退避等待，受总时间上限控制。SDK 无内建重试。拒绝结果不换源；HTTP 401/403、结构失败不原地重发。
- 迁移 0006 首次补齐旧调用可确认的名称快照；将空 analysis/knowledge_ask 绑定从 extract 显式迁移一次，此后清空即停止调用。旧模型同时绑定 embedding 与语言时整次迁移失败并提示先拆分登记，不自动删除绑定。

### 10.1 验证与尚未实现

使用本地模拟传输验证协议、错误分类和预算；使用隔离 schema + 事务回滚验证全链迁移和管理写入。模拟通过不代表用户供应商已经连通，也不执行真实收费测试。

本节为增量完成时的历史记录；视觉/多模态嵌入/生图由第 11 节继续补齐。其余仍未完成的设计包括：租户隔离与平台共享；远端目录分页；可调测试有效期；AES-GCM/AAD 与重加密管理；完整 DNS/内网许可与 SSRF 网络策略；幂等键和操作审计；持久 invocation 预算恢复、未知请求自动/人工对账及金额预算。现有语言请求账本会保存 running/unknown，但不宣称 Worker 崩溃后可恢复同一逻辑调用或已完成费用核对。嵌入/重排业务调用的完整用量账本与重试仍需接入；本次测试请求已记录相关数量。

OpenAI Responses 参数依据：[官方 API 参考](https://developers.openai.com/api/reference/resources/responses/methods/create)，`max_output_tokens` 最小 16；未填写 temperature 时不主动发送，以免不兼容模型收到隐式参数。

### 10.2 迁移 0006 DDL

```sql
ALTER TABLE llm_provider
ADD COLUMN protocol TEXT NOT NULL DEFAULT 'openai_compatible',
ADD COLUMN auth_mode TEXT NOT NULL DEFAULT 'api_key' CHECK (auth_mode IN ('api_key','none')),
ADD COLUMN revision INT NOT NULL DEFAULT 1,
ADD COLUMN config_revision INT NOT NULL DEFAULT 1,
ADD COLUMN credential_revision INT NOT NULL DEFAULT 1,
ADD COLUMN api_key_updated_at TIMESTAMPTZ,
ADD COLUMN last_test_config_revision INT,
ADD COLUMN last_test_id BIGINT;
UPDATE llm_provider SET auth_mode = 'none' WHERE api_key_ciphertext IS NULL;
ALTER TABLE llm_model
ADD COLUMN kind TEXT NOT NULL DEFAULT 'language' CHECK (kind IN ('language','embedding','rerank')),
ADD COLUMN api_mode TEXT NOT NULL DEFAULT 'chat_completions',
ADD COLUMN capabilities JSONB NOT NULL DEFAULT '["text_input","json_output"]',
ADD COLUMN extra_retries INT NOT NULL DEFAULT 1 CHECK (extra_retries BETWEEN 0 AND 10),
ADD COLUMN revision INT NOT NULL DEFAULT 1,
ADD COLUMN config_revision INT NOT NULL DEFAULT 1,
ADD COLUMN last_test_config_revision INT,
ADD COLUMN last_test_provider_revision INT,
ADD COLUMN last_test_id BIGINT;
ALTER TABLE llm_model DROP CONSTRAINT llm_model_provider_id_model_id_key;
CREATE UNIQUE INDEX ux_llm_model_active ON llm_model(provider_id,model_id) WHERE deleted_at IS NULL;
ALTER TABLE llm_feature
ADD COLUMN max_total_requests INT NOT NULL DEFAULT 6 CHECK (max_total_requests BETWEEN 1 AND 20),
ADD COLUMN deadline_seconds INT NOT NULL DEFAULT 600 CHECK (deadline_seconds BETWEEN 1 AND 86400),
ADD COLUMN revision INT NOT NULL DEFAULT 1;
ALTER TABLE llm_call_log
ADD COLUMN invocation_id UUID,
ADD COLUMN candidate_ordinal INT,
ADD COLUMN retry_ordinal INT,
ADD COLUMN request_ordinal INT,
ADD COLUMN model_name_snapshot TEXT,
ADD COLUMN provider_name_snapshot TEXT,
ADD COLUMN model_key_snapshot TEXT,
ADD COLUMN vector_count INT,
ADD COLUMN document_count INT;
CREATE UNIQUE INDEX ix_llm_call_invocation ON llm_call_log(invocation_id,request_ordinal);
UPDATE llm_call_log c SET provider_name_snapshot=p.name
FROM llm_provider p WHERE c.provider_id=p.id;
UPDATE llm_call_log c SET model_name_snapshot=m.display_name,model_key_snapshot=m.model_id
FROM llm_model m WHERE c.model_id=m.id;
CREATE TABLE llm_test (
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
);
CREATE INDEX ix_llm_test_model ON llm_test(model_id,created_at DESC);
INSERT INTO llm_feature(key,name,description) VALUES ('rerank','检索重排','对检索候选进行专用重排；未配置时保留混合检索顺序') ON CONFLICT DO NOTHING;
INSERT INTO llm_feature_model(feature_key,model_id,priority)
SELECT f.key,fm.model_id,fm.priority FROM llm_feature f CROSS JOIN llm_feature_model fm
WHERE f.key IN ('analysis','knowledge_ask') AND fm.feature_key='extract'
AND NOT EXISTS (SELECT 1 FROM llm_feature_model existing WHERE existing.feature_key=f.key);
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM llm_feature_model e JOIN llm_feature_model other
ON e.model_id=other.model_id WHERE e.feature_key='embedding' AND other.feature_key<>'embedding')
THEN RAISE EXCEPTION '同一模型同时绑定向量和语言功能，请先拆分模型登记后重新迁移';
END IF;
END $$;
UPDATE llm_model SET kind='embedding',api_mode='embeddings',
capabilities='["text_input","embedding"]',temperature=NULL,max_tokens=NULL
WHERE id IN (SELECT model_id FROM llm_feature_model WHERE feature_key='embedding');
```


### 10.3 Ollama 兼容嵌入实测（2026-10-05）

已用 Ollama 0.35.1 的 `qwen3-embedding:0.6b` 验证 `POST /v1/embeddings`：真实适配器批量返回 3 条 1024 维向量，管理页测试返回 1 条 1024 维向量。此结论只覆盖该实际端点/模型的纯文本嵌入，不证明所有 Ollama 模型或知识库全链路可用；原生 `/api/embed` 未单独登记。

模型测试增加运行中提示以及当次响应的 vector_count/embedding_dimensions/document_count，页面展示实际数量、维度和耗时，不回传向量内容。测试成功不自动绑定；知识库使用前需在功能页绑定嵌入模型并为资料构建相应索引。


## 11. 四类模型、能力与参数补齐（2026-10-05）

此前三个种类、固定能力、少量通用参数的版本没有完整满足根目录设计。本节按设计继续补齐，不将第 10 节列出的差距视为削减需求的授权。

- 基础种类为 language、embedding、rerank、image_generation。语言视觉由 image_input 表达；嵌入输入类型由 capabilities 派生为 text/multimodal，不加入音频或视频。
- adapter_profiles 返回 required/default/allowed capabilities、参数 schema、参数边界及适配器版本。supported_parameters 可按模型收窄；parameters 只允许受控键，禁止覆盖 model、URL、认证等请求身份。新增、编辑和目录导入共用字段，参数保存后实际参与业务和测试请求。
- 语言适配 OpenAI/兼容 Chat Completions、Responses，Anthropic Messages，Gemini generateContent 的文本和图片输入；JSON 是可选声明，现有抽取/分析功能仍要求 JSON。
- 嵌入支持 OpenAI/兼容文本与可选 dimensions，Gemini 原生 batchEmbedContents 的文本/图文、dimensions/task_type。标准 OpenAI embeddings 不假定支持图片。Ollama 的 /v1/embeddings 仍走既有真实兼容适配。
- 生图支持 OpenAI/兼容 images/generations 与 Gemini generateContent 图片输出，配置尺寸/质量/格式或宽高比/分辨率。只请求一张；验证 base64 内容可实际解码为 PNG/JPEG/WebP，不抓取返回的任意 URL。生图绑定独立于语言功能。
- 测试按 text、vision、embedding、multimodal_embedding、rerank、image_generation 分别保存。文本成功不能证明视觉或图文嵌入。长测试先持久登记测试及调用身份，202 返回后执行；刷新继续查询，不重发。超时/进程中断标为结果未知，不自动重试。
- 测试图仅从本站临时预览接口读取；配置改变或证据过期即不可预览，失效满 24 小时清理图片字节，保留历史事实。维护在管理查询与既有 worker 派发中运行，不新增业务素材。
- embedding_space_id 由服务端分配，参数/能力改变产生新身份，不能由用户手填相同 ID 冒充兼容。知识库读取已保存参数；完整跨实例兼容证明及索引固定候选恢复仍需进一步落实。

测试方式：协议模拟器验证载荷与严格响应；独立 PostgreSQL schema 验证迁移、参数、能力证明、临时预览与引用检查。模拟协议验证不等于云端服务已实测。

### 11.1 协议依据

- [OpenAI 视觉输入](https://developers.openai.com/api/docs/guides/images-vision)
- [OpenAI 图片生成](https://developers.openai.com/api/reference/resources/images/methods/generate)
- [Gemini 图文嵌入](https://ai.google.dev/gemini-api/docs/embeddings)
- [Gemini generateContent 参数](https://ai.google.dev/api/generate-content)
- [Anthropic 视觉输入](https://platform.claude.com/docs/en/build-with-claude/vision)

参数是已实现协议的上限，不代表每个模型接受清单中所有参数；模型管理员应收窄 supported_parameters，并显式测试实际服务。工具调用、流式响应与完整租户/共享/预算账本等缺口尚不能标为完成，见需求核对表。

### 11.2 迁移 0007 DDL

```sql
ALTER TABLE llm_model DROP CONSTRAINT llm_model_kind_check;
ALTER TABLE llm_model ADD CONSTRAINT llm_model_kind_check
        CHECK (kind IN ('language','embedding','rerank','image_generation'));
ALTER TABLE llm_model
        ADD COLUMN parameters JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(parameters)='object'),
        ADD COLUMN supported_parameters JSONB,
        ADD COLUMN embedding_space_id UUID;
UPDATE llm_model SET embedding_space_id=gen_random_uuid() WHERE kind='embedding';
ALTER TABLE llm_test
        ADD COLUMN call_log_id BIGINT REFERENCES llm_call_log(id),
        ADD COLUMN timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 90,
        ADD COLUMN result JSONB NOT NULL DEFAULT '{}',
        ADD COLUMN preview_data BYTEA,
        ADD COLUMN preview_mime TEXT,
        ADD COLUMN invalidated_at TIMESTAMPTZ;
ALTER TABLE llm_call_log ADD COLUMN image_count INT;
INSERT INTO llm_feature(key,name,description) VALUES
        ('image_generation','图片生成','图片模型管理、功能绑定与显式测试；不自动生成业务素材')
        ON CONFLICT DO NOTHING;
```


## 12. 配置预算统一与迁移 0012（2026-10-11）

模型管理字段范围由 `model_profiles.py` 的 MODEL_FIELDS/FEATURE_FIELDS 声明，API 请求校验及 `/llm/settings` 元数据共用；页面读取元数据，不再重复写上下限。模型 timeout_seconds 支持有限小数 ≥1，extra_retries ≥0，总请求次数与调用总时限 ≥1，均无人工最大值。max_tokens、top_k、top_n 移除统一人工上限；Responses 的 max_tokens 最小 16 等协议约束保留。

候选绑定数量与 failover_limit 仍最多 10；嵌入/重排仍只绑定一个模型。预算只限制真实执行，不修改正在运行的分析 attempt。下面增量取代 0006 的三个旧 CHECK；历史 DDL 保留以便迁移审阅。新增证据块配置与运行预算默认值一致。

```sql
ALTER TABLE llm_model DROP CONSTRAINT llm_model_extra_retries_check,
        ADD CONSTRAINT llm_model_extra_retries_check CHECK (extra_retries >= 0);
ALTER TABLE llm_feature DROP CONSTRAINT llm_feature_max_total_requests_check,
        DROP CONSTRAINT llm_feature_deadline_seconds_check,
        ADD CONSTRAINT llm_feature_max_total_requests_check CHECK (max_total_requests >= 1),
        ADD CONSTRAINT llm_feature_deadline_seconds_check CHECK (deadline_seconds >= 1);
INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.max_evidence_blocks', 'L1', 'int', '160'::jsonb, '每模块保留的原文证据块上限', false);
```
