# 架构清理交接

更新：2026-11-25。已读取并续接会话 `01a1fda4-e125-7eb2-a4ef-a1f5cb59b3c3`，完成架构清理、前端修复、补件后中断续跑修复和自动化验收。当前分支 `main`，最新提交以 Git 记录为准。

## 本轮错误归属审查修复（2026-11-25，已完成）

- 修复刷新恢复按文案误清除操作失败：所有错误设置/清空共用入口生成独立身份，只在实际展示刷新错误时登记身份；恢复成功仅清除仍属于该次刷新的提示。相同文案的关联保存失败、其他操作及定位错误不再被误清除，取消不清除新错误。
- 浏览器先在修改前复现关联保存失败后提示消失，修复后同文案/不同文案、自动恢复、永久访问错误与取消等20项专项通过；前端类型检查、68项单测通过。首次生产构建原生进程以3221225478退出，未改代码重试标准构建通过；完整110项桌面/窄屏浏览器回归全部通过，耗时7.2分钟。
- 本轮只修改前端和文档，后端与数据库无新增改动。日志.cache/error-owner-e2e-before.log、error-owner-e2e-focused.log、error-owner-e2e.log、error-owner-web-build.log。浏览器测试服务已退出，已核对54383、55478无监听；未创建备份，未自动提交。

## 本轮两项审查修复（2026-11-25，已完成）

- 修复前置错误清空状态后停止轮询：HTTP错误保留状态；轮询活动与可见正文分离，已知活动任务遇到5xx/408/429/网络错误继续自动重试，永久访问错误停止。完整读取成功后确认活动终态、清除该次错误提示；取消不清除新请求状态。
- 应用层过滤登记专题键后再生成PG输出声明列，保留未知专题错误回执；ASCII和中文长键不再触发PostgreSQL63字节列名截断冲突，未知单专题返回404。
- 19项后端专项、24项PG专项、68项前端单测、类型检查和生产构建通过；统一后端Ruff、五项分层、64个mypy目标、1026项离线测试和OpenAPI漂移通过，76.17秒。全套243项PG集成通过，371.81秒；106项桌面/窄屏浏览器回归全部通过，6.6分钟，覆盖分析/资料处理中的503与网络错误自动恢复、永久访问错误停止轮询和缓存清除。62个文本UTF-8、36个Python语法及差异空白检查通过，工程29同步当前验证结果。
- 临时PG根目录C:/Users/wph98/AppData/Local/Temp/ai-tender-review-fix-20261125-91b331dd，data子目录，主进程32808，端口55478，测试库tender_review_fix_20261125_test。已核对身份与零客户端并正常关闭PG；浏览器已退出，55478、54383释放，测试目录保留。未创建备份，未自动提交。

## 本轮前置失效与精确读取优化（2026-11-25，已完成）

- 用户授权四项优化，工程29记录当前实现。前置状态/详情失败或已有报告从列表消失时清除正文、缓存版本和在途定位；正常取消不清除新结果，恢复请求不携带旧版本。无报告时保留独立问答定位。
- 最新快照检查只查询ID，完整快照2次读取降为1次；保留无快照的data_not_ready、版本变化判定、等待后和事务内重新核验。
- 展示与内部投影共用record_citations，先核验再复制可见正文；40条隐藏记录复制40降到0，返回内容仍与持久记录隔离。合并接口传专题键到既有仓储，SQL筛选与公司隔离保留，13专题选1时取回13降为1；默认Worker和发布全量读取保留。
- 39项后端专项、22项PG专项通过；统一后端Ruff、五项分层、64个mypy目标、1023项离线测试和OpenAPI漂移通过，114.97秒。全套241项PG集成通过，388.44秒；前端类型检查、64项单测、最终生产构建和8项失败清理/恢复/取消浏览器专项通过。浏览器先复现六个旧正文保留用例；首轮全套95通过、1项初始脚本无堆栈SyntaxError导致未进入断言，异常检查保留，最终96项完整复测全部通过，5.5分钟。60个修改文本UTF-8、36个Python语法与差异空白检查通过。
- 本轮原生PG根目录C:/Users/wph98/AppData/Local/Temp/ai-tender-precise-read-20261125-171cf632，data子目录，主进程35168，端口55478，测试库tender_precise_read_20261125_test。已核对身份、零客户端后正常关闭PG；浏览器服务已退出，55478、54383释放，测试目录保留。未创建备份，未自动提交。

