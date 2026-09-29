# 01 · 接口调研：MinerU

> 调研对象：`opendatalab/MinerU`
> 调研版本：**4.0.7**（发布 2026-09-23），要求 `>=4.0,<5`
> 调研日期：2026-09-26
> 接入方式：**自托管容器 + `/v1/*` HTTP API**（不使用官方云端）

## 1. 为什么选它

| 能力 | 说明 |
| --- | --- |
| 中文版面解析 | 针对中文文档的版面/表格/公式模型，国内招标文件场景表现好于通用英文方案 |
| 扫描件 OCR | 内置完整 OCR 子系统（检测 + 方向分类 + 识别），非外部依赖 |
| 多格式 | PDF / 图片 / Office / OFD / HTML / EPUB / CSV 统一入口 |
| 坐标输出 | 公开 schema 中 bbox 已是 **0–1 归一化坐标**，可直接对应页面相对位置 |
| 稳定定位符 | 官方提供 `page/block/char` 三级 locator，且把"Agent 答案可追溯到 page/block/bbox/source hash"列为 P0 目标 |
| 本地化 | 默认本地解析，`--remote` 为显式选项，满足涉密要求 |

**它替我们覆盖了流水线的 L1（内容提取）与 L2（版面结构化）两层**，我们只需在 L3（业务字段抽取）构建自己的 Agent。

## 2. 部署形态

三种可用入口，本项目选第 2 种：

| 形态 | 命令 | 用途 |
| --- | --- | --- |
| CLI | `mineru parse <file>` | 人工调试、问题复现 |
| **自托管 API 服务** | `mineru-kit api-server --host 0.0.0.0 --port 8000 --tier standard` | **生产接入** |
| 多 GPU 编排 | `mineru-router --host 0.0.0.0 --port 8002 --local-gpus auto --worker-tier standard` | 扩容时使用，对外暴露完整 `/v1/*` |
| Gradio WebUI | `mineru-kit webui` | 仅内部演示，不用于集成 |

- OpenAPI 文档：`http://<host>:8000/docs`
- 鉴权：服务以 `--api-key` 启动时，请求需带 `Authorization: Bearer $MINERU_API_KEY`
- **`--upload-dir` 与进程内状态**：上传的文件字节存放于 `--upload-dir`（未配置时是临时目录，正常退出即删除），而"上传/文件/任务"的资源索引是**进程内状态**。→ **服务重启后 job_id 全部失效**，我们的 Worker 必须能识别并重建（见第 8 节）。

## 3. 能力矩阵（重要限制）

**格式 × 档位**

| 输入类型 | 可用档位 | 页面几何 |
| --- | --- | --- |
| PDF（含扫描件） | `flash` / `basic` / `standard` / `advanced` | **完整**（page_size + bbox） |
| 图片（png/jpg/webp/tiff…） | 全部四档 | 完整（单页） |
| Office（doc/docx/ppt/pptx/xls/xlsx） | **仅 `flash`** | **无**（整文档解析，reflow） |
| OFD / HTML / MHTML / EPUB / CSV(TSV) / RTF / ODF | **仅 `flash`** | **无**（整文档解析） |
| 纯文本（txt/md/rst/tex） | 不解析 | — |

三条由此推出的结论：

1. **Office 走原生通道拿不到页码与 bbox**，且非 PDF 输入**不接受 `--pages` 参数**（整文档解析，没有页的概念）。
2. 官方 README 另有一条佐证：Office 的 block image 只对**图片块**可用，文字块无法按块导出影像，即没有可靠页面几何。
3. → **非 PDF 必须先经 Gotenberg 转成 PDF**，这是设计文档 [02](02-接口调研-LibreOffice.md) 的存在理由。

**档位语义**

| 档位 | 引擎 | 用途 |
| --- | --- | --- |
| `flash` | 原生文本解析 / Flash OCR | 快速预览、建索引。**不可作为正式结果** |
| `basic` | ONNX 或 Torch 小模型 | OCR、公式、表格；无需 VLM |
| `standard` | 小模型 + VLM | **本项目默认**，复杂版面与高质量解析 |
| `advanced` | 同 standard，更多推理计算 | 疑难件（扫描质量差、复杂表格） |

- `mineru-kit parse` 与 Python `parse()` 对 PDF **默认 `standard`**；`advanced` 必须显式指定。
- 数字 PDF 走文本层直取（"Native text parsing needs no inference models"），**扫描页才落 OCR 通路，逐页自适应**。一本标书里数字页与盖章/手签字页混排时无需拆分文件。

