# AI-Tender 交接摘要（2026-09-28）

> 这是一份**工作交接**，不是设计文档。设计口径一律以 `docs/` 下对应文档为准。
> 新会话用法：第一句话发「读仓库根目录 HANDOVER.md，然后从 §7 的下一步继续」。

## 1. 项目与硬约束

- 仓库：`G:\aicode\AI-tender`（Windows + PowerShell）。
- 目标：招标文件解析 + 溯源定位。用户上传（docx/pdf）→ 归一化为 PDF → MinerU 解析 → 抽取 Agent 出字段 →
  前端「左原文 / 右结果」，点结果证据高亮原文；带复核、重跑、评测体系。
- 环境：`python` = E:\miniconda3 Python 3.12.4；`uv` 0.8.24；`node` v24.16.0；`pnpm` 11.5.2。
- 前后端：`apps/web`（Next.js 16 / React 19 / Tailwind v4 / zustand / pdfjs-dist 6 legacy 构建）；
  `apps/api`（FastAPI + SQLAlchemy + Alembic，含 API、Celery Worker 与外部服务适配器；抽取与 MiddleJson 元素归一化尚未落地）。
- 硬约束：**不能出内网**（MinerU 禁 `--remote`、LLM 走内网网关、服务不暴露公网）；
  外部服务（MinerU / Gotenberg / Postgres / MinIO / Redis）**由用户部署**，我们只保证「调用正确」。
- 协作约定：中文注释/文档；注释写「**为什么**」；**禁止自动提交**（先提议、等确认；提交信息中文、不写作者）；
  前端只用 pnpm；控制台中文乱码只是显示问题，用 `[IO.File]::ReadAllText(...)` 回读验证。

## 2. 本机环境陷阱（都踩过，别再踩）

- `apply_patch` 在本环境有缺陷 → **不要用**；写文件统一：
  `[IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $false))`（UTF-8 无 BOM + LF）。
- `Add-Content` / `Set-Content` 写中文会按 GBK 落盘 → 禁止用来写代码/文档。
- `$s.Replace(a, b)` **最多 2 个参数**；`-replace` 的替换串要先赋值给变量再传（否则报 overload 错）。
- `Join-Path` 只接 2 个参数；读二进制用 `[Text.Encoding]::GetEncoding('ISO-8859-1')`。
- 某些 `Remove-Item` / `Get-ChildItem -Recurse` 写法会被策略拒绝 → 换等效途径（如写进 `.gitignore`）。
- pytest 的 `--basetemp` 每次换新目录（如 `.tmp\run-<日期>-<序号>`）：复用同一目录时，启动阶段清理旧目录会撞 Windows `PermissionError`，
  表现是一批与代码无关的 setup error（换新目录立刻全绿）。
- pnpm / uv 正常输出会写到 stderr；**判断成功看 `$LASTEXITCODE`**。
- 端口 3000 落在 Windows 保留段（2601–3500）→ 本地预览用 **4321**：
  当前是一个 `next start` 生产服务在跑（改了前端要 `pnpm build` 后重启它才生效）。

## 3. 提交状态（git log 从新到旧）

| 提交 | 内容 |
| --- | --- |
| `af885c2` | 前端：模型管理页、配置中心页与工作台接真实 API |
| `f8bd3cf` | API 路由与 Worker 编排：项目文件、解析抽取、复核导出与质量闭环 |
| `5d02571` | 应用层：抽取 Agent、字段 Schema、MiddleJson 归一化与 LLM 路由 |
| `827cb94` | 外部服务适配器与配置中心内核 |
| `5d97b5a` | 数据模型与迁移：存储、LLM 管理与配置中心三批表结构 |
| `f072283` | Gotenberg 适配器：Trace 校验、错误码翻译与版本快照 |
| `03c6185` | 结果面板改分组标签页；证据列表支持多处溯源逐条定位 |
| `559e096` | 前端定位闭环（阶段 1）：原文视图 + 证据层 + 结果面板 + 样本坐标自检 |
| `df7935f` | 修正 alembic env.py 注释 |
| `ff924e1` | 初始化：设计文档与工程骨架 |

阶段 1~3 的代码（API、MinerU / S3 / Redis / Celery 适配器、配置中心、LLM 管理、质量闭环、前端两个设置页）
已按「迁移契约 → 适配器与配置 → 应用层 → API 与 Worker → 前端 → 文档」分 6 批提交，工作区干净。
§5~§16 里各轮记录中的「未提交」写的是当时状态，实际都已随这些提交入库；最后一批是文档与交接补记（即本文件）。

## 4. 关键契约（不可动摇）

- 锚点 `p{page}b{block}`，1-based，唯一范围为 `parse_run`；坐标 `[x0,y0,x1,y1]` 0–1 归一化、**左上原点、视觉方向**。
- `width_pt/height_pt` 记**未旋转** MediaBox；视觉尺寸由 `rotation` 换算（`viewport_size()`）。旋转页曾把这两者搞反过，注意。
- **预览 = 前端 pdf.js（Range 流式）**；服务端不渲染整页图、不做缩略图。定位 = 证据 bbox × 视口画框（缩放/resize 自动重算）。
- 四条溯源不变量：锚点唯一、bbox 契约、证据非空、**人工修正必须带锚点**。
- 许可：PyMuPDF（AGPL）排除；用 pypdfium2；pdfjs-dist Apache-2.0。**不用 Univer 做预览**（它渲染自有数据模型，没有「原 PDF 某块在哪」的概念）。
- MinerU：**只吃 PDF**（Office 必须先经 Gotenberg 转）；`output_formats: ["middle_json","zip"]`；
  `page_range: "all"`（否则默认只解析前 10 页）；不传 `callback`；
  job 终态拼写 `canceled`（**单 l**），upload 是 `cancelled`（**双 l**）；错误码 400 `bytes_mismatch` 与 413 `upload_size_mismatch` 双容错。
- Gotenberg：一次只传一个文件（多文件回 ZIP）；必传并校验 `Gotenberg-Trace`；400 不重试、5xx 退避重试；
  `converter_version` 必须落库（`document_version.converter_version`）。

## 5. 最近一轮做了什么（`f072283`）：Gotenberg 适配器

- `apps/api/src/tender/ports/converter.py` —— `OfficeConverter` 端口 + `ConvertResult`（签名不含 Gotenberg 概念）。
- `apps/api/src/tender/adapters/gotenberg.py` —— 冻结转换参数；**先取版本再转换**（`/version` 进程内缓存）；
  Trace 串包校验；5xx 指数退避重试 3 次、4xx 立即失败；重试前回退输入流；200 非 PDF 直接失败；`health()` 非 200 即不健康。
- `apps/api/src/tender/domain/errors.py` —— `ConversionFailed`（不可重试）/ `ConversionUnavailable`（retryable=True）；基类补 `retryable`。
- `apps/api/src/tender/core/settings.py` —— `gotenberg_url()` / `gotenberg_credentials()`（凭据只配一半报错）+ `_setting()` 助手；`.env.example` 同步。
- 测试：`tests/unit/adapters/test_gotenberg.py`（11 条）+ `tests/unit/core/test_settings.py`（+4 条）。
- 依赖：`httpx 0.28.1`（`pyproject.toml` / `uv.lock`）。
- 文档：`docs/调研/02` §6 加了实现说明；`docs/工程/07` 阶段 1 勾掉 Gotenberg 与前端定位两条、拆出 MinerU 待办。
- 验证：`ruff` 通过、import-linter **5 契约 KEPT**、`pytest 76 passed`。
- 已提交：`f072283`。

> 测试抓到过一个真 bug：中文文件名不能进 HTTP 头（只认 ASCII），现压成 ASCII 安全名（纯中文退化为 `document`），
> 原始文件名保留在 multipart 里。

## 6. 自检命令

```powershell
# 后端
Set-Location G:\aicode\AI-tender\apps\api; uv run ruff check; uv run ruff format --check; uv run lint-imports
# pytest 必须带一个本次新建的 --basetemp（用过的目录别再复用，见 §2；下次改成 run-2）
uv run pytest -q --basetemp=G:\aicode\AI-tender\.tmp\run-1
# 前端
Set-Location G:\aicode\AI-tender\apps\web; pnpm test; pnpm typecheck; pnpm verify:sample; pnpm build
# 样本重生成（6 页合成标书 + 假结果，含一处跨页多证据）
Set-Location G:\aicode\AI-tender; uv run --project apps/api python scripts/make_sample_pdf.py
```

## 7. 当前状态与下一步