## 本轮分析取数与刷新优化（2026-11-25，已完成）

- 用户授权实施六项优化；工程28记录实现与实测结果。最终提交按完整引文去重，工具收尾复用进度，空质量问题跳过全来源查询，删除草稿薄包装；单次提交仍逐条检查本项目引用，正式保存和发布保留授权、版本与租约核验。
- 展示通过既有仓储窄字段查询读取协议、输出声明与模块质量；PostgreSQL用jsonb_to_record一次解析JSON，保留Worker和发布的完整取数。
- 分析页每轮合并读取全部专题，服务端先核验权限再生成版本，仅返回变化正文；同次请求共享引文解析和冻结输入核验，前端失败清除对应正文与缓存版本。13专题每轮15个HTTP请求降为3个，40条共享引文提交解析40降为1，工具收尾自查80降为40。
- 13专题每专题40条记录的未变化刷新响应345,827降为1,632字节。13专题每专题160条长记录的PG摘要取数11,226,260降为4,478字节，中位耗时57.327降为12.116ms；具体样本和其余取数指标见工程28。
- 统一后端Ruff、五项分层、64个mypy目标、1016项离线测试和OpenAPI漂移通过，离线测试135.81秒。最终窄字段SQL的20项PG专项通过，全套239项PG集成通过，415.27秒；前端类型检查、64项单测、最终生产构建、既有88项和新增2项浏览器回归通过。新增用例断言完成初始化后的手动刷新为3个请求，未变化正文只返回版本；开发模式首次挂载会取消一次状态请求，不能把该请求计入手动刷新。59个修改文本UTF-8、36个Python语法与差异空白检查通过。
- 本轮独立PG根目录C:/Users/wph98/AppData/Local/Temp/ai-tender-record-optimization-20261125-1c6ec509，data子目录，主进程13556，端口55478，测试库tender_record_optimization_20261125_test。已核对身份与零客户端连接，正常关闭PG；浏览器服务已退出，55478、54383释放。测试目录保留，未创建备份，未自动提交。

## 本轮六项增量清理（2026-11-25，已完成）

- 实施工程27的六项清理：删除普通证据补读旧路径和_read_batch；一次同步操作的_ReviewEvaluation复用事项、依赖、原文版本与签名，正文/进度共用自查结果；收敛重复证据完整性判定与四个空转响应字段；OutputSchema/OutputSection统一输出声明。
- 问答项目ID按真实来源范围声明为整数，权限只用SDK的read/write；消息计量支持SDK消息简写和一次性迭代器，图输入及配置按真实SDK契约声明。qa_agent.py进入统一mypy目标，未放宽协议与真实装配检查。
- 40条已自查草稿和160块原文样本每页自查判断80降到40次、原文版本计算640降到160次。计算视图不持久化，下次请求重新核验；原文、依赖及草稿变化仍使旧自查失效。
- 新增共享原文复用/下次失效、消息迭代器和真实问答文件权限回归。普通补读测试迁到现行语义块与紧凑模式，保留窗口、权限、版本、容量、续读和原文完整性断言。
- 统一后端入口的Ruff、五项分层、64个mypy目标、1007项离线测试和OpenAPI漂移检查通过，离线测试118.44秒。首轮1006项通过、1项日志夹具用空资料快照失败；补齐合法来源后专项与完整复测通过，保留供应商错误和密钥不可回显断言。
- 独立空库236项PostgreSQL集成通过，390.40秒。前端未使用变量/参数类型检查、60项单测、生产构建和88项桌面/窄屏报告与编制回归全部通过，浏览器约5.6分钟。48个当前修改文本的UTF-8、Python语法及差异空白检查通过。
- 工程27、设计05、14及交接同步；当前架构和业务目录保留。用户不允许自动备份，本轮未创建备份，未自动提交。

