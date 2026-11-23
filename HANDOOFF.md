# 架构清理交接

更新：2026-11-23。已读取并续接会话 `01a1fda4-e125-7eb2-a4ef-a1f5cb59b3c3`，完成架构清理、前端修复、补件后中断续跑修复和自动化验收。当前分支 `simplify/backend-cleanup`，最新提交以 Git 记录为准。

## 本轮方法、参数与配置清理（2026-11-23）

- 删除分析服务、文档流水线仓储和解析仓储的闲置构造参数及字段，装配不再为文档流水线额外创建配置注册表。
- 删除配置快照的闲置公司参数、项目上传和替换的闲置身份参数，以及仓储补跑的无效参数传递；用例内明确指定专题的有效判断仍保留。
- 删除只有测试调用的项目文件上传包装；集成测试改走真实上传入口，覆盖文件读取、业务校验和返回结果。
- 删除无调用的 Gotenberg、MinerU 健康方法及专用测试；MinerU 健康路径仍用于服务版本和输出能力验证。DocumentParser 补齐 Worker 实际使用的 aclose 协议。
- 将文档任务纳入统一 mypy，配置坐标字段使用对应 Literal 类型，解析耗时的可空时间变量与其它阶段的非空时间变量分开。
- 删除证据预算异常的闲置容量结构和补读重复截断判断；显式补读不再创建去重索引或归一化文本。相同 12 块原文的探针中归一化调用由 90 次降到 0 次，保留证据仍为 13 块。
- 删除模型配置的重复 parameter_bounds 结构、未接入业务的图片功能登记及种子、停用绑定标记和专用分支；图片模型测试、预览、失效及清理继续可用。当前业务功能为 analysis、knowledge_ask、embedding、rerank 四项。
- 删除闲置 sparkle、user 图标，同步前端类型与夹具，清理过时审查文案和测试名；工程21、设计12已同步。
- LLM 集成夹具直接读取当前基线，同时将显式 agent_runtime schema 重命名到夹具空间；该隔离仍是必需的，不能删除。

已完成验证：

- `.cache/cleanup-methods-backend.log`：Ruff、5项分层、63个 mypy 目标、982项离线测试及 OpenAPI 漂移检查全部通过；清除空 SQL 后另有41项基线、ORM及DDL契约测试通过。
- 前端 TypeScript 额外开启 noUnusedLocals、noUnusedParameters 后通过；10个文件、60项单测通过，`.cache/cleanup-methods-web-build.log` 记录生产构建通过。
- `.cache/cleanup-methods-e2e.log`：desktop 两项浏览器回归通过，验证功能大预算保存和模型候选顺序调整。本轮隔离前端服务已关闭，54383释放，原有开发进程11972保留。
- `.cache/cleanup-methods-postgres.log`：231项完整 PostgreSQL 集成测试通过，耗时550.60秒；测试库为 tender_method_cleanup_20261123_test，当前基线版本0001_current_schema、23项配置和4项业务功能种子已核对。
- 核对程序、数据目录和零客户端连接后，原生 PostgreSQL 已正常关闭，55478释放，postmaster.pid消失；数据目录与测试库保留。关闭因检查点同步耗时超过默认60秒，延长等待后完成，服务日志为 `.cache/cleanup-methods-postgres-server.log`。
- 93个现存修改文件 UTF-8 检查及48个 Python 文件语法检查通过，最终 Ruff 与差异空白检查通过。
- 提交前独立审查未发现需修复问题；另行复测202项后端专项测试和前端未使用变量、参数类型检查通过，27个 Skill 文件的业务规则正文与清理前一致。

本轮改动的提交状态以 Git 记录为准。

## 上一轮增量清理（2026-11-23）

