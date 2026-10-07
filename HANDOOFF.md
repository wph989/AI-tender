# 前端界面重构交接

更新日期：2026-10-04

工作目录：`G:\aicode\AI-tender`

> **新会话先读**：当前最高优先级是第 22、23 节的 DeepAgents 标书解析重构（goal 仍 active，全部未提交）。顶部 2026-10-04 的状态描述是历史记录。

状态：前端重构、现有后端接口对接及审查问题修复已完成，构建、测试与浏览器验证通过；本次按用户要求提交相关代码、测试与文档。

**接口对接见第 12 节，随后审查发现的两处问题及修复见第 13 节，提交说明见第 14 节。第 1—11 节保留此前重构与产品讨论的历史记录，其中“尚需最终验证”和旧服务状态已由后文更新。RAG、GraphRAG、动态报告和分类选择仍处于设计阶段。**

## 1. 当前任务与用户要求

用户原始要求：

> 使用 frontend-design 技能，完全重构当前项目的前端界面，不要再参考当前 UI 布局和调色；后端接口交互可以保留。

本轮结束前，用户要求将任务、进度、问题、计划和经验写入本文件。文件名按用户要求为 **HANDOOFF.md**，不要与项目已有的 `HANDOVER.md` 混淆。

需要继续遵守的项目约定：

- 文件始终使用 UTF-8 读写。
- 运行环境是 PowerShell，使用 PowerShell 命令。
- 使用 pnpm，不使用 npm。
- 注释和文档优先中文，注释解释原因。
- 禁止自动提交；仅在用户明确要求后提交，提交信息用中文，不添加作者说明。
- 用户要求上下文使用超过 80% 后压缩。
- 未获明确要求，不启动子代理。本次没有使用子代理。

本轮读取并使用的技能：

- `C:\Users\wph98\.skills-manager\skills\frontend-design\SKILL.md`（用户明确指定的路径）。
- `C:\Users\wph98\.codex\skills\karpathy-guidelines\SKILL.md`。

## 2. 产品与技术背景

AI-Tender 面向投标方，核心流程是：

**项目 → 上传招标材料 → 转换/解析/抽取 → 对照原文核对结果 → 导出。**

界面覆盖：

| 路由 | 用途 |
| --- | --- |
| `/` | 重定向到项目空间 |
| `/projects` | 项目列表、创建与搜索 |
| `/projects/[id]` | 文件切换、PDF 原文、结果复核与溯源 |
| `/projects/[id]/files` | 文件上传、角色、处理进度、重跑和删除 |
| `/settings/models` | 供应商、模型、功能绑定 |
| `/settings/config` | 分层配置、版本、发布、回滚 |

前端位于 `apps/web`：Next.js 16.3.6、React 19、TypeScript、Tailwind CSS 4、Zustand、pdfjs-dist。原有 API 请求封装、接口类型、坐标计算、业务纯函数均保留，本轮主要修改组件和样式。

## 3. 已完成内容

### 3.1 全新视觉系统与导航

已替换原来的深色窄侧栏、暖纸色、宋体标题与荧光黄视觉。

新方向为「清晰的标书分析空间」：

- 雾紫背景、白色圆角面板、紫色操作与定位、青绿色完成状态。
- 背景 `#f7f8fc`，正文 `#27283f`，主色 `#7156ce`，确认色 `#2d866f`，错误色 `#bf4764`。
- 标题使用 Bahnschrift / Segoe UI / 中文系统字体栈，数据使用 Cascadia Code / Consolas。
- 使用本地字体，不引入需要联网的字体依赖。
- 品牌和图标改为统一描边风格，增加 `Icon.tsx`。
- 主导航改为顶部横向；普通页面统一面包屑、标题、操作区和页脚。
- 首页的识别元素为「文档条款连接到抽取结果」，使用 CSS 和现有组件构建。
- 首页插画有明确的示意说明，没有往业务列表写入虚构项目数据。
- 统一按钮、输入框、状态标签、焦点样式及减少动画偏好。

关键文件：

- `apps/web/src/app/globals.css`
- `apps/web/src/app/icon.svg`
- `apps/web/src/app/layout.tsx`
- `apps/web/src/components/AppRail.tsx`（名称保留，实际已是顶部导航）
- `apps/web/src/components/PageShell.tsx`
- `apps/web/src/components/ui.ts`
- `apps/web/src/components/Icon.tsx`（新增，尚未跟踪）

### 3.2 项目空间

`components/projects/ProjectList.tsx` 已重写：

- 新的介绍区、真实项目概览、项目卡片。
- 支持「全部项目 / 待复核 / 需要处理」筛选。
- 支持卡片、列表视图切换。
- 保留服务端按名称或编号搜索，支持 `/` 聚焦。
- 请求序号防止连续搜索时旧响应覆盖新结果。
- 搜索后的概览明确标为搜索结果范围。
- 新建项目改为原生 `dialog`，有焦点约束、Esc 关闭、提交状态、错误信息。
- 加载骨架、无项目、搜索无结果、接口失败都有对应界面。
- 项目没有待办时使用「暂无待办」，不误报为「已核实」。

### 3.3 文件管理与上传

主要涉及 `ProjectFiles.tsx`、`UploadPanel.tsx`、`FilePipeline.tsx`：

- 上传区改为居中的拖放区域。
- 选择文件后再显示批次上传动作。
- 解析档位、OCR、文件角色、自动解析和大小限制收进可展开区域。
- 修正文案：「松开鼠标，添加到待上传列表」，不再把选择文件误说成已经入库。
- 上传时禁用选择、移除和选项操作，避免处理中修改批次。
- 保留上传进度、逐文件成功/拒绝回执、ZIP 行为。
- 文件列表改为带文件图标和独立操作区的卡片。
- 处理进度改为「转换 → 解析 → 抽取」连接节点。
- 保留文件角色修改、删除确认、重跑抽取、重新解析确认及原接口。
- 原先详情中的哈希不再占用主要可见空间；接口数据未改。

### 3.4 核对工作台

主要涉及 `ProjectWorkspace.tsx`、`DocumentWorkbench.tsx`、`Toolbar.tsx`、结果与 viewer 组件：

- 文件切换移到顶部横向标签，继续使用 `?file=` 保存当前文件。
- 转换期间自动轮询，发现可打开的版本。
- 以版本号作为工作台 key，切文件时重新建立文档状态。
- 文档区域和结果区域使用新的圆角工作区。
- 章节树默认收起，给原文更大宽度。
- 页码跳转、前后翻页、缩放、适应宽度与 Excel 导出保留。
- 结果卡片、分组、证据入口、统计、复核按钮更新视觉。
- 证据高亮改为紫色，坐标转换逻辑未改。
- 窄屏提供「文档原文 / 解析结果」切换，工具区另做压缩。
- 结果中的证据入口会在窄屏切回原文；原文角标会切到结果面板。
- 切换版本时清除上一份文件的 activeEvidence、currentPage、jumpRequest 和 notice，防止版本内同名锚点串用；缩放偏好保留。
- 表格引文预览去除常见 HTML 排版标签，只展示文字；原始 quote 与锚点不变。

**最后三项相关改动是在最近一次成功生产构建之后加入的，后续必须补做最终编译验证。**

### 3.5 模型与配置设置页

- 模型管理改为左侧步骤导航：连接供应商 → 管理模型 → 分配功能。
- 配置中心改为运行参数、解析配置、抽取配置、版本与发布分类导航。
- 通过 `hidden` 切换内容，保持面板挂载，切换时不会丢失未保存表单。
- 供应商/模型表格在自身容器中横向滚动，不撑破页面。
- 配置字段改为有留白的编辑行，补充输入框可访问名称。
- 保留供应商与模型操作、测试、拉取模型、功能优先级、配置门禁、确认、激活和回滚。
- 修改了旧文案「在右侧确认」为「到版本与发布」，与新布局一致。

## 4. 验证情况：已通过与尚未覆盖

### 已通过

1. `pnpm --dir apps/web typecheck`：通过（重构过程中的一轮）。
2. `pnpm --dir apps/web test`：**12 个测试文件、71 项测试通过**。
3. `pnpm --dir apps/web build`：多轮通过，包含 TypeScript 检查与全部路由构建；最近一轮编译约 723ms。
4. `git diff --check -- apps/web`：清理空白后通过；最后几处小改之后应再检查一次。
5. 真实后端数据的 1440px / 390px 浏览器检查：**27 项断言通过，无未捕获异常**。
6. 最后启动的 320px 检查已实际完成。写交接文档时确认报告：**7 项断言全部通过**，包括 5 个页面无横向溢出、原文角标切到结果、浏览器无异常。

浏览器已验证的交互包括：

- 项目数据加载、待复核筛选、卡片/列表切换。
- 新建弹窗打开、首个输入框焦点、Esc 关闭。
- 供应商编辑入口、设置分类切换时保留表单。
- 文件与 PDF 加载。
- 复核队列、证据点击、原文高亮。
- 窄屏结果切换、证据跳回原文、原文角标反向切到结果。
- 各主要页面在对应尺寸下不产生整页横向溢出。

### 验证边界

- 最近追加的版本切换清理、原文角标回到结果、引文预览处理，**尚未重跑最终 typecheck/build/test**。
- 320px 的反向定位已通过；多文件来回切换后的状态清理尚未专项验收。
- 浏览器检查主要是读取、导航、表单打开和定位，没有对真实数据库执行新建/删除/复核确认/配置激活等写入验收，也没有触发真实模型重跑。
- 不要将上述检查称为所有后端写入流程的完整端到端验证。
- 已查看桌面及 390px 截图；320px 报告已确认通过，但这批截图尚未逐张人工查看。
- 尚未给用户正式的「重构完成」答复；用户在收尾阶段中断，改为要求交接。

## 5. 当前问题与运行状态

**目前没有必须等待用户回答的阻塞。** 剩余的是最终核验与收尾。

2026-10-03 写本文件时检查端口：

- 未发现 `4400`、`8300` 或测试浏览器 `9463` 处于监听状态。
- 之前验收时前端和后端都在运行；下个会话需要先检查并按需启动，不能默认它们仍然在线。
- 前端代码和临时验证产物都仍在工作区。

开发访问地址应使用：

`http://localhost:4400/projects`

本地后端常用：

`http://127.0.0.1:8300`

启动方式以 `本地启动指南.md` 和用户已有的 `scripts/start-backend.ps1` 为准。前端需要设置 `API_PROXY_TARGET=http://127.0.0.1:8300` 和 `PORT=4400`，使用 pnpm 启动。

## 6. 下一步计划

按以下顺序继续，避免重做已经完成的设计：

1. 查看 git 状态，保留所有现有改动；不要还原用户原有文件。
2. 对最终代码执行：
   - `pnpm --dir apps/web typecheck`
   - `pnpm --dir apps/web test`
   - `pnpm --dir apps/web build`
   - `git diff --check -- apps/web`
3. 如需浏览器复查，先启动后端和前端，使用 localhost 地址。
4. 查看 320px 最终截图；专项检查两个文件间来回切换后不会残留旧高亮、旧页码或旧结果。
5. 如最后改动引发问题，集中修复对应组件，不再重做整体视觉方向。
6. 确认通过后向用户说明重构覆盖页面、访问地址、验证情况和验证边界。
7. **不要自动 git commit，也不要自动推送。**

可顺手整理新代码中过长的 JSX 行与局部缩进，但仅限本轮修改文件，不扩大到无关业务重构。现有历史设计文档仍可能描述旧布局，后续如要同步文档，应以实际实现为准。

## 7. 浏览器验证脚本与截图位置

这些都在 gitignore 的 `.tmp` 下，不会自动进入版本控制：

| 路径 | 内容 |
| --- | --- |
| `.tmp/redesign-browser-check.mjs` | 1440px / 390px 真实页面与交互检查 |
| `.tmp/redesign-check/checks.json` | 27 项检查结果 |
| `.tmp/redesign-check/projects-desktop.png` | 真实项目首页 |
| `.tmp/redesign-check/models-desktop.png` | 供应商设置 |
| `.tmp/redesign-check/model-list.png` | 模型列表 |
| `.tmp/redesign-check/provider-form.png` | 供应商编辑表单 |
| `.tmp/redesign-check/config-desktop.png` | 配置编辑 |
| `.tmp/redesign-check/config-releases.png` | 配置版本与发布 |
| `.tmp/redesign-check/files-desktop.png` | 文件管理 |
| `.tmp/redesign-check/workbench-desktop.png` | 原文与结果 |
| `.tmp/redesign-check/evidence-highlight.png` | 原文定位高亮 |
| `.tmp/redesign-check/*-mobile.png` | 390px 截图 |
| `.tmp/redesign-compact-check.mjs` | 320px 与反向定位检查 |
| `.tmp/redesign-compact-check/checks.json` | 7 项检查结果 |
| `.tmp/redesign-compact-check/*-320.png` | 320px 截图 |
| `.tmp/redesign-compact-check/reverse-locate-320.png` | 原文角标反向定位截图 |

运行验证：

```powershell
node .tmp/redesign-browser-check.mjs
node .tmp/redesign-compact-check.mjs
```

脚本使用本机 Edge headless + CDP，没有额外引入 Playwright 依赖。浏览器程序路径为：

`C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe`

完整脚本使用 CDP 端口 9462，紧凑脚本使用 9463。脚本正常退出会关闭它自己启动的浏览器；若中断，检查残留进程，不要误杀用户浏览器。

脚本假设项目 1 仍有可读 PDF 和证据。现有样本项目 1 名为「启动自检 172050」，文件 `tender-sample.docx`；项目 2 名为「111」。这些是原有真实数据，数量和复核数可能随后台任务变化，不要写死数值判断。

**不要重新执行 `.tmp/redesign-*.py` 等批量替换脚本。** 它们是一次性修改工具，依赖旧源码片段，重复运行可能报错或重复插入代码。只重跑两个浏览器检查脚本。

## 8. 踩过的坑

### 8.1 127.0.0.1 导致看似一直加载

最初用 `http://127.0.0.1:4400` 拍截图，页面一直停留在服务端输出的加载状态；直接请求后端却正常。

开发日志显示 Next.js 拒绝来自 127.0.0.1 的开发资源/HMR 来源。改用 **localhost:4400** 后，客户端交互与真实数据立即正常。

- 不是后端接口坏了。
- 不是多等几秒就能解决。
- 本次没有为此修改 `next.config.ts`。
- 早期 `.tmp/redesign-*-live.png` 和 `.tmp/redesign-*.png` 可能只是加载态；优先看 `.tmp/redesign-check` 下的最终截图。