本轮临时PostgreSQL目录为C:/Users/wph98/AppData/Local/Temp/ai-tender-incremental-20261125-ac401d54/data，独立库tender_incremental_20261125_test。收尾核对实际主进程、程序、数据目录和零客户端连接后正常关闭；前端服务已退出，55478、54383释放。临时数据目录保留。

## 本轮七项代码清理（2026-11-25）

用户已授权实施工程26审查报告的七项清理，代码修改已完成：

- 分析详情、原始模块、正式快照、独立证据、质量问题和运行账均使用明确响应契约，只序列化声明字段；前端相关类型直接从OpenAPI生成类型派生。
- 删除详情research_gaps、前端旧缺口回退、闲置AnalysisFieldResponse、on_context_changed摘要回调和无输出声明的记录路径；GET与SSE建流前复用同一任务读取。
- 通用指纹直接引用domain/shared/digest.py，删除plain_text转导出；数据和浏览器夹具使用当前正文、质量问题与真实预算。
- 草稿回读缓存只留在当前图内，原地修改也会刷新；首页分段构造由520降到6，后续页序列化由200对象、1,811,000字符降到0。总数、原文完整性、去重及权限检查保留。
- 配置和异常更新专题Agent措辞，基线种子、设计05、14和工程26同步。Ruff与差异空白检查通过，全部修改文本文件的UTF-8及Python语法检查通过。

当前验证状态：统一后端入口的Ruff、五项分层、63个mypy目标、1004项离线测试和OpenAPI漂移检查通过，离线测试117.98秒；前端未使用变量/参数类型检查、60项单测及生产构建通过。旧mypy SQLite缓存报database disk image is malformed；统一入口和真实签名探针改为禁用增量缓存，并使用操作系统空设备作缓存目录，不放宽实现检查。

PostgreSQL首轮234项通过、2项旧夹具失败（空运行预算、旧正文断言）；修正后三项参数化复测通过，最终空库全套236项通过，耗时387.86秒。浏览器首轮87项通过、1项业务断言通过后出现无堆栈SyntaxError；保持异常断言，独立desktop/mobile复测两项通过，最终完整88项全部通过，耗时约5.1分钟。新库0001_current_schema、专题Agent配置说明、成功计数NO/0均已核对。

本轮验证PostgreSQL数据目录为C:/Users/wph98/AppData/Local/Temp/ai-tender-cleanup-20261125-83b3ef85/data，端口55478，主进程4272；最终测试库tender_cleanup_final_20261125_test。已核对主进程4272、可执行文件、数据目录及零客户端连接，正常关闭临时PostgreSQL；前端测试服务已退出，55478、54383释放。用户不允许自动备份；本轮未创建备份，不自动提交。

## 本轮审查问题修复（2026-11-24）

- 修复问答关系第二跳因标段名称、别名或列举顺序不同而漏扩展：范围键统一使用 `kind` 与 `lot_ids` 集合，加入和匹配遍历节点使用同一键；原文范围继续用于展示。
- 新增3项顺序、名称及别名回归和2项不同标段集合回归，测试数据由真实 `resolve_scope` 生成。修复前3项失败、2项通过，修复后关系扩展文件16项全部通过；公共范围与标段范围、不同标段及包含关系的范围继续隔离。
- 设计13同步范围判定规则。统一后端入口最终重跑的Ruff、5项分层、63个mypy目标、996项离线测试及OpenAPI漂移检查全部通过，离线测试耗时212.69秒。UTF-8检查日志为 `C:/Users/wph98/AppData/Local/Temp/ai-tender-scope-check-20261124-2248.log`；本轮修改文件编码、Python语法及差异空白检查通过。

