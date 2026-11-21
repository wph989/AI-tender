# 05 · 后端 API 设计

> 2026-10-14：字段抽取及其复核、导出和金标接口已下线，当前分析协议见 [19](19-Agent检索与专题汇总.md)。

## 1. 设计原则

- **REST + SSE**：读操作走 REST；长任务进度走 SSE（比 WebSocket 简单，且天然支持断线重连）。
- **版本是路由主体**：涉及 bbox/锚点/证据的接口一律挂在 `versions/{version_id}` 下，避免"文档ID + 隐式当前版本"带来的歧义。
- **锚点是前端一等公民**：提供锚点直接反查接口，让前端做反向标注时无需拼装参数。
- **一切坐标出口都是归一化 bbox**（见 [03](03-数据模型与溯源设计.md) 第 3 节），后端不做任何按需坐标转换。
- **文件流支持 Range**：PDF.js 需要按需分片拉取大文件。

## 2. 接口清单

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/projects/{id}/files` | 批量上传文件（multipart），返回 project_file/job |
| `GET` | `/api/v1/versions/{vid}` | 版本详情（页数、转换信息、解析运行列表） |
| `POST` | `/api/v1/versions/{vid}/parse` | 触发解析（可指定 tier、是否强制重跑） |
| `GET` | `/api/v1/versions/{vid}/file` | 获取 PDF 基座流（支持 Range） |
| `GET` | `/api/v1/versions/{vid}/original` | 获取原始上传件流 |
| `GET` | `/api/v1/versions/{vid}/pages` | 页面清单（尺寸、旋转、文本层；不含页图 URL） |
| `POST` | `/api/v1/versions/{vid}/reparse` | **重新解析**（admin，二次确认；生成新的解析批次） |
| `GET` | `/api/v1/versions/{vid}/pages/{page_no}/elements` | 该页元素（含 bbox、锚点、类型） |
| `GET` | `/api/v1/versions/{vid}/outline` | 章节树 |
| `GET` | `/api/v1/versions/{vid}/anchors/{anchor}?parse_run_id=` | **锚点反查**元素（**必须带 run**：锚点只在所属 `parse_run` 内唯一） |
| `POST` | `/api/v1/versions/{vid}/anchors/resolve` | 批量锚点反查（请求体带 `parse_run_id`） |
| `GET` | `/api/v1/jobs/{job_id}` | 任务状态 |
| `GET` | `/api/v1/jobs/{job_id}/events` | **SSE 进度流** |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | 取消任务 |
| `POST` | `/api/v1/projects` | 创建项目（**不支持批量创建**） |
| `GET` | `/api/v1/projects` | 项目列表 |
| `GET` | `/api/v1/projects/{id}` | 项目详情（含文件清单、标段） |
| `PATCH` | `/api/v1/projects/{id}` | 修改项目元数据 |
| `DELETE` | `/api/v1/projects/{id}` | 软删除项目 |
| `POST` | `/api/v1/projects/{id}/files` | **批量上传文件**（多文件或 zip，自动解包与分流） |
| `PATCH` | `/api/v1/projects/{id}/files/{fid}` | 改元数据（重命名 / 角色 / 排序） |
| `POST` | `/api/v1/projects/{id}/files/{fid}/replace` | **换内容**（新版本 + 替代关系，与改元数据严格区分） |
| `DELETE` | `/api/v1/projects/{id}/files/{fid}` | 软删除文件（结果标记"来源已移除"） |
| `GET` | `/api/v1/config/items` | 配置项定义 + 当前生效值（按 L1/L2 分组） |
| `GET` | `/api/v1/config/releases` | 配置版本列表 |
| `POST` | `/api/v1/config/releases` | 创建配置版本（只动 L1 立即生效；含 L2 落 draft） |
| `GET` | `/api/v1/config/releases/{id}` | 版本详情：全量值 + diff + 影响清单 + 门禁预览 + 审计 |
| `POST` | `/api/v1/config/releases/{id}/acknowledge` | 变更影响清单逐条确认（谁确认了哪一条） |
| `POST` | `/api/v1/config/releases/{id}/activate` | 激活配置（受门禁约束） |
| `POST` | `/api/v1/config/releases/{id}/rollback` | 回滚到该版本 |
| `GET` | `/api/v1/config/audit` | 变更审计（谁 / 何时 / 哪个 key / 旧值 / 新值 / 理由） |

> 原 `/documents*` 四条已删：版本、解析状态与文件元数据都挂在项目文件下
> （`/projects/{id}/files`），再留一套文档级入口会出现两条互相漂移的路径；版本详情走 `/versions/{vid}`。

## 3. 关键接口详述

### 3.1 批量上传项目文件

```
POST /api/v1/projects/{id}/files
Content-Type: multipart/form-data