### 8.2 Tailwind 扫描 PDF 静态资源与 Windows 文件锁

历史启动日志出现过 Turbopack 读取 `public/pdfjs/pdf.worker.min.mjs` 时的 Windows 文件占用错误。

本次将 CSS 入口改成：

```css
@import "tailwindcss" source("../");
```

相对 `src/app/globals.css`，扫描范围限定在 `src`，避免把 PDF 资源复制和无关目录纳入样式扫描。不要随意恢复为扫描整个工作区。

### 8.3 不要只靠定时截图判断加载成功

最初固定等待 3.5 秒，后来延长到 12 秒，仍无法解释客户端未启动的问题。最终脚本使用 DOM 条件等待真实项目卡片、PDF canvas、结果卡片出现，同时记录浏览器异常。

截图前应确认内容已加载，不要拿骨架屏作为验收结果。

### 8.4 测试样本可能有多处证据

项目 1 的有效结果有两处证据。脚本最初只找「定位原文」文字按钮，因此误报找不到溯源入口。

实际多证据入口是 `[data-evidence-row]`。脚本已改为进入复核队列，再优先点击证据行。测试失败不一定是功能坏了，先核对当前数据形态。

### 8.5 小屏「不溢出」不代表可用

最初 390px 页面没有横向滚动，但导航、工具栏和重复说明占了大半屏，结果卡片几乎看不到。

已针对工作台压缩小屏顶部导航、页码/缩放/导出工具栏，隐藏重复抬头和键盘提示，保留原文/结果切换。需要继续关注实际可读高度。

### 8.6 表格批量包裹不要只替换闭合标签

第一次给设置表格加滚动容器时，功能绑定表格的 class 与另外两个表格不同，导致只增加了闭合 div，TypeScript 报 JSX 结构错误。已修正。

今后如需批量替换 JSX，检查每个目标实际结构。

### 8.7 PowerShell、UTF-8 与脚本引用

- 本轮通过 PowerShell 单引号 here-string 写文件，明确指定 `-Encoding utf8`。
- Python 辅助脚本读取用 `utf-8-sig` 兼容 BOM，输出用 `utf-8`。
- 写 JS 测试脚本时曾因两层字符串转义丢失单引号转义而报 SyntaxError，已修复。
- 不要把 JSON 字符串化当成 Shell 转义。
- 旧 PowerShell 5.1 脚本的中文 BOM 要求见本地启动指南；不要顺手重写用户启动脚本。

### 8.8 apply_patch 的同路径删建限制

一次 patch 同时 Delete 和 Add 同一个绝对路径被拒绝，未造成文件改动。后续改用完整 UTF-8 写入或有明确定位的修改。

### 8.9 工作区已有用户未提交改动

开始本任务时已存在：

- `本地启动指南.md`：已修改。
- `scripts/start-backend.ps1`：未跟踪。

它们不是本次前端重构创建的，不要覆盖、还原、删除或替用户提交。本轮前端约 30 个文件有变更，新增 `Icon.tsx`，没有修改后端服务代码。

## 9. 交接摘要

整体视觉和主要交互已实现，桌面/390px 检查 27 项通过，最终 320px 检查 7 项通过。收尾前补做最后几处定位/预览改动的编译与测试，专项检查多文件切换，随后交付用户验收即可。无需从旧界面重新设计，也无需再请求一次重构授权。

## 10. 后续讨论：RAG 与 GraphRAG（2026-10-03）

- 用户已要求根目录 `AGENTS.md` 写入任务开始前使用 UTF-8 读取本文件的规则，已加入。
- 用户希望引入 RAG + GraphRAG，并明确第一版优先“项目内问答与关联分析：查条款、串联资格条件和废标风险，每条回答可定位原文”。
- 接入建议见 `docs/设计/13-RAG与GraphRAG项目知识检索.md`，已加入文档索引。存储、模型和接口仍是建议设计，尚未安装依赖、迁移数据库或实现知识检索功能。
- 建议复用解析元素与锚点，增加混合检索、带证据的领域图谱和项目问答。GraphRAG 当前按图谱增强检索方法设计，暂不绑定 Microsoft GraphRAG 框架。
- 关键边界：锚点必须绑定解析批次；项目范围在检索与图谱遍历时约束；关联结论逐项引用原文；全量废标风险汇总不能仅依靠 top-k 检索。
- 用户进一步明确后续还要用于标书检查与历史标书复用。设计文档第 10 节已补充三种用途共用的来源、集合、权限、分层分块与证据契约；随后确认的智能报告与分类要求见第 11 节及本文件第 11 节。
- 标书检查以招标要求为依据、当前投标文件为被检查对象，保留要求与响应的双向证据；历史标书仅作复用参考，不能证明本次已满足要求。后续复用需保留原项目与版本、适用条件、待替换信息和衍生来源链。
- 前述前端最终验证仍未在本次讨论中执行，原有未提交代码保持原状。所有新增文档也未提交。

## 11. 智能分析与类别选择的确认结果（2026-10-03）

- 用户要求解析超出固定字段，形成前端可渲染的动态报告，并能逐项点击定位原文；已接受“必检主题 + 自主发现”、事实/判断/建议区分、独立引用及段落/表格块级高亮。
- 类别由用户在界面上先选，再启动智能分析；项目保存默认类别，标段可单独覆盖。系统可以提示分类与原文不一致，但不自动改选。
- 最终分类决策：**仅工程、货物、服务一级单选，不做多级分类和分类管理页面。** 保留平铺多选的附加分析专题（如安装、调试、运维），不把专题做成下级分类。
- 已更新 `docs/设计/13-RAG与GraphRAG项目知识检索.md` 第 11 节及文档索引。当前范围包含智能分析报告、项目问答和关联分析；标书检查与历史复用仍分期实现。
- 用户调用的 `grill-me/SKILL.md` 仅转入 `grilling` 访谈技能，没有解析模板。按该技能的明确要求，曾委派一个子代理进行只读事实核查，未修改文件；没有找到专用标书解析 Skill。
- 核查确认：当前结果仍受固定 FIELDS 及字段级证据结构限制；动态报告需要扩展结果存储与接口、前端渲染和完整引用身份，不能只换提示词。已有解析锚点可复用，但首版不承诺原句或单元格精确高亮。
- 本阶段完成的是设计与交接记录，尚未实现上述功能、安装相关依赖或执行数据库迁移。用户未要求提交，所有改动保持未提交。

## 12. 现有后端接口对接完成（2026-10-04）

### 12.1 本轮范围与根因

- 用户要求先完成已重构界面的后端接口对接，暂不实施 RAG、动态报告与类别选择。
- 之前界面已有真实 API 调用，但上传后等待转换、任务重跑刷新、部分结果状态和服务端错误存在缺口；不能把本轮描述成从静态假数据开始接入。
- 用户启动时已经设置 `API_PROXY_TARGET=http://127.0.0.1:8300`、`PORT=4400`，代理健康检查通过。环境变量缺失或默认端口不是本轮问题的根因。

### 12.2 已完成修复

1. `api/projects.py` 项目详情的文件新增 `latest_job`（任务 ID、阶段、状态、进度及失败原因）；列表异常统计纳入任务失败，包括转换失败。对应接口设计文档、前端类型已同步，无数据库迁移。
2. `lib/projects/pipeline.ts`、`ProjectFiles.tsx`、`ProjectWorkspace.tsx` 依据任务状态持续轮询：尚无 PDF 版本也显示排队/转换；重解析优先新任务；已有部分结果不能盖过仍在运行或已失败的抽取；仅归档文件不持续等待转换。
3. `DocumentWorkbench.tsx` 接收外层任务刷新令牌，解决尚无 `parse_run` 时工作台停留空结果。文件切换清除旧定位已用两份含同名锚点的 PDF 验证。
4. 文件操作修复 `project_file_id` 与 `version_id` 的忙碌状态混用；运行期间禁用重复解析/抽取；展示后端任务失败原因；上传成功后刷新失败不会再把上传误报为失败。
5. `lib/api/client.ts` 项目列表遍历后端分页并保留搜索条件，避免只显示前 50 项。服务端单页上限为 **100**，请求不能使用 200。
6. `api/exports.py` 和 `worker/exports.py` 修复导出 SQL 的同名 `status` 列歧义，恢复真实 Excel 导出，并确保复核后状态及筛选一致。
7. `api/quality.py` 修复字段统计 500：转换数值时排除字符串分组维度 `review_mode`。逐条复核、批量确认、抽检三档均有回归测试。
8. `next.config.ts` 本地默认代理与启动指南统一为 8300，显式 `API_PROXY_TARGET` 仍优先；容器继续使用其显式配置 `api:8000`。

### 12.3 最终验证结果

- 前端 typecheck 通过；12 个测试文件、**76 项测试通过**；最后代码的 `pnpm --dir apps/web build` 通过，包含 TypeScript 与所有路由构建。
- 后端 `TENDER_RUN_DB_TESTS=1` 下 **266 项测试通过、2 项跳过**。有一条 Starlette TestClient 对 httpx 的弃用提醒，不影响本次测试；没有为此升级依赖。
- 修改 Python 文件及新增测试的 Ruff 检查通过，5 项分层依赖契约通过，`git diff --check` 通过。
- PostgreSQL 集成测试以连接内临时表覆盖同步/后台导出的全部、待复核、已确认三种筛选，事务回滚，不读写原有业务表数据。
- 浏览器 **16 项检查全部通过**，无未捕获异常，85 次记录到的 API 请求均成功。
- 浏览器实际操作覆盖项目创建、双文件上传、队列状态与自动刷新、文件角色保存、PDF 与证据高亮、复核保存及回显、切文件清理旧定位、第二份文件的同名锚点定位、停用供应商创建/编辑、配置读取、文件删除。
- Excel 通过真实导出接口获取，另用 openpyxl 确认包含两条结果，复核状态分别为 `verified` 与 `need_review`。

### 12.4 验证边界与临时产物

- 联调创建独立的 `接口联调-*` 项目和停用供应商；结束后通过 API 软删除本轮测试项目并删除测试供应商，未修改原有项目或在用模型绑定。
- PDF 上传、对象存储、版本生成与页面探测走真实服务；测试脚本对测试任务调用 `process_file.apply()`。解析、抽取及证据数据由该测试项目专用 fixture 写入，**没有调用真实 MinerU/OCR/LLM，也不代表完整后台队列与模型链路已验收**。
- 项目软删除不物理清理解析与复核记录，联调数据仍留在数据库；后续排查全局字段统计时须注意这些测试样本。
- 配置激活/回滚及在用模型调用未执行写入验收。后台导出 SQL 通过真实数据库查询测试，未触发用户正在使用的 worker 消费测试导出任务。
- 临时脚本、报告、Excel 和截图均在 gitignore 的 `.tmp` 下：
  - `.tmp/api-integration-fixture.py`
  - `.tmp/api-integration-browser.mjs`
  - `.tmp/api-integration/checks.json`
  - `.tmp/api-integration/export.xlsx`
  - `.tmp/api-integration/files.png`
- 复跑浏览器检查前必须先运行 `python .tmp/api-integration-fixture.py prepare` 生成不同哈希的 PDF，再执行 `node .tmp/api-integration-browser.mjs`；使用 `apps/api/.venv/Scripts/python.exe`。
- 脚本等待真实项目标题/结果 ID，不把骨架或上一份相同金额的结果卡片当作加载完成；证据入口兼容多证据行和带页码的“定位原文”按钮。

### 12.5 运行状态与后续

- 验证完成时前端在 `http://localhost:4400/projects`，后端在 `http://127.0.0.1:8300`；下个会话仍应重新检查端口。
- 本轮启动并在修复后重启的 API 进程为 **25292**，没有热重载；用户已有前端进程 **16924** 未停止。不要仅凭历史 PID 操作进程，应先核验当前命令和端口。
- 后台导出 worker 在下次启动后加载本轮 SQL 修复；本轮未主动停止用户 worker。
- 本轮任务已经完成，无需重复设计 UI。后续按用户指示推进 RAG/GraphRAG 设计或实施，不要把设计文档中的功能说成已经上线。
- 本地启动指南、启动脚本及先前前端重构改动均保留。**没有提交或推送。**

## 13. 代码审查问题修复（2026-10-04）

用户要求检查全部未提交更改，审查确认两处问题，随后明确要求修复。本轮只围绕两处问题修改代码、测试与说明。

1. **启动脚本误杀风险**：`scripts/start-backend.ps1` 原先只凭 PID 存活便执行 `taskkill /F /T`。现保存创建时间与完整命令行，终止前验证当前仓库解释器、服务模块、创建时间和命令行。旧格式记录及身份不符记录不直接用于终止；现场扫描仅接纳本项目 API/worker/beat，并在实际停止前二次核验。重复启动检查、`-Force`、`-Status` 共用身份判断；旧格式文件中仍运行的合法服务显示“运行/未登记”。保留 UTF-8 BOM。
2. **小屏远页证据超时**：结果视图隐藏原文后，测宽归零并卸载虚拟页占位；立即定位时占位还没恢复，远页不能挂载。`apps/web/src/hooks/useLocate.ts` 现等待目标页占位恢复有效高度后再滚动、等待渲染并高亮。等待有上限，取消过期点击；卸载时使旧定位失效，防止切文件后写回旧证据。

验证：

- `scripts/tests/start-backend.test.ps1`：**19 项检查通过**，覆盖三种合法服务、JSON 身份记录、PID 复用、其它解释器/模块、命令变更、已退出进程、旧记录及整条停止路径。测试通过 PowerShell AST 只加载函数，模拟进程查询并拦截 `taskkill`，没有终止真实进程。
- 前端 typecheck、**76 项测试**、生产 build、`git diff --check` 通过。
- 只读浏览器回归使用现有 137 页文档：390px 下从结果点击第 22 页证据，修复前超时且滚动位置为 0；修复后正确高亮 `p22b1`。1440px 下同一证据也成功定位。
- 浏览器脚本与报告：`.tmp/review-mobile.mjs`、`.tmp/review-mobile/checks.json`，截图为同目录 `390.png` / `1440.png`。脚本只读，不写复核或触发解析。
- 仅以 `-Status` 验证运行中服务的身份识别，未启动、停止或重启用户服务；第 12 节 PID 已可能变化，后续必须重新检查。
- 本轮未调用 OCR/LLM，无数据库迁移，全部更改仍未提交。