## 本轮精确取数与冗余状态清理（2026-11-24，已实施）

用户已授权继续优化，本轮六项清理已完成：

- 问答关系按稳定 `block_id` 精确补读，跳过已命中块，复用 `read_chunk_window(source, offset, 1)`；块按整数序号排列，保留关系、端点、来源和权限核验。
- 报告正文改用带公司过滤的 `report_module(report_id, module_key)` 单模块查询，保留正文权限和冻结输入检查。
- 分析最终草稿删除重复的 `draft.fields`，发布检查和日志计数统一读取 `published_items(state)`；问答草稿的 `fields` 仍有用途。
- 正式模块统一读取独立 `evidence/evidence_ids`，缺失证据使整条记录不可用，内联引用不能回退；已投影的空列表直接复用。
- 删除专题紧凑分页与图谱扩展的未装配组合分支，普通问答继续扩展；删除不可读条目的旧 `record_id` 别名透传，保留缺口和人工裁定的有效字段。
- 清理恢复夹具的重复断言和取值，修正报告仓储注释，同步设计13、14及相关测试。

实测：13个专题请求取回模块行由169份降至13份；8条记录工作区由53,021字节降至39,761字节，减少13,260字节；长元素8块中唯一关系引用已经命中时，不再补读来源。

验证及现场状态：

- 相关6个单测文件89项通过，正常导入运行；统一后端入口最终重跑的Ruff、5项分层、63个mypy目标、991项离线测试及OpenAPI漂移检查全部通过，离线测试耗时266.69秒。mypy禁用增量缓存，保留真实协议与装配检查。
- 首轮完整离线测试990项通过、1项流增量超时测试失败；单独复测通过。测试准备阶段先初始化SDK流资源，防止首次加载占用首包时限，保留原5秒时限和全部断言；该文件49项通过。
- 从空库执行当前基线后，236项完整PostgreSQL集成测试通过，耗时425.53秒，覆盖单模块查询、权限、发布和恢复。
- 收尾发现 `test_analysis_recovery_flow.py` 的实际内容读成无关渲染文档并含NUL；按既有验证记录的SHA-256核对恢复材料后还原，恢复链路10项重新通过，耗时133.49秒。597个Git管理的文本文件完成编码和Python语法扫描，更新本交接前的88个既有修改文件均与验证摘要一致；恢复后Ruff及差异空白检查通过。旧 `.cache` 材料也曾出现无关内容，后续使用前须核对内容及摘要。
- 本轮临时数据库位于系统临时目录 `ai-tender-validation-20261124-c67adb3a/data`，测试库为 `tender_validation_20261124_test`。核对进程31580、数据目录及零客户端连接后正常关闭，55478释放。当前用户API、Worker、Beat入口进程为36132、23116、27136，仍在运行。

用户明确反对自行备份，后续不得创建备份。本轮更改的提交状态以Git记录为准；用户已授权一并提交既有环境、Compose、部署、启动脚本及docker/mineru修改。

## 本轮六项清理的实施前分析依据（2026-11-24）

以下保留实施前的分析与探针依据，对应清理已在上方记录完成：

- 问答关系扩展仍按element_id展开：唯一引用块已经命中时，现行语义块探针仍完整读取来源，从1块扩成8块，额外7块没有被关系引用。应按block_id精确展开并跳过已命中块，缺失块复用有界原文读取，保留遍历前的引用与权限核验。
- 专题正文接口每次先report_modules取全报告再按module_key筛选；前端逐专题请求使13个专题取回169份模块行。建议在现有报告仓储/端口中按report_id、module_key单查，继续逐请求核验正文权限与冻结输入。
- 分析最终提交的draft.fields是staged_items中final_ids所选记录的完整深拷贝，生产仅用于最终本项目引用检查和计数。8条记录探针删除此副本可把工作区从53,021字节降到39,761字节；可从published_items(state)取同一结果，保留正式business_data。
- module_records仍兼容无evidence_ids的内联引用形态，现行正式写入统一为独立evidence/evidence_ids；应统一证据读取并保留缺证据拒绝。
- ResearchSession中compact_results与expand同时启用的扩展截断分支只由测试构造；专题只用紧凑分页，问答只在普通模式扩展。可清理未装配的组合分支，保留两条现行路径。
- visible_items的条目record_id旧别名透传已无生产写入者；旧display_items删除后正文统一用id。同名缺口和人工裁定字段仍有用途，不能一并删除。