fields:
  files       file    必填，可重复多个
  archive     file    可选，ZIP 压缩包
  auto_parse  bool    可选，默认 true
  tier        string  可选，默认 standard
  ocr_mode    string  可选，默认 auto
  role        string  可选，由文件名推断
```

响应 `202 Accepted`：

```json
{
  "added": [
    {
      "project_file_id": 501,
      "display_name": "招标文件.pdf",
      "role": "main",
      "is_parseable": true,
      "version_id": null,
      "job_id": "job_01HXZ8Q3"
    }
  ],
  "jobs": ["job_01HXZ8Q3"],
  "skipped": []
}
```

上传只确认文件已入项目；可解析文件先返回 `202`，后台完成页面探测后才创建或复用 `document_version`。
因此响应中的 `version_id` 固定为 `null`，也不承诺 `deduplicated`；版本 ID 与最终状态通过 `GET /api/v1/jobs/{job_id}` 查询。
不可解析附件会返回 `job_id: null`，仍保留在项目文件清单中。

`GET /api/v1/projects/{id}` 的 `files[]` 同时返回 `latest_job`，包含最近任务的
`id / status / stage / progress / error_code / error_message`；没有任务时为 `null`。
前端在 `version_id` 仍为空、解析尚未生成 `parse_run` 时也依据该状态轮询；转换失败展示
后端错误原因，仅归档文件不等待转换。抽取已写入部分结果时，仍以任务状态决定是否继续刷新。

### 3.2 页面清单

```
GET /api/v1/versions/2048/pages?from=1&to=20
```

```json
{
  "total": 137,
  "page_count": 137,
  "pages": [
    {
      "page_no": 12,
      "width_pt": 595.276,
      "height_pt": 841.89,
      "rotation": 0,
      "has_text_layer": true
    }
  ]
}
```

> **原文没有服务端位图可回退**：预览的唯一数据源是 `GET /versions/{vid}/file`（Range 流式）。前端**必须**用 `width_pt/height_pt` 与 PDF.js 读到的视口尺寸做一次一致性断言（容差 1%）。若不一致，说明渲染基座与解析基座错位，应立即告警而不是继续渲染高亮——这是防止"高亮整体漂移"类事故的最后一道防线。

### 3.3 该页元素

```
GET /api/v1/versions/2048/pages/12/elements
```

```json
{
  "page_no": 12,
  "elements": [
    {
      "anchor": "p12b5",
      "type": "text",
      "order_no": 5,
      "bbox": [0.121, 0.402, 0.878, 0.437],
      "text": "3.2 投标保证金金额为人民币伍万元整（¥50,000.00）。",
      "source": "native",
      "continues_prev": false
    },
    {
      "anchor": "p12b6",
      "type": "table",
      "order_no": 6,
      "bbox": [0.110, 0.450, 0.890, 0.720],
      "html": "<table>...</table>",
      "source": "ocr"
    }
  ]
}
```

**为什么 `bbox` 用数组而不是对象**：前端直接展开为几何计算，少一层字段名映射，也便于与 MinerU 的原始格式对照。

### 3.5 锚点反查（反向标注）

```
GET /api/v1/versions/2048/anchors/p12b5?parse_run_id=77
```

```json
{
  "anchor": "p12b5",
  "page_no": 12,
  "bbox": [0.121, 0.402, 0.878, 0.437],
  "text": "3.2 投标保证金金额为人民币伍万元整（¥50,000.00）。",
  "type": "text"
}
```

用户在原文上框选修正时，前端先拿到所在块的锚点（可从已加载的 `elements` 中命中，或用 `resolve` 批量反查），再提交修正：

```
POST /api/v1/instances/4102/reviews
{
  "attempt_id": 9001,
  "action": "correct",
  "review_mode": "item",
  "new_value": { "amount": 50000, "currency": "CNY" },
  "evidence": [{ "anchor": "p12b5", "match_type": "manual" }]
}
```

### 3.7 批量上传文件到项目

```
POST /api/v1/projects/{id}/files
Content-Type: multipart/form-data