已实现：MinerU/Gotenberg/S3/MinIO/Celery 适配器；PDF Range 响应；PDF 页面几何探测与幂等写入；项目、文件、版本、job API 与 SSE；前端按 `versionId` 读取真实 API；文件预处理 worker 会转换、查重、建版本并按 `auto_parse` 提交 MinerU。API/Worker 队列共用路由配置，job 重投递由 PostgreSQL advisory lock 串行化。LLM 管理模块（供应商 / 模型 / 功能绑定三层、按优先级的故障转移、调用记录与 `/settings/models` 页面）也已落地，见 docs/设计/12。抽取链路（锚点文档、分块与关键词选块、证据校验、两遍式合并、Excel 导出）已实现并有单测，见 §12、§13。

尚未完成或实测：

1. ~~`scripts/verify_coords.py` 输出原点与旋转语义候选图，需目视确认~~ ✅ 已实测（2026-10-01，见 §16 补记）：原点 `top_left`、旋转 `visual`。Gotenberg 真实转换与 MinIO 已联调通过。
2. MiddleJson → `element` 结构归一化、锚点、标题父子关系和事务写入已实现，并已用真实 MinerU 结果跑通（3 页 PDF → 54 个元素）。bbox 取值已确认并写入 `apps/api/.env`。
3. 阶段 1 全链路验收需要部署 PostgreSQL、MinIO、Redis、Gotenberg 与 MinerU。真实联调前不标记阶段验收完成。
4. ~~LLM 管理模块缺 `cryptography`~~ ✅ 已解决（2026-09-28）：`uv lock` 已把 `cryptography 50.0.1` 写进 `uv.lock`，`uv sync` 已装入 `.venv`，`tests/unit/core/test_secrets.py` 的 6 条用例实跑通过。
5. LLM 页面的真实连通性测试、拉取远端模型与降级链未实测，需要真实供应商凭证与已部署的 API。
6. 抽取链路的真实标书端到端未做（20+ 字段、404 率 = 0、review_action ≥ 50），见 `docs/工程/07` 待验证清单第 15 项。

## 8. 文档地图

- `docs/README.md` —— 全局索引 + 决策记录（如「决策 42：服务端不渲染页图」）。
- `docs/设计/03` 数据模型与溯源（锚点/坐标口径/表结构）；`04` 解析流水线与抽取 Agent；
  `05` 后端 API（错误码表 §5、契约冻结清单 §7）；`06` 前端展示与定位（§2.1 结果面板口径）。
- `docs/工程/07` 部署与实施计划（阶段划分、待验证清单）；`10` 技术选型与工程结构（§4 目录与分层、§5 关键接口定义）；`11` 架构设计。
- `docs/调研/01` MinerU 接口；`02` LibreOffice（Gotenberg）接口。
- `docs/质量/08` 动态配置中心；`09` 评测与质量门禁。
- `packages/contract/coords-vectors.json` —— 前后端共享坐标测试向量（唯一允许的重复逻辑）。

## 9. 与用户的协作方式

- 用户偏 grilling 模式：先给结论 + 建议理由，他说「按你的建议」再动手。
- 提交前必须先问；大改动前说清楚要动哪些文件；不要顺手改无关代码。
- 已确认的系统决策：前端 Next.js + 后端 Python（不是全 TS）；桌面浏览器优先；不考虑加密文档；
  准确率 ≥95%；**并发数要在页面上改、改完立即生效**（用 Redis 分布式信号量 + 中心化调度实现——
  Celery 的并发参数表达不了「集群级在途上限」）；多租户（公司隔离）为后续扩展，本期不实现。

## 10. 当前实现补记（2026-09-27）

- 检查：后端 `uv run ruff check`、`uv run lint-imports` 与坐标脚本 Ruff 检查通过；前端 `pnpm typecheck` 通过。未运行测试，未提交。
- `process_file` 读取数据库 job 与项目文件记录，PDF 直通、Office 经 Gotenberg；按原件 SHA-256 与转换器版本复用版本，使用 pypdfium2 探测页面并幂等 upsert `page`，最后更新文件/job 并按快照排入 MinerU。
- MinerU `poll_parse` 已补充重启后 `resubmitting` 的未知结果保护，MiddleJson 对象写入失败可重试。
- 坐标诊断命令：`uv run --project apps/api python scripts/verify_coords.py <pdf> <middle.json> --page 1 --output-dir coord-check`。普通页输出 top-left/bottom-left 候选，旋转页另输出 visual/unrotated 候选；**真实方向已于 2026-10-01 实测确认**（见 §16 补记）。
- 新增 `application/middle_json.py`：校验页与块结构、按页生成 `p{page}b{block}`、生成标题父子关系，并在单个事务内写入元素。页眉页脚只留在原始 MiddleJson 存档中。
- `MINERU_BBOX_ORIGIN` 与 `MINERU_BBOX_ROTATION` 默认 `unknown`；原点或旋转方向未确认时不写 bbox，防止错误定位。**2026-10-01 已配置为 `top_left` / `visual`**（判据见 §16 补记）。
- `docs/设计/05` §3.1 已改为当前项目批量上传接口；去重结果在异步预处理完成后通过 job 查询，不在上传响应中提前承诺。
## 11. 当前实现补记（2026-09-28）：LLM 管理模块

- 设计权威：`docs/设计/12-LLM管理与模型路由.md`（DDL 在 §6；`alembic/versions/0003_llm_management.py` 是副本，契约测试盯住两侧不漂移）。
- 三层结构 `llm_provider` → `llm_model` → `llm_feature_model`：**priority 只存在于绑定层**，1–10 唯一且连续；接口只收整表有序 `model_ids`，按位置写 1..N，不做单行改级。
- 规则单点：`application/llm_registry.py`（优先级展开、转移深度夹取）、`application/llm_routing.py`（按级降级 + 调用记录）；`api/llm.py` 只做校验、SQL 与响应整形。
- 密钥：`core/secrets.py` 用 Fernet 加密后写 `api_key_ciphertext`，主密钥取 `LLM_SECRET_KEYS`（逗号分隔，首个加密、其余解密，支持轮换）；未配置时禁止保存密钥（`secret_key_unavailable`），其余功能正常。
- 回退顺序：库内密文 → `.env` 的 `LLM_API_KEY`；注册表为空时整体回退 `.env` 单模型逻辑，已部署环境不因本模块失效。
- 记录：调用写 `llm_call_log`；`extraction` 增 `llm_model_id` / `llm_model_name`（改名后历史仍可读）。
- 前端：`/settings/models` 三块面板（供应商含测试与远端导入 / 模型含参数与测试 / 功能绑定含排序与深度）；顶部导航与工作台共用 `components/AppNav.tsx`；"设为 N 级、其余自动降级"在 `lib/llm/priority.ts` 整表重排，单测 7 条。
- 本轮验证：后端 ruff format/check、compileall、lint-imports（5 契约 KEPT）、`pytest tests/unit`（61 passed，0 skipped，含密钥加解密与轮换 6 条）；前端 `pnpm typecheck`、`pnpm test`（23 passed）、`pnpm build`（路由含 `/settings/models`）。
- 刻意不做：配置中心、多协议适配、embedding/rerank、按字段绑定、配额与成本统计。**本轮未提交。**
## 12. 当前实现补记（2026-09-28）：抽取链路测试

- 新增 `tests/unit/application/test_fields.py`（10 条）、`test_extraction.py`（24 条）、`test_agent.py`（12 条），共 46 条：锚点文档与章节路径、分块与重叠、关键词选块、标段识别、证据校验（精确/规范化/人工三档），以及两遍式合并（低置信复抽、投票冲突、规则与模型一致/分歧）。
- 阶段 2 的两条硬不变量写成了用例：**锚点不存在或引文无落点时结果只能是 `not_found`（不许带证据入库）**；**两遍冲突一律 0.5，不给任何一方加权**。
- 顺带修掉一个真 bug：`application/fields.py` 的 `comparable` 正则被写成双反斜杠 `r"[\\s\\u3000,…]"`，字符类在 `\\]` 处提前闭合，空格与标点从未被剥掉——`50,000 元` 与 `50000元` 会被当成两个不同值，进而在投票阶段误判冲突。已改为 `r"[\s\u3000,，。:：;；()（）\[\]【】]"`，并写了回归用例。`comparable` 只在 `application/agent.py` 内部使用，改动面可控。
- 验证：`pytest tests/unit` **107 passed**（此前 61）、`ruff format --check` / `ruff check` 全过、`lint-imports` 5 契约 KEPT、0003 契约 9 passed。**未提交**。
- 仍未覆盖：`worker/extraction.py` 的落库与状态机路径没有单测，要等 PostgreSQL 联调；`docs/工程/07` 阶段 2 清单尚待按实际状态回填（已在 §13 完成）。

## 13. 当前实现补记（2026-09-28）：导出列补齐与阶段 2 清单回填