局部附带项：assemble_dataset对已预计算的空列表用or再次投影，13个空专题额外调用13次module_records；恢复集成夹具有完全重复断言和重复取值；报告端口/查询仍有“模块含工具日志”“运行账含暂存成果”的过时注释。

3个纯数据测试文件38项通过。离线图谱探针直接执行现行函数源码，其余使用真实草稿、正文用例和投影。6文件检查在第三方SDK导入阶段等待过长、尚未执行测试，已结束并转用纯数据验证；本轮未启动数据库或调用模型。静态候选中的框架回调、流接口、独立排名算法、坐标契约及PID缓存继续保留。

实施前材料：`.cache/next-cleanup-analysis-20261124.md`、`.cache/next-cleanup-probe-proof-20261124.json`、`.cache/next-cleanup-static-candidates-20261124.json`、`.cache/next-cleanup-data-tests-20261124.log`。完整验证结果以上方实施记录为准。

## 本轮新机器空库部署计数验证（2026-11-24）

- 用户明确要求其他机器从空库部署时正确，继续保留唯一的 `0001_current_schema` 基线。两个成功计数字段为 `integer DEFAULT 0 NOT NULL`，新增中文原因注释；ORM保持非空映射，首次运行与补跑均使用数据库默认值。
- 增加2项离线基线契约，防止零默认值或非空定义被删除；新增 `tests/integration/test_database_baseline.py`，直接从空命名空间执行完整基线，调用真实首次运行、补跑及 `_settle` 实现，覆盖初始化为0、成功递增、失败和重复回执不计数、拒绝NULL。
- 在现有PostgreSQL实例创建独立空测试库 `tender_new_deploy_20261124_7a381e57_test`，实际执行部署入口 `alembic upgrade head`，版本为 `0001_current_schema`，两个字段均为NO/0。新增3项及原有2项成功计数集成回归通过，ORM/基线与配置契约共41项通过；相关文件Ruff、UTF-8和差异空白检查通过。现场业务库未参与本轮测试，独立测试库保留。
- 验证脚本为 `.cache/verify-new-deployment-counters-20261124.py`，凭据为 `.cache/new-deployment-counters-20261124-proof.json`；工程17补充新机计数字段验收查询。统一后端入口尝试记录在 `.cache/new-deployment-counters-backend-20261124.log`，当前受其他清理改动的13项Ruff错误阻挡，包括 `test_knowledge_flow.py` 的旧夹具 `attach_completed_module` 引用；未改动这些文件。

## 本轮重复投影与问答关系链路清理（2026-11-24）

用户已授权实施上一轮追加分析确认的清理，现已完成：

- 正式模块只保存 `business_data`，删除模块 `items`、`trace` 和报告 `summary` 的ORM、当前空库基线、写入与响应。详情只返回执行、质量与运行信息；正文从独立records接口读取，引用在正文读取时按实时权限核对。
- 问答关系改接最近completed/partial当前协议报告的最新正式业务快照，删除旧 `knowledge_relation` 表、ORM、读写接口及空关系发布载荷。首跳由命中原文块触发，第二跳按稳定记录ID及同一适用范围展开，最多24条。关系与端点须已核实，全部引用在遍历前复核所选来源、解析版本、集合关联和原文可读性；失效边不能带出第二跳，相同引文复用一次核验。
- 删除空转的 `merge_field_entries`、`display_items`、`summarize`，闲置模型工厂 `extra_retries_limit`、RoutingModel候选数量属性、无block_id引文回退、固定跳过的语义启发式及 `defer_semantics`。本项目引用要求、现行草稿自查、模型配置的实际重试预算继续生效。
- 删除6个未注册的API辅助包装，测试直接使用现有用例装配。前端同步详情类型，删除无发送者的扫描计数与旧摘要专题角标；OpenAPI类型及设计03、05、13、14同步。
- 两个图谱集成用例改走真实草稿、自查、最终提交、运行仓储发布和统一快照，验证保函原文经关系进入问答；不再通过直接写旧关系表掩盖生产链路失效。新增8项关系遍历单测和4项快照可见性集成回归。