**硬件要求**

| 档位 | 模型引擎 | 模型体积 | 最低内存 | 加速 |
| --- | --- | --- | --- | --- |
| `basic` | ONNX | ~0.8 GB | 2 GB | 无需（CPU 可跑） |
| `basic` | PyTorch | ~0.8 GB | 8 GB | 建议 GPU/MPS |
| `standard`/`advanced` | ONNX + llama.cpp | ~2 GB | 8 GB | CPU 可跑（Vulkan 推荐） |
| `standard`/`advanced` | PyTorch + vLLM | ~3 GB | 16 GB | GPU 8 GB+ VRAM |

> 官方提示：8 GB 显存只是**规划起点，不是保证**。高吞吐部署建议按 16 GB 系统内存规划。

## 4. V1 HTTP API 请求周期（已核实）

> 核实基准：仓库 `master` @ `9227669`（版本 4.0.7）。证据来自官方文档 + 被单测覆盖的示例脚本 `scripts/http_api_example.sh` + `mineru/parser/api_server.py` 源码 + `tests/unittest/test_parser_api_contract.py` 断言。
> **尚未做过真实 HTTP 实测**，阶段 0 需实跑验证（尤其错误码，见 8.1 节）。

### 完整序列

| 步骤 | 方法与路径 | 成功码 | 说明 |
| --- | --- | --- | --- |
| 1 创建上传 | `POST /v1/uploads` | 200 | body 见下 |
| 2 上传字节 | `PUT {upload_url}` | 200 | 必须原样使用返回的 method/url/headers |
| 3 完成上传 | `POST /v1/uploads/{upload_id}/complete` | 200 | 重复调用返回 409 `upload_already_terminal` |
| 4 提交解析 | `POST /v1/parse/jobs` | **202** | 返回 `job_id`，初始状态 `queued` |
| 5 轮询状态 | `GET /v1/parse/jobs/{job_id}` | 200 | 文档建议初始 2 秒、指数退避、上限 30 秒 |
| 6 下载产物 | `GET /v1/files/{file_id}/content` | 200 | 自托管直接返回字节；官方云 302 到对象存储 |
| 能力发现 | `GET /v1/health` | 200 | **无需鉴权** |
| 档位探测 | `GET /v1/tiers` | 200 | 查询当前服务实际支持的 tier |

### 步骤 1：创建上传

```json
{
  "filename": "tender.pdf",
  "bytes": 5242880,
  "mime_type": "application/pdf",
  "purpose": "parse",
  "sha256sum": "<64 位小写 hex>"
}
```

- `bytes` 必填且必须 > 0；`purpose` 取 `parse` 或 `input_image`。
- **`sha256sum` 命中已有文件时直接返回 `status: completed` 并内嵌 `file` 对象，跳过步骤 2、3**——内容寻址去重是服务端原生能力。
- upload 的 `status` 枚举：`pending` / `completed` / `cancelled` / `expired`。
- 响应返回 `upload_url`、`upload_method`、`upload_headers`，必须原样使用，不要硬编码。

### 步骤 2：上传字节

- 自托管返回**同源** URL：`/v1/uploads/{upload_id}/content`，`upload_method` 为 `PUT`，`upload_headers` 为 `{"Content-Type": "<mime_type>"}`。
- 同源且服务启用 `--api-key` 时，此 PUT 需带 `Authorization: Bearer <key>`。
- **跨源（官方云预签名 URL）绝不可附加 MinerU Key**，否则泄漏凭据。
- 本项目使用自托管 MinerU，适配器只接受与 API 同源的 upload_url，避免把标书交给未配置的存储服务。

### 步骤 4：提交解析任务

```json
{
  "files": [
    { "source": { "type": "file_id", "file_id": "file-..." }, "page_range": "all" }
  ],
  "tier": "standard",
  "ocr_mode": "auto",
  "output_formats": ["middle_json", "zip"]
}
```

- `files[].source` 四种类型：`file_id` / `url` / `inline`（base64）/ `local`（仅自托管且开启 `--allow-local-source`）。
- **`page_range` 支持 `all`**——必须显式传，否则默认只解析前 10 页。非 PDF 传页码会报 `page_range_invalid`。
- **`ocr_mode` 三态**：`auto`（默认，逐页自动判断）/ `txt`（强制用文本层）/ `ocr`（强制 OCR）。**一个 job 内所有文件共用此设置。**
- `tier`：`flash` / `basic` / `standard` / `advanced`。服务实际支持哪些**以 `GET /v1/tiers` 为准**；不支持时返回 503 `quality_tier_unavailable`。
- `output_formats` 默认 `["markdown"]`；自托管 4.0.7 白名单见第 7 节。
- **`callback` 自托管不支持**，传了返回 400 `invalid_request`——适配器不要发送该字段，只能轮询。