- Excel 导出补「尝试次数」列（`docs/README.md` 4.5 节决策 20）：`application/exporting.py` 增列，筛选范围改用 `get_column_letter()` 从常量推导（原来写死 `A1:J`，加一列就会漏掉最后一列）；`api/exports.py` 与 `worker/exports.py` 的 SELECT 补 `effective.machine_attempt_no`，人工修正的行显示「人工」。
- 新增 `tests/unit/application/test_exporting.py`（2 条）：列清单与顺序、缺列写空不错位、筛选范围随列数走。
- `docs/工程/07` 阶段 2 清单 12 项按「代码就绪」回填 `[x]`，每项挂具体文件引用；未做实的地方写进批注（结果面板尚未展示 `lot_code`、冲突计算依赖 PostgreSQL 尚无单测、尝试链与复核动作落库及单字段重跑待联调、结果面板六种形态无前端单测）；待验证清单加第 15 项「抽取链路端到端」。文件头补了状态口径行：`[x]` 只代表代码就绪，不代表验收通过；验收行尚未开始。
- 修掉两处行宽超限（`ruff` E501）：`exporting.py` 的列注释与 `test_exporting.py` 的模块 docstring。
- 修掉契约测试的块号漂移：设计/03 新增 §5.1.1（0002 的 DDL）插在 §5.1 与 §5.2 之间，`tests/contract/test_ddl_matches_docs.py` 里 0001 的 sql 块号没跟着改（0、1、2、3 已错位成 0、1、3、4），0002 也没进 `_MIGRATIONS`。已改映射并把 0002 纳入契约——0001 的 9 条历史失败全部消失，契约套件 **42 passed, 1 skipped**（跳过的是 0002 的删表逆序断言，它没有显式 `_TABLES_IN_DROP_ORDER`）。
- 验证：`pytest tests/unit` **109 passed**、`ruff check` / `ruff format --check` 全过、`lint-imports` 5 契约 KEPT。**未提交。**
- 环境提醒：`--basetemp` 每次要换新目录。复用同一目录时 pytest 启动清理旧临时目录会撞 Windows 权限错（`PermissionError` 出现在 16 个 setup 上，与代码无关，换新目录即全绿）。

## 14. 当前实现补记（2026-09-28）：P0 契约缺口 + P1 前端复核面

- **P0 补齐文档清单里缺的 5 条接口**（`docs/设计/05` §2 与路由逐条比对后的缺口）：`GET /versions/{vid}`（版本详情，带 `project_id` 供项目级动作定位）、`GET /versions/{vid}/outline`（章节树，纯逻辑在 `application/extraction.build_outline`）、`POST /versions/{vid}/anchors/resolve`（批量反查，查不到的进 `missing` 不整批 404）、`POST /jobs/{job_id}/cancel`、`POST /projects/{id}/rerun`（按字段类型 / 仅失败项，默认 limit 50）。单字段重跑的校验与建任务逻辑抽到 `api/common.start_rerun`，两个入口共用。
- **路径统一**：冲突裁定从 `POST /projects/{pid}/conflicts/{cid}/decision` 改成文档写的 `POST /conflicts/{cid}/resolve`（新建 `conflicts_router`）；归属校验与行锁在同一条 SQL 里，越权与不存在都 404。`docs/设计/05` 删掉 `/documents*` 四条（版本与解析状态都挂在项目文件下）。
- **取消是协作式的**：worker 侧所有 job 状态写入都拒绝把 `canceled` 改回去（`worker/{tasks,extraction,exports}.py`），抽取在字段之间查一次状态；`poll_parse` 落终态时按 `rowcount` 判断，取消后不再接力排抽取任务。
- **抓到一个真 bug**：`api/exports.py` 的导出端点返回标注写成 `Response | dict`，FastAPI 0.141 在**装配路由时**就抛 `FastAPIError`——也就是 `tender.api.app` 根本 import 不了，API 从未成功启动过（本机没有服务所以一直没暴露）。加 `response_model=None` 修复。
- **新增路由契约测试** `tests/contract/test_api_routes_match_docs.py`：解析 05 §2 表格，断言「清单里的都实现了」（例外表 `_PLANNED` 装阶段 3 的 9 条，实现后必须删，有断言盯着）与「代码里的都上了清单」（例外表 `_UNDOCUMENTED` 3 条，写明理由）。
- **P1 前端**：`ExportButton`（按 Content-Type 分流：xlsx 直接下，>2000 行转 job 再下载；文件名优先解析 RFC 5987 的 `filename*`）、`ConflictsPanel`（并列展示候选 + 采用/忽略）、结果面板「批量确认」只挑 `auto` 档（`selectBatchConfirmable`）。状态文案与徽标抽到 `lib/results/labels.ts`，六种形态口径有单测。
- 验证：后端 `pytest` **171 passed, 1 skipped**、ruff check/format、lint-imports 5 契约 KEPT；前端 `pnpm test` **35 passed**（新增 12 条）、`typecheck`、`build` 全过。**未提交。**
- 已知缺口：冲突的「都不对，手动填入」未做（现只有采用/忽略）；结果面板组件交互仍无测试；`docs/设计/06` §9.4 的标段筛选器仍未做。

## 15. 当前实现补记（2026-09-29）：P2 配置中心 + 动态派发

- **配置中心落地在 `apps/api/src/tender/config/`**（文档 10 §4.2 预留的位置）：`schema.py`（27 项三层配置定义 + 解析 + 权限矩阵 + 类型校验）、`gate.py`（影响清单 + 硬/软门禁，纯函数）、`audit.py`（审计与逐条确认）、`snapshot.py`（任务级快照只写不改）、`registry.py`（活动配置读路径：Redis 缓存 → 数据库回源）。默认值同时存在于代码与 `config_item` 种子，两者一致性由 `tests/contract/test_config_items_match_migration.py` 盯着（解析迁移里的 INSERT 逐项比对）。
- **迁移 `0004_config_center.py`**（五张表在 0001 就已建好，本次只补种子与派发所需的列）：`job.dispatched_at`（NULL = 尚未交给 broker）、`job.config_snapshot_id`（指向 `job_config_snapshot`）、部分索引 `ix_job_dispatch`、27 条 `config_item` 种子（L1 11 + L2 10 + L3 6）、一条基线 release（`values='{}'` = 全部取默认值，`created_by='system:seed'`）。`docs/设计/03` 新增 §5.1.2 作为它的文档切片，`test_ddl_matches_docs.py` 为此支持 `require_tables=False`（该迁移只 ALTER 不改表结构）。
- **提交侧闸门（本阶段最关键的架构改动）**：API 不再直接 `enqueue`，所有任务由 beat `dispatch_pending` 每 5 秒读 L1 配置、数在途、只提交差额（`worker/dispatch.py`）。四条派发线：convert（`converting/probing`）、parse（`submitting`）、extract（`extracting`）各受名下 `*.max_inflight` 约束，export 只借道派发不设闸门。改动点：`api/{project_files,parsing,exports,common}.py` 去掉投递与 `queue_unavailable` 兜底，`worker/tasks.process_file` 不再自己接力 `submit_parse`（留在 pending/submitting 等 beat），`worker/extraction.create_extraction_job` 不再 `send_task`。
- **与文档 10 §3.5 的差异（已写进 docs/质量/08 的实现口径表）**：convert/extract 原计划用 Redis 分布式信号量，本期统一用"已派发且未结束"的 `job` 行计数——worker 崩溃或消息丢失时状态会收敛，信号量要额外 TTL 与回收逻辑才能达到同等可靠性；`dispatch.interval_seconds` 由 beat 固定 5 秒唤醒 + tick 内节流实现（只能拉长，不能缩短），避免"改配置依赖 beat 重启"。
- **API**（`api/config.py`，7 条全部登记进 `docs/设计/05` §2 表）：`GET /config/items`（定义 + 生效值 + 每层可写性）、`GET/POST /config/releases`、`GET /config/releases/{id}`（全量值 + diff + 影响清单 + 门禁预览 + 审计）、`POST /config/releases/{id}/acknowledge`（逐条确认，非影响清单内的条目 400）、`POST /config/releases/{id}/activate`（硬门槛不过 422 `gate_failed`；软门槛需 `force + reason`，记 `force_activate`）、`POST /config/releases/{id}/rollback`（历史版本直接置回 active，旧 active 记 `rolled_back`）、`GET /config/audit`。L1-only 的 `POST /releases` 一个事务里归档旧 active + 插入新 active 并写两条审计，提交后刷新 Redis 缓存并 PUBLISH `config:invalidate`。
- **`_PLANNED` 缩减**：`tests/contract/test_api_routes_match_docs.py` 里配置相关的 4 条已删，剩 5 条（regression-runs、regression-runs 报告、gold-items、stats/fields、spot-checks）全是 P3。
- **前端**：`/settings/config` 页（`components/config/{ConfigCenter,LayerEditor,ReleasePanel}.tsx` + `lib/api/config.ts` + `lib/config/draft.ts`）。L1 层"保存并立即生效"，L2/L3 保存后是草稿；版本面板显示 diff、影响清单逐条"确认已知悉"（刻意不做"全部确认"）、门禁阻断/软门槛文案、强制激活需填理由、历史版本可回滚、审计时间线。控件样式抽到 `components/ui.ts`，`components/llm/ui.ts` 改为转发。`draft.ts` 的补丁构造（类型转换、未改不提交、JSON 解析错误）有 9 条单测。
- **验证**：后端 `pytest tests/unit tests/contract` **224 passed, 2 skipped**、`ruff check` / `format --check` 全过、`lint-imports` 5 契约 KEPT；前端 `pnpm test` **44 passed**（新增 9 条）、`typecheck`、`build` 全过（路由多出 `/settings/config`）。**未提交。**
- **部署口径变化（重要）**：beat 成了唯一派发入口，worker 必须消费 `tender` 队列。`docs/工程/07` §1 的 compose 草图已改为 `-Q tender,convert,parse,extract` 并补 `beat` 服务；漏跑 beat 的表现是"任务一直 pending、页面不报错"。
- **仍未验证 / 已知缺口**：迁移 0004、快照写入、门禁 422、Redis 缓存与 5 秒生效都需要 PostgreSQL + Redis 实测（已记入 `docs/工程/07` 待验证清单第 16 项）；`extract.fields`/提示词/模型/置信度阈值这几项 L3 配置没进种子（默认值要等 P3 回归标定）；配置页组件交互无前端单测；`config_ack` 的第四种 kind `config_changed` 与 `value_type` 的 `number` 是对 08 文档 DDL 注释的补充（注释已同步）。