- API仅装配数据库、存储、模型网关和配置；移除无消费者的转换客户端、队列包装及访问器。Worker转换工厂使用现有OfficeConverter端口。
- 删除旧展示摘录、全源证据扩展、自动审查上下文和检索预取入口；移除专用研究缓存、检查点字段、恢复参数和容量分支。
- 删除停用的complete_validated接口及校验回调。请求身份、预算、协议错误、取消与有效回执恢复的回归已迁到当前chat路径；保留原生工具参数校验及有界纠正。
- 删除无消费者的仓储方法、响应模型、配置常量和旧GapInput；移除仅验证已删除行为的测试及空转样例分支。
- 前端删除16项闲置导出及对应旧测试，坐标契约辅助与SQL排名的独立参考算法继续保留。
- 清理27个Skill文件中的100处旧主题标记；逐文件对照确认业务规则正文一致。运行时不再剔除旧阶段标记。
- ORM、文档与裸SQL列引用契约共用当前基线解析器，移除历史加列、改型与删除回放；工程21文件树已同步。

验证已完成：

- `scripts/check-backend.ps1`：Ruff、5项分层、62个类型目标、983项离线测试及OpenAPI漂移检查全部通过。
- 前端额外启用未使用变量、参数检查的TypeScript验证通过；10个文件、60项单测及Next.js生产构建通过。
- `scripts/check-postgres.ps1`：231项集成测试通过，覆盖续跑、快照、锁、检索及任务恢复。
- 新建独立测试库`tender_unused_cleanup_20261123_test`，确认当前基线版本与23项配置种子；核对进程身份和零客户端连接后，已关闭本轮启动的原生PostgreSQL实例。数据目录和测试库保留，端口为55478。

本轮改动的提交状态以 Git 记录为准。

## 当前目标与约束

用户授权全面分析和优化架构，删除重复、冗余、停用代码及过时注释，文档只描述当前版本。用户明确不考虑已有数据和历史迁移，数据库直接创建当前空库基线。保留模块化单体、API＋单Worker＋Beat、人工裁定和编制门槛。

使用PowerShell、UTF-8、pnpm和中文注释。依赖安装由用户执行，不自动提交，不自动启动WSL。后端目录与装配遵循根目录AGENTS及工程21。

## 当前实现

- 分析采用每专题单Agent＋Skill。旧阶段编排、独立审查、业务覆盖投影及其兼容分支已删除。草稿保存在工作区，最终提交才发布正式结果。
- 续跑中断专题使用最新运行工作区的质量，完成专题使用正式结果质量。补件后中断的轮次不再受旧正式缺件结论阻挡；当前轮确认仍缺件且资料未变时继续要求补件。再次续跑保留草稿、输入签名和有效自查。
- 执行状态、机器自查和人工裁定分别表达；编制只采用当前冻结输入上的人工确认或修正。旧快照指纹、质量映射、任务补配置及旧分块读取已删除。
- 问答业务与分析编排分离，共用检索和模型适配留在application/shared。
- Alembic只保留 `0001_current_schema.py`，创建当前表、索引、约束和23项配置种子。检查点继续使用独立初始化命令。
- API响应由Pydantic定义，前端使用OpenAPI生成类型；统一后端检查包含生成漂移检查。
- 删除始终为空的配置软预算门禁及无效强制发布开关，普通发布仍要求逐项确认并记录理由。前后端类型、客户端、页面与夹具已同步。
- 检索一次展开向量并物化评分，避免重复解压和评分。专题读取在单次请求内复用完整相同引文，下一次请求重新检查权限。容量依据见工程25。
- 默认启动脚本和Compose使用readyz检查PostgreSQL、Redis及存储，healthz表达进程存活。
- 删除无调用的会话工厂、知识库包装、旧批量记录处理及旧审查替身。最新人工裁定查询使用每条记录的最大ID。
- 文档已更新当前架构、配置、API、数据库、部署和文件树；源码中过时章节引用已改为当前文档路径。配置限制表与当前23项登记一致。
- 前端配置单测改用独立的通用类型样例，不再引用已删除的业务配置。
- 前端已删除要求旧协议报告继续展示的浏览器用例，以及报告页的历史条目计数和对应夹具。共享Markdown取值分支仍用于当前问答，保留实现并将注释改为实际用途；专题记录读取失败清除缓存正文的测试也改为当前语义。
- 前端类型检查同时覆盖浏览器夹具，已清除旧review_status、进度阶段字段及去噪配置夹具。人工复核分别提示机器自查失败与原文缺失。项目、模型、知识库及资料删除采用确认框的await模式，正常业务错误保留确认框重试，不再触发全局未处理异常。