## 14. 用户授权提交（2026-10-04）

- 用户在审查修复完成后明确要求“提交代码”，本次提交包括前端重构、接口对接、两处审查修复、启动脚本与测试、设计文档和交接规则。
- 使用中文提交信息，不添加作者说明或协作者尾注。不包含 `.env`、`.tmp`、日志或构建产物，不执行推送。
- 第 1—13 节中的“未提交”描述保留为当时的历史状态。RAG/GraphRAG 相关提交仅为设计文档，不代表已实现相关功能。

## 15. 知识库与 Skill 综合分析实施中（2026-10-04）

- 用户通过 grill-me / grilling 访谈确认：通用多库管理；类别用途区分；Skill 可自行改造但定位沿用现有方式；项目全部当前有效文件共同分析；手动开始；资料新增/替换提示更新；默认等齐，显式允许部分分析。用户回复“按建议来”后已开始实施。
- 已找到 `投标skill/parse_skills`，被 Git 忽略，含 12 标准解析模块、通用兜底、4 历史分类模块。之前“未找到 Skill”是历史错误状态。普通模板缺稳定引用，格式模块原依赖唯一 DOCX；已按授权改为统一带 PDF 锚点的模块协议。
- 已新增迁移 0005 和知识库/来源/索引/报告/模块/关系/问答表，并在开发数据库执行。现场 PG 18.6 无 pgvector；暂用数组存向量、范围内精确余弦检索。用户明确向量服务稍后填写，当前先实现代码接口。
- 新代码：`api/knowledge.py`、`application/knowledge.py`、`knowledge_store.py`、`analysis_skills.py`、`worker/knowledge.py`、`adapters/openai_embedding.py`、`ports/embedding.py`；原 Skill Markdown 81 文件打包至 `resources/parse_skills`。新增前端知识库列表/详情及 ProjectAnalysis、CitationViewer、ReportItems、QuestionPanel；项目首页默认综合报告，`?file=` 或 `?view=fields` 保留旧字段工作台。
- 最新测试：新增专项 15 passed（含真实 PostgreSQL 临时表，全部回滚）；旧后端 263 passed、5 skipped；前端 typecheck 通过。全部未提交。
- 当前运行中的 API/worker/beat 尚未重启加载新代码，前端开发进程可能已自动更新。不要把现有运行状态当作新功能已经可访问。
- 待做：复核新任务的恢复/权限/引用过滤；为报告固定 Skill 快照；确保旧归档文件可重新处理；修复 Ruff 残留长行；同步 DDL/API 契约测试和文档；跑全部数据库测试/前端测试/build；使用测试资料做浏览器跨文件与移动端定位。详见 `docs/设计/14-知识库与综合分析实现.md`。
- `.tmp` 中可创建独立验收脚本与截图。不要重放旧 UI 批量修改脚本。禁止自动提交。


## 16. AI 模型管理增量完成（2026-10-05）

- 用户要求参考根目录 `11-AI模型管理详细设计.md` 继续完善模型管理。本轮接续已有未提交的模型能力代码，保留知识库等其它改动，没有自动提交或推送。
- 修复 ModelSettings 缺失 profiles/secretReady 导致的 TypeScript 编译失败。管理页现有供应商、模型、功能绑定、调用记录四类；导入显示 created/skipped 且默认停用，失败不再无限显示加载中，最多导入 100 项。
- 功能草稿按功能分别保留，切换/刷新不丢排序；保存带旧 revision，预算和绑定原子保存。供应商/模型表单也固定打开时的 revision，避免刷新后无意覆盖并发修改。保存过程中冻结表单。
- 模型协议能力与参数范围由服务端清单驱动；Responses 最小输出预算 16，temperature 留空不再强塞 0。原生 OpenAI/兼容、Anthropic、Gemini 协议有本地金样测试；不把这些测试当作真实供应商连通。
- 测试持久记录并返回 test_id，可查询详情；7 天有效期、配置变化失效、同值保存/改名保留有效性；同时检查供应商版本与测试开始顺序，较早测试不能覆盖较新结果。专用重排目录明确 unsupported。测试日志包含向量/重排数量及名称快照。
- 调用记录支持功能/模型/状态筛选、分页和 invocation_id 请求链。修复历史错误回显网关 HTML 的问题；参数校验错误不返回 Pydantic input/ctx，防止密钥进入响应。新增明确拒绝停止换源、Retry-After、默认 A/A/B/B/C/C、总请求上限及数据库登记失败不出站测试。
- 0006 迁移先在独立 schema 的事务内验证完整 0001—0006，再成功应用到当前开发库；本轮没有变更 `.env`。开发库现在为 `0006_model_capabilities`。向量/语言混用旧绑定会阻止迁移，避免自动删除绑定。
- 最终验证：后端 **340 passed、4 skipped**（TENDER_RUN_DB_TESTS=1），前端 **76 项测试**、typecheck、生产 build 通过；本模块 Python Ruff 和 **5 项依赖分层契约**通过。剩余一条 Starlette/httpx 弃用提醒未升级依赖。
- 浏览器 **17 项检查通过**：真实 API 创建匿名供应商、拉取本机模拟目录并导入停用模型、测试、改名、有效性、调用记录历史名称与筛选、跨功能草稿保留，以及 390/320px 四面板无整页溢出。人工查看桌面/320px 截图后修复选择框在面板内被裁切。没有向用户真实供应商发送模型请求。
- 浏览器只操作独立的 `接口联调供应商-*` 与 fixture 模型，结束通过 API 软删除供应商和模型；测试调用历史按设计保留，未改原有功能绑定。数据库集成测试创建独立 schema，事务结束全部回滚。
- 脚本与产物：`.tmp/llm-management-browser.mjs`、`.tmp/llm-management-check/checks.json`、`models-desktop.png`、`calls-desktop.png`、`calls-mobile.png`。脚本自己启动 9486 模拟协议服务和 9484 Headless Edge，退出会关闭两者。
- 本轮启动的 API 当前 PID **28004**，`http://127.0.0.1:8300`；前端开发服务器在 `http://localhost:4400/settings/models`。下轮检查实时进程，不凭历史 PID 直接终止。没有启动 Worker/beat，也没有重跑真实抽取。
- 根目录设计包含 PPT、多工作区等跨项目约定。适用范围、真实交付及后续项已写入 `docs/设计/12-LLM管理与模型路由.md` 第 10 节并同步 API/DDL 契约；不要将视觉/多模态/生图、平台共享、完整网络策略、动态测试策略、持久预算恢复、unknown 对账或金额预算描述为已实现。嵌入/重排当前仍是单模型单次请求，完整业务账本待补。


## 17. 修复回环 IP 访问不取数（2026-10-05）

- 用户使用 `http://127.0.0.1:4400/settings/models`，控制台 HMR WebSocket 握手失败；浏览器复现页面仅保留 SSR 的“正在加载模型配置”，没有任何模型 API 请求。同一服务用 localhost 可正常取数，后端及两种地址的 API 代理均返回 200。
- 根因：Next.js 16.3.6 默认开发来源允许 localhost，但未自动允许 127.0.0.1；`/_next/hmr` 被开发来源检查拒绝，客户端启动未完成。上一轮只用 localhost 验收，遗漏了启动指南中的回环 IP 地址。
- `apps/web/next.config.ts` 增加 `allowedDevOrigins: ["127.0.0.1"]`，仅补允许本机地址。开发服务已自动重新加载；启动指南同步说明 localhost/IP 均可使用，健康接口成功不能替代页面取数检查。第 8.1 节仅换 localhost 的旧规避方式已被本节修复替代。
- 修复后浏览器在两种地址均加载真实供应商/模型/功能/设置，API 全部 200，原 WebSocket 握手错误消失；typecheck、diff check 通过。诊断脚本 `.tmp/frontend-origin-browser.mjs` 只读，不写业务数据，报告 `.tmp/frontend-origin-check/checks.json`。
- 本轮没有重新启动后端、修改接口或提交代码。当前用户自行启动的服务 PID 已与第 16 节不同，仍须实时核验身份。


## 18. Ollama 嵌入真实验证与测试反馈（2026-10-05）

- 用户反馈 Ollama 嵌入不可用，要求核实是否真正适配。现有实现调用 OpenAI 兼容 `POST /v1/embeddings`，不是模拟返回；尚未单独实现 Ollama 原生 `/api/embed`。
- 当前供应商 ollama（ID 4）为 `http://127.0.0.1:11434/v1`、匿名，模型 qwen3-embedding:0.6b（ID 4）登记为 embedding/embeddings。服务返回版本 0.35.1。
- 先用现有适配器发送三条合成短文本，真实返回 3×1024 维有限、非零向量，约 10.8 秒；随后通过真实管理页点击该模型测试，返回 1×1024 维向量、3.1 秒，4 项浏览器检查通过。没有调用其它供应商或提交用户私有文档。
- 查到用户最近一次嵌入测试已成功，耗时约 39 秒；此前页面只有禁用按钮，没有明确运行反馈。本轮补“测试中”、等待上限与可能的本地加载提示，成功后显示实际向量数量、维度、耗时。响应增加可选 vector_count/embedding_dimensions/document_count，不新增迁移，维度仅当次响应展示。
- 同时修复 `GET /llm/tests` 不传 model_id 时 PostgreSQL 无法推断 NULL 参数类型导致 500；改成按筛选条件生成 SQL。专项覆盖无筛选、匹配/不匹配模型及嵌入测试实测形状，14 项后端专项通过；前端 typecheck/build、Ruff 和 diff 检查通过。
- 当前 embedding 功能绑定为空，所以知识库不会自动使用模型；本轮没有擅自设置绑定或重建用户索引。已向用户询问是模型测试失败、知识库使用失败还是配置绑定问题，截至本轮收尾未收到选择，不能把空绑定断言为其全部问题根因。
- 真实测试未复现失败。后续如用户明确是知识库问题，应在授权范围内完善绑定与索引构建/检索链路验证，不因模型探测成功就宣称整个知识库已验收。
- API 在确认无近期 running 测试后核验父子进程身份，只重启 API 加载修复；当前 PID 33064，未重启 Worker/beat。诊断脚本 `.tmp/ollama-embedding-browser.mjs`、报告 `.tmp/ollama-embedding-check/checks.json`、截图同目录 models.png。下轮重新核验实时进程。


## 19. 按用户纠正补齐模型分类与配置（2026-10-05）

- 用户质疑“完全按需求实现了吗？模型分类没这么少吧？模型的配置也不全吧？”。已经承认第 16 节版本没有完整覆盖需求；不能继续把三种类型、固定能力、少量参数描述为完整交付，也不能用“跨项目设计”当作删减范围的授权。
- 新增 `docs/设计/15-AI模型需求核对.md`，逐项记录 AI01—AI22 的已验证、部分及未完成状态。根设计顶部链接该核对表；设计12第11节与 API/DDL 契约同步。后续继续按原基线补齐，未完成项没有被用户取消。
- 本轮补齐四基础 kind：language、embedding、rerank、image_generation；视觉为 image_input；嵌入派生 text/multimodal。模型种类、接口模式、能力独立；适配器限制之外的组合明确拒绝。
- 新建、编辑、目录导入共用 `ModelConfigurationFields.tsx`。后端 profiles 有 required/default/allowed capabilities 与参数 schema；模型 supported_parameters 可收窄，parameters 持久化并参与实际请求。语言有 Top P/K、停止词、种子、惩罚、推理强度、显式输出预算字段等适用项，嵌入有 dimensions/task_type，重排有 top_n，生图有尺寸/质量/格式或宽高比/分辨率。字段按协议控制，不接受任意请求覆写。
- 真实适配代码：OpenAI/兼容 Chat Completions/Responses、Anthropic Messages、Gemini generateContent 均发送原生图片内容；Gemini 原生 batchEmbedContents 支持真正图文嵌入；OpenAI/兼容 embeddings 仍只支持文本。生图新增 ProviderImageModel（OpenAI/兼容 images/generations、Gemini 图片 generateContent），解码校验 PNG/JPEG/WebP，只请求一张，不抓取供应商返回的任意 URL。Pillow 成为显式运行时依赖，uv.lock 已同步。
- 模型能力测试分 text/vision/embedding/multimodal_embedding/rerank/image_generation，独立保存证明；总体有效性也取各能力的聚合。文本成功不证明视觉/图文。保留同步 `/test`，增加 `/tests` 202 受理后执行，刷新继续查询；发送前在同一事务登记测试和调用记录。测试超时或 API 崩溃后收敛为 unknown，不自动重发。
- 新增测试图临时预览端点；图片字节只在 llm_test 保留，失效即时停止预览，失效满24小时清理。API 查询及既有知识任务派发会维护清理；未新增正式素材，也未启动生图业务。新增 image_generation 功能绑定；原生图调用端口与测试已连接。
- 迁移 `0007_model_inputs` 已验证并应用开发库。新增模型参数/空间身份、测试结果/临时图/超时快照/调用关联、图片用量。0006没有再改。后续结构变更必须继续新增迁移，不再修改已应用0007。
- JSON 是可选能力，当前抽取/分析功能必须有 JSON；绑定和修改都校验，worker 同时过滤。修复旧模型表单将默认参数清单显式保存时无谓失效的问题，改名/参数顺序变化保持原证明。
- 最终后端 **363 passed、5 skipped**，Ruff、5项依赖分层检查、diff检查通过。前端 **76项测试**、typecheck/build通过。5个跳过包含迁移没有新增表的适用性跳过，不是新增模型场景未测。
- 浏览器12项通过：4分类、视觉配置保存、图文实际带图、运行中刷新不重发、分别保留能力证明、可读生图预览、图文目录导入/参数/默认停用、390px四面板、无未捕获异常。脚本 `.tmp/model-inputs-browser.mjs` 与报告/截图 `.tmp/model-inputs-check/`。模拟供应商结束已软删除，调用历史保留。首次脚本在“分配功能”标签写错处失败，修正选择器后12项通过，不是产品故障。
- Ollama 经新异步测试入口重测：现有模型ID4 `qwen3-embedding:0.6b` 返回1×1024维，3.89秒，test_id=15。未改原有模型配置/功能绑定或重建索引。云端模型没有发收费测试；其它协议是模拟载荷验收。
- API 已在核实进程身份且无 running 测试后重启加载全部补丁，最后启动父进程31360；运行子进程须实时查询，不能凭该PID停止。日志 `.tmp/model-inputs-api-final.*.log`。前端仍4400、API8300；保留 allowedDevOrigins。未重启 Worker/beat。
- 原设计仍有未完成项：工具/流式、远端分页、动态测试/执行策略、多工作区/共享、AES-GCM/AAD、完整网络策略/审计幂等、持久预算和unknown对账、嵌入/重排多候选与完整业务账本、跨实例空间证明/旧索引固定模型读取。不能称全文完成。详见逐项核对表，后续应真正落实代码，不能只更新“后续”列表。
- 全部未提交，保留此前知识库等修改，没有启动子代理。