## 16. 当前实现补记（2026-09-29）：P3 质量闭环

- **新增 5 条接口全部落地**（`api/quality.py`，`tests/contract/test_api_routes_match_docs.py` 的 `_PLANNED` 清空）：
  `POST /config/releases/{id}/regression-runs`、`GET /regression-runs/{id}`、`GET /gold-items`、
  `GET /stats/fields`、`POST /spot-checks`。文档侧在 `docs/设计/05` §3.9/§3.12/§3.13 各补了"实现口径"段。
- **指标口径**（`application/stats.py` 纯函数 + `api/quality.py` 取数）：首次通过率、第 k 次救回率、
  累计通过率、人工兜底率；顶层数字只代表**逐条复核档**，批量/抽检原样放在 `by_mode`（09 第 1 节的口径）。
  `rescue_rate` 与 `cumulative_pass` 的键是机器解析序号。`system` 块额外给 404 率与 bbox 为空占比（09 第 9 节埋点）。
  同一 attempt 被复核多次时只认最后一次结论（`DISTINCT ON` + `ORDER BY created_at DESC`），避免同一条同时进分子分母。
- **重跑按钮收起**：服务端在 `stats/fields` 下发 `rerun_button`（`extract.rerun.hide_threshold` / `min_sample` 来自 L3 配置，
  样本不足一律 `show`）；前端 `lib/results/rerun.ts` 只渲染三值，`ResultCard` 在 `hide` 时把入口降级为卡片底部灰色链接（不硬拦截）、
  `show_hint` 时提示"重跑一次通常能修好"；统计接口失败回落"全部显示"。
- **回归回放 worker**（`worker/regression.py`，独立 `regression` 低优先级队列）：
  复用既有 `parse_run` / `element`（sha256 保留在 `document_version`，不重新转换/解析），只重跑抽取；
  优先选 gold 锚点所在的 run，找不到解析产物记 `gold_unavailable`（不进通过率分母）。
  失败分类：`value_mismatch` / `hallucination`（有值无证据）/ `anchor_404` / `extraction_failed` / `gold_unavailable` / `replay_error`。
- **门禁补强**（`config/gate.py`）：`replay_error` → 硬门槛 `regression_run_failed`（空报告不能把"不倒退"放过去）；
  `build_impact` 不再为 `replay_error` / `extraction_failed` / `gold_unavailable` 生成影响条目；
  `_regression_for` 只认 `finished_at` 非空的报告（回放在跑按冷启动口径），跑完写 `config_release.regression_run_id`。
- **gold 集**：`api/reviews.py` 的 `correct` / `supplement` 早已与复核动作同事务写入 `gold_item`（值 + 锚点 + 参数快照）；
  本阶段补了查询接口。线性比对把"人工填的 `50000元`"与结构化 `{"amount": "50000.00"}` 视为一致（`values_match`，有单测）。
- **随机抽检**：抽样框 = 最后一次结论为 `batch + confirm` 的尝试；批量确认之后已被抽检过的不重复抽；
  插入 `review_task(reason = spot_check)` 打标。抽样是同步的，`job_id` 只是批次关联号（明细 `review_task_ids`），已写进 05 §3.13。
- **部署口径变化**：worker 的 `-Q` 要加 `regression`（`docs/工程/07` §1 已改）；漏了它表现为"回放一直排队"。
- **验证**：后端 `pytest tests/unit tests/contract` **241 passed, 2 skipped**（新增 17 条：stats 10 / regression 5 / gate 2）、
  `ruff check` / `format --check` 全过、`lint-imports` 5 契约 KEPT；前端 `pnpm test` **47 passed**（新增 3 条）、
  `typecheck`、`build` 全过。**未提交。**
- **仍未做 / 已知缺口**：
  1. L3 的 `extract.fields` / `extract.prompt.version` / `extract.model` / `extract.confidence.*` 还没接入运行期消费（默认值未种）。
     后果：回放当前只在"重跑抽取"这一层起作用，**参数本身不影响回放结果**；参数接入后回放链路不用改（它读的是 release 值）。
  2. 软门槛 `first_pass_rate / baseline_first_pass_rate` 在 `regression_run` 里没有列、线上首次通过率也未按 release 归集，
     `evaluate_gate` 支持但实际不会触发；要真用软门槛，需要给表增列或按 release 归集线上指标。
  3. `gold_unavailable` 的条目没有清理入口（文档被删后会一直出现在失败明细里）。
  4. 运营统计报表页没做（前端目前只消费 `rerun_button`）；抽检任务也没有"抽检队列"入口页面。
  5. 回归回放与统计的取数 SQL、门禁 422 都需要 PostgreSQL/Redis/真实模型凭证实测（`docs/工程/07` 待验证清单第 17 项）。

## 17. 部署编排补记（2026-09-29）

- 仓库根新增 **`docker-compose.yml`**（可执行版本；docs/工程/07 第 1 节是结构示意）与根目录 **`.env.example`**
  （`docker compose` 只读仓库根 `.env`；`apps/api/.env` 仍只服务宿主机直接跑 uvicorn/celery 的场景）。
- 服务：postgres / redis / minio / minio-init（建桶 + 开版本化）/ mineru 随 `up` 启动；migrate / api / worker / beat / web 挂在 `app` profile 上。
  （Gotenberg 已在 2026-10-01 移出本文件，见本节末尾。）
  所有 `ports` 只绑 `127.0.0.1`，由反向代理转发；web 对外 4321（Windows 保留段避让，见 §2）。
- 镜像：`apps/api/Dockerfile`（uv 装进系统解释器，api/migrate/worker/beat 共用）、`apps/web/Dockerfile`
  （pnpm workspace 根上下文 + Next standalone 产物）、`docker/gotenberg/Dockerfile`（官方镜像 + 中文字体；
  版权字体放 `docker/gotenberg/fonts/`，该目录已被 .gitignore 排除）。
- 前端为此在 `next.config.ts` 开了 `output: "standalone"` 与 `outputFileTracingRoot`（pnpm workspace 必需），
  `API_PROXY_TARGET` 是**构建参数**（rewrites 在构建期求值，运行时改无效）。
- 验证：compose 用 PyYAML 解析通过（11 个服务、锚点展开、依赖引用无悬挂）、standalone 产物路径按本地 `pnpm build` 实测核对；
  前端 47 passed / typecheck、后端 241 passed / 2 skipped 未受影响。
  **未验证**：本机没有 Docker，镜像构建与 `docker compose config` 未执行，首次部署需实测。
- 单服务交付：**`docker/gotenberg/docker-compose.yml`** 是「只跑 Gotenberg」的自包含编排（`build: .` + 同目录 Dockerfile +
  `fonts/`；端口/内存/请求预算/鉴权都走同目录 `.env`，照同目录 `.env.example` 抄），同样带 `gotenberg-lb`，所以 `--scale gotenberg=N` 的动态扩缩在这里也能用
  （交付时只拷 `docker/gotenberg/` 一个目录，LB 的 nginx 配置已内联进编排文件）；全栈编排是仓库根 `docker-compose.yml`，共用同一个 Dockerfile。