### 步骤 5：状态查询

```json
{
  "job_id": "job_...",
  "status": "completed",
  "progress": { "completed": 1, "failed": 0, "total": 1 },
  "files": [
    {
      "file_id": "file-...",
      "name": "tender.pdf",
      "status": "completed",
      "parse": { "model_used": null, "duration_ms": 8234, "parser_version": "4.0.7" },
      "output_files": {
        "middle_json": { "file_id": "file-...", "bytes": 184320 },
        "zip": { "file_id": "file-...", "bytes": 286720 }
      },
      "error": null
    }
  ]
}
```

- job 状态：`queued` / `running` / `completed` / `partial` / `failed` / `canceled`。
- 文件级状态：`queued` / `running` / `completed` / `failed`（**没有 canceled**）。
- **`output_files` 是按格式命名的对象，不是数组**，取值路径为 `files[].output_files.middle_json.file_id`。
- 未请求的格式键会以 `null` 出现——「键缺失」与 `null` 视为等价。
- `parse.model_used` 在本地实现中**恒为 `null`**，不可用于模型路由判断；`parser_version` 是包版本。
- `links.self` 是相对路径，适配器需自行拼 base URL。

### 能力发现响应

```json
{
  "status": "ok",
  "version": "4.0.7",
  "features": {
    "webhook": false,
    "output_formats": ["markdown", "middle_json", "structured_content", "zip"],
    "sources": ["file_id", "url", "inline"]
  }
}
```

- 开启 `--allow-local-source` 时 `sources` 增加 `local`。
- 若 `--preload-models` 预加载失败，`/v1/health` 返回 **503** 而非 200——健康检查必须按非 200 判定为不健康。

### ⚠️ 状态拼写不一致（真实坑）

| 对象 | 取消状态的拼写 |
| --- | --- |
| upload | `cancelled`（**双 l**，英式） |
| parse job | `canceled`（**单 l**，美式） |

解析任务终态判断必须用单 l 的 `canceled`。写错会永远等不到终态，表现为任务"卡死"。

### ⚠️ 没有幂等键

文档提到 `Idempotency-Key`，但 4.0.7 源码中**没有任何实现**，官方 SDK 文档也提示当前不会自动重试创建任务。因此适配器必须：

1. 自己持久化 `job_id` 与提交状态（不能只依赖服务端）。
2. **禁止盲目重放**创建请求——一次网络抖动可能制造重复解析。
3. 服务重启后 `upload_id` / `file_id` / `job_id` 全部失效（索引是进程内状态），只能按 `sha256` 重新提交；因命中秒传，重提交成本很低。

## 5. MiddleJson 2.0 契约

这是我们要消费的核心产物。

```
MiddleJson
  └── pages: list[PageInfo]
        PageInfo
          └── blocks: list[PageBlock]
                InlineContentBlock
                  └── content: list[InlineSpan]
```

> **已核实：V1 API 可直接获取 MiddleJson** ✅
> 在 `POST /v1/parse/jobs` 的 `output_formats` 中显式加入 `"middle_json"` 即可；生成逻辑是 `result.to_dict(skip_defaults=True)` 序列化为 UTF-8 JSON，文件名为 `{源文件名}.middle.json`，再用 `files[].output_files.middle_json.file_id` 经 `GET /v1/files/{id}/content` 下载。
> 官方 Python SDK 连远程 API 时**默认请求的正是这一格式**。→ **无需 CLI 旁路**，P0 阻塞项已消除。
已验证的事实：

| 事实 | 对我们的影响 |
| --- | --- |
| schema 版本常量 `MIDDLE_JSON_SCHEMA_VERSION = "2.0"`（3.0 从未发布） | 落库时记录 `schema_version`，升级时可判定是否需要重解析 |
| **public schema 中 bbox 统一为 0–1 归一化坐标或 `null`** | 省去我们自己归一化的步骤，但 `null` 必须处理 |
| **`PageInfo` 不含 `page_size`** | 无法由 MiddleJson 还原绝对坐标 → 页面尺寸必须由我们自己的 PDF 引擎读出并落库 |
| 旧版带 bbox/图片职责的 Line/Span **不会恢复**；`InlineSpan` 只表达行内文字/公式/代码/链接 | 块级定位是官方长期契约，行内级定位不要指望 |
| `ParseResult.to_dict()` 输出 `schema_version: "2.0"` + MiddleJson 字段，无顶层 `_backend`/`_meta` | 不要依赖非公开字段 |
| Pipeline / VLM / Hybrid / Office / HTML 各 backend 的 block type 与 span 粒度**存在差异** | 必须记录本次解析的 `backend`，归一化时按 backend 分支处理 |