- 最终只读复验：127.0.0.1 与 localhost 的模型页均实际请求后端，四组 API 全部200，HMR均101，无浏览器异常。API当前监听子进程2672（父进程31360），仍须实时核验。


## 20. 分批提交（2026-10-05）

- 用户要求分批提交代码；按「后端模型管理 → 后端知识库 → 前端模型管理 → 前端知识库 → 开发环境 → 文档」六批提交，中文提交信息，无作者或协作者尾注，未推送。
- `59ad29b` 后端模型管理（多协议适配、能力参数校验、测试有效性与调用记录、迁移 0006/0007、设计 12/15 及根设计）。
- `0367c0b` 后端知识库（迁移 0005、多知识库、Skill 综合分析、带引用问答、81 个解析 Skill 资源、设计 05/13/14）。
- `7a64199` 前端模型管理四面板；`dee88b1` 前端知识库与项目默认页切换。
- `5d68a7c` 回环 IP 开发源修复（next.config.ts）；`e282bbb` 交接记录与设计索引（本文件、docs/README.md）。
- 提交前验证：后端单测+契约 345 收集（0 失败、18 个沙箱 tmp_path 环境错误、5 跳过）、模型管理集成 16 项、知识库集成 6 项、Ruff、5 项分层契约、前端 typecheck、git diff --check 均通过；前端 vitest 因沙箱 spawn EPERM 未复跑。
- `本地启动指南.md` 是用户自己的未提交修改，按第 8.9 节约定未代为提交。

## 21. 重新打通标书解析流程（2026-10-05，进行中）

用户当前明确目标：重新打通标书解析，包括知识库构建，使用 Agent + Skill 解析招标文件。线程 goal 已激活，不得把仅修复上传或单测通过当作完成。无 token 预算。未提交、未启动子代理。开始前已读本文件，使用 karpathy-guidelines。

### 已修改且已验证的代码

- `adapters/mineru.py`：纯哈希 PDF 存储键提交上游时补 `.pdf`；真实旧错误是 `Unsupported file type: <hash>`。不改存储字节/键/hash。
- `adapters/gotenberg.py`：`trust_env=False`，与 MinerU 一样内网直连。原 worker 版本探测 502，直连正常；重启后 DOCX 真实转换完成。
- `adapters/openai_chat.py`：只兼容完整外层 Markdown JSON 围栏；仍拒绝说明文字、截断 JSON、NaN/Infinity。真实 llama.cpp 返回了完整 fenced JSON，修复前被当非法 JSON 换源失败。
- `application/knowledge_store.py`：来源关联最新预处理任务，即使没有 parse_run 也可显示失败和错误。embedding_signature 用 embedding_space_id + parameters 替代 config_revision，纯改名不再换向量空间；旧签名需重建。
- `worker/knowledge.py`：空文字索引失败；完整报告遇到已失败/partial/unsupported 文件终止等待列出文件，不再无期限等待。未开始全文扫描的失败报告重试重新等待原范围最新可用批次。
- `application/analysis_skills.py`：新增独立 SCAN_CONTRACT，扫描只分配模块候选，避免与 Agent search/read/finish 协议混用。扫描结构错误最多纠正两次，不能跳过批次；首个模型请求前初始化覆盖块总数。Skill 必须加载通用 extraction_rules、类别及标段覆盖规则；给出候选位置，必须读取扫描候选才能 finish；结构/引文错误反馈 Agent 修正，32 步上限不变。规则快照增加 `__scan_contract__`。
- `api/knowledge.py`：集合来源增加 semantic_ready/needs_reindex，当前空间匹配才标向量可用；重试前扫描失败返回 waiting，已开始扫描返回 pending。
- 前端 KnowledgeCollectionDetail：补解析完成至索引派发间隔轮询、当前向量是否需要重建、文件错误可见。ProjectAnalysis：文件处理中也轮询，失败/partial 文件可直接重新处理。
- 更新设计14与API设计05，标为本轮验收进行中。无需数据库迁移。`本地启动指南.md` 为用户原有未提交内容，没有改动它。

### 真实服务验收与现场配置

- 独立验收项目 **13**，名称 `解析全链路验收-1791201167`；主文件 `采购招标文件.docx`、补充 `交货期补充通知.pdf`。独立参考库 **7**，上传项目14，文件 `设备保修参考.pdf`。自有资料库集合6。
- 所有文件仅通过真实 API 上传，经历实际 Gotenberg、MinerU、数据库/存储/队列，未插入解析/索引/报告 fixture。3份均完成解析并得到真实1024维向量索引。主文件source9，补充source11，参考source12。
- 索引早期失败因本机 Ollama 没启动，已启动本机已有 `ollama serve`，进程当时33068，日志 `.tmp/tender-flow-check/ollama.*.log`。没有下载新模型或改绑定。
- 当前绑定：analysis/knowledge_ask/extract 的首选是模型16 `qwen3.5-9b`，provider11 lammacpp `http://127.0.0.1:7896/v1`；后备glm模型2。embedding绑定模型4 `qwen3-embedding:0.6b`，Ollama `http://127.0.0.1:11434/v1`。
- 原 llama.cpp PID28816 健康200但槽连续数分钟卡同一进度、极短请求超时。核验完整身份后，**保留原参数**重启成17796：exe `G:/llama-cpp/llama.cpp/build/bin/Release/llama-server.exe`，cwd `G:/llama-cpp/gguf/qwen3.6-9b`。参数备份 `.tmp/tender-flow-check/llama-restart.json`，日志同目录 `llama.*.log`。原参数含 Q8模型、mmproj、`-c 256000`、自动4槽、q4 KV、fit；尚未调小上下文。不要凭旧PID杀进程。
- 重启后短请求约5.2秒，真实响应含 fenced JSON。复杂请求本机常在每秒4—20 Token波动，默认90秒不足；通过管理API将模型16 timeout从90调到**300秒**、max_tokens从空设为**4096**，revision现3，旧值完整留在 `model-settings-before.json`。未改模型绑定或云端配置。`reasoning_effort=none` 与直接 `chat_template_kwargs.enable_thinking=false` 的诊断仍返回 reasoning_content，没有为这些未生效参数新增代码。
- 本机llama `--help`确认支持 `--reasoning on|off|auto`、`--reasoning-budget`、`--parallel`。后续若需要性能调优，可据真实负载研究；未调小原ctx256000。不要因模型慢就缩小验收范围。
- 本次两条旧字段抽取耗尽时间争抢本机模型，已通过API取消样本项目13的 job `040b7bf79c0e40b0a1942ade17a44106`、`4723674317e14a8f86ae03f2fe94c6af`。其它用户项目任务没有取消。当前主目标是13模块Agent综合报告。
- 旧报告4保留失败历史（PDF后缀、语言JSON、扫描协议）。新报告 **5** 使用修订后的完整规则快照，**最后核验 running，全文20/20块扫描完毕，project_basic_info_parsing模块running，其它尚未创建**。必须继续轮询这个真实任务，不能启动重复报告，也不能将超时观察当任务终止。
- 后端最后通过安全启动脚本重启加载本轮代码：API父15488、worker父24000、beat父20804；实际子进程实时核验。所有最新代码均已加载，扫描模块修正也已加载。模型配置在DB中，不需重新启动读取。

### 测试及后续必须完成

- 最后后端完整 `TENDER_RUN_DB_TESTS=1`：**383 passed, 5 skipped**，一次Starlette/httpx提醒。工具会话50514已输出完整结果，但若需确认退出可poll一次。
- 前端76项测试、typecheck、生产build通过；5条分层契约通过；新改动Ruff通过（最后整个修改集合应再做一次diff/Ruff检查）。
- 真实混合检索 `GET /knowledge/collections/7/search?q=保修期限` 返回 hybrid、source12、4块，逐项resolve成功；结果 `.tmp/tender-flow-check/retrieval.json`。
- 浏览器7项通过：真实知识库语义就绪、检索命中、PDF原文高亮、项目显示2文件、390/320px无整页溢出、无未捕获异常。截图已看knowledge-desktop，显示真实原文正确高亮。**报告完成后的13模块展示与报告引用测试尚未执行**；脚本只在report.completed时执行这两项，最终必须确认它没有跳过。
- `.tmp/tender-flow-check.py status` 会读取state.json内的报告ID并保存最新report.json；不要重跑start（它会拒绝已有state，避免重复项目）。用 `.\apps\api\.venv\Scripts\python.exe`，设置 `$env:PYTHONUTF8='1'`。
- `.tmp/tender-flow-browser.mjs` 用Headless Edge 9491，运行 `node .tmp/tender-flow-browser.mjs`。截图与checks在 `.tmp/tender-flow-check/browser/`。
- `.tmp/probe-analysis-model.py` 是直接合成样本诊断，不走调用账；旧会话35166已完成，证明新围栏适配+旧扫描能解析一批。无需反复调用与主任务争抢GPU。
- 下一步：继续报告5真实运行，检查最终所有13模块而非仅状态；验证已读工具轨迹、逐项引文、补充通知45日与主文30日差异、独立历史质保五年不得污染本项目三年要求。遇到真实错误按证据修复并针对失败模块重跑。
- 接着走真实项目/知识库问答与独立库隔离引用，重跑浏览器报告定位（至少两文件与移动端）；将最终证据更新设计14和本交接文件；审查diff后再调用goal complete。未达到全部要求不能宣称打通。不要自动提交。

### 第21节最新续记（Skill资源冲突已确认）

- 报告5完成全文20/20扫描后，首个项目概况模块因“模型输出不是合法JSON”失败，否决条件模块开始运行。检查资源确认**13个SKILL及输出模板仍要求旧Markdown**，bid_format_outline还强制不存在的read_docx_structure及DOCX element_index。这与当前PDF块工具/JSON报告相冲突，必须真正修改资源，而非只靠优先级提示遮盖。
- 已告知使用技能 `C:/Users/wph98/.codex/skills/skill-creator/SKILL.md` 并读取。这个技能明确要求改现有Skill时保留旧版，并做旧版/新版测试与展示结果；其中明确的测试子代理流程属于允许委派的来源。尚未启动子代理。领域/输出/成功条件已由用户原目标与项目设计明确，**不用再向用户确认范围**。
- 旧81份markdown已按UTF-8复制到 `.tmp/parse-skills-workspace/skill-snapshot/`，尚未修改原资源。计划保留领域逻辑与原skill名称，统一SKILL输入为带block_id的PDF原文块，工具search/read/reference，最终finish/items/relations；替换旧Markdown输出模板为动态条目及每行引用，格式大纲模块改PDF锚点，保留逻辑标/三级层级/目录排除，不再调用DOCX工具。
- 为避免已知冲突继续消耗本地模型，已通过API取消**本次样本报告5**，来源和索引保持就绪。下一轮先查询确认取消状态；不要把它当作仍在正常等待的原任务。
- 可用 skill-creator 的双子代理评估旧/新版典型输入（项目基本信息、否决条款、格式大纲），但**最终仍以项目配置的真实qwen模型、真实报告13模块及浏览器引用为验收**，不能用Codex子代理输出替代应用链路。
- 最后全量后端仍为383 passed/5 skipped，工具会话50514已poll确认exit0。前端与浏览器结果同前。
- 下一轮可能需要更有效的LLM诊断：在应用调用层保存合成样本的原始响应到.tmp或增加安全阶段错误分类，而不是放宽引文校验。原始响应不可写成用户可见未经校验报告。


### 第21节续记：2026-10-06 Skill 适配、纠正与依赖中断

- 本轮属于实质进展，goal 仍 active，未提交。开始已读取本文件；继续使用 karpathy-guidelines 和 skill-creator。按后者明确的配对测试流程启动新版/旧版两个子代理，各自只读指定版本并写 `.tmp` 评估产物。第三个 grader 子代理因服务限流未执行，最终评分由主代理完整读取原始产物并逐项核验，不把它称为独立 grader 结果。
- 上次一次性适配脚本的13个 Skill 修改已审查并继续修正：统一 PDF block 输入与 search/read/reference/finish 协议；输出模板改为核对清单；多标段逐项引用；移除空反引号和旧 HTML 单元格指令；类别使用 category/lots，不自行默认 service；81份旧资源快照仍保留，不要重跑一次性转换脚本。
- 修正否决 Skill 缺失规则路径，及货物/服务 examples 把一般强制、星号、合格栏目直接当否决的问题。格式模块保留逻辑标、三级层级、独立附件，引用必须覆盖父子关系完整正文，目录只供导航；技术模块不再排除纯参数表，保留数值、单位、上下限、接口/标准/检测要求。
- 真实 qwen 诊断发现仅输出“需要读取补充通知”及“说明文字+JSON”的情况。新增 `InvalidModelOutput` 细分已收到的非法JSON；`json_completion` 对直接模型最多纠正两次。实际 RoutingModel 在换候选前先最多两次修改提示，仍计入原有6请求/600秒总预算；最终失败回到普通 ExtractionFailed，避免外围循环重置预算。连接、配置、权限和明确拒绝不进入格式纠正。已测试主模型纠正后不触碰不可用后备、纠正耗尽后换源、总预算不重置。
- 支持性校验现在最多反馈两次让 Agent 补读或修正无依据结论，仍受32轮动作上限；最终不支持仍保留 insufficient/unsupported，不自动视为事实。
- worker 修复“补跑本模块”顺带执行其它失败模块：只执行 pending 或中断遗留 running；未选中的 failed 和 completed 保留。新增真实 PostgreSQL 临时表集成用例，但本轮依赖断开，尚未跑该新增用例。
- 最新单元+契约测试 **365 passed、5 skipped**，此前383是上一轮含数据库的数量，不能沿用为本轮完整结果。路由最后15项专项通过，Ruff全src/tests和diff check通过。依赖分层5条通过（随后仅调整应用层内部代码和文档，没有跨层依赖）。前端本轮没改，没有重复跑前端历史76项。

#### 真实模型诊断与对照产物