- **`docker-compose.deps.yml` 已合并进仓库根 `docker-compose.yml`（2026-10-01）**，两份文件不再需要手工同步：
  默认 `docker compose up -d` 只起依赖（postgres / redis / minio / minio-init / mineru），
  `docker compose --profile app up -d --build` 才把 migrate / api / worker / beat / web 也拉起来；建表（应用在宿主机跑时）走
  `Set-Location apps/api; uv run alembic upgrade head`。
  MinerU 发布在 `MINERU_PORT`（默认 8100，避开宿主机 uvicorn 的 8000）：`apps/api/.env` 的 `MINERU_URL` 要跟着改成
  `http://localhost:8100`，`MINERU_API_KEY` 也要与容器同名变量一致——不一致只会得到解析全 401，不会启动报错。
  没有 GPU 的机器加 `--scale mineru=0` 跳过它。
- Gotenberg 扩副本（2026-10-01 补）：在 `docker/gotenberg/` 那侧跑 `docker compose --scale gotenberg=N`，副本入口是
  **`gotenberg-lb`**（nginx 配置内联在 `docker/gotenberg/docker-compose.yml` 的 `configs` 里：nginx 1.27-alpine + Docker 内嵌 DNS，副本增删 5 秒内生效）。
  副本不再各自发布宿主端口（第二个副本 Bind `127.0.0.1:3000` 会失败），`GOTENBERG_URL` 始终指向入口，所以加副本不用改
  任何客户端配置；配套要调配置中心的 `convert.max_inflight`（在途上限）与内存预算（`副本数 × GOTENBERG_MEMORY`）。
  超时按三层配齐：客户端 `GOTENBERG_TIMEOUT_SECONDS` ≥ 服务端 `API_TIMEOUT`（两者默认 1800s）＜ LB 的
  `proxy_read_timeout`（3600s）。依据是 `投标skill/LibreOffice安装.md` 的实测：600 MB 标书在 6 GB 内存下要 12 分半，
  官方默认 30s（硬超时再多 5s）的请求预算根本转不完；`GOTENBERG_TIMEOUT_SECONDS` 由此新增到 `settings.py`（默认 1800，非正数直接报错）。
  查了 Gotenberg 源码（v8.37.0）才定下这两个名字：v8 已没有 `--api-timeout-process` 参数，容器里的环境变量是 `API_TIMEOUT`
  （规则是「参数名去前缀大写」，只有 Basic Auth 那两个是 `GOTENBERG_` 前缀的特例）；另外 LibreOffice 模块的进程池
  `maxConcurrency` 写死为 1 —— 一个容器同一时刻只转一份文档，所以并行度只能靠副本数，这也是官方文档
  「Does not apply to LibreOffice: scale Gotenberg containers instead」的意思。
- **Gotenberg 移出仓库根 `docker-compose.yml`（2026-10-01 再次调整）**：转换是重资源服务，和 api / 数据库分机部署很常见，
  根编排因此只留依赖与本体（默认 `up` 起 postgres / redis / minio / minio-init / mineru，`--profile app` 再加
  api / worker / beat / migrate / web，共 10 个服务；`gotenberg` 与 `gotenberg-lb` 两段整体删除）。
  Gotenberg 只用它自己那份 `docker/gotenberg/docker-compose.yml`（自带 `gotenberg-lb`，单文件自包含）。跨编排靠
  `GOTENBERG_URL`：api / worker 的默认值改为 `http://host.docker.internal:3000`，并给四个后端服务（共享锚点 `&api-base`）
  加了 `extra_hosts: host.docker.internal:host-gateway`——Linux 上这个域名不会自动解析，必须显式映射到宿主网关。
- **Gotenberg 编排改为单文件自包含（2026-10-01 再补）**：LB 的 nginx 配置从 `docker/gotenberg-lb/nginx.conf` 内联进
  `docker/gotenberg/docker-compose.yml` 的 `configs.content`，`docker/gotenberg-lb/` 目录随之删除。动因是实测：漏拷
  挂载源时 Docker 会把挂载点当目录建出来，nginx 起不来且报错不直观——交付要拷的目录越少越不容易出错。
  `--scale gotenberg=N` 的能力不受影响（nginx 仍靠 Docker 内嵌 DNS 解析服务名，副本增删 5 秒内生效）。
  改内联配置时注意 `$$proxy_add_x_forwarded_for` 是 compose 的转义写法（compose 会把 `$xxx` 当变量插值），
  别把 `$$` 退回成单个 `$`。
- **Gotenberg 镜像构建：可选字体包与 apt 源（2026-10-01 再补）**：实测官方 `gotenberg:8` **自带 `curl` 与
  `fonts-noto-cjk`**（apt 输出里只多出 `fonts-noto-cjk-extra` 134MB + `fonts-wqy-zenhei` 8MB）。内网 / 跨境网络下
  这 142MB 能把构建拖到几十分钟（实测 1000+ 秒仍停在 `Get:1`），因此改为默认不装、用 `INSTALL_EXTRA_FONTS=1`
  显式开启，并新增 `DEBIAN_MIRROR` 构建参数用于换源。`COPY fonts/` 同时提到 apt 之前，慢网络重试时不必重传
  167MB 的自有字体。`docker/gotenberg/fonts/` 已放入宋体/黑体/仿宋/楷体/华文中宋/华文楷体/华文仿宋/华文细黑/
  微软雅黑/等线/SimSun-ExtB/Times/Arial 共 16 个文件（商业字体不进版本库，`.gitignore` 已排除），
  方正系列仍缺，若发现公文字体替换导致页数漂移再按该目录 README 的清单补。
- **MinIO 钉版本 + `minio-init` 保留（2026-10-01）**：`minio/minio:latest` 换成 `${MINIO_IMAGE:-minio/minio:RELEASE.2025-04-22T22-12-26Z}`
  （该版本是 2025-04-22 的社区版；2025-05-24 起官方把内置 Web 控制台标记为弃用并迁到单独的 object-browser 项目，
  LDAP / OIDC 登录也移出社区版，继续用 latest 会让 9001 白发布），`minio/mc` 同样钉到 `RELEASE.2025-08-13T08-35-41Z`。
  另按用户给的独立部署参考补了 `minioconfig:/root/.minio` 卷（证书 / 配置，数据仍在 `miniodata`）。
  `minio-init` 不是可有可无：它做的是建桶 + 开版本化（`mc mb --ignore-existing` + `mc version enable`），而适配器
  只读写对象、不建桶（`adapters/s3.py`），删掉它首次上传就是 `NoSuchBucket`；版本化是「原件被误覆盖 / 误删还能找回」
  的兜底（对象键是内容哈希，正常不会覆盖）。它幂等、跑完即退，换成外部对象存储时用不到——在对方那边手工执行这两条
  命令即可（`.env.example` 的 MinIO 段已给出）。当时本机仍没有 Docker，镜像切换只做了静态检查，未实跑。


## 18. 外部服务真实联调补记（2026-10-01）

环境：远端 `172.29.199.222`（Gotenberg 在 `3456`、MinerU API 在 `8000`，Postgres / Redis / MinIO 同机）。
本轮把阶段 1 的真实链路跑通了，并且**在真实服务上抓到两个适配器 bug**——都是「本机没有 Docker + 未实测」留下的。

### 18.1 已联调通过

- PostgreSQL 18.6（`postgres` / `ledger_admin`）：`alembic upgrade head` 建出 29 张表，`pg_trgm 1.6` 已装。
- Redis 7.0.15、MinIO（桶 `ai-tender` + 版本化已建）。
- Gotenberg 8.37.0：docx → PDF 真实转换成功（3 页、有文本层、中文字形正常，宋体生效）。
- MinerU 4.0.7（`mineru-kit api-server`）：PDF → MiddleJson 成功，`standard` 档 3 页耗时约 134 s；
  接着跑 MiddleJson → `element` 归一化，得到 54 个元素，锚点形如 `p1b1`。

### 18.2 抓到的两个 bug（已修 + 已补回归）

1. **`GET /version` 返回纯文本，不是 JSON**（`adapters/gotenberg.py`）。实测 8.37.0 回 `8.37.0`
   （`Content-Type: text/plain`），而实现按 `{"version": ...}` 解析 → 版本永远读不出来，表现成
   「转换一次都没成功，报的错却是版本读取失败」。现在两种形状都接受；形状完全不认识时仍然失败，
   不降级成空值（`converter_version` 是溯源记录的一部分）。