fields:
  files       file    必填，可重复多个
  archive     file    可选，zip 压缩包（自动解包）
  auto_parse  bool    可选，默认 true
```

响应 `202 Accepted`：

```json
{
  "added": [
    { "project_file_id": 501, "display_name": "招标文件.pdf", "role": "main", "is_parseable": true, "version_id": null, "job_id": "job_01HXZ8Q3" },
    { "project_file_id": 502, "display_name": "工程量清单.xlsx", "role": "boq", "is_parseable": false, "version_id": null, "job_id": null },
    { "project_file_id": 503, "display_name": "图纸总平面.dwg", "role": "drawing", "is_parseable": false, "version_id": null, "job_id": null }
  ],
  "jobs": ["job_01HXZ8Q3"],
  "skipped": []
}
```

**约定**

- **不允许批量创建项目**：项目必须逐个创建，此接口只做"项目内批量加文件"。
- zip 自动解包后按扩展名分流：可解析的走解析链路，图纸与嵌套压缩包**只入库不解析**（`is_parseable: false`），但仍可下载。
- 可解析文件先返回 `202`，`version_id` 在后台转换与页面探测完成前为 `null`；任务完成后可从 job 资源读取版本 ID。内容哈希复用在 worker 中判定，因此该响应不提前声称是否去重。
- 一次批量上传若包含多份可解析文件，返回**多个 job_id**（每个文件一个任务），前端需展示多任务进度。

**改元数据与换内容必须走不同接口**，这是刻意的：

```
PATCH  .../files/{fid}            { "display_name": "..." }        # 就地更新，不影响结果
POST   .../files/{fid}/replace    { "file": <新文件> }             # 生成新版本，旧版本标记"已被替代"
```

> 合并成一个接口会让用户以为改的是同一件事，导致溯源指向错误版本。

### 3.9 配置发布与影响确认

L1 保存后立即生效；L2 保存为草稿，管理员逐项确认变更影响后激活。配置版本、审计和任务快照继续保留。

### 3.11 文档重新解析

POST /api/v1/versions/{vid}/reparse 重新生成解析批次，沿用或显式指定档位与 OCR 模式。
已有分析报告固定原资料快照，新报告使用最新解析。专题重试走报告的 /retry 接口。

### 3.14 本轮新增的响应字段（不是新端点）

界面要回答「这一步为什么没有结果」，需要两处已有接口各多带一个字段。**没有新增端点，
也没有改数据模型（无 DDL 变更）**：

| 端点 | 新增字段 | 用途 |
| --- | --- | --- |
| `GET /projects/{id}` 的 `files[]` | `parse_tier` / `parse_ocr_mode` | 最近一次 `parse_run` 的档位与 OCR 模式（后者取自 `config_snapshot ->> 'ocr_mode'`）。文件清单页的「重新解析」要沿用它们，否则 `advanced` / `ocr` 的文件会被静默降回默认档 |

为什么只取「最近一条」抽取任务：界面要解释的是「这一次为什么一条结果都没有」，
历史任务对用户没有意义；真需要历史时应走任务列表，而不是把版本详情撑成日志。
## 4. SSE 进度

`POST /api/v1/jobs/{job_id}/cancel` 返回当前任务状态。尚未执行的 `pending` 任务立即进入 `canceled`；已开始的任务先进入非终态 `canceling`，`finished_at` 保持为空，重复取消幂等。已经完成或失败的任务返回 409。

`canceling` 期间仍占用当前阶段的在途配额，并阻止同版本或知识来源重复解析。本地转换退出后收尾；已提交的远端解析继续轮询到终态或确认任务不存在，再在同一事务内将 Job 和活动 ParseRun 标为 `canceled`。取消后的轮询不下载解析成果，也不因远端任务丢失而重新提交。提交结果不明时保留占用并提示 `parse_submission_unknown`，需人工核对远端任务后处理，不能把取消请求当作远端已经停止。

解析超时、轮询预算耗尽或提交结果未知时，任务进入非终态 `draining`，保留首次 `error_code`/`error_message`，`finished_at` 为空，继续占用配额并阻止重复解析。轮询只确认远端生命周期，不要求 MiddleJson 成果存在；确认远端终态或任务不存在后，同事务将 Job/活动 ParseRun 标为 `failed`，保留原错误。无句柄或未知重提的任务需人工核对，不能自动重新提交或依据旧句柄释放占用。

SSE 对 `canceling` 和 `draining` 发送 `progress`，最终进入 `canceled` 或 `failed` 才发送 `done` 并关闭连接；客户端应继续按终态判断结束等待。

```
GET /api/v1/jobs/job_01HXZ8Q3/events
Accept: text/event-stream
```

```
event: progress
data: {"stage":"converting","percent":10,"message":"Office 转 PDF"}