**待实测验证（P0）**：bbox 的**原点方向**（左上还是左下）。官方文档只写"0–1 归一化"，未声明原点。→ 用一份已知内容的 PDF 在 `standard` 档跑一次，取首页第一个块的 bbox 与页面位图（一次性调试渲染，不进产品链路）目视比对即可确定，结论写入 [03](../设计/03-数据模型与溯源设计.md) 并锁定。

## 6. Locator 规范

```
doc:{short_id}
doc:{short_id}/tier:{tier}
doc:{short_id}/tier:{tier}/page:{page_no}
doc:{short_id}/tier:{tier}/page:{page_no}/block:{block_no}
doc:{short_id}/tier:{tier}/page:{page_no}/block:{block_no}/char:{offset}
```

- `page`、`block` 为 **1-based**；`char` 为**块内 0-based** 字符偏移。
- `char` 偏移的存在意味着我们**可以做到块内字符级证据**（用于文本层精确高亮），这是块级 bbox 之外的额外精度。

**使用约束（关键）**

- `doc:{short_id}` 省略 tier 时，服务会选最高质量的**已缓存**结果——依赖缓存状态，**不可用于业务逻辑**。
- `short_id` 是 MinerU 本地文档库的标识，绑定其缓存与配置；**清缓存、换机、升级、`invalidate` 都会使其失效**。
- → **业务主键必须是自有的 `sha256 + version_no`**；locator 仅作为"可重算的派生引用"存档，用于问题复现与人工核对，不参与任何业务关联。

## 7. 输出格式与获取方式

**自托管 4.0.7 的实际能力白名单**（唯一事实来源是 `GET /v1/health` 的 `features.output_formats`）：

| 格式 | 可用 | 说明 |
| --- | --- | --- |
| `markdown` | ✅ | 默认格式，仅用于人工排查 |
| **`middle_json`** | ✅ | **我们的主要产物**，含版式/块/坐标 |
| `structured_content` | ✅ | 通用结构化输出 |
| `zip` | ✅ | 含**文档内嵌图形**的图片 sidecar。**不含整页渲染图**——我们也不需要：在线预览由前端 `pdfjs-dist` 直接渲染 PDF 基座，服务端只在多模态抽取时按 bbox 裁剪局部图（见 [04](../设计/04-解析流水线与抽取Agent.md) 第 ③ 阶段），不依赖此产物 |
| `html` / `latex` / `docx` | ❌ | 协议枚举中存在，本地实现拒绝（匿名 403 `feature_requires_api_key`；带 Key 400 `unsupported_output_format`） |

注意事项：

- `images` **不是合法格式值**，不要尝试。
- **不要用 `json` 或 `content_list_v2` 作为格式名**——文档明确它们不是正式格式名。
- 图片命名：`images/page_{page_idx}_{parent_type}_{parent_index}.{ext}`，**页索引从 0 开始**（与 locator 的 1-based 页码不同）。不要自行拼接文件名，一切以文档内实际引用为准。
- `mineru parse --json` 返回的是面向 Agent 的命令响应，**不是 MiddleJson**，二者不能互相转换。我们的 Worker 必须走 V1 API：`output_formats: ["middle_json", "zip"]`。
- **zip 默认不下载**：首次解析只取 `middle_json`。只有确实需要「文档内嵌图形」时才按需拉取该 zip，并按文档 `sha256` 缓存复用——排版类产物不必人人下载一遍。

**我们的固定取值**

```json
"output_formats": ["middle_json", "zip"]
```

不带 `markdown`：正文由 MiddleJson 还原，多一份 Markdown 只增加带宽与存储，没有使用场景。`zip` 保留在请求里但**默认不下载**：它只能取到「文档内嵌图形」，页面几何与坐标都不依赖它，所以按需再拉。

## 8. 约束、坑与我们的对策