- `.tmp/parse-skills-workspace/iteration-1/review.html` 由 skill-creator 自带 viewer生成，benchmark和grading完整；新旧静态测试均8/8。测试用同一8块/2来源的合成输入，覆盖项目概况、否决、格式。新版21条24引用；旧版22条40引用（含关系）。旧版依赖上级协议覆盖旧Markdown/DOCX规则，不说明原生兼容；单次静态Codex结果不能推断优劣，更不能代替真实应用链路。全程token/耗时工具没有提供，timing只记录部分观测83秒/136秒，不能做速度比较。
- `.tmp/probe-current-skill.py` 使用真实本地qwen与应用run_module，但原文是独立合成块，无数据库/应用调用账，仅作故障诊断。不能称它完成项目13报告。脚本参数为模块key，可选第二参数为输出后缀，避免覆盖旧尝试。
- `local-model-probe/attempt-2/result.json`：项目概况11项，134.3秒，全部supported；45日引用同时含主文件及补充通知，未混入合同模板。
- `local-model-probe/disqualified_items_parsing/result.json`：2项，183.4秒，全部supported；营业执照和2023年1月1日起2项业绩及合同/验收证明逐项保留；真实非法JSON两次被拒绝后经纠正继续。旧自然语言失败响应也保留。
- `local-model-probe/bid_format_outline_parsing/result.json`：8项，322.6秒，但**只有3项supported，5项unsupported**，还有培训附件被误归技术标。不能把模块正常结束当质量验收通过。已据此修改父子引用与独立附件规则，并加入支持性修正循环。
- 新格式诊断输出目录 `local-model-probe/bid_format_outline_parsing-revised/`，工具会话 **43715** 正在跑，最后已读两来源并继续生成。必须继续poll同一会话、检查最终8项及supported状态、附件归属，不要重复启动。该记录若有后续结果，以后文为准。

#### 当前服务与阻塞

- 本轮开始API、worker、beat、前端、llama均已停止，Ollama11434仍在。已用既有脚本启动后端：API父10764、worker父16648、beat父18236，实际身份须实时核验；这些进程在后续代码修改前启动，待依赖恢复后需加载本轮最终代码。
- 按 `.tmp/tender-flow-check/llama-restart.json` 原参数重启llama，PID当时14420；**未改原256000上下文/4槽/Q8参数**，约65秒加载，当前本地模型可用。前端没有重启。
- 依赖地址 **172.29.199.222** 当前不能正常响应：PostgreSQL连接被服务器关闭，Redis关闭或超时，MinerU/Gotenberg HTTP超时或无响应；TCP能连接不代表服务可用。API health200但报告查询500。重测证据 `.tmp/tender-flow-check/dependency-status-20261006.json`，API/worker日志`.tmp/logs/`。本机有Meta网卡，未擅自改VPN/路由或依赖地址。
- 已异步询问用户该服务器当前地址或是否需先启动，尚未答复。没有创建新报告、没有重复上传。报告5最后已知状态是上轮取消，**本轮因数据库断开无法重新核实**。项目13/集合6/参考库7/source9、11、12均应继续复用。
- 下一步：完成当前格式诊断；依赖恢复后实时核验任务与服务、加载新版后端；确认报告5终态再创建新报告保存state；验收13模块报告、所有引用、30→45日关系与项目三年/历史五年隔离；真实问答和浏览器完整报告/两文件/移动端定位；新增重试集成与最终必要测试。目标尚未完成，不能调用complete，也不要自动提交。


#### 2026-10-06 本轮结束前的最后核验

- 格式重测会话43715已exit0，191.5秒生成8项，全部引用来自格式正文，层级和父路径大体修正；但**不能宣布质量通过**：技术标text仍说包含培训附件，而培训条目的cells写独立章节、text又称技术标附件，且层级写0。`supported` 全true不足以证明语义正确。
- 已加强 `verify_items` 提示，要求同时核对title/text/cells的一致性及父子依据；关系校验文本补入scope。用上述真实结果再次独立调用本地模型，会话2860已exit0，仍把8项全部判supported。结果保留为 `bid_format_outline_parsing-revised/verification-recheck.json`。这个模型支持性判断未发现已知矛盾，后续必须解决或保留明确待复核，不能靠绿色状态作为通过证据；不要只反复加提示然后宣称成功。
- 当前没有仍运行的本轮模型诊断会话。主模型进程仍可用；未创建新数据库报告。
- 最后后端单元/契约仍365通过、5跳过，Ruff全src/tests和diff check通过。数据库新增用例未运行；前端和浏览器没有在依赖断开下冒充成功。
- 为判断172.29地址是否是重启后变化的本机虚拟机，尝试只读Get-VM/Get-VMNetworkAdapter，OS明确拒绝权限；未提权、未换路径绕过、未改网络。用户关于依赖服务器的澄清问题仍待回答。
- 后续优先：确认依赖地址/启动状态恢复全应用验收；并针对格式的结构化父路径、正文和relations一致性设计可靠验证/纠正，真实回归不能只数条目或看supported布尔值。新规则资源、路由及worker最终变更仍需重启服务加载。

#### 2026-10-06 续记：格式节点结构与独立材料清点

- 上述节点正文、cells、relations冲突已有结构性修复：新增 `application/analysis_outline.py`。格式Agent仅提交 `outline_nodes`，字段为id/name/node_type/parent_id/requirements/citations，程序从唯一parent_id生成动态条目、完整父路径、层级及关系。逻辑标根0级、独立材料1级、材料最多三级；拒绝重复ID、缺失父级、循环、无依据名称/要求及缺少完整父路径引文。分类/归属判断仍经支持性检查，不能将结构合法当语义正确。
- 快照新增 `__outline_contract__`；历史无此键继续items协议。前端/API不换数据模型、不新增迁移。格式SKILL和引用规则已同步。新增 `test_analysis_outline.py`；支持性修正要求完整返回，防止只修一项时丢其他节点。
- 最初 `missing_outline_nodes` 让模型对照已有节点查漏。诊断会话18011已exit0，374.7秒，6项全部supported，但仍漏“营业执照复印件”和“业绩证明”。真实响应7显示完整性检查也漏判，不能视为通过，产物 `bid_format_outline_parsing-nodes-coverage/`。
- 据此改为从原文独立提取 `outline_inventory`，不让模型看到已有节点及requirements。程序按名称+引用块比较；父节点requirements里提及不能抵作独立节点。已检查块缓存，新读块增补，纠正不能靠下一次模型忘掉遗漏而通过。最多两次补全，仍漏则模块失败。成功执行记录包含最终节点和材料清单。未实施稀疏更新、自动扩展引文或预读候选。
- 独立清点诊断24733已exit0，实际发现上述两个子材料，产物 `.tmp/parse-skills-workspace/local-model-probe/independent-inventory/`。清点未列逻辑标容器本身，不能把它称为完整覆盖所有类型；主节点列表仍有两容器，实际复核不能只看布尔值。
- **当前完整模块诊断会话74907仍在运行**：`.tmp/probe-current-skill.py bid_format_outline_parsing independent-inventory`，输出 `.tmp/parse-skills-workspace/local-model-probe/bid_format_outline_parsing-independent-inventory/`。须继续poll并核验8个节点、层级、独立附件、引用和支持性；不要启动重复诊断。本段结果以之后续记为准。
- 最新单元/契约378通过、5跳过，Ruff全src/tests通过，diff check仅原有行尾提醒。新增测试覆盖来源区分、增量清点、清点缓存、编造/越界引用、补全成功或耗尽失败。数据库集成fixture已适配outline_inventory，但数据库集成未跑；前端本轮无改动，无需重复历史测试。
- 10:56复测依赖仍不可用：PostgreSQL OperationalError，Redis TimeoutError，Gotenberg/MinerU ReadTimeout；API `/api/v1/healthz`200，报告 `/api/v1/analysis/reports/5`在5秒只读探测中超时。不能说本轮确认报告5取消。安全复测脚本 `.tmp/check-flow-dependencies.py`，结果 `dependency-status-latest.json`，不输出凭据。最初写错健康/报告URL导致404，已修正后重测，最终文件是正确路径结果。
- 原验收项目13、自有集合6、独立库7及source9/11/12继续复用，未上传或创建新报告。用户关于服务器地址/启动状态的问题仍待答复，不重复询问。API/worker/beat需在依赖恢复后核验身份并加载最终代码。

#### 2026-10-06 格式诊断后续修复（本段更新前述运行状态）

- 会话74907已失败退出：314.4秒，模型两次仍返回6节点，独立清单门禁正确拒绝残缺结果。`independent-inventory`目录中的完整模块复测与独立清点目录不是同一个产物；前者失败，后者确实识别出遗漏。
- 补全改为单独的精简生成步骤：仅提交新增outline_nodes，程序和原节点合并，拒绝重复旧ID及不合法证据/层级。最多两次且计入32步。trace包含phase=outline_completion、真实新增响应、合并ID及最终清单；已有节点不能被新增步骤覆盖或删除。新增重复ID拒绝后第二次纠正测试。
- `sparse-completion`会话85808在持续重复同一拼接引文错误后停止；停止前核验了自有Python PID26592/27412及完整命令。错误定位现在包含节点ID和名称。`precise-correction`会话10146也反复在同两处引文/父路径错误间切换，核验自有PID27244/7708后停止。两者均不是因观察超时而重启，不得称质量通过。
- 格式模型输入现只带最近一份finish草稿及完整工具读取记录，历史错误草稿仍完整保留在审计trace；新用例确认多次纠正不会删除审计也不会把旧稿全部重喂。
- `compact-correction`会话56047已结束（exit1），读到独立清点并进入补全；原始响应留存，不能声称该会话完成八节点。随后调整证据汇集规则：每节点只给自己的合法引文，程序沿唯一父路径汇集已经校验过的祖先引文，不要求模型重复抄写祖先引文。**不再要求子节点自己重复提供包含所有祖先名称的引文**；已改格式协议、输出模板和规则。没有自动扩展原文、替换坏引文或根据相邻位置猜父级，父子归属仍是judgment并接受支持性校验。
- 当前唯一待续诊断是会话 **7220**：`.tmp/probe-current-skill.py bid_format_outline_parsing lineage-evidence`，目录 `local-model-probe/bid_format_outline_parsing-lineage-evidence/`。必须继续poll同一会话。最终用 `.tmp/check-outline-probe.py lineage-evidence`核对8名称、层级、5条包含关系、正文引用、独立培训附件及补全轨迹；该脚本需要result.json，失败情况下不要伪造结果。
- 小工具 `.tmp/inspect-outline-probe.py <后缀>`可检查每次响应的JSON及节点校验错误，保留全部原始response JSON，不输出模型服务凭据。
- 最近全单元/契约381通过、5跳过，Ruff全src/tests通过；之后仅改祖先引用汇集，专项34通过、Ruff通过，最终仍需确认本轮完整检查。前端本轮未变。数据库仍不可用，最新依赖证据10:56记录，不能沿用旧383含数据库的结果。

#### 2026-10-06 依赖恢复，已重新开始真实报告（必须优先续看此段）

- 11:21 Redis/Gotenberg恢复；随后PostgreSQL实际SELECT 1成功，报告5重新读取确认为canceled。3份来源source9/11/12仍全部解析和索引completed。MinerU8000当时仍ConnectError，需继续核验恢复情况；不要重传已有文件。
- 回放旧合法六节点草稿的局部诊断 `.tmp/probe-outline-completion.py` 会话69421已完成：153.0秒，真实模型完成独立清点、新增节点和支持性检查，得到8节点5关系；`.tmp/check-outline-probe.py replayed-draft-completion`29项全部通过。产物目录 `bid_format_outline_parsing-replayed-draft-completion/`有mode.json明确前三次为回放，不可称全程自主生成通过。此前完整lineage-evidence会话7220被停止，停止时最新响应已到清点阶段，没有完整result；不能当完成或正式失败终态。
- 通过已核验身份的启动脚本加载最终代码：API父6740、worker父24820、beat父28052，实际子PID需实时查。启动脚本会话98474已exit0。llama7896没重启、参数没改。
- **已创建真实报告6**（项目13，完整两文件，无partial），state.json已更新并保留旧报告4/5。最后状态running，全文已扫描6/20块，尚无模块。续用 `.tmp/tender-flow-check.py status`，禁止重复创建新报告或重跑start。
- 最新完整后端 `TENDER_RUN_DB_TESTS=1 pytest -q`：**410 passed、5 skipped**，会话45289已exit0，包含新增选中模块重试及节点协议集成用例；Ruff和diff check通过。单元/契约381+5是其中子集，不重复累计。
- 前端启动的Start-Process命令曾被工具策略拦截，未启动；已用直接工具会话运行 `pnpm --dir apps/web dev` 成功，**会话21037**，localhost:4400已Ready，API_PROXY_TARGET=127.0.0.1:8300。不要结束此会话或重复启动。没有改用户的本地启动指南。
- 当前无活跃本地模型诊断，模型算力供真实报告6使用。接下来继续13模块实际报告、每条引用与30→45日关系/三年与历史五年隔离；真实问答和完整报告浏览器验收。先更新浏览器脚本，必须明确报告completed才开始最终验收，不能沿用旧脚本跳过报告分支的7项通过冒充完成。
- 目标仍active，依赖恢复后不能按旧阻塞记录调用blocked；尚未满足完整验收，不得complete，不自动提交。

#### 2026-10-06 11:47 最新：真实报告7运行中，报告6因质量问题取消