event: progress
data: {"stage":"parsing","percent":55,"message":"MinerU 解析中（第 3 / 5 步）","pages_done":137,"pages_total":137}

event: progress
data: {"stage":"extracting","percent":80,"message":"字段抽取中","fields_done":18,"fields_total":24}

event: done
data: {"status":"completed","version_id":2048}
```

约定：

- **`stage` 用固定枚举**（与状态机一致），前端据此渲染步骤条，**不解析 `message` 文案**。
- 事件 ID 递增，支持 `Last-Event-ID` 断线重连补发。
- 终态（`done` / `error`）后服务端主动关闭连接。
- 心跳：每 15 秒发一次注释帧，防止中间层（Nginx/网关）超时断连。

## 5. 错误码

统一响应体：

```json
{
  "error": {
    "code": "conversion_failed",
    "message": "文档转换失败：文件可能已损坏或需要密码",
    "detail": { "converter_version": "8.34.0", "trace_id": "job_01HXZ8Q3" },
    "retryable": false
  }
}
```

| code | HTTP | retryable | 说明 |
| --- | --- | --- | --- |
| `invalid_argument` | 400 | 否 | 参数错误 |
| `unsupported_format` | 400 | 否 | 不在支持矩阵内 |
| `conversion_failed` | 422 | **否** | Gotenberg 400 → 文件本身问题，重试无意义 |
| `conversion_unavailable` | 503 | 是 | Gotenberg 500/503 |
| `upload_size_mismatch` | 422 | 否 | MinerU 400 `bytes_mismatch` 或 413 `upload_size_mismatch` |
| `parse_failed` | 422 | 有条件 | MinerU 失败；附 `partial` 时的已完成产物 |
| `parse_unavailable` | 503 | 是 | MinerU 可安全重试的网络或服务故障 |
| `parse_submission_unknown` | 503 | **否** | 解析任务提交响应丢失；结果未知，不得盲目重放 |
| `parse_incomplete` | 200 | 是 | MinerU `partial`，**产物可用但需告知前端标记缺失** |
| `service_restarted` | 409 | 是 | 轮询或下载产物时 MinerU 索引 404；调用方从 document_version 取 PDF key/SHA-256 后重新提交 |
| `llm_unavailable` | 503 | 是 | 抽取模型不可用，解析产物仍可用 |
| `version_conflict` | 409 | 否 | 并发修改同一条结果 |
| `anchor_not_found` | 422 | 否 | 复核修正时锚点未指向当前版本的任何 element |
| `missing_evidence` | 422 | 否 | `correct` / `supplement` 未提供锚点 |
| `rerun_in_flight` | 409 | 是 | 同一实例已有进行中的重跑 |
| `reparse_ack_mismatch` | 409 | 否 | `acknowledge_invalidated_count` 与后端实际算出的一致数不符 |
| `gate_failed` | 422 | 否 | 配置未过门禁（硬门槛或影响清单未确认） |
| `not_found` | 404 | 否 | — |
| `forbidden` | 403 | 否 | 无权限或越权访问 |

**原则**：`retryable` 是给调用方的机器可读信号，**不要靠 HTTP 状态码猜测**。前端据此决定"重试按钮"是否可用。

## 6. 鉴权与权限

| 角色 | 权限 |
| --- | --- |
| `viewer` | 查看项目、页面、结果、证据。**不能下载原件** |
| `reviewer` | viewer + **下载原件** + 复核/修正结果 + 重跑单字段 |
| `operator` | reviewer + 上传/增删改项目文件、触发解析、取消任务、改 L1 配置 |
| `admin` | operator + 删除项目、L2 配置发布、冲突裁定、导出全量数据、**重新解析文档**、**发起抽检** |

- 所有资源查询强制带 `company_id` 过滤（多租户隔离在数据层，不在应用层靠判断）。
- 文档下载走**短时效签名 URL**（原件属于敏感资产），并记录审计日志：谁、何时、下载了哪一版。
- 越权访问一律返回 404 而非 403，避免泄露资源存在性。


### 6.1 多租户预留（本期不实现）

公司隔离、跨公司数据共享、平台管理员均为**后续扩展**。本期为单租户部署，但保留两件事：

- 所有资源查询**统一通过"当前租户上下文"注入 `company_id` 过滤**，业务代码不得直接写死。
- 越权访问一律返回 **404 而非 403**（避免泄露资源存在性），这一行为在多租户开启后同样适用。

## 7. 契约冻结清单

以下内容一旦上线即视为契约，改动需版本化并通知前端：

| 项 | 冻结内容 |
| --- | --- |
| `bbox` | 数组 `[x0,y0,x1,y1]`，0–1，左上原点，视觉方向 |
| `anchor` | `p{page}b{block}`，1-based |
| 证据字段名 | `anchor` / `page_no` / `bbox` / `char_start` / `char_end` / `quote` / `quote_source` / `match_type` |
| SSE `stage` 枚举 | 与流水线状态机一致 |
| 错误码 | 第 5 节表格 |
| `trigger` 枚举 | `first` / `hinted_rerun` / `user_rerun` / `param_rerun` / `reparse` / `manual_edit` |
| `action` 枚举 | `confirm` / `correct` / `supplement` / `reject` |
| `review_mode` 枚举 | `item` / `batch` / `spot_check` |
| 统计字段名 | `first_pass_rate` / `rescue_rate` / `cumulative_pass` / `manual_fallback_rate` / `rerun_button` |

## 知识库与综合分析接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/knowledge/collections` | 知识库与项目综合分析，见设计/14 |
| `POST` | `/api/v1/knowledge/collections` | 知识库与项目综合分析，见设计/14 |
| `GET` | `/api/v1/knowledge/collections/{collection_id}` | 知识库与项目综合分析，见设计/14 |
| `PATCH` | `/api/v1/knowledge/collections/{collection_id}` | 知识库与项目综合分析，见设计/14 |
| `DELETE` | `/api/v1/knowledge/collections/{collection_id}` | 知识库与项目综合分析，见设计/14 |
| `POST` | `/api/v1/knowledge/collections/{collection_id}/reindex` | 知识库与项目综合分析，见设计/14 |
| `GET` | `/api/v1/knowledge/collections/{collection_id}/search` | 知识库与项目综合分析，见设计/14 |
| `POST` | `/api/v1/knowledge/citations/resolve` | 知识库与项目综合分析，见设计/14 |
| `POST` | `/api/v1/knowledge/embedding/test` | 知识库与项目综合分析，见设计/14 |
| `POST` | `/api/v1/knowledge/sources/{source_id}/process` | 知识库与项目综合分析，见设计/14 |
| `GET` | `/api/v1/projects/{project_id}/knowledge` | 知识库与项目综合分析，见设计/14 |
| `PUT` | `/api/v1/projects/{project_id}/knowledge/collections` | 知识库与项目综合分析，见设计/14 |
| `GET` | `/api/v1/projects/{project_id}/analysis` | 知识库与项目综合分析，见设计/14 |
| `PUT` | `/api/v1/projects/{project_id}/analysis/settings` | 知识库与项目综合分析，见设计/14 |
| `POST` | `/api/v1/projects/{project_id}/analysis` | 知识库与项目综合分析，见设计/14 |
| `GET` | `/api/v1/analysis/reports/{report_id}` | 知识库与项目综合分析，见设计/14 |
| `GET` | `/api/v1/analysis/reports/{report_id}/modules/{module_key}/records` | 返回 records、evidence 与冻结 Skill 的 output_schema，实时核对资料权限 |
| `GET` | `/api/v1/analysis/reports/{report_id}/data` | 读取最新或指定的业务数据快照，按实时资料权限过滤 |
| `POST` | `/api/v1/analysis/reports/{report_id}/context` | 按单个标段获取大纲、正文或检查的编制依据 |
| `POST` | `/api/v1/analysis/reports/{report_id}/cancel` | 知识库与项目综合分析，见设计/14 |
| `POST` | `/api/v1/analysis/reports/{report_id}/retry` | 知识库与项目综合分析，见设计/14 |
| `POST` | `/api/v1/analysis/reports/{report_id}/reviews` | 对当前分析快照中的单条事项确认、修正或驳回 |
| `POST` | `/api/v1/knowledge/collections/{collection_id}/ask` | 知识库与项目综合分析，见设计/14 |
| `POST` | `/api/v1/projects/{project_id}/knowledge/ask` | 知识库与项目综合分析，见设计/14 |
| `GET` | `/api/v1/knowledge/answers/{answer_id}` | 知识库与项目综合分析，见设计/14 |