2. **上传响应的顶层 id 是 `id`，不是 `upload_id`**（`adapters/mineru.py`）。实测 `POST /v1/uploads`
   返回 OpenAI 风格的 `id`（`upload_...`），调研文档记的是 `upload_id`。现在两个名字都认，都没有则报错。
   顺带确认对得上的部分：`POST /v1/parse/jobs` 确实回 **202**；SHA-256 去重命中回 `status: completed`
   并内嵌 `file.id`；`/v1/health` 顶层给 `version` 与 `features.output_formats`。
   补了 `tests/unit/adapters/test_mineru.py`（此前 MinerU 适配器**一条测试都没有**）。

### 18.3 两项 P0 实测结论（此前一直挂着「未验证」）

- **bbox 原点 = `top_left`**：样本是「顶部一行 + 底部一行、中间大片留白」的单页 PDF，实测最上墨迹 0.0972，
  `top_left` 预测 0.0940（差值即行高留白），`bottom_left` 预测 0.8890。
- **旋转语义 = `visual`**：把单页设成 `/Rotate=90` 后提交，横排文字块的 bbox 变成
  `[0.886, 0.115, 0.908, 0.238]`（落在右侧的纵长条），与视觉坐标系的预测一致。

取值已写入 `apps/api/.env`；`docs/调研/01` §5、`docs/设计/03` §3.2、`docs/工程/07` §6 已同步。
副带发现：那份 `/Rotate=90` 样本被 MinerU 判成了 `header`——旋转页的块分类可能不准，遇到旋转扫描件要抽检类型。

### 18.4 仍未验证

- 扫描件 OCR 质量（要真实扫描样本）。
- Gotenberg 转换的页数一致性（要和原件页数对照；本轮只验证了「转换本身可用且中文正常」）。
- LLM 抽取链路（还没有内网网关地址与凭证；`LLM_SECRET_KEYS` 已生成）。
- 旋转页的块分类准确度（见 18.3 末尾）。

### 18.5 MinerU 部署要点

- 必须跑 `api-server` 入口：`webui`（7860）没有 `/v1/*` 那套端点，接不上。
- 模型目录（`MINERU_HOME`）在 api-server 与 webui 之间**可以共用**（都是只读加载同一份权重）；
  但**显存不能共用**，两个进程各加载一份，单卡同时跑两个要先看显存够不够。


## 19. 端到端联调 + 前端路由落地（2026-10-01 晚）

环境：宿主机直接跑进程（本机没有 Docker），后端 `127.0.0.1:8300`、前端 `127.0.0.1:4400`。
远端的 Postgres / Redis / MinIO / Gotenberg / MinerU 沿用第 18 节那套地址。

### 19.1 端口：8000 与 4321 在本机不可用

`netsh int ipv4 show excludedportrange protocol=tcp` 显示 Windows 保留了 `7981-8080`、`8081-8180`、
`4247-4346` 三段（Hyper-V / WSL 占用），所以 **8000、8010、8080、8100、8800、4321 全部无法 bind**，
报错是 WinError 10013「以一种访问权限不允许的方式做了一个访问套接字的尝试」——看起来像权限问题，
实际是保留端口。实测可用：`8300`（API）、`4400`（前端）。前端不改代码，靠
`API_PROXY_TARGET=http://127.0.0.1:8300` + `PORT=4400` 两个环境变量对接。

启动命令（都在 `apps/api` 或 `apps/web` 下）：

```powershell
# API
.\.venv\Scripts\python.exe -m uvicorn tender.api.app:app --host 127.0.0.1 --port 8300
# worker（Windows 没有 fork，必须换线程池，否则 prefork 池直接起不来）
.\.venv\Scripts\python.exe -m celery -A tender.worker.celery_app worker `
  -Q tender,convert,parse,extract,regression -P threads -c 4 -l info
# beat
.\.venv\Scripts\python.exe -m celery -A tender.worker.celery_app beat -l info `
  --schedule ..\..\.tmp\celerybeat-schedule
# 前端
$env:API_PROXY_TARGET = "http://127.0.0.1:8300"; $env:PORT = "4400"; pnpm dev
```

### 19.2 第三个真机 bug：派发闩锁没有随阶段推进交还（已修 + 已补回归）

**症状**：docx 上传后转换成功（Gotenberg 200、`document_version` 落库、`page_count=1`），
但解析永远不动——`parse_run` 一直为空，job 停在 `pending` / `stage=submitting`。
beat 每 5 秒都在跑，返回的却是空字典。

**根因**：`job.dispatched_at` 的语义是「**本阶段**已投递」，闸门的候选条件是 `dispatched_at IS NULL`
（`worker/dispatch.py` 的 `_PENDING_SQL`）。转换阶段占用了这个闩锁；转换完成把 stage 改成
`submitting` 交棒给解析时，**没有清掉它**，于是这条 job 永远不满足闸门条件。
`process_file` 又特意不再自己投递（注释写着「派发交给 beat」），两条路一起把 job 卡死。

**修复**：`worker/tasks.py` 的 `_finish_file_version` 在推进到 `submitting` 时一并
`dispatched_at = CASE WHEN :should_parse THEN NULL ELSE dispatched_at END`——
只在真的进入下一阶段时清，直接以 completed 收尾的 job 保持原值。
修完后 worker 和 beat 都不需要改动，重启 worker 后那条卡住的 job 自己就往下走了。
补了 `tests/contract/test_job_dispatch_latch.py`（源码级断言：这一行被删掉就变红）。

**验证**：`submit_parse` → `poll_parse` → `extract_fields` 三段任务全部出现在 worker 日志里；
`element` 表落 16 行（15 个 text + 1 个 table），锚点 `p1b1..p1b16`，bbox 与第 18 节实测的
`top_left` / `visual` 约定一致（如标题块 `[0.116, 0.109, 0.376, 0.133]`）。

### 19.3 前端：把设计文档 06 的路由矩阵真正落地

此前只有工作台一个页面，且**没带 `versionId` 时静默回落到静态样本**——用户打开系统看到一份
假标书，分不清是演示数据还是自己的文件没传上去。本轮补齐：

| 路由 | 页面 | 说明 |
| --- | --- | --- |
| `/` | 重定向 | 跳到 `/projects` |
| `/projects` | 项目列表 | 新建项目、按名称/编号搜索、文件数与待复核数列 |
| `/projects/[id]` | 项目工作台 | 顶部文件切换条 + 左原文 / 右结果；当前文件走 `?file=` |
| `/projects/[id]/files` | 文件管理 | 拖拽上传（含 ZIP 解包）、角色维护、重解析、软删除、流水线进度 |

配套改动：

- `DocumentWorkbench` 改为接收 `versionId`（不再自己猜），并新增「没有抽取结果」的可解释空状态——
  当前 `LLM_*` 未配置，抽取必然失败，这个状态就是那件事的落点，而不是丢给用户一个空白面板。
- 新增 `components/PageShell.tsx`（列表类页面统一外框）、`components/projects/FilePipeline.tsx`
  （转换 → 解析 → 抽取 三段的进度轨迹）、`lib/projects/pipeline.ts`（阶段推导，纯函数 + 7 条单测）。
- 后端两处查询补齐列表页要用的聚合：`GET /projects` 加 `file_count` / `review_count`；
  `GET /projects/{id}` 的 `files[]` 加 `extraction_count` / `review_count` / `extraction_status`。
  都只统计 `is_current` 的抽取，历史尝试不算——否则待复核数永远清不干净。

### 19.4 视觉：一套「公文」气质的调色板

- 字体栈不变（内网构建不能联网拉字体），新增等宽栈给页码/哈希/报价这类要上下比对的值。
- 调色板在 `globals.css` 的 `@theme` 里**整站重映射** `slate / amber / sky / rose / emerald`
  五个色阶，而不是逐个文件改名：22 个组件已经铺满这些类名，改名是一次几百行的纯噪声改动。
  现在语义是：`slate` 墨（结构）、`amber` 荧光标记黄（全站唯一强调色，对应「证据高亮」）、
  `sky` 靛蓝（可点）、`rose` 朱红（失败）、`emerald` 墨绿（完成）。
- 签名元素是 `.mark-ink`（压扁 14% 的荧光笔痕，只用在待复核数字上）与流水线轨迹；
  主按钮改成实心墨色，一屏里不再出现多个实心彩色按钮。

### 19.5 本轮未验证 / 已知限制

- **LLM 抽取链路仍然缺凭证**：`LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` 为空，
  抽取 job 会以 `extraction_failed` 结束（`extraction` 表为空）。配置入口是
  `/settings/models` 与 `/settings/config`，但真正能用的地址还没拿到。