验证完成：

- `.cache/cleanup-followup-backend-20261124.log`：统一后端入口的Ruff、5项分层、63个mypy目标、983项离线测试和OpenAPI漂移检查通过；最终夹具同步后另有10项控制器生命周期回归通过，Ruff及生成漂移复核通过。
- 前端TypeScript额外开启未使用变量、参数检查通过，10个文件、60项单测通过；`.cache/cleanup-followup-web-build-20261124.log`记录生产构建通过。构建在 `.cache/web-followup-20261124` 源码副本执行，103个前端源码文件与工作区逐字节一致，避免覆盖用户开发缓存。
- `.cache/cleanup-followup-e2e-20261124.log`：既有系统Edge desktop/mobile项目的88项报告与编制回归通过；详情夹具彻底移除items后，`.cache/cleanup-followup-wire-e2e-20261124.log`另有10项取数、轮询、报告切换及成功次数复测通过。临时前端服务已退出，54383释放。
- `.cache/cleanup-followup-postgres-20261124.log`：235项完整PostgreSQL集成测试通过，耗时381.63秒。独立空库为 `tender_followup_cleanup_20261124_test`；基线版本、删除字段与旧表、23项配置、4项业务功能种子及成功计数的非空零默认值均已核对，凭据为 `.cache/cleanup-followup-baseline-proof-20261124.json`。
- `.cache/cleanup-followup-source-proof-20261124.json`记录当前修改文件的UTF-8、Python语法及内容摘要，差异空白检查通过。原始目标文件备份为 `.cache/followup-cleanup-before-20261124/`，仅供本轮差异复核，不是全工作区快照。
- 核对本轮临时PostgreSQL进程29832、可执行文件、数据目录、55478端口及零客户端连接后正常关闭；postmaster.pid消失、端口释放，数据目录和测试库保留。日志为 `.cache/cleanup-followup-postgres-server-20261124.log`。用户API、Worker、Beat进程31208、34048、30748仍在运行，现场成功调用次数修复保留。

本轮改动尚未提交。用户原有环境示例、Compose、部署文档、启动脚本和docker/mineru修改保留；按既定策略仅修改当前空库基线，未改写现场业务库。

## 本轮成功调用次数恢复（2026-11-24）

- 页面成功次数空白来自现场业务库：`agent_module_run.successful_model_calls` 与 `successful_tool_calls` 仍可空、没有默认值，13条现存运行记录均为NULL。现行 `0001_current_schema` 已定义 `DEFAULT 0 NOT NULL`，但现场库虽然记录同一基线版本，列定义仍停留在旧状态；`NULL + 1` 导致成功结算无法累加。
- 在单事务内短暂锁定运行表，按 `agent_call_attempt` 中 `status='ok'` 的幂等回执恢复空计数，再同步两个字段的零默认值与非空约束。恢复时运行1为模型成功35次、工具成功24次，其余12条等待记录为0；后续结算继续正常递增。
- 验证13条运行的计数与真实成功回执全部一致，报告API返回整数；独立无头Edge读取真实项目页面，实际显示“模型请求成功39次 · 工具执行成功26次”。现场修复脚本为 `.cache/repair-success-counters-20261124.py`，修复前后凭据为 `.cache/success-counters-repair-20261124-proof.json`，页面截图为 `.cache/success-counters-live-20261124.png`。