独立知识库上传复用 `/projects/{upload_project_id}/files`，集合详情提供该标识。
报告与问答返回逐项引用，定位前通过 `/knowledge/citations/resolve` 校验完整身份。

集合详情的每个来源增加 `semantic_ready`、`needs_reindex`：前者表示已完成且与当前绑定模型空间匹配，
后者表示全文已就绪但须重建当前空间的向量索引。不能仅凭 `embedding_model_id` 非空宣称语义检索可用。

同步知识库搜索对查询向量最多等待15秒，超时取消该请求并回退全文检索，返回 `mode=keyword` 和
可读的 `warning`；页面展示该提示，避免冷启动拖到代理断开后只返回500。后台问答仍使用模型配置的等待预算。
来源的 `processing_status` 保留最新转换/提交/解析任务状态，`error_message` 优先返回这条任务的错误，
从而在尚无解析批次时也能显示文件失败原因。

完整分析等待阶段如发现资料已失败、仅部分解析或格式不支持，报告转为 `failed`，错误列出文件。
修复后可重试，或重新发起 `allow_partial=true` 的分析。从未固定检索批次的报告重试返回 `waiting`，
等待资料可用；已经开始的报告重试返回 `pending` 并保留原资料批次。
`retry` 接受 `failed`、`partial`、`canceled`、`completed` 报告；显式 `module_keys` 可重跑已完成模块，
已完成模块从零开始，其它模块保持原状态。不传 `module_keys` 时只补跑失败与已取消模块；
取消时尚未创建任何模块的报告可以重新进入 `waiting`。
恢复进程中断留下的 `running` 模块不受此限制。`runtime_version` 与当前运行时不一致的历史报告只读展示，
补跑返回 409 `runtime_retired`。历史报告不比较参考来源快照：旧流程不记录该快照，否则库中只要有参考来源
就会恒判为“材料已变化”。

