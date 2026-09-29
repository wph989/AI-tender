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

1. `scripts/verify_coords.py` 输出原点与旋转语义候选图；需用真实 MinerU `standard` 结果与同一 PDF 目视确认。Gotenberg 真实文档版式与 PDF Range 的 MinIO 联调也待用户部署服务。
2. MiddleJson → `element` 结构归一化、锚点、标题父子关系和事务写入已实现。bbox 原点/旋转未实测前保持 `NULL`；确认后配置 `MINERU_BBOX_ORIGIN` 与 `MINERU_BBOX_ROTATION`。
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
- 坐标诊断命令：`uv run --project apps/api python scripts/verify_coords.py <pdf> <middle.json> --page 1 --output-dir coord-check`。普通页输出 top-left/bottom-left 候选，旋转页另输出 visual/unrotated 候选；**真实方向仍未确认**。
- 新增 `application/middle_json.py`：校验页与块结构、按页生成 `p{page}b{block}`、生成标题父子关系，并在单个事务内写入元素。页眉页脚只留在原始 MiddleJson 存档中。
- `MINERU_BBOX_ORIGIN` 与 `MINERU_BBOX_ROTATION` 默认 `unknown`；原点或旋转方向未确认时不写 bbox，防止错误定位。完成诊断后分别配置 `top_left|bottom_left` 与 `visual|unrotated`。
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