- **无头截图不可靠**：本机 Chrome 的 `--headless=new --virtual-time-budget` 下，
  客户端 `fetch` 经常在预算耗尽前不返回，截到的是「正在加载…」而不是数据行；
  带数据的渲染只截到过两次（1680×1000 与 1200×900），不要把它当成稳定的验收手段。

## 20. 前端 UI 重构收口（2026-10-01 深夜）

### 20.1 一眼结论

前端已从「通用后台模板」重做成一套叫**「校对台」**的视觉系统：冷灰墨阶的纸面 +
荧光笔黄作为全站唯一强调色，宋体做标题与字段名、等宽做数据，签名元素是每一行左侧
那道 3px「卷宗脊」色条。规范写在 `apps/web/src/app/globals.css` 的 `@theme` 里，
完整口径见 `docs/设计/06-前端展示与定位.md` 第 12 节。

### 20.2 本轮改了什么

- `components/AppRail.tsx`（新）：左侧深色竖导航，替代已删除的 `AppNav.tsx`。
- `components/PageShell.tsx` 收口为 `eyebrow / title / description / actions / width`；
  `ModelSettings` 与 `ConfigCenter` 也改成用它，四类列表页现在共用同一个页头。
- 结果面板：状态一律「小圆点 + 同色文字」（`lib/results/labels.ts` 的
  `statusDotClass / statusTextClass / statusSpineClass`），不再用药丸；
  卡片版式固定为「字段名（宋体）→ 值（等宽 17px）→ 出处 → 动作」。
- `ModelSettings` / `ConfigCenter` 补了真正的错误态与「重试」，`ConfigCenter` 的
  刷新按钮现在会走 `reload()`（原先只清提示文案）；`llm/ui.ts` 转发 `SELECT_CLASS`，
  设置页的下拉框不再露出系统控件外观。
- `lib/api/client.ts` 修掉了 `rerunMode` 的单参调用（原先漏传 `rerunModes`）。

### 20.3 版式问题（截图发现并修掉）

- 文件清单的行网格 `12rem / 10rem` 不够宽：流水线第三段后面的状态文字会顶到「待复核」
  列上，操作区三个按钮会折成「打开工作/台」。已放宽为 `15rem / 13rem`，
  并让 `FilePipeline` 的文字允许换行（`flex-wrap`）。
- 工作台的 `DocumentWorkbench` 顶栏在窄屏下同样回到「正在加载…」是不对的，
  实测是 headless 的问题而不是代码问题，见下条。

### 20.4 截图验收：改用 CDP，弃用 `--virtual-time-budget`

§19.5 说的「无头截图不可靠」有可靠解法：**`--virtual-time-budget` 会卡死 PDF.js 的
worker 通信**，所以带 PDF 的工作台永远停在加载态。改成用 CDP 真等（`.tmp/cdp-shot.mjs`，
用 `node --remote-debugging-port` 驱动 Edge，`Page.navigate` 后真实 sleep 再
`Page.captureScreenshot`），本机 5 个页面全部截到带数据的画面。

另外一个坑：**必须用 `http://localhost:<port>` 访问 `next dev`**。用 `127.0.0.1` 会被
Next 16 判为跨源而拒绝 `/_next` 下的开发资源，页面只出 SSR 的空壳，看起来像「接口挂了」。

### 20.5 本轮未做

- 结果面板不能折叠（核对时无法把原文放到最大）；
- `/review` 复核队列页、`/settings` 账号与审计页仍是规划状态；
- 字体仍走系统栈（`Source Han Serif SC / Songti SC / SimSun`），没有内嵌 woff2。

## 21. 前端「校对台 v2」第一段：视觉全换 + 工作台补齐（2026-10-01 深夜）

### 21.1 一眼结论

上一轮（第 20 节）只搭了骨架：配色做了，但**字阶太保守**（239 处字号里 201 处是
11–13px）、**宽页卡在 1200px**，1600px 屏上就是「中间一条窄带」；界面上还缺一半形态——
失败态没有出路、原文没有角标、没有章节树、没有复核统计、没有复核队列。
本轮按用户「视觉全换、力度拉满」的要求重定尺度表，并把缺的形态补齐。

### 21.2 用户两条不满的正面回答

| 不满 | 处理 |
| --- | --- |
| 「解析失败也没有重新解析功能」 | 新增版本级端点 `POST /versions/{vid}/extract`（只重跑抽取、复用解析产物），工作台的空态/失败态与文件清单行都把「重跑抽取」给成第一出口 |
| 「我要求的完全重构 UI，你就给加了一个框架」 | 字阶与结构尺度整体上调（21.3），补齐四种缺失形态（21.4） |

### 21.3 视觉底座：只改 token 与常量，组件里的类名不动

`apps/web/src/app/globals.css` 的 `@theme` 与 `apps/web/src/components/ui.ts`：

- **纸面转暖**：`--color-white: #fdfbf7`（米白暖纸）、`slate-50 #f6f4ef`、`slate-100 #eae6dd`、
  `slate-200 #dcd7cb`；`.desk` 底色 `#e3ded2`。**`slate-300` 及更深一律保持冷墨不变**——
  「米白纸 + 冷黑墨」才是印刷配对，结构线的冷调正是墨感的来源。荧光笔黄/靛蓝/印泥红/墨绿四色没动。
- **尺度表**（字号/行高）：页面标题 26→**34/44**（serif）、区块标题 16→**19/28**（serif）、
  字段名 13→**15/22**（serif，宋体落在这里才像标书）、结果值 17→**22/30**（mono，全屏最大）、
  正文 13→**14/22**、次要说明 12→**13/20**、数据小字 11→**13/18**（mono）；
  `EYEBROW_CLASS` 保留 11/0.18em（它是指路牌不是正文）；`AppRail` 标签 11→12。
- **结构尺度**：`AppRail` 76→**92px**、卷宗脊 3→**4px**、`RESULT_PANEL_WIDTH` 404→**460px**、
  `PageShell` 的 wide 1200→**`max-w-[1680px]`**、narrow 900→**1180**、内边距 `px-10` 且
  ≥1536px 时 `px-14`；原文纸 1100→1240。
- **按钮不再折行**：`ui.ts` 六个按钮常量都加了 `whitespace-nowrap`（按钮文字折成「打开工作/台」
  是上一轮就截图发现、但没根治的问题），文件清单行的操作列 13rem→**21rem**，
  以同时容纳「打开工作台 / 重跑抽取 / 重新解析 / 删除」四个动作
  （§20.3 里那句「已放宽为 15rem / 13rem」被本条取代）。
- 签名元素没动：墨线分层、编号、`rounded-[2px]`、全站唯一那处阴影、三段色块流水线。

### 21.4 工作台补齐（本轮的主体）

- **原文角标气泡** `components/viewer/AnnotationLayer.tsx`：按 `evidenceIndex.byPage` 在每页
  渲染该页证据编号，点角标反向定位并高亮对应结果卡；激活项荧光黄实心、其余墨线空心。
- **章节树** `components/workbench/OutlineNav.tsx`：接 `GET /versions/{id}/outline`（此前前端零接入），
  可折叠（折叠留 36px 竖脊，入口不消失），点章节跳页并高亮标题块。
  当前章用「页码 ≤ 当前页的最后一个」判定 —— level 不保证连续、也可能缺父节点，用不到树的形状。
- **复核统计条** `components/workbench/ReviewStatsBar.tsx`：接 `GET /projects/{id}/stats`
  （零后端改动），通栏显示「已复核 / 已修正 / 待复核」，点「待复核」切复核模式。
- **复核模式**：结果面板顶部两档开关「复核队列 / 全部结果」；复核模式下 conflict → need_review →
  其余 → not_found 排序（`lib/results/reviewQueue.ts`），冲突项就地展开两侧取值待裁决。
  **没有新增 `/review` 路由**（用户已确认的取舍），路由矩阵不变。
- **三态空态/失败态**（都在 `DocumentWorkbench.tsx` 的结果面板里）：
  未解析 → 指路（去文件管理页），解析失败 → 错误码 + 重新解析，抽取失败/0 条 → **抽取 job 的错误码
  与消息 + 主按钮「重跑抽取」**+次按钮「重新解析」。
- **键盘流**：`j/k` 移动、`Enter` 确认、`Shift+Enter` 打开带提示重跑、`Esc` 收起、`/` 聚焦搜索。
- **三种重跑的文案口径不许混用**：重跑（单字段，秒级）/ **重跑抽取**（复用解析产物、分钟级、
  不动锚点与已确认结果）/ **重新解析**（重建锚点、已确认打回复核、更久）。重新解析前先出后果横幅，
  写明「此前 N 条已确认结果需重新复核」。

### 21.5 后端这一轮只加了一个端点、两个响应字段