DeepAgents 报告补跑可选 `max_output_tokens`（整数，最小值 1，无人工最大值）和 `timeout_seconds`（整数 ≥1，无人工最大值），只覆盖新 attempt 的对应字段；其余限值（模型/工具次数、证据块、上下文、时长）取配置中心当前值，用户调大预算后补跑立即生效。旧 attempt、报告创建时的快照和累计用量保留不回写，请求次数不随之扩大。输出仍受模型自身配置的 `max_tokens` 和供应商实际能力约束。各配置的实际限制与建议见 `docs/工程/18-配置限制清单.md`。
模型路由收到非法 JSON 时，在换候选前最多追加两次格式纠正提示，计入既有总请求/时间预算；该行为不放宽引用校验，也不把连接、配置、权限或明确拒绝错误当作格式问题重试。
结论的支持性检查最多反馈两次供 Agent 补读或修正，仍受模块总步数限制；最终不支持的条目明确标记 `insufficient` / `unsupported`。


### 业务快照与编制上下文

`GET /analysis/reports/{report_id}/data?snapshot_id=...` 返回
`report_id / snapshot_id / revision / schema_version / stale / data`。
省略 `snapshot_id` 时读取最新正式快照；指定旧版本仍可查看，但 `stale=true`，不能作为新编制任务的依据。
报告正在补跑、材料或分析设置变化时也标记过期。
报告取消后若模块尚未退出或本轮正式快照尚未发布，旧快照也保持过期，`context` 返回409。
`data` 的业务结构、引用和 DDL 见
[14-知识库与综合分析实现](14-知识库与综合分析实现.md) 的“单标段编制的业务数据”。
读取会按实时权限过滤，不直接把数据库中的历史 JSON 原样返回。
历史快照只有在当前报告终态、冻结资料与专题成果指纹一致时才可复核；旧版快照由此读取的专题成果恢复输入签名，
资料或专题成果不匹配时继续标记过期。