## 本轮追加代码分析依据（2026-11-24，已实施）

以下记录实施前的分析与探针结果；对应清理和验证已在上方“本轮重复投影与问答关系链路清理”完成。分析阶段核对草稿、正式成果、报告页面、问答及模型工厂的生产读写链路，确认以下候选：

- 问答图谱读取链路失效：DraftWorkspace.finalize 将关系保存在 business_data.records，draft.relations 固定为空；AgentRuntime._draft_payload 继续传空 relations，AgentRunStore._publish 只删除 knowledge_relation、不插入关系。KnowledgeStore.verified_relations 与 graph_expand 仍读旧表。真实草稿、自查、最终提交探针得到1条现行业务关系，发布语句只有模块更新和旧关系删除；现有两个图谱集成用例直接向旧表插入关系，未覆盖现行发布入口。建议改接现行正式业务快照，复用权限、来源及版本核对，再删除旧关系表与空转发布载荷，保留带证据的业务关系能力。
- 报告仍重复保存和读取展示投影：AnalysisReport.summary 由 summarize 复制模块 items，get_report 再对模块和 summary 分别做 visible_items。ProjectAnalysis 丢弃详情中的 items，loadReportRecords 始终从独立 records 接口重建正文；页面未消费 report.summary。3条记录共用1块引文的离线探针中，get_report 解析引文2次，records 接口再解析1次。建议清理 summary 和已被独立记录替代的模块展示链路，同步响应模型、前端类型及直接验证旧投影的夹具；正式 business_data 和快照仍为下游来源。
- merge_field_entries 在唯一生产调用上空转：现行持久 items 均经 display_items 带 record_id，普通专题逐条跳过合并，格式专题直接返回原列表。探针确认3条记录的内容、顺序及对象身份全部不变；问答没有调用该合并器。可删除合并器及专用旧字段合并用例。
- 模型工厂 extra_retries_limit 只有 test_model_routing.py:47 传入，生产调用未使用；RoutingModel.candidate_count 属性无消费者。可删除闲置入口，保留 _invoke 中实际控制候选数量的同名局部变量及模型配置的 extra_retries。
- EvidenceWindows.find 的 by_element 回退只为无 block_id 的旧引文准备；当前问答唯一生产调用先经 validate_answer/validate_items，citation 总会保留 block_id。探针确认现行引用不访问元素回退；相应用例仍显式制造旧 attempt 无块身份。可删除该回退索引，保留同块、邻域、续句及章节核对。
- validate_project_claims 唯一生产调用固定 defer_semantics=True，当前最终字段均有 business，旧缺席措辞和双来源修订启发式被全部跳过；对应测试仍用默认参数和旧字段夹具验证未运行分支。可删除启发式与失效开关，保留实际执行的本项目来源约束，并继续覆盖当前 Agent 自查与修订端点校验。
- analysis_module.trace 无生产写入者，仅建库默认空数组、ORM字段和 get_report.pop；运行审计已使用 Agent 状态、事件与归档。可同步删除空列及文档字段。前端 coverage.scanned_blocks/total_blocks 无现行发送者，跨专题 module_keys 角标只服务已闲置的 summary，可随报告投影一起清理。
- API辅助包装器未注册路由：analysis.routes 的 report_row、visible_items 仅测试调用，data_snapshot、context_data 无调用；knowledge.routes 的 project_collection、public_sources 无调用。服务层对应方法仍有现行消费者，清理仅针对API重复包装，集成夹具应改用既有用例装配。

补充判断：退役协议过滤与拒绝用例可按既定空库策略另行评估，不能把协议版本、Skill指纹和工作区结构核验一并视为无用；当前冻结输入和检查点恢复仍依赖版本身份。模型及检查点的有界自动恢复、前端 contextOnly 和人工修正后的 partial 均有生产用途。