- 全部依赖已恢复。MinerU正确健康地址为 `/v1/health`，先前探测误用 `/health`恢复后显示404，现已修复`.tmp/check-flow-dependencies.py`；11:27全部200/协议成功，不能再沿用早期离线状态。真实报告5已确认canceled。
- 报告6完成扫描后暴露质量缺口：基本信息10条没有预算、限价、补充通知45日，交货期仍写30日；否决只提营业执照，漏超限价。真实DB trace证明基本信息未读c2预算和source11，否决读到c7却未提取。不能把completed/supported当完整通过。
- 已通过API取消验收报告6并保留历史；`.tmp/tender-flow-check/report-6-quality-review.json`及`modules-with-trace.json`保留结果。最后确认canceled，已完成10个模块，后续没继续。真实调用账可用`GET /api/v1/llm/calls?feature_key=analysis`查询；`model-probe-ledger.py`是历史一次性修改脚本，**不要执行**。
- 新增普通模块覆盖策略，快照键`__coverage_contract__`：每份来源首批至多12块加入必读候选（仍须实际工具读取，不是自动宣称已读）。对结束时未被items引用的候选按6块独立补漏；每块必须被结果引用或列入unrelated_block_ids。结构/引文/遗漏分类可纠正两次，随后失败。补漏草稿和原草稿合并后统一支持性校验；纠正反馈包含合并草稿，完整trace保存candidate_completion阶段及最终接受草稿。历史无该快照键仍走历史规则。
- 新测试覆盖扫描未分配补充文件时仍须读、已读却漏提的限价否决独立补回、静默遗漏候选被拒绝。集成FixtureModel适配新协议。**最新完整含DB测试413 passed、5 skipped，最后测试已exit0**；Ruff全src/tests及diff check通过。前端产品代码本轮没改。
- 局部真实原文诊断会话23941已exit0：`.tmp/probe-live-candidate-completion.py`复用报告6原文及旧草稿，只调用补漏/验证、不写业务结果。项目概况补回预算80万、限价78万、45日且supported；“项目名称与编号”混同样本编号被判unsupported。否决补回超限价条款且supported。产物`.tmp/tender-flow-check/candidate-completion-probe/`。这不是新报告最终结果，不可代替13模块验收。
- **当前真实报告为7**，已写state.json（previous_reports含4/5/6）。最新代码已加载：API父25644、worker父19692、beat父25700，需实时核验子PID。llama7896参数保持原样，Ollama11434工作；前端会话21037仍运行在localhost:4400。没有活跃的本轮模型诊断。
- 独立参考库真实问答 **answer1** 已completed，state.reference_answer保存ID。两条supported：历史质保五年；参考不能替代本项目要求。snapshot.mode=hybrid、4个检索块、1024维、source12，graph_used=false（独立参考问答没有报告图谱，正常）。原始结果`reference-answer.json`；脚本`.tmp/check-reference-answer.py`只在state无ID时创建，后续仅轮询，勿重复创建。
- 浏览器脚本`.tmp/tender-flow-browser.mjs`已增强：开始就要求真实报告+13模块completed，不允许跳过报告分支；桌面1440及390/320三种宽度，主文件→补充通知→主文件来回切换并检查PDF/引文/高亮；最后通过真实页面提交项目问题，核对45日、当前三年和历史五年及独立来源，保存project-answer.json和state.project_answer。当前只通过node --check，**尚未执行增强版最终浏览器检查**，须等报告7内容验收合格后运行。浏览器引用摘录可能被resolve接口扩成完整块，需要按实际接口调整预期，不能将测试预期问题当UI故障。
- 下一步：持续读取`.tmp/tender-flow-check.py status`看报告7，不创建重复报告；逐模块核验预算/限价/45日/三年/技术参数/否决完整性以及引用。源读取及补漏能降低遗漏，仍不能直接保证质量。必要时据真实错误修复并补跑，先保留已完成模块；执行增强浏览器及项目问答，逐条resolve引用，核对独立资料隔离和图谱关系；最后更新设计14和本交接，真正全部通过后才goal complete。目标仍active，不blocked、不提交。

#### 2026-10-06 12:09 真实报告7继续执行

- 已完成项目概况16项、否决2项，预算80万元/限价78万元/交货期30→45日及两项否决已逐项核对，均有本项目引文。独立库问答1另经8项引用与来源核对通过。
- 商务模块失败：调用459本地模型耗尽4096个生成token后返回空正文，后备模型2随后两次连接超时。其余模块继续运行，最新技术模块running。不要取消报告、重复上传或重建报告；观察会话53461仍在运行。
- 已修复适配器在JSON模式收到空正文时抛InvalidModelOutput，进入既有最多两次格式纠正；普通文本空正文仍为ExtractionFailed，不将reasoning_content当结果。38项模型适配/路由专项和Ruff通过。**此修复尚未加载到运行服务，必须等报告7终态后重启再单独补跑失败模块。** 其余服务及llama参数没有改动。
- `.tmp/check-live-report.py`增补商务/技术/评分/开标/保证金/封装/报价/业绩/人员的实际样本条件核对，`--brief`只打印摘要，完整review始终存于report-quality-checks.json。最终仍用`--final`。
- 浏览器脚本新增逐项进度打印、首次问答轮询即记录ID、已有project_answer则拒绝重复提交；目前只通过语法检查，仍须等待报告合格后执行。项目问答尚未创建。

#### 2026-10-06 12:23 范围调整与桌面预检

- 用户明确“不需要考虑手机端”。后续验收只做桌面，不再做390/320px检查；旧移动端记录仅保留历史，不是当前交付门槛。`.tmp/tender-flow-browser.mjs`已只保留1440px。
- 真实报告7现已完成4模块：概况16项、否决2项、技术5项、评分3项；技术设备/数量/IPv6/双电源/2小时及评分30/50/20与业绩条件均已核对，无unsupported。商务failed等待终态后补跑；开标running，其余待执行。观察会话53461持续运行。
- 桌面预检（显式`--preflight`，不提交问答、不当最终验收）第二次14项通过，主文件→补充通知→主文件的PDF、引文、高亮、无溢出均通过；关键截图已人工查看。产物`browser-preflight/`，第一轮失败详情因第二轮重写checks，原因已记录如下。
- 第一轮独立库搜索前端代理报ECONNRESET/500；随后直接后端6.94秒返回正确hybrid结果，再次浏览器成功。不能断言已确定首次断开原因；同步向量长等待仍是实际暴露的薄弱点。
- `knowledge_retrieval.py`增加可选embedding_timeout，搜索API传15秒；超时取消向量调用、关闭客户端，回退带引用的全文结果与warning。后台问答不传此参数，保持原预算。KnowledgeCollectionDetail展示warning。29项知识专项、Ruff、前端typecheck通过。此改动和空正文InvalidModelOutput修复均尚未重启服务加载。
- 空正文修复后的完整后端416 passed、5 skipped已exit0（含DB），Ruff全量及diff check通过；搜索等待修复是在此之后新增1项测试，最终应再次覆盖新增集成检查。尚未创建项目问答、未提交代码。

## 22. 用户纠正架构：采用 DeepAgents（2026-10-06 19:10，当前最高优先级）

- 用户明确否定现有“全文扫描分派＋每模块必读文件首批段落＋串行运行”形式。要求每个解析模块一个独立subagent，自主从文档与知识库检索，去重后综合分析，可配置subagent并发数。已明确选择 **DeepAgents**，不再询问LangGraph选型。
- 用户进一步要求权限、重试、上下文管理、运行管理等稳定性控制，不能只调用框架入口。已确认方向：项目/关联库权限在工具层强制、只读Skill快照、禁任意磁盘/Shell/网络、独立上下文、去重与按需阅读、有界预算/重试、任务取消和恢复、跨报告并发控制、可观察执行记录。
- 当前原实现是自写Python JSON工具循环，FastAPI/Celery调度，OpenAI兼容适配调用本地Qwen/llama.cpp；并无DeepAgents/LangGraph运行时。已向用户明确说明，不可把旧13模块报告验收当新架构交付。
- 19:06现场核验：API8300、worker、beat、前端4400、llama7896都已停止，工具会话53461/21037/37528等已失效；仅Ollama11434存在，PID17600。不是本轮主动停止的。数据库也OperationalError，取消报告7的API及精确数据库状态更新均未成功，**报告7取消未确认**。后续恢复依赖时，先取消旧报告7再启动worker，禁止自动续跑旧方案。
- 旧报告7最后已知完成5模块（概况16、否决2、技术5、评分3、开标4），商务failed，保证金running。旧资料项目13/库6与7/source9/11/12仍需复用，不重新上传。
- 用户早先明确“不需要考虑手机端”，后续只验收桌面。旧桌面预检14项通过，不等于新架构通过。
- 旧代码最后完整检查：后端417 passed、5 skipped（含DB），Ruff通过；前端76测试、typecheck通过。生产build会话37528在用户间隔后失效，未取得最终退出结果，不能称最后build已通过。
- 新增但尚未加载运行服务的旧流程补丁仍保留：空JSON正文进入有限纠正；同步知识搜索向量15秒超时回退全文且UI显示warning。新增架构应复用稳定的上传/索引/引用/模型管理，不重复实现。
- 已实际获取官方DeepAgents overview/subagents/skills/models文档；PyPI当前版本0.7.22。开始用uv添加固定版本依赖。已委派只读研究代理`deepagents_research`核实当前真实API，不写仓库、不跑模型。
- Goal仍active，禁止complete/blocked/提交。后续应真正实现并验收DeepAgents模块subagent＋权限检索＋去重综合＋并发与生命周期管理；原报告7的完成已不再是目标。

## 23. 新会话接手说明（2026-10-07，交接整理）

> 本节用于让全新会话在不读旧对话的情况下继续任务。开始前先读 AGENTS.md 与本文件第 22、23 节，本节优先于更早的历史状态。

### 23.1 一句话状态

目标是重新打通标书解析流程（知识库构建 + Agent/Skill 解析招标文件），框架已由用户明确选定为 **DeepAgents**。运行时核心构件已写好并通过 20 项新架构专项测试，但**尚未接入 worker / API / 前端**，没有任何真实端到端验收；goal 仍 active，全部改动未提交。

### 23.2 用户硬性要求（不可偏离）

- 每个解析模块一个独立 subagent；subagent 并发数必须可配置，且是**跨报告的硬配额**，不能只有每报告 Semaphore。
- 子 Agent 自主按需检索项目文档 + 关联知识库，去重后综合分析。禁止沿用“全文扫描分派 + 每模块必读首批段落 + 串行执行”的旧形式。
- 稳定性控制是需求本身：工具层强制权限（支持动态撤销）、只读 Skill 快照、禁止任意 FS/Shell/网络、有界重试与预算（重试和摘要调用都计入）、上下文压缩、checkpoint 恢复、失败模块补跑、幂等、租约、审计与状态查询。
- 不需要手机端，只验收桌面端。
- 禁止自动提交；确有提交时用中文、不带作者。
- 项目约定：UTF-8 读写、PowerShell、JS 用 pnpm、Python 用 uv、注释与文档优先中文。

### 23.3 仓库状态（务必先看）

- HEAD：`2eb51b7 文档：补记分批提交结果`。工作区共 90 个变更：81 个已跟踪文件被修改、9 个未跟踪新文件；**全部未提交，都是本轮成果，不要回滚、不要擅自提交**。
- 本阶段新增且未跟踪的核心文件：
  - `apps/api/src/tender/application/analysis_research.py`：权限、去重、预算与证据会话。
  - `apps/api/src/tender/application/deep_analysis.py`：DeepAgents 模块子图桥接（RoutedAgentModel / build_module_agent / invoke_module）。
  - `apps/api/src/tender/application/analysis_outline.py`：格式大纲模块结果校验。
  - `apps/api/src/tender/adapters/agent_chat.py`：LangChain 原生工具消息适配。
  - 对应测试：`apps/api/tests/unit/application/test_analysis_research.py`、`test_deep_analysis.py`、`test_analysis_outline.py`、`apps/api/tests/unit/adapters/test_agent_chat.py`。
- 未跟踪的 `.claude/` 不属于本次交付，不要提交。
- 依赖已在 `apps/api/pyproject.toml` 和 `uv.lock` 落地并安装完成：`deepagents==0.7.22`、`langchain-openai>=1.1,<2`、`langgraph-checkpoint-postgres>=3,<4`、`psycopg-pool>=3.2,<4`。不要重复安装。

### 23.4 已实现并验证的部分

- `analysis_research.py`：默认预算（模型调用 32 / 工具 48 / 证据 160 块 / 900 秒 / 上下文 24000 token / 输出 4096）；显式项目与关联库范围；每次工具操作前后及检索完成后复核授权；越权与错误批次原子拒绝；同 source+run+element 及规范化正文去重、同文不同来源保留；`read_source` 支持压缩后补读；async 锁计数；可导出 seen/events/tool_calls 到 checkpoint。
- `agent_chat.py` + `openai_chat.py`/`llm_routing.py` 的 `chat()`：全部 SDK `max_retries=0`，重试统一走项目既有路由；工具消息与 `tool_call_id` 完整往返；usage 落账；支持 429 Retry-After；识别拒绝响应；关闭客户端；强制关闭 LangSmith tracing，避免标书内容外发。
- `deep_analysis.py`：真实 DeepAgents 图（`StateBackend`、只读 Skill 与历史文件的 `FilesystemMiddleware`、80% 阈值的 `SummarizationMiddleware`、负责授权/工具预算/checkpoint 的 `ResearchMiddleware`）；权限首条匹配并兜底 deny；关闭自动 general-purpose subagent；`submit_analysis` 复用 `_module_result`/`outline_result` 证据校验并限制 3 次纠正；`invoke_module` 通过 `aget_state` 从框架 checkpoint 恢复，已完成线程不会重跑。
- 2026-10-07 复跑测试：
  - `uv run pytest tests/unit/adapters/test_agent_chat.py tests/unit/application/test_analysis_research.py tests/unit/application/test_deep_analysis.py -q` → **11 passed**。
  - `uv run pytest tests/unit/application/test_analysis_outline.py -q` → **9 passed**。
- 上述只覆盖新构件单元行为。旧链路完整结果为后端 417 passed / 5 skipped、前端 76 测试 + typecheck（旧架构），**新增代码后尚未重跑全套**。

### 23.5 尚未完成（新会话主要工作，建议按序）

1. 把 `deep_analysis.py` 接入 worker：新报告走模块子图；历史报告按旧快照兼容；移除新报告对旧 scan/coverage 契约的依赖。
2. 新增迁移 `0008`（不要改已应用的 0005/0007）：建 `agent_runtime` schema、受控初始化 checkpoint 表（`AsyncPostgresSaver.setup()`）、模块运行状态/预算/审计表。
3. 生命周期与配额：跨报告硬并发配额（配置项）、真实请求累计预算（含重试与摘要调用）、工具次数、总时长、取消检查、租约恢复、失败模块补跑、幂等与状态查询 API。
4. 权限与上下文收尾：动态撤销在工具层端到端生效；摘要只写 `/conversation_history/**`；证据独立保存，摘要不得成为引用来源。
5. 编排与汇总：确定性控制器保证 13 个模块都被调度，日志能证明每个模块是独立子 Agent；主汇总去重、冲突保留双方依据、核对跨文件修订。
6. 适配 API/Skill/前端（桌面端），并创建 `docs/设计/16-DeepAgents标书分析运行时.md`（当前不存在）。
7. 新架构专项测试：故障恢复、越权、并发、上下文与引用。
8. 依赖恢复后：**先取消旧报告 7，再启动 worker**，防止旧方案自动续跑；随后用既有资料做真实模型与桌面浏览器最终验收，不重新上传文件。