| # | 风险 | 对策 |
| --- | --- | --- |
| 1 | **`mineru parse` 对 PDF 默认只解析前 10 页** | 显式传 `--pages all`；并在代码中禁止不带页范围的调用（封装层强制） |
| 2 | **服务重启后 job 索引丢失**（进程内状态） | 提交任务前先把 `sha256` 落库并记录为 `submitted`；服务重启后按 sha256 重新提交即可命中文件复用，避免重复解析 |
| 3 | Office 格式只有 `flash` 档、无几何 | 上游统一转 PDF（[02](02-接口调研-LibreOffice.md)） |
| 4 | 官方云端会**上传文档** | 生产环境禁用 `--remote`；适配器层不实现该参数 |
| 5 | 匿名遥测 | 部署时执行 `mineru telemetry disable` |
| 6 | 大版本 schema 不兼容 | 锁定 `>=4.0,<5`；原始产物按 `doc_version` 存档；升级前用存档产物跑回归比对 |
| 7 | `partial` 被误判为成功 | 终态解析必须区分四种；`partial` 落库并标记缺失产物 |
| 8 | 模型下载需联网 | 镜像构建阶段预下载模型，运行时不联网 |
| 9 | bbox 可能为 `null` | 落库层允许 `bbox` 为空，此时该证据**降级为页级定位**并在 UI 上标注 |
| 10 | 扫描件 OCR 错字进入 `quote` | 记录证据来源（`native` / `ocr`），UI 允许人工更正 |

### 8.1 4.0.7 已核实的额外差异

| # | 差异 | 影响与对策 |
| --- | --- | --- |
| 1 | **错误码文档与源码不一致**：文档写 `400 bytes_mismatch`，源码用 `413 upload_size_mismatch`（PUT 与 complete 两处） | 适配器两个码都要容错，不能只匹配文档写的那个 |
| 2 | **状态拼写**：upload 用 `cancelled`（双 l），job 用 `canceled`（单 l） | 见 4 节；写错会表现为任务"卡死" |
| 3 | **无幂等键实现** | 自己持久化 job 状态，禁止盲目重放（见 4 节） |
| 4 | `callback` 自托管不支持 | 适配器不要发送该字段 |
| 5 | `/v1/health` 在模型预加载失败时返回 **503** | 健康检查按非 200 判定不健康，并解析错误 envelope 的 `code` |
| 6 | 本地拒绝 `html`/`latex`/`docx` 输出 | 只用第 7 节白名单内的格式 |
| 7 | `parse.model_used` 恒为 `null` | 不要用它做任何判断；模型信息以我们自己的配置快照为准 |
| 8 | 服务重启后 `upload_id`/`file_id`/`job_id` 全部失效 | 已在第 4 节给出恢复策略 |

## 9. 可选增强（默认关闭，建议开启）

MinerU 通过 `$MINERU_HOME/config.yaml` 的 `llm_aided` 段（OpenAI 兼容接口）提供两项 LLM 后处理，**默认均为 `false`**：

```yaml
llm_aided:
  api_key: ${MINERU_LLM_API_KEY:-}
  base_url: https://<自建网关>/v1
  model: <模型名>
  enable_thinking: false
  max_concurrency: 16
  features:
    title_leveling: true                # 段落级标题归并为 2-6 级层次
    cross_page_table_cell_merge: true   # 跨页表格边界行单元格是否延续
```

- `title_leveling`：正好用于构建**章节树**（[04](../设计/04-解析流水线与抽取Agent.md) 的 Agent 分块依赖它）。注意它仅在 `MiddleJson.is_full_document` 为真时运行——**按页选取输入会跳过**，所以必须整文档解析。
- `cross_page_table_cell_merge`：正好治**评标办法表跨页**这一最难的坑。
- 两项都需要非空的 `api_key`/`base_url`/`model`；`max_concurrency` 默认 16，可用 `MINERU_LLM_AIDED_MAX_CONCURRENCY` 覆盖。
- **接入自建 LLM 网关，禁止配置公网地址**（涉密要求）。

## 10. 选型结论

采用 MinerU 4.x 自托管 API 服务作为**唯一的文档解析引擎**，约束如下：

1. 只接受 PDF 输入，Office 由上游转换（保证所有文档具备一致的页 + 块几何）。
2. 生产档位固定 `standard`；扫描质量差的疑难件允许人工触发 `advanced`。
3. 必须整文档解析（`--pages all`），否则 `title_leveling` 失效。
4. 消费 MiddleJson + PDF 基座（页面几何与预览），不消费 Markdown 作为中间态（Markdown 仅用于人工排查）。
5. 所有 locator 一律降级为派生引用，业务主键自持。
6. 版本锁定 `>=4.0,<5`，原始产物全量存档。