`POST /analysis/reports/{report_id}/reviews` 按当前快照 ID 和事项 ID 追加确认、修正或驳回记录；
保存前会在同一报告事务中复核报告快照、项目资料设置及原文权限。有证据的“不适用”结论沿用其
`review_id` 提交相同的裁定；只有人工确认的不适用结论进入编制覆盖信息。

`POST /analysis/reports/{report_id}/context` 只读取依据，不创建生成任务或调用正文生成模型：

```json
{
  "snapshot_id": 123,
  "purpose": "outline",
  "lot_id": 7,
  "requirement_ids": [],
  "offset": 0,
  "limit": 100
}
```

| 字段/用途 | 契约 |
| --- | --- |
| `snapshot_id` | 必填，正整数；须属于该报告且为当前有效快照 |
| `lot_id` | 单个正整数；多标段必填，单标段可省略并解析为唯一标段；无标段且没有未决分标线索时允许项目级编制 |
| `purpose=outline` | 公共及所选标段的项目事实、适用要求、完整格式树、关系、覆盖和缺口 |
| `purpose=content` | 必须提供本快照、所选标段下有效的 `requirement_ids`（最多500条）；额外检索已关联企业/历史库，片段单列 `references`，可能带 `reference_warning` |
| `purpose=check` | 所选范围的完整要求清单及分批记录，不能用检索 top-k 代替完整检查输入 |
| `offset / limit` | 要求列表分页；默认0/100，limit为1–200，事实与格式树不分页 |

响应包含 `schema_version / snapshot_id / purpose / lot_id / facts / requirements / format_nodes /
relations / coverage / gaps / unresolved / readiness / references`，另有完整 `requirement_manifest`
（要求 ID 数组）、`total_requirements` 和 `next_offset`。应持续读取直到 `next_offset=null`，
各页固定同一快照、用途和标段。正文用途的清单限定为本次显式选择的要求。
`readiness` 为 usable、partial 或 unavailable；partial 会同时返回已核实可用数据及未决事项。

| 状态 | 错误码与含义 |
| --- | --- |
| 400 | `invalid_argument`：字段类型或取值不满足 schema，例如传入标段数组 |
| 404 | `not_found`：报告不存在或不属于当前公司 |
| 409 | `data_reanalysis_required`：旧协议报告没有业务数据，需重新分析 |
| 409 | `data_not_ready`：没有可读取的正式快照，或指定快照不属于该报告 |
| 409 | `report_running`：报告尚未结束或正在补跑 |
| 409 | `data_stale`：来源/设置变化，或指定的不是最新快照 |
| 409 | `source_unavailable`：必要来源删除或撤销，含检索进行期间发生的撤销 |
| 422 | `lot_selection_required / invalid_lot / lot_scope_unresolved`：标段未显式选择、不属于快照或分标线索未解决 |
| 422 | `requirements_required / invalid_requirements`：正文未选要求，或要求来自其他范围、已失效、尚未确认 |