验证凭据：`.cache/cleanup-followup-analysis-20261124.py`（离线探针）、`.cache/cleanup-followup-analysis-proof-20261124.json`（行为结果、SQL与关键源码摘要）。相关6个测试文件共50项离线测试通过；分析阶段未启动数据库或改变用户运行进程。

## 本轮现行运行契约清理（2026-11-24）

- 删除当前草稿入口无法生成的 conditions、materials、scoring、category 字段及5个专用模型；前端类型、空转展示、样式和夹具同步。条件、材料及评分内容继续由各专题 content 表达，人工修正后的 structuring 和标段缺口保留。
- 删除无消费者的 work_ids、business_protocol，以及退役的 loaded_skill 结算分支、analysis_evidence 清理分支、旧模板文本剔除、覆盖检查问题码和问答重复附带字段。
- 报告查询直接读取运行账的成功次数，删除审计事件聚合回退。当前建库基线将两个成功计数设为 DEFAULT 0 NOT NULL，ORM同步非空映射；首次运行和补跑都复用基线初始化，结算仍在既有事务中幂等递增。
- 文件派发只保留有整数配额的转换、解析两条线，删除无限并发支持并同步端口、仓储和测试。
- 删除已无发送者的旧审查日志处理；工程20、22同步当前模型日志及工具审计的保存位置。浏览器补充依据回归改用实际正文与证据契约，继续验证独立原文定位。

验证完成：

- `.cache/cleanup-current-runtime-backend-20261124.log`：统一后端入口的 Ruff、5项分层、63个 mypy 目标、981项离线测试及 OpenAPI 漂移检查全部通过。
- 前端 TypeScript 额外开启 noUnusedLocals、noUnusedParameters 后通过，10个文件、60项单测通过；`.cache/cleanup-current-runtime-web-build-20261124.log` 记录生产构建通过。
- `.cache/cleanup-current-runtime-e2e-20261124.log`：系统Edge既有 desktop/mobile 项目共88项报告与编制回归通过。临时前端服务已关闭，54383释放，临时浏览器配置已删除。
- `.cache/cleanup-current-runtime-postgres-20261124.log`：231项完整PostgreSQL集成测试通过，耗时370.25秒。测试库为 tender_runtime_cleanup_20261124_test，由当前空库基线新建；两个成功计数的非空零默认值、23项配置和4项业务功能种子已核对，凭据见 `.cache/cleanup-current-runtime-baseline-proof-20261124.json`。
- `.cache/cleanup-current-runtime-source-proof-20261124.json`：45个现存修改文件 UTF-8、28个Python文件语法检查通过；查询表达式确认报告取数不再关联审计事件或聚合，草稿不再携带旧字段。差异空白检查通过。
- 核对临时PostgreSQL可执行文件、数据目录、进程33020和零客户端连接后正常关闭实例，55478释放，测试库与数据目录保留；日志为 `.cache/cleanup-current-runtime-postgres-server-20261124.log`。

本轮更改尚未提交；用户原有环境示例、Compose、部署文档、启动脚本、docker/mineru及上一轮身份参数修改保留。

## 上一轮闲置身份参数清理（2026-11-24）

- 删除 ProjectService、JobService、VersionService 从未使用的 company_id 构造参数，装配和现有任务取消测试同步；三个仓储仍接收 company_id 并负责公司隔离。
- 本轮扫描覆盖后端函数、常量、构造参数、实例字段及前端导出。框架回调签名、坐标契约辅助和分析归档的 PID 缓存参数都有实际用途，继续保留。
- `.cache/cleanup-unused-identity-backend-20261124.log`：统一后端入口的 Ruff、5项分层、63个 mypy 目标、982项离线测试及 OpenAPI 漂移检查全部通过。
- 本轮 Python 修改文件 UTF-8、语法和差异空白检查通过；原有环境示例、Compose、部署文档、启动脚本及 docker/mineru 修改已按内容摘要核对保留。

本轮更改尚未提交；上一轮清理提交为 `52234be`。

## 上一轮方法、参数与配置清理（2026-11-23）

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