- `POST /api/v1/versions/{vid}/extract`（`api/parsing.py`）：body `{field_keys?: string[], hint?: string|null}`，
  空数组 = 全部字段；`hint` 非空 → trigger `hinted_rerun`，否则 `user_rerun`（沿用既有枚举，没扩枚举）。
  复用最近一次 `completed/partial` 的 parse_run，**不重建锚点、不作废已验证结果**；用
  `pg_advisory_xact_lock` 做并发互斥。错误口径：`404 not_found` / `409 version_not_parseable` /
  `409 parse_incomplete` / `409 rerun_in_flight` / `400 invalid_argument`；成功 `202`。
  为什么必须单独开这个入口：解析与抽取是两个 job，抽取失败时 `parse_run` 往往已经 `completed`、
  结果却一行都没有，此时 `/projects/{id}/rerun` 是从**已有结果行**里筛候选的 → 必然 0 条；
  而 `/reparse` 要重建锚点、代价高一个量级。
  **为什么不复用 `/projects/{id}/rerun`**：它的语义是「项目级批量补跑已有结果」，这次要的是
  「一个版本一条结果都没有时重新抽」。两者前置条件互斥，硬合并会让 0 结果的项目永远走不通。
- 响应新增字段（不是新端点，见 `docs/设计/05` 第 3.14 节）：
  `GET /versions/{vid}` 加 `latest_extraction_job`（失败态的「错误码 + 消息」只能来自 job 行）；
  `GET /projects/{id}` 的 `files[]` 加 `confirmed_count`（重新解析的二次确认要列出失效条数）。
- API 层不许 import `tender.worker.*`（import-linter 强制），所以端点走 `TaskQueue` 端口，不直接把
  `create_extraction_job` 搬进 API。

### 21.6 真机跑通这一环，顺手挖出两个一直躺着的 bug

抽取这一环**此前从没在真机跑通过**（第 18~20 节都是单测与假数据），第一次真跑就连撞两个：

1. `worker/extraction.py` 的 `_load_candidates` 写 `m.api_key_ciphertext`，但该列属于
   `llm_provider` → 改成 `p.api_key_ciphertext`。报错信息是
   `column m.api_key_ciphertext does not exist`，只在真机暴露。
2. `worker/tasks.py` 的 `_finish_file_version` 把 stage 从 `converting` 推进到 `submitting` 时
   没清 `dispatched_at`。`dispatched_at` 的语义是「**本阶段**已投递」、派发闸门只认
   `dispatched_at IS NULL`，所以漏清 = job 静默停在 pending，界面表现是「解析永远在排队」。
   处理：`dispatched_at = CASE WHEN :should_parse THEN NULL ELSE dispatched_at END`。

两个都补了**源码级**契约测试（跑真机太贵，而这两条都是「写法」层面的不变式）：

- `tests/contract/test_worker_sql_columns_exist.py`：从 alembic 全部迁移里解析出
  表 → 列集合（含 `ALTER TABLE ... ADD COLUMN`），再校验 worker 里所有 `别名.列名`
  （别名由 `表名 AS 别名` 给出）。已用「把 fix 改回 bug → 测试变红 → 改回 → 变绿」双向验证过。
- `tests/contract/test_job_dispatch_latch.py`：钉住阶段推进的那条 UPDATE 里
  `dispatched_at = CASE WHEN ... THEN NULL` 还在，同时钉住 `ELSE dispatched_at END`
  （不进入下一阶段时不能无条件清）。

真机闭环：项目 1（抽取失败、0 结果）走 `POST /versions/1/extract` → job 落库 → worker 跑完
**14/14 字段、0 失败**，`GET /projects/1` 的 `extraction_count` 从 0 变 14。

### 21.7 截图验收

用 `apps/web/.tmp/cdp-shot.mjs`（§20.4 那两个坑仍然有效：**必须 `localhost:4400`**、
**不能加 `--virtual-time-budget`**），1600×1000 逐页截：

| 页面 | 结果 |
| --- | --- |
| `/projects` | 通栏卷宗清单（仍是第二段的形态，本轮只跟着换尺度） |
| `/projects/1/files` | 交件台 + 清单双动作「重跑抽取 / 重新解析」 |
| `/projects/1`（有结果） | 复核进度条 + 两档开关 + 章节/角标 + 键盘提示 |
| `/projects/1`（抽取失败） | 错误码 + 消息 + **主按钮「重跑抽取」**（见下） |
| `/settings/models`、`/settings/config` | 撑满，无中间窄带 |

这两个形态的来源说明：`/projects/1` 的**抽取失败态**与**章节树**在当前样本数据上复现不出来
（抽取已跑通、不再有失败 job；MinerU 把样本 docx 的四个小节标题判成了普通 `text`，
`/outline` 返回空数组）。这两个形态用 `apps/web/.tmp/cdp-state-shot.mjs` 截图：
在页面加载前包装 `window.fetch`，**只替换被验证的那一个响应体**，其余请求走真实接口，
不改数据库也不改代码。章节树注入的内容就是该文档真实的小节标题（`p1b2/p1b7/p1b10/p1b13`），
失败消息用的是库里真实记录的那一条。

### 21.8 已知偏离

- **统计条不显示「/ 共 N」分母**：`/projects/{id}/stats` 不返回「项目内结果实例总数」，
  前端自己拼分母会拼出「分母 < 已复核」这种自相矛盾的数字。宁可少给一个数，也不能给错的。
- **重新解析的后果确认只在 UI 层**：后端 `/reparse` 目前不接收 `acknowledge_invalidated_count`
  （`docs/设计/05` 第 3.11 节写的是设计意图），横幅只负责「先摆出数字再让人按下去」，数字不回传核对。
- **`/review` 路由仍未实现**：复核队列做在工作台内，路由矩阵不变。
- **`OutlineNav` 在 outline 为空时整块不渲染**（不占 236px 白跑一栏）。样本 docx 目前就属于这种，
  所以真实数据下工作台看不到左栏——这是有意为之，不是没实现。

### 21.9 第二段待办（等用户看截图确认方向后再推）

`ProjectList` 通栏卷宗清单（列头 + 行高 56px + `/` 聚焦搜索）、`UploadPanel` 拖拽区加高并写明
支持格式/ZIP/上限/角色推断规则、逐文件上传进度、`settings/models` 与 `settings/config`
≥1536px 双列网格、`PageShell` 面包屑补全到更多页面。

### 21.10 本轮验证命令与结果

```
apps/web:  pnpm typecheck   → 通过
apps/web:  pnpm test        → 66 passed（原 54）
apps/web:  pnpm build       → 成功，7 条路由
apps/api:  pytest -q        → 257 passed, 2 skipped
apps/api:  ruff check / ruff format --check / lint-imports → 通过
```

### 21.11 按代码审查修复（除 P1）

第一段交付后做了一轮代码审查，除 P1（`POST /versions/{vid}/extract` 会作废已确认结果，与 docstring / 界面文案矛盾，
需要产品决策）外全部修掉：

- **提交后立刻重取**：重跑抽取 / 重新解析提交成功后先刷一次工作台（文件清单页同理先刷列表），`pipelineRunning`
  才会立起、5 秒轮询才能接管等待；此前整段等待里界面停在失败态并显示「重跑中…」，自相矛盾。
  顺带订正两处注释里「任务在跑时会自己轮询」的错误前提（那只对「打开页面时已经在跑」成立）。
- **重新解析不再静默降档**：`GET /projects/{id}` 的 `files[]` 补 `parse_tier` / `parse_ocr_mode`
  （取自最近一次 `parse_run.tier` 与 `config_snapshot->>'ocr_mode'`），文件清单页的重新解析沿用它们；
  此前该页硬编码 `standard` / `auto`，`advanced`（或 `ocr`）上传的文件在这里重解析会被降档。
- **`list_projects` 的聚合子查询补 `company_id` 过滤**：原来只在外层过滤，聚合仍会把其它公司的 `project_file`
  整表扫一遍再丢掉（结果正确，纯代价）。
- **`onSettled`**：工作台复核 / 重跑落定后通知外层重取项目，左侧文件栏的流水线与待复核数不再停在打开页面那一刻。
- **清理**：`ResultCard` 去掉死 import（`triggerLabel`），注释里的 17px 订正为 22px。

验证：`pnpm typecheck` / `pnpm test`（66 passed）/ `pnpm build`（7 路由）、`pytest`（257 passed, 2 skipped）、
`ruff check` / `ruff format --check` / `lint-imports` 全绿；另用 `TestClient` 对真实库跑了一遍 `GET /projects` 与
`GET /projects/1`，确认新 SQL 与 `parse_tier` / `parse_ocr_mode` 的返回值。