## AI 模型管理接口

参数与行为见 [12-LLM管理与模型路由](12-LLM管理与模型路由.md) 第 10 节。路径保留 `/llm`，不增加平行 `/ai` 入口。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/llm/settings` | 能力清单、参数范围与加密设施状态 |
| `GET` | `/api/v1/llm/tests` | 最近测试记录 |
| `GET` | `/api/v1/llm/tests/{test_id}` | 查询执行状态、能力证明有效性与当次用量 |
| `GET` | `/api/v1/llm/tests/{test_id}/preview` | 有效生图测试的临时图片，失效返回 410 |
| `GET` | `/api/v1/llm/providers` | 供应商列表 |
| `POST` | `/api/v1/llm/providers` | 创建供应商 |
| `PATCH` | `/api/v1/llm/providers/{provider_id}` | 修改供应商与密钥 |
| `DELETE` | `/api/v1/llm/providers/{provider_id}` | 软删除供应商及未被引用的子模型 |
| `POST` | `/api/v1/llm/providers/{provider_id}/test` | 目录连通测试 |
| `GET` | `/api/v1/llm/providers/{provider_id}/remote-models` | 服务端代理远端目录 |
| `POST` | `/api/v1/llm/providers/{provider_id}/models/import` | 勾选导入，返回新增及跳过数量 |
| `GET` | `/api/v1/llm/models` | 模型列表 |
| `POST` | `/api/v1/llm/models` | 手动创建模型 |
| `PATCH` | `/api/v1/llm/models/{model_id}` | 修改能力与参数 |
| `DELETE` | `/api/v1/llm/models/{model_id}` | 检查引用后软删除模型 |
| `POST` | `/api/v1/llm/models/{model_id}/test` | 按 capability 测试一次，保留同步兼容入口 |
| `POST` | `/api/v1/llm/models/{model_id}/tests` | 持久受理后 202 返回 test_id，页面轮询查询 |
| `GET` | `/api/v1/llm/features` | 功能及完整有序绑定 |
| `PATCH` | `/api/v1/llm/features/{feature_key}` | 修改调用预算 |
| `PUT` | `/api/v1/llm/features/{feature_key}/models` | 原子保存绑定顺序与预算 |
| `GET` | `/api/v1/llm/calls` | 分页调用日志或有序请求链 |

`GET /llm/calls` 可使用 feature_key、model_id、status、invocation_id、limit、offset。测试响应包含 test_id、status、latency_ms、http_status、error；HTTP 200 仅表示操作完成，status 为 error/unsupported 时不能显示通过。

模型测试成功时还返回适用的 vector_count、embedding_dimensions、document_count；不适用项为 null，供应商目录测试可省略。这些诊断字段不包含向量内容，维度信息当前仅在本次响应展示。


## DeepAgents 模块运行管理

新报告执行与恢复契约见 [16-DeepAgents标书分析运行时](16-DeepAgents标书分析运行时.md)。历史报告保留原快照兼容。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/analysis/reports/{report_id}/runs/{run_id}/events` | 模块审计分页，after默认为0，limit为1到200；验证公司及报告归属 |

报告详情增加 runtime_version、runtime_settings、reference_snapshot、summary 及各模块 runs。
新报告 coverage.mode=agent_research，界面显示13个专题的完成数，不使用 scanned_blocks/total_blocks。
补跑为所选模块创建新 attempt；原运行记录和未选中模块保留。取消接口与报告详情返回 `canceling`：
取消先把报告置为 `canceled`，无执行者的排队/遗留运行立即终止，持有会话锁的模块由心跳取消并释放配额。
`canceling=true` 时页面持续轮询并禁用补跑；旧控制器或模块仍持锁时，补跑返回409 `cancellation_pending`。
重复取消幂等，不影响已完成模块。取消与领取任务通过报告行锁串行化，避免取消后又领取排队任务。