### 23.6 环境与验收数据（2026-10-07 核查）

- 本机服务：API 8300、worker、beat、前端 4400、llama.cpp 7896 均未运行；仅 Ollama 11434 在监听（PID 16244，PID 会变）。
- 远端依赖 `172.29.199.222`：Postgres 5432 / Redis 6379 / MinIO 9000 / Gotenberg 3456 / MinerU 8000 五个端口 TCP 均可达。此前出现过“TCP 可达但服务不健康”，需用真实请求复核；本轮未做 PostgreSQL 实际查询。
- 旧报告 7：取消**未确认**。最后已知完成模块为概况 16、否决 2、技术 5、评分 3、开标 4，商务 failed，保证金 running。`.tmp/tender-flow-check/state.json` 中 `report.status=waiting` 是创建时的旧值，不代表实时状态。
- 复用数据（勿重传）：项目 13、自有库 6；主文件 source9 `采购招标文件.docx`、source11 `交货期补充通知.pdf`；独立参考库 7 / 知识项目 14 / source12 `设备保修参考.pdf`；参考问答 answer1 已通过，项目问答未创建。
- 验收样本关键事实：预算 80 万、限价 78 万；交货期主文件 30 日、补充文件 45 日；本项目质保三年，参考历史五年不可替代；10 台交换机 / IPv6 / 双电源；故障响应 ≤2 小时；付款验收 90%、余款质保期满；业绩 2023-01-01 以来每项 10 分封顶 20 分、需合同复印件；项目负责人 1 名、劳动合同、不要求特定职称；四种格式材料为投标函、报价明细表、营业执照、技术响应表。

### 23.7 工具与坑

- 旧验收脚本 `.tmp/tender-flow-browser.mjs`（仅 1440px，`--preflight` 不创建问答）与 `.tmp/check-live-report.py`（`--brief`/`--final`）需要适配新架构后才能作为最终验收依据。
- 不要用旧报告 7 的完成度充当新架构验收；新架构验收标准是：13 个模块各自独立 subagent、自主检索去重、权限/预算/恢复生效、桌面浏览器引用核对通过。
- 不要修改用户既有的 `本地启动指南.md` 改动；上下文超过 80% 自行压缩。

### 23.8 新会话可直接粘贴的提示词

```text
继续 AI-Tender 的 DeepAgents 标书解析重构。工作目录 G:\aicode\AI-tender。
先按 AGENTS.md 读取 HANDOOFF.md 第 22、23 节，并以第 23 节为准。

goal 仍 active：每个解析模块一个独立 DeepAgents subagent、并发可配（跨报告硬配额），
Agent 自主检索项目文档与知识库、去重后综合分析；落实权限、重试、预算、上下文压缩、
checkpoint 恢复、失败补跑与运行管理。禁止沿用旧的全文扫描分派形式。

现状：analysis_research.py、deep_analysis.py、analysis_outline.py、agent_chat.py 已实现，
4 个专项测试文件共 20 项通过；但尚未接入 worker/API/前端，无真实端到端验收。
按第 23.5 节顺序继续：先把模块子图接入 worker 并新增迁移 0008，再做配额与生命周期、
汇总、文档、专项测试与真实验收。

约束：不提交代码；不重传项目 13 的资料；依赖恢复后先取消旧报告 7 再启动 worker；
只验收桌面端。
```

## 24. DeepAgents 接入与真实验收进行中（2026-10-07，本节更新第23节）

- 目标仍 active，所有改动未提交。已读取第22/23节并按23.5推进；没有使用 Codex 子代理。继续使用 UTF-8、PowerShell、pnpm/uv；不改用户本地启动指南、不重传项目13资料，只验收桌面。
- 已新增 `0008_deepagents_runtime.py` 并应用到实际数据库（0005/0007未改）：报告 runtime_version/runtime_settings/reference_snapshot/summary，agent_module_run、agent_run_event 和 agent_runtime schema；配置中心增加 analysis.max_inflight（默认2）、请求/工具/时间/上下文/输出预算。
- `application/agent_checkpoints.py` 提供显式初始化命令 `uv run python -m tender.application.agent_checkpoints`，AsyncPostgresSaver.setup 已执行，4张 checkpoint 表在 agent_runtime 内。Windows 用 SelectorEventLoop，worker 不隐式建表。
- `application/agent_runtime.py` 已实现公司范围跨报告/跨进程配额、独立 NullPool 会话锁、owner fencing、租约、动态关联/资料批次复核、每实际请求/工具预算和用量审计。恢复保留 deadline/预算/证据，未回传模型请求标记 unknown。仍持锁时不能因租约过期被抢占；配置降低后排空再接新任务。
- `worker/deep_analysis.py` 先持久创建全部13模块，再并发调度独立 DeepAgents 图，真实 PostgreSQL checkpoint、原生工具、校验证据、单模块失败隔离、确定性汇总等价断言。`worker/knowledge.py` 按 runtime_version 分流，新报告不经过 scan_document；历史 legacy 保留。
- API新报告固定运行时/配置/参考库快照；详情暴露各模块 runs，不暴露原始 state/trace；新增 `/analysis/reports/{report_id}/runs/{run_id}/events` 审计分页。补跑新 attempt 保留旧记录，并发重复补跑拒绝。报告结论和summary按实时知识库关联过滤。
- 项目 Skill 全部切换为原生检索/submit_analysis，领域规则保留；general reduce_strategy 的最后一处旧扫描说明也已移除。报告9的既有快照不回写，system契约一直禁止扫描分派。
- 桌面 ProjectAnalysis 展示13专题进度、各attempt用量/时限/错误，综合条目折叠区与失败补跑。新增设计文档 `docs/设计/16-DeepAgents标书分析运行时.md`、接口文档及DDL契约映射。
- 测试：一轮完整后端 **440 passed / 6 skipped**（TENDER_RUN_DB_TESTS=1）；前端 **76 passed**、typecheck和生产build通过；Ruff和diff check通过（CRLF提示不是错误）。此后新增了坏输出token记账/限流冷却/恢复unknown和预算提示，相关专项已通过，最终需覆盖最新增量。
- 新增集成 `tests/integration/test_deepagents_runtime.py`：独立随机schema，真实多连接配额/过期不抢占/恢复预算证据/13真实子图+Postgres checkpoint/补跑/动态撤销。原 `test_llm_management.py` 重放迁移时将显式agent_runtime schema重命名到测试空间，避免触碰业务checkpoint；原知识集成测试显式legacy以继续验证历史兼容。
- 真实报告7现场为partial，已按用户要求精确更新为 **canceled**，查询确认后才启动worker。没有活动旧报告。
- 新架构真实报告 **9**，项目13、source9/11、参考库7/source12。勿重复创建。状态文件 `.tmp/deep-flow-state.json`；完整验收资料 `.tmp/deep-flow-check/state.json`。当前实际首选模型17/qwen3.8-flash-next-262k（https://x666.me/v1），其次16/本地qwen3.5-9b，再2/glm-5.3-flash。沿用用户配置，没有调整模型绑定。
- 真实9已验证同时2个独立模块在跑，各自检索项目和参考库、产生混合检索/去重证据；但尚无完整质量验收。首选模型出现429及空响应，后备本地模型较慢。修复路由429后短暂冷却、坏输出保留已知token用量；增加每轮剩余预算与连续无新增证据提示，避免无限复读。
- 已进行受控后端重启：重启前快照 `.tmp/deep-flow-check/before-worker-restart.json`；停止API/worker/beat后确认运行槽锁为0，只把报告9 lease调为过期，以立即触发自动恢复。**需继续确认9的resumed事件、原thread/计数不重置、以及unknown请求记录**。首次起始约10:22，模块总时限900秒不会因重启延长，若耗尽需等报告终态补跑失败模块。
- 最后启动：API父20920、worker父3976、beat等待启动脚本会话92915的最终结果。前端session13847，localhost:4400；llama PID9804，原参数原路径启动（记录仍在`.tmp/tender-flow-check/llama-restart.json`）；Ollama11434继续运行。PID需现场核验。启动脚本为用户原有 scripts/start-backend.ps1，未改。
- 新验收脚本 `.tmp/check-deep-report.py --brief/--final` 和 `.tmp/deep-flow-browser.mjs --preflight`/无参数。仅桌面1440；浏览器无参数会提交一次项目问答并记录ID，已有ID时拒绝重复。旧脚本/旧报告结果没有覆盖。**新浏览器脚本尚未执行**，必须等9有source9和11有效引用；最终需13模块全部完成且关键事实合格。
- 下一步：确认重启恢复→观察/修复真实9失败模块（保留已完成模块）→逐模块事实与引用核对→桌面与真实项目问答→核对运行记录/权限/预算/恢复证据→最终检查文档与测试。未达到真实验收前不能goal complete。


### 24.1 真实验收追加修复（2026-10-07 10:45前后）

- 受控重启恢复已验证：`.tmp/deep-flow-check/checkpoint-recovery.json` 13项线程一致/计数不倒退通过，实际有 resumed 与 requests_unknown 事件。
- 原概况/否决模块到32次请求预算后 failed，否决保留已提交draft；业务补跑需保留旧记录。发现 LangChain 默认缓存 httpx 客户端，模块关闭后其它模块会复用已关闭连接报 RuntimeError；AgentChat已显式创建独立异步/同步客户端，隔离测试通过。
- 同报告恢复优先旧线程，prepare_report将失去会话锁的旧running重新显示pending，避免UI显示4个running而实际只有2槽。该修复通过5项运行时DB集成；不要以running状态行数代替pg_locks真实占用数。
- 商务模块曾completed12项，但人工核对发现未证据化的质保起算/免责推断、缺失条款结论、单边修订引用、仅历史引用证明当前项目等，不能作为合格结果。已精确将商务模块及该attempt标为failed并记录quality_rejected，移除该模块已发布关系；旧items/state保留审计，没有人工改写答案。
- 新增 validate_project_claims：项目结论和参考建议必须有本项目引用；缺失/未约定推论只能写research_summary；跨文件修订同条目引双方。支持性verify_items强调禁止补造起算点、服务期间、范围和免责效果。支持性验证提前到 submit_analysis，在同一子图内反馈修正（最多3次）；worker仍复核恢复草稿。汇总排除failed模块。
- 补跑可以沿用已通过结构/引用校验的draft继续支持性验证，若新约束判定旧draft无效则重新检索；新attempt预算为0，旧账保留。原module验证未通过的新结果不能再只打supported就交付。
- 最后一轮相关图/DB专项 **13 passed**；HTTP适配/路由专项 **22 passed**；import-linter **5 kept / 0 broken**。最新质量约束之后应补最终完整测试，前端补跑未完成模块按钮也需要最后typecheck/build。
- 桌面运行管理脚本`.tmp/deep-runtime-ui.mjs` **6项通过**，截图`.tmp/deep-flow-check/runtime-desktop/`已人工查看；这是runtime-only，不是内容验收。原固定CDP端口9492/9494被Windows拒绝bind，脚本已改端口0并读取DevToolsActivePort，不能再使用旧固定端口版本。
- 最新后端启动父PID：API12648、worker19252、beat26272，启动会话19697。前端13847及llama9804未动。API/worker已加载最新配额恢复排序和内容校验。资料、报告仍为9，禁止重建报告/重传资料。尚无合格完整报告，项目问答未创建；目标仍active。

### 24.2 质量与协议追加修复（2026-10-07 11:15前后）

- 继续执行 goal，尚未真实验收完成。报价模块原completed结果经人工核对不合格（未划分标段/全项目范围、未明示税率与格式缺口、其它条目引用未覆盖当前断言）。已精确标记module61/run9为failed并写quality_rejected事件，删除其已发布关系；原items/state和旧账保留，未改写答案。拒绝快照在`.tmp/deep-flow-check/price-quality-rejected.json`。
- `verify_items(explain=True)`供DeepAgents使用：每批6项，先列无依据断言再给supported；即使supported=true，只要有无依据断言也判unsupported。校验输入不携带旧verification标签。具体原因反馈给submit_analysis纠正；legacy继续兼容原布尔协议。
- 原生工具schema增加CitationInput/ItemInput/RelationInput/OutlineInput的具体字段，避免list[dict]令模型猜测引用/节点格式。图测试包含非空条目落库前的引用校验。**该schema追加在最新服务重启后，需等首轮终态后重启加载，再补跑。**
- 生成提示要求正文直接依据原文、可选字段无依据则省略、每条引文覆盖自己的金额/数量/范围；扩充缺失断言拦截。补跑已质量拒绝的verified草稿不再复用；未完成支持性验证的草稿清items_verified后重新验证。
- 人员模块63/run11 completed，21次模型请求/17次工具，人工核对负责人1名、劳动合同、不要求特定职称均有相符引用。格式模块64/run12 completed，29次模型请求/19次工具，四个独立章节及引文已核对。补充发现仍running；不要用两个完成模块充当完整验收。
- 后端完整 **454 passed/6 skipped**（DB开启），随后原生schema增量图测试15通过；import-linter5 kept/0 broken。前端76测试、生产build通过；桌面runtime-only6项再次通过。原生schema后的运行时DB专项正在执行，需读取会话92044结果。
- 前端只展示completed模块的items/引用，避免补跑时把旧失败结果当有效结论；知识库设置文案已说明同时用于专题分析与问答。
- 本次重启前再次确认旧报告7 canceled、实际运行锁0，恢复9不重置线程/预算。最新服务父PID：API28008、worker23712、beat29584；前端和模型未动。仅在适当时机再重启加载最后schema，不频繁消耗在途请求。
- 新临时只读诊断`.tmp/inspect-deep-runtime.py [模块key片段]`，输出预算/状态及精简结果。继续用`.tmp/check-deep-report.py`和`.tmp/deep-flow-browser.mjs`，最终项目问答仍未创建。

### 24.3 上游故障与429补强（2026-10-07 11:30前后）