## 上一轮验证

- `.cache/retry-quality-backend.log`：992项离线测试通过，包含9项补件后中断续跑回归；Ruff、5项分层、63个类型目标及OpenAPI漂移检查全部通过。
- `.cache/retry-quality-postgres.log`：231项完整PostgreSQL集成测试通过。新增3项回归验证partial、failed、canceled轮次再次续跑正确入账，保留草稿和有效自查及上一轮正式结果；未确认解析配置的发布门槛回归也通过。
- `.cache/current-baseline-proof.json`：两个新建空库的版本、23项配置、86个业务索引、7个检查点索引、41张表的列/约束及序列一致。新库为 `tender_delivery_baseline_20261122_test`、`tender_delivery_restore_20261122_test`；备份为 `.cache/cleanup-delivery-baseline.dump`。
- `.cache/audit-backup-proof.json`：带业务样本的恢复逐表核对41张表的行数和内容摘要，其中22张非空；人工裁定读取一致，检查点状态可读。
- `.cache/recovery-final-source-audit.json`：当前Git清单中622个文本文件UTF-8解码通过，66个本地Markdown链接及锚点有效；复核脚本为 `.cache/recovery-source-audit.py`。配置文档表已与当前23项登记逐项核对。
- mypy的损坏SQLite缓存已移到 `.cache/mypy-corrupt-20261122-recovery`，重新生成缓存后统一检查通过。
- 已核对临时PostgreSQL程序、数据目录及连接活动后正常关闭该实例；数据目录和备份保留。前端测试服务与构建进程均已退出，隔离端口54383已释放。

临时PostgreSQL数据目录为 `.cache/cleanup-postgres-20261122/data`，程序目录为 `C:/Users/wph98/.codex/recovery/AI-tender-20261114-2015/pgsql/bin`，验收端口为55478。需要再做数据库验证时使用原生实例并重新核对进程身份。

## 上一轮前端验收结果

用户已完成冻结镜像安装，246个包安装成功。日志为 `.cache/pnpm-install-mirror.log`；React、Next、Vitest、TypeScript、Playwright及PDF.js入口均可解析，PDF.js静态资源已准备好。

- `.cache/recovery-frontend-typecheck.log`：应用源码与全部浏览器夹具类型检查通过。
- `.cache/recovery-frontend-test.log`：10个文件、66项单测通过。
- `.cache/recovery-frontend-e2e.log`：系统Edge的desktop/mobile项目共115项通过；1项只适用于窄屏的固定操作列检查在desktop按条件跳过。覆盖analysis-data、synthesis、management，以及配置范围、版本详情、模型启停和删除错误回归。
- `.cache/recovery-frontend-build.log`：Next.js生产构建通过，静态页面生成与TypeScript检查通过；独立运行入口已生成于 `apps/web/.next/standalone/apps/web/server.js`。
- `.cache/recovery-delete-unhandled-before.log`：新增断言复现了项目删除失败后的全局异常。最终浏览器验收同时证明项目、模型、知识库及资料删除失败可重试或取消，且不产生浏览器未处理异常。

本轮架构清理、前后端自动化验证、数据库初始化与备份恢复检查已完成。前端文档的验证命令已与本次通过的入口统一；差异检查通过。

真实单Agent语义验收的最新记录仍为v6失败，原文和轨迹在 `C:/Users/wph98/.codex/recovery/AI-tender-agent-led-20261115/live-v6/results`。新冻结版本的人工语义验收按 `docs/工程/24-解析Agent稳定性验收.md` 执行。