- 用户补充明确要求考虑上游偶发异常与429。已新增并应用0009_provider_cooldown（不修改已应用迁移），在llm_provider增加rate_limited_until；ProviderCooldown按供应商共享截止时间，跨模块/报告/worker/重启可见，GREATEST保证并发更新不会缩短冷却。
- RoutingModel先用未冷却供应商，全部冷却时等待最早恢复者，不为等待消耗请求预算，受模块心跳/取消/总时限约束。Retry-After支持秒数与HTTP日期，未提供默认30秒；同供应商切模型不能绕过冷却。408/500/502/503/504与连接超时沿用指数退避+抖动和有界请求记录；重试、切换、格式纠正仍计费计数。
- 真实上游异常进一步定位：报告9 general模块attempt2的三次submit_analysis实际args={}，每次completion_tokens恰好4096且reasoning约2000，供应商仍把finish_reason写成tool_calls。不是Agent没理解字段，而是输出被截断。诊断脚本`.tmp/inspect-deep-submissions.py <完整模块key>`通过图aget_state_history恢复DeltaChannel消息，不能只读saver.aget_tuple的channel_values（后者不含增量messages）。
- 新ModelOutputTruncated：finish_reason达到长度或缺必填参数且用量达到输出上限，适配器拒绝作为业务工具调用，保留usage并直接故障转移，不同额度下盲目重复格式纠正。非截断的必填工具参数缺失交路由有限纠正，不占业务提交三次校验机会。
- 最新完整后端 **471 passed/7 skipped**（DB开启）；随后新增HTTP-date专项，适配器14项通过。共享冷却真实独立连接/不缩短截止时间等集成和路由适配器专项38项已通过；Ruff通过。前端上轮76测试和build、runtime-only6项仍有效。
- 报告9首轮最终2模块完成（人员/格式已人工核对）。已通过API补跑其余11模块，产生attempt2，旧账保留；快照`.tmp/deep-flow-check/before-retry-2.json`。general attempt2已因上游空参数再次failed（当时尚未加载截断修复）；其余补跑中，最终还需补跑general。
- 11:30前后再次受控重启，先确认旧报告7 canceled且实际槽锁0，再过期报告9 lease，原attempt2线程/预算继续恢复。**当前服务已加载共享429冷却及输出截断修复**。API父PID21420、worker29788、beat6340，启动会话24133完成；前端4400和模型保持不变。
- 最新补跑情况需实时查询`.tmp/inspect-deep-runtime.py`：概况/否决运行，其余排队，人员/格式完成，general失败。所有未提交，不重传资料，项目问答仍未创建，goal仍active。
- 下一步：观察新适配是否将4096截断转到后备模型并完成报告9 → 按需要补跑失败模块 → 逐项人工核对并执行最终桌面和项目问答；真实验收尚未通过，不得complete。

### 24.4 分批提交与现场验证追加（2026-10-07 11:37前后）

- 为避免大结果一次挤入4096token导致上游截断，submit_analysis新增final（默认true）；普通模块可final=false分批校验并暂存2–3条，最后合并完成。staged_items/staged_relations在独立运行state保存，提示只补新增项。格式大纲需整体父子校验，禁止分批。
- 新attempt可携带已验证暂存成果和证据；清旧tool_results和invalid_submissions，旧attempt记录不变。partial暂存不显示为已完成报告。图分批验证+运行时21项通过，追加真实DB暂存补跑专项后7项通过。
- 实际调用日志已验证截断检测生效：否决attempt2在03:33:40 UTC的4096token输出被记为error/“模型输出达到token上限”，随后转到本地qwen3.5-9b，未继续消耗业务提交纠错机会。`.tmp/inspect-deep-calls.py`可查最近调用和共享冷却状态。
- 为加载分批提交，本轮最后重启API/worker/beat，旧7 canceled、槽锁0后原线程恢复9，未重置预算。最新父PID：API25292、worker27620、beat3792，启动会话96006完成。**当前服务已加载全部已写修复**。
- 报告9 attempt2：概况和general在截断修复加载前已failed，后续需补跑；人员/格式完成；否决和商务继续，其余排队。仍无完整真实验收，项目问答尚未创建。不要重新建报告或上传资料，不提交代码。

### 24.5 原生工具畸形响应（2026-10-07 11:42前后）

- 真实本地后备模型曾把整份答案放进工具name（submit_analysis=...），args为空。AgentChat现先验证工具名属于当前声明及必填参数，畸形名称走有限协议纠正/故障转移，错误不回显整份文档；避免框架unknown-tool错误把巨大草稿再塞回上下文。适配器15项专项通过。
- 最新重启已加载该校验；API父23632、worker25192，beat见`.tmp/backend-pids.json`，启动会话52312。原报告9/attempt2继续，预算与线程不重置，旧7仍canceled。
- 否决attempt2也已到时失败；当前商务与技术在运行，其余排队，概况/general待最终补跑。不要从analysis_module.items读取running模块的有效结果：里面可能是旧质量拒绝的答案，应看当前run.state.draft/staged_items。诊断脚本已按此区分。
- 仍没有完整验收，项目问答未创建，不提交、不重传。已完成且人工核对的仍为人员/格式两模块。

### 24.6 为后备模型预留时间（2026-10-07 11:55前后）

- 现场配置：qwen3.8主模型timeout90秒，本地qwen3.5-9b为300秒且重试1次，glm第三候选90秒。发现本地两次慢响应可吃光功能600秒时限，让第三候选实际无法执行。
- RoutingModel现按模块剩余时限与功能预算较小值设总deadline，再根据剩余候选/重试次数分配单次等待上限（不超过模型配置timeout）。实际请求数/unknown用量仍照常记账，未变更模型绑定或用户配置。模拟连续超时确认可到第三候选；路由+DB专项30项通过。
- 已重启加载全部修复：API父10492、worker22056、beat19992，启动会话89396已完成。再次确认旧7 canceled及锁0后恢复9，原线程/预算保留。技术/评分仍在运行，技术已收到具体内容支持性反馈；最终状态需实时查询。仍无完整真实验收，goal active。

### 24.7 下一轮补跑输出预算（2026-10-07 12:00前后）

- 多次真实4096token截断证明输出空间（含思考）不足；仅修正参数或换到慢本地模型不足以完成验收。新增RetryInput.max_output_tokens可选512–16384，只作用于新attempt.limits；旧attempt/原报告快照和账目不改。请求次数与总时限不扩大。按module_id固定补跑创建顺序。
- 下一轮失败补跑使用8192。`.tmp/retry-deep-failed.py`已加该参数，仍只用报告9原资料；当前进行中的attempt2继续原4096预算。API该新字段尚未加载到现有进程，**等本轮终态再重启加载后调用补跑脚本**，避免无谓中断在途请求。
- API预算override的7项DB集成通过；前端运行记录新增单次输出上限展示，types与typecheck已通过。最后完整backend仍471/7，此后新增分批/畸形工具名/时间预留/补跑预算专项分别通过，最终需全套覆盖；最后前端build在新增输出上限展示之前。
- 目前报告9已完成仍为人员/格式，当前评分与开标运行；概况、否决、商务、技术、general的attempt2已失败或到时，余下继续排队，需实时查询。主模型qwen3.8 timeout90/max_tokens未固定，本地qwen3.5-9b timeout300/max_tokens4096，第三glm timeout90/max_tokens未固定；没有修改用户模型绑定。
- 当前服务仍API10492/worker22056/beat19992，已加载24.6及之前的运行时修复。未加载的只有本节新API预算参数（及自动创建顺序）；前端dev已加载输出预算显示。仍未创建项目问答，goal active，不提交、不重传。

### 24.8 当前全量检查（2026-10-07 12:04前后）

- 最新全部代码：后端TENDER_RUN_DB_TESTS=1完整 **475 passed/7 skipped**，Ruff全部src/tests通过，import-linter5 kept/0 broken；前端76测试、typecheck和生产build通过，git diff --check通过。
- 上述不等于真实模型验收完成：报告9仍运行且只有人员/格式两个已核对完成。当前attempt2继续原4096输出预算；后续失败补跑脚本使用8192，调用前需重启API加载新字段（24.7），当前API10492仍旧版字段。
- 未提交、未重传资料，goal active。继续观察本轮终态，再加载新API并执行`.tmp/retry-deep-failed.py`，随后逐条核对、桌面引用、项目问答。不要先创建新报告或重复上传。

### 24.9 新窗口继续交接（2026-10-07 13:55 实时核实）

本节是新窗口续作入口，按任务记忆模板整理目标、进度、结论、下一步；需求与硬约束仍以第22、23节为准，第24.1—24.8节为实现与修复记录。

#### 目标与约束

- goal 仍 active：13个解析模块各自独立 DeepAgents subagent；并发可配且跨报告硬配额；Agent 自主检索项目文档与知识库、去重后综合分析；落实权限、重试、预算、上下文压缩、checkpoint恢复、失败补跑与运行管理；禁止旧全文扫描分派。
- 用户追加：必须处理上游偶发异常与 429 限流（已实现，见24.3）。
- 不提交代码；不重传项目13资料；只验收桌面端；重启或恢复前先确认旧报告7为 canceled。未完成全部真实端到端验收前不得把 goal 标 complete。

#### 当前进度（2026-10-07 13:52 读取 API 与 DB 核实）

- 报告9 `status=partial`：13模块中 **2 completed、11 failed**；全库 `agent_module_run.status='running'` 为 0，无在途请求；`llm_provider` 无未到期的429冷却。
- 已完成且人工核对：
  - 人员 `personnel_requirement_parsing` module63/run11/attempt1：负责人1名、劳动合同、不要求特定职称，引用一致。
  - 格式 `bid_format_outline_parsing` module64/run12/attempt1：投标函、报价明细表、营业执照、技术响应表四章节，引用已核对。
- 11个失败模块（均为 attempt2，限值快照 `max_output_tokens=4096`、请求32、工具48、时限900秒）：

| 模块 | run | 失败原因（模块 error_message） |
| --- | ---: | --- |
| 项目概况 | 51 | 连续三次提交无效结果 |
| 否决项 | 52 | 总时长预算耗尽 |
| 商务 | 53 | 总时长预算耗尽 |
| 技术 | 54 | 模型请求超时，供应商执行结果未知 |
| 评分 | 55 | 总时长预算耗尽 |
| 开标 | 56 | 模型请求预算耗尽（32/32） |
| 保证金 | 57 | 模型请求预算耗尽（32/32） |
| 封装 | 58 | 总时长预算耗尽 |
| 报价 | 59 | 连续三次提交无效结果 |
| 业绩 | 60 | 连续三次提交无效结果 |
| 补充发现（general） | 50 | 连续三次提交无效结果 |

- 上游异常与429真实现场：业绩 run60 的调用记录中 04:33Z 出现 `completion_tokens=4096` 的“模型输出达到token上限”；04:35Z 两次90秒“供应商执行结果未知”；随后轮换本地 qwen3.5-9b 与主模型并成功。截断识别、未知用量记账、供应商轮换和共享冷却链路均已在真实流量触发。迁移0009（`llm_provider.rate_limited_until`）已应用，当前无活动冷却。
- 服务现场：API 启动器10492（11:53:58启动），实际监听8300的是其子进程30600；worker 22056、beat 19992存活；llama.cpp 7896（PID 9804）、Ollama 11434（PID 16244）在听。**前端4400当前未监听，需要新窗口重启**。
- **运行中的 API 尚未加载24.7的 retry `max_output_tokens`**：`apps/api/src/tender/api/knowledge.py` 最后修改11:57:24，晚于API启动11:53:58；worker/beat不需要为该字段重启。重启时无在途 run，不会打断分析。
- 旧报告7 已再次核实 `canceled`。项目问答尚未创建（state 中只有 `reference_answer`）。

#### 下一步

1. 重启 API 加载 retry 输出预算字段（worker/beat 可不动）；重启后确认8300可达、报告7仍 canceled、running run=0。
2. 运行 `python .tmp/retry-deep-failed.py`：只补跑上述11个失败模块，`max_output_tokens=8192`；脚本自动断言报告7 canceled、报告9为 failed/partial，并写 `before-retry-3.json` 快照。人员和格式模块不得覆盖。
3. 轮询 `python .tmp/check-deep-report.py --brief` 到终态，再跑 `--final`；随后逐模块人工核对事实、条件、引用覆盖和跨文件修订双方引用，不把模型 supported 当人工通过。
4. 重启前端4400（`apps/web` 下 `pnpm dev -- --port 4400` 或既有方式），先跑 `.tmp/deep-flow-browser.mjs --preflight`；报告 completed 后跑最终脚本，覆盖1440/390/320、主文件与补充通知来回切换、PDF高亮、引用 resolve、独立参考库隔离和项目问答。
5. 项目问答由最终脚本首次创建并记录ID，后续必须复用，禁止重复创建。
6. 全部通过后更新本文件与 `docs/设计/16-DeepAgents标书分析运行时.md`，再评估 goal complete；不自动提交。

#### 验收事实基准（人工核对用）

- 编号 TEST-2026-1005；预算80万元、最高限价78万元；交货期30日被补充通知改为45日；本项目质保三年，历史五年不可替代。
- 技术：交换机10台、IPv6、双电源、故障响应不超过2小时；验收合格付款90%，余款质保期满支付；不可抗力延迟需提供证明材料，不能补造免责。
- 业绩：2023-01-01起同类合同每项10分、封顶20分、需合同复印件；负责人1名、劳动合同、不要求职称。
- 保证金10000元、投标截止前到账、可用银行保函；正本1副本2分别密封标注、现场递交；开标2026-11-20 09:30园区一楼会议室，法定代表人或授权代表携身份证与授权委托书；四项格式材料；未提供营业执照、超过最高限价为明确否决或无效条件。
- 参考库7/项目14/source12 只作边界对照，不得替代本项目要求。

#### 坑与工具

- running/failed 模块的 `analysis_module.items` 可能是旧答案，必须读当前 `run.state.draft/staged_items`。
- DeepAgents 使用 DeltaChannel：恢复消息必须走图 `aget_state_history`，直接读 saver 的 channel_values 看不到 messages。
- 不要频繁重启（模块时限与预算不重置，会消耗在途请求和总时限）；不要创建新报告或重传资料；不要执行 `model-probe-ledger.py`。
- 诊断脚本：`.tmp/check-deep-report.py --brief|--final`、`.tmp/inspect-deep-runtime.py [模块片段]`、`.tmp/inspect-deep-calls.py`、`.tmp/inspect-deep-submissions.py <完整key>`、`.tmp/retry-deep-failed.py`、`.tmp/deep-flow-browser.mjs --preflight`、`.tmp/resume-deep-lease.py`（仅停后端并确认无锁后用于过期 lease）。
- 记忆索引：`.agents/memory/project.md`（顶部指向本文件）。
