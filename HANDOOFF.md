# 前端界面重构交接

> **2026-11-16 审查问题修复**：修复两项代码审查问题。`drafts.py` 的缺件凭据改为严格嵌套输入模型，校验文件名、原文ID数组和资料ID数组；错误通过既有工具反馈返回同一Agent，更新问题时也校验沿用的凭据。最终范围比较按冻结标段目录统一编号、名称和别名，拒绝歧义简称，未进入目录的标段继续按原文比较。新增11项回归覆盖错误后纠正提交、父子节点与关系端点别名互认、不同标段及歧义拒绝。定向31项通过，统一 `scripts/check-backend.ps1` **1776通过／13跳过**（199.49秒），Ruff、5项分层及协议／真实装配mypy通过。未提交、未重载服务、未调用真实模型；下方真实语义验收未通过状态仍有效，live-v6冻结资源未覆盖此次修复。

> **2026-11-16 20:05 最终续接状态：核心实现完成，真实语义验收未通过，未上线**。v6开标50/run1465 completed（9模型/19工具/302.5秒，输入201166/输出18645）；商务50/run1461 completed（21模型/42工具/641.6秒，输入958515/输出40174）。两项source/config终态均未变化，最终正文等于所选草稿。完整人工semantic.json、audit-view.txt及历史在C恢复根live-v6/results。开标异议与线上抽K已正确，但程序仍混合“检查密封/电子解密”且自查放行。商务付款/文件交付改善，仍漏责任条款，未读c10/c69/c265核清期限，草稿错误引用c185代替c190；final关联问题被拒后清空问题record_ids，未决冲突仍留正文。独立缺件留存正常。不能计通过，未启动round2/3或13专题。
>
> **验证终态**：backend-v6-final.log 1765通过/13跳过，Ruff/5分层/mypy通过；PG恢复后pg-v6-retry.log **64通过**（196秒），覆盖恢复/真实装配/正式数据。首次pg-v6-focused.log在PG停机时8连接超时、1取消计时失败，已由恢复后同组全绿覆盖。此前PG全量249、前端67与typecheck、定位6项仍有效。本轮新增补读/上下文变更均在最新统一检查及专项中。源码冻结live-v6共338文件，worktree-v6备份133未提交文件，最后文档另同步。
>
> **无在途真实模型验收**，勿重复运行已有版本轮次；继续前先读semantic失败依据。C盘原生PG55456已恢复，三个隔离库保持；未重载业务服务、不启动WSL、不提交。下一步须解决同Agent自查未落实到正文与遗漏问题，然后新冻结版本首轮通过才冷启动复测，再13专题。避免继续堆同义提示或给代码增加语义否决/独立审查来掩盖失败；四附件仍缺。


> **2026-11-16 晚间：v6真实首轮在途**。原生PG55456在凌晨系统终止后已退出，首次v6启动连接超时、没有created.json也没有模型调用；使用原C盘pgdata恢复成功，未改业务服务。v6重试日志`live-v6/opening-1-retry.log`／`biz-1-retry.log`；开标报告50/run1465 exec62785，商务报告50/run1461 exec51942，均round1。先查terminal/progress再续接，不重复创建。
>
> 最新统一`backend-v6-final.log` **1765通过/13跳过**（109秒），Ruff/五分层/实际装配mypy全过；首次统一唯一失败是批量读取测试仍期待旧单侧1块范围，按新请求窗口修正后25专项过，再统一全绿。PG专项exec9604曾等数据库，现在已连接并在测试，日志`pg-v6-focused.log`。133个未提交文件严格UTF8/无NUL并备份于worktree-v6；338源码与live-v6逐字节一致。辅助pg_ctl启动命令exec41581已无pg_ctl进程但句柄可能仍在，勿因会话未退出终止PG。无上线、提交、WSL。


> **2026-11-16 00:20续接：v5两项均失败，v6已冻结待首轮**。v5开标49/1464 completed，45模型/50工具/17分52秒；初稿正确邮件异议被自查改错为冲突，未决问题又标resolved。v5商务49/1460 completed，78模型/80工具/33分16秒；期限改善但付款/例外遗漏、自查失实、保证金越界。两项semantic.json及audit-view.txt在live-v5/results，正文与最终所选草稿一致；不计冷启动通过。
>
> **新增工具修复**：research.py取消compact读取每侧1块限制，尊重请求窗口（常规总12块，元素完整性/上下文/证据总预算保留）；skill_agent.py上下文按草稿→关联完整原文排列并去重，草稿内只保留引文ID防止摘录挤占页面；公共Skill明确按record_ids选草稿并沿分页核对。反例先失败后通过。旧阶段工具自身限制未改。当前backend-v6.log统一检查exec21885、pg-v6-focused.log恢复/真实装配/正式数据exec9604在运行。live-v6已冻结338资源文件（包括上述改动），尚未启动真实轮。新辅助audit_run.py整理终态轨迹，必须另提供人工verdict才能生成semantic.json，不会自动判语义通过。无上线、提交、WSL。


> **单Agent验收续接：v4已失败结束，v5在途，勿上线**：v4开标48/run1463 completed，11模型/17工具/312秒，仍漏读c68前附表线上异议并遗漏c30开标后线上抽K；商务48/run1459 completed，19模型/32工具/约8分钟，未读c10/c63/c265期限，遗漏通用条款条件例外。两项semantic.json已保存，不能计通过。统一backend-v4.log为1763通过/13跳过。
>
> 最后两处Skill修改已冻结为恢复根`live-v5`（338文件）：商务区分输出边界与阅读范围，先取公告/前附表/填写期限；开标回读前附表整行，并提示chapter仅供导航。**当前开标49/run1464，exec6813；商务49/run1460，exec2590；均round1**。分别沿用两个隔离库、原模型/预算/资料，日志live-v5/opening-1.log、biz-1.log；先读terminal和progress核对终态，勿重复创建。无服务重载、提交或WSL。此段取代下方v4在途描述。


> **2026-11-15 23:25 单Agent真实验收续接：未通过，勿上线**：仍执行用户完整计划，无提交/WSL/服务重载。C根 `C:/Users/wph98/.codex/recovery/AI-tender-agent-led-20261115`。真实v1两轮已终态且semantic.json判失败：开标45/run1460为工具容器类型错误+后备503/断流/超时；商务46/run1457 completed但期限冲突、结算遗漏、专用例外丢失。v2开标46/run1461 completed但邮件/现场异议混用；商务47/run1458 completed但已读c265的“签订日起2年”错记缺失，未读c10/c63/c69，整条付款和交付因缺参数丢弃。v3仅开标47/run1462 completed，纠正程序缺项、异议移出草稿，但误称没有优先规则且将尚未解决的问题resolved，仍失败。三版均保存semantic.json及初稿/自查/修改/最终轨迹，不计冷启动通过。
>
> 新修：WorkspaceTool只对具有Pydantic反馈能力的工具将完整JSON参数错误交回同一Agent（内部x-tender-tool-validation不发供应商）；非法JSON/名称/ID/截断仍拦截。新增类型反馈、批检索子查询断连不重复扣预算、父路径变化、关系端点变化及范围扩大反例。最终范围比较已取证原文标段名，不依赖另一专题先发布数据库ID。错误反馈带字段；坏内层JSON字符串报告位置而不回显正文。Skill要求保存后get_research_context回读再自查、先核对项目身份/方式/优先规则，分开已知义务与缺失参数，删除争议正文时仍保持问题open；商务与开标细则补对应反例。
>
> **当前真实在途（勿重复创建）**：v4冻结338文件、`live-v4/acceptance.py`，开标exec66246，商务exec87097，均round1、新建报告、原模型/资料/80模型100工具3600秒。先读`live-v4/<opening|biz>-1.log`和results目录，报告/run以created/progress为准。两个库仍C原生PG55456的parse_1349_other_acceptance / parse_1349_acceptance。v4对应最新源码；v1/v2/v3冻结目录不可覆盖。先两项首轮语义通过才各冷启动2、3，再13专题；四份附件仍缺。
>
> 验证：`backend-v2-final.log`1762通过/13跳过；`pg-v2.log`249通过（219秒），`pg-v3-focused.log`25保存点恢复/数据读取通过；前端types-v2通过、tests-v2为67通过。新增错误反馈之后19专项过，统一`backend-v4.log`正在运行exec1362。源码与文档有本轮新增未提交变更，最终必须再核对日志、严格UTF8/diff与更新工程24及本交接。尚未安全加载三服务。此段取代下面v1“正在运行”的旧状态。
>

> **2026-11-15 单Agent链路重构续接（真实验收待完成，勿直接上线）**：用户已授权完整实施每专题单Agent＋Skill方案。生产已接`skill_agent.py`，新增`drafts.py`和公共流程Skill，13专题资源同步；协议`skill-agent-v1`／runtime v6。草稿版本、自查、稳定问题ID、回放、补跑、独立缺件与最终原子发布已实现；重跑不清空旧正式数据，正式数据未变不增加快照版本，v5历史可读但不可执行。没有提交、启动WSL或加载业务服务。
>
> 验证根`C:/Users/wph98/.codex/recovery/AI-tender-agent-led-20261115/`：`backend-final2.log`统一1755通过／13跳过（123秒），`pg-final.log`隔离PG249通过（258秒），`pg-recovery.log`10项包含研究、草稿、自查、修改、final五保存点断连恢复通过；前端67单测、typecheck通过，浏览器92项中88通过，4失败修复后新进度2项及定位4项共6通过（`frontend-location-final.log`）。最后新增父路径／关系端点一致性校验已在PG249中覆盖，仍需补专门反例并统一复验。
>
> **真实首轮准备/运行现场**：C盘PG55456。冻结338源码文件于`live-v1/apps/api/src`，脚本`live-v1/acceptance.py`；开标隔离库`parse_1349_other_acceptance`新报告45，商务`parse_1349_acceptance`新报告46，各round1，exec开标13366／商务96636。先读`live-v1/<opening|biz>-1.log`及`results/<module>/1/{progress,terminal,result}.json`核实是否在途，禁止重复收费创建。先前两次启动分别被数据库地址检查和历史派生标段检查拦住，均无模型请求；已显式设置隔离库、将本次报告lot_settings冻结回原43的空数组（项目目录不变），使用`--execute-created`仅在报告waiting且零运行行时继续。原预算80模型／100工具／3600秒，模型配置和资料保持。真实准确性未判定，两项通过后各再冷启动两轮并扩展13专题。四份附件仍缺。
>
> **操作注意**：每条exec独立设置C盘RUFF_CACHE_DIR／MYPY_CACHE_DIR；PowerShell重定向默认UTF16，日志用`Out-File -Encoding utf8`。旧测试日志部分UTF16可Get-Content识别，源码一律UTF8。勿直接凭历史PID杀进程。前端现有3000服务PID17932被复用验收，不是本轮启动。保存点恢复和旧参数用例已迁新协议，旧阶段纯函数测试仍保留。待继续：真实验收、完整工具契约复查、最终文档状态、活动任务检查后安全加载三服务、交接收尾，不自动提交。


> **2026-11-15 20:02 本轮验证收尾**：单Worker部署完成，当前三个服务及现场见下段。统一入口1748通过/13跳过中的3个失败（一次5秒计时超时、两项mypy内部缓存错误）在新C盘MYPY_CACHE_DIR下全部复验通过（169.43秒），日志`single-worker-checks-retry.log`；没有修改计时上限或放宽类型检查。Ruff/5项分层、46项启动检查、3项队列覆盖、PG全量247通过。相关测试进程已结束。默认进程精简目标已完成；原解析准确性、缺件跨包收敛与完整13专题验收仍待继续，不能标记原解析目标完成。

> **2026-11-15 19:57 单Worker切换完成**：正式脚本已清理用户19:23启动的旧六服务，当前仅API31456、全队列Worker34556、Beat36580。Celery inspect确认唯一节点`tender-worker@DESKTOP-NAL6HD9`消费全部五队列，active/reserved均空，业务六类活动均0；API健康，配置指纹与切换前完全一致。记录C备份根`single-worker-pre-switch.json`、`single-worker-after.json`。源码/文档等47个未提交文件已严格UTF-8与diff核对并备份至`single-worker-worktree/`，无提交。PG全量247通过（529.20秒）；统一1748通过/13跳过，3失败为5秒增量计时超时和mypy两项INTERNAL ERROR，正用新C缓存复验exec44476，日志`single-worker-checks-retry.log`。Ruff及5项分层通过。
>
> 完整生产审查回放已找到四包最终结果，均在`evidence-first/.tmp/production-replay/results.json`：开标材料主包failed，补充包返回空issues；商务主包157.485秒仍read、补充包210.703秒provide_input（实际附件转引c208在补充包）。因此两项人工定向对照改善不能外推完整生产通过，商务分包结论合并仍需核对。没有在途回放请求，勿再沿下方旧“商务在途”状态处理。

> **2026-11-15 19:53 用户要求恢复简单启动**：用户指出默认四组Worker没有必要，明确“继续”执行合并。`scripts/start-backend.ps1`、Compose、环境模板与启动/架构文档已恢复默认API＋单Worker＋Beat，单Worker消费`convert,parse,tender,poll,analysis`，7线程沿用原本地总执行槽位。保留旧scheduler/poller/analysis身份识别用于清理。46项脚本身份/预检和3项队列覆盖通过，Compose解析及PowerShell BOM通过。业务六类活动、四个旧Worker active/reserved均0，配置指纹`93b6f139e2223328759b87e5c82290f2076d3d1b54815024ea77ac5c5f129472`，记录C备份根`single-worker-before.json`。尚待统一检查、PG验证与安全切换；exec47269统一、70758 PG，日志`single-worker-backend.log`和`single-worker-pg.log`。不要重复启动服务或测试。
>
> 解析续接新增修复：审查原文先行、先解释适用性再判断支持性；规则指纹进入请求与缓存身份，防止规则更新后复用旧通过回执。缓存反例先失败后通过，80项专项通过。C备份根`input-findings/.tmp/evidence-first-replay/results.json`两项对照均改善（材料否决、商务provide_input），但完整生产包回放`evidence-first/.tmp/production-replay/`材料主包失败：覆盖回执格式、后备503和输出未完整结束；补充材料包返回空issues。回放进程已终止，商务在途请求结果尚须核对，不重复收费重跑。新审查提示附有尾部指令，旧测试模型仅解析末行JSON导致8项PG和1项单测失败，已修正夹具按protocol JSON行解析；另2项日志启动子进程30秒超时待统一复验。G盘Ruff缓存损坏出现NUL及panic，统一重跑改用C盘RUFF_CACHE_DIR，源码没有因此改动。完整解析准确性/效率目标仍未达成。
>
> 操作事故：清理旧验证进程时错误包含另一`G:/aicode/docx-sdk`工作区pytest PID31024/28832，已向用户说明误停，未自行重跑他项测试。此后进程操作须以当前工作区、命令行和创建时间核对身份，禁止沿旧PID清单直接终止。

> **2026-11-15 续接指定会话**：已读取`01a1d9e8-09a1-7a43-ac99-8e440e63300b`及原目标。其23:55前的落盘进度晚于下方22:50交接：重复新增返回原record_id、适用性回执、缺件线索传递均已在源码；最终统一**1750通过／13跳过**，PG全量**247通过**，日志C备份根`input-findings-backend-final.log`、`input-findings-pg-final.log`。335源码逐文件与`input-findings/source-manifest.json`一致，指纹`3d4206fc1e1af2668f317703c84114b279f5e196c44420138835dbe3c8969c18`。
>
> 旧真实轮均已终态：开标44/run1458 completed/verified，18发布、15分52秒，人工准确性失败（2018日期、现场材料、A/B程序、重复新增）；商务45/run1455 completed，43分6秒、6发布、13个待核对问题。三条适用性定向复核只拦住旧日期和两套程序。`input-findings/.tmp/context-replay/results.json`进一步确认：人工补c57/c59/c68/c69后到场材料仍supported=true；生产分包传缺件线索后商务仍返回read。不能把自动化检查当作语义通过。
>
> C盘原生PG55456于11-15 01:43停止；本次19:04使用原pgdata及显式`-p 55456 -h 127.0.0.1`恢复。当前API8300未监听；尚未加载23:55补丁。正在进行原文先行、依据先于判定的两项顺序对照，脚本C备份根`input-findings/replay-evidence-first.py`，exec63470，输出`input-findings/.tmp/evidence-first-replay/`，禁止重复收费启动。原模型、原文、草稿和额度保持。完整13专题正常资料验收仍缺四份附件；不启动WSL，不提交。

> **2026-11-14 22:50 最新续接**：已读取指定会话的原始用户任务及本交接。开标44/run1456已completed/verified，22:26:13–22:36:46、10分33秒、7发布，但人工核对**准确性失败**：旧广州地址、到场原件材料、A现场/B电子两套程序仍被支持。旧exec90465已回收。材料包缺c68/c57/c59，流程包虽有c68/c69仍误判适用性；旧原文证据和终态完整保存在post-recovery目录。
>
> 新补丁：按工作读取的草稿正文及每个长正文片段带修改用record_id；两项恢复反例先失败后通过。研究/审查明确先判项目身份、已选方式和原文优先顺序，再提取生效要求；控制依据关联全部受影响工作并保留引用或显式事项依赖。没有按地址、年份或标题硬编码删除。源码`3b11ddff0a66abc6acf8a90b57745b38e4c4122053ef6b5e733b95c55d48b63e`，工作区与C active335文件逐字节一致；d988源码存备份根source-d988074c。
>
> **真实开标新轮在途**：PG55456、报告44/run1458、exec **5366**，22:48:32冷启动，原材料/配置/额度一致。脚本`active/.tmp/parse-1349-live-applicability.py`，产物`active/.tmp/parse-1349/live/opening_requirement_parsing/applicability/`，只读脚本`active/.tmp/parse-1349-inspect-applicability.py`。勿重复启动、勿修改在用源码。统一首次1734通过/13跳过、1个旧手工夹具无id失败；补齐生产必有id后统一重跑exec **53868**，日志备份根applicability-backend-final.log。业务服务仍22:27的d988，尚未加载此补丁。

> **2026-11-14 22:27 续接进度**：到期恢复补丁最终统一1733通过／13跳过（241.12秒）、PG全量247通过（285.57秒），Ruff/分层/mypy通过，39049/92987已回收。旧C库1452/1453遗留预占已用同一仓储逻辑清理，保存内容及deadline不变，`orphan-settlement.json`：商务40ok/12error/3unknown，开标2ok/1error/1unknown，均无running请求。
>
> **新开标正在执行**：C盘PG55456，报告44/run1456，exec **90465**，源码d988074c；脚本`C:/Users/wph98/.codex/recovery/AI-tender-20261114-2015/active/.tmp/parse-1349-live-post-recovery.py`，产物`active/.tmp/parse-1349/live/opening_requirement_parsing/post-recovery/`，勿重复启动。只读脚本同目录`parse-1349-inspect-post-recovery.py`，传`opening_requirement_parsing`；源码及产物在C盘，部署环境仍读取原G盘.env。G盘旧PG55455已正常停止。
>
> **22:27已加载最终d988补丁**：54868已回收，前后六类活动均0，API健康，配置值与发布指纹相同。PID api18360、documents27536、scheduler41700、poller36844、analysis40940、beat26208。正式启动脚本日志在C备份根`final-services-load.log`。工程23/24已补存储根因、迁移校验及新恢复修复；完整附件路径问题仍等待用户。

> **2026-11-14 22:20 最新状态：存储故障已隔离，验收待新补跑**：20:13原生PG55455写WAL遇Windows483（致命设备硬件I/O错误），系统同刻及20:06有Disk0的154事件；G盘位于Disk0。两项真实进程均退出，不能再沿用下方“在途”。PG20:15自动恢复后已导出两库；当前G盘PG55455已正常停止，业务API健康。
>
> **C盘独立备份与运行目录**：`C:/Users/wph98/.codex/recovery/AI-tender-20261114-2015/`位于另一物理Disk1。766个文件（约25MB）逐一SHA256通过，含未提交源码/文档/全部1349取证；两个自包含dump约92/91MB。备份的335源码文件仍固定10c4460d，不覆盖。新原生PG **55456**，数据`pgdata/`、程序`pgsql/`、日志`pg-server.log`，已恢复`parse_1349_acceptance`及`parse_1349_other_acceptance`，另建隔离测试库`parse_1349_tests`。两库17类关键表（含完整检查点、调用账、原文及模型配置）与原库内容散列一致：`database-restore-audit.json`。
>
> 两轮旧期限均已过，经生产执行器按原时限收尾：商务45/run1452、开标44/run1453在C库均failed，原因“模块总时长预算已耗尽，恢复不会重置时限”；未新增模型请求。结果位于备份根的`.tmp/parse-1349/live/<module>/delivery-recovered/`，对应脚本`.tmp/parse-1349-live-recovered.py`；终态收尾进程已回收。原商务仅复核12/21，重复草稿及缺件收敛仍未通过。开标新轮在硬件中断前只有2次成功模型、1次records容器类型错误及1次未返回请求，不能计语义通过。
>
> **新补丁已写，最终验证中**：到期检查在claim前退出导致旧预占及llm_call_log永远running；`AgentRunStore._recover_calls`复用既有幂等结算，abandon先取当前库运行事务锁，再原子终止pending并结算已保存成功、其余unknown，保护真实持锁执行者。新增`test_expired_recovery_settles_saved_results_and_closes_orphan_attempts`先失败后通过；11项恢复/跨库锁/硬配额专项通过。统一检查exec **39049**、PG全量exec **92987**，日志在C盘备份根`expired-recovery-backend.log`及`expired-recovery-pg.log`。**业务服务仍是20:08的10c版本，尚未加载这项新补丁。**
>
> 新源码指纹`d988074c274066ee389d5b89a4446183293ffe738000838ab59969d025117e4c`，335文件已复制并校验到C盘备份根`active/apps/api/src/tender/`，元数据`active/source-manifest.json`。准备好的恢复补跑脚本`active/.tmp/parse-1349-live-post-recovery.py`，读取原G盘部署配置但源码与运行产物在C盘；启动须设`PYTHONPATH=<active>/apps/api/src`、`PYTHONDONTWRITEBYTECODE=1`和端口55456的对应DATABASE_URL。脚本用原报告mode=resume创建新attempt，原材料/配置须一致，`post-recovery/created.json`防重复；**尚未启动**。仍需先结算旧终态遗留调用账（调用同一恢复仓储逻辑，不能推测成功），再完成检查/加载/真实补跑。四份完整附件位置仍待用户提供。

> **2026-11-14 20:08 最新续接，解析目标未完成**：已读取会话`01a1d93b-eccd-75d0-915e-1187443c9794`，其19:25落盘内容晚于下方19:10交接。跨库锁过滤已覆盖全部8处遗漏查询（另有1处原已正确），候选原文超容量分片及大块只重验本块已实现。全量回归发现新加covered/unsupported强拒绝造成6项失败，现改为沿用同次明确否决生成needs_action与修复问题，保持原结论不可发布且二次校验幂等，避免整包重试。
>
> 最终源码`10c4460d0334cb7ff7ef61a4d071ccb534ca5f8c6c722e303d8fdddb0d64d845`。统一后端**1733通过／13跳过**（113.84秒），Ruff/五项分层/协议与真实装配mypy通过：`.tmp/parse-1349-resume-backend-delivery.log`；PG全量**246通过**（258.54秒），最终否决处理改动后核心PG**60通过**（233.44秒），分别`-resume-pg.log`、`-resume-pg-final.log`。91项否决与语义专项通过；31个改动文件严格UTF-8及diff通过，审计`.tmp/parse-1349/resume-file-audit.json`。测试会话已回收。
>
> **当前在途，勿重复创建**：新开标delivery脚本`.tmp/parse-1349-live-delivery.py`，隔离库`parse_1349_other_acceptance`报告44/run1453，exec **60130**；使用restart冷启动，产物`.tmp/parse-1349/live/opening_requirement_parsing/delivery/`，启动前source/reference/runtime与原报告43逐项相同。只读用`.tmp/parse-1349-live-inspect.py --delivery opening_requirement_parsing`。原商务convergence报告45/run1452，exec **24636**对应进程40264仍存活，最近复核9/21，原863d源码已保存在`.tmp/parse-1349/source-863d48a0/`，不能视为最新代码验收；原开标convergence44/1451已failed，15分48秒，回执错误及503，旧46841可回收。旧原业务43保持取消。
>
> **20:08已安全加载业务服务**：正式`scripts/start-backend.ps1 -Force`完成，API健康，前后六类业务活动均0、0022已应用，配置值及发布指纹相同。PID api10896、documents32132、scheduler50016、poller46116、analysis43496、beat39004；日志`.tmp/parse-1349-resume-services-load.log`，18186已回收。新开标1453已running并正常发出模型请求，未被另一库旧商务锁阻塞。不更改模型/参数/额度，不设置300秒限时，不新增app、不启动WSL、不提交。
>
> 真实商务恢复又新增多条同标题同范围的付款/期限事项，较旧已核实内容更简略，审查量扩大；需继续核对终态和恢复时的重复新增问题。已再次询问四份完整附件所在项目/目录，尚待用户回复，完整资料13专题验收仍缺基线。工程23/24已补最新根因；待新开标结果逐项核对网上方式、时间、异议、旧广州纸质片段及完整定位，再更新最终状态。

> **2026-11-14 19:10 最新续接，目标仍active**：源码已更新为`863d48a0096da0bd6abf6bed22c8639748e590cb000298eb5309499bbf7b0c7e`。最终商务45/1451已完成：28分39秒、13发布、8个read问题，code_unchanged=true；开标44/1450已partial：15分51秒，地点条目加候选原文超容量。两个final会话63849/53738均已回收。随后修复待补读问题被当作固定结论缓存、缺件合并丢说明/依据、研究叙述和旧问题重复占容量、共享原文导致错配复核问题；真实跨包check使用partition/covered_here，各包必须实际核对，不能互相deferred。原开标回放4包，含纠错预留8857/11913/11953/11830估算token，全部原文保留；旧商务14问题回放8请求，全部有责任包及完整依据。
>
> 统一后端**1721通过／13跳过**（107.33秒），后加3项分包门禁专项通过，Ruff/分层/mypy通过；日志`.tmp/parse-1349-convergence-backend-final.log`。真实PG全量**238通过**（217.02秒），`.tmp/parse-1349-convergence-pg.log`。source最后仅在PG启动后调整模式字段的容量预留与格式，统一检查包含最终代码。代码未加载业务服务，仍是18:12版本。
>
> **真实补跑进行中，勿重复创建或修改src干扰语义验收**：脚本`.tmp/parse-1349-live-convergence.py`，产物`.tmp/parse-1349/live/<module>/convergence/`。商务库`parse_1349_acceptance`报告45/run1452，exec **24636**；开标库`parse_1349_other_acceptance`报告44/run1451，exec **46841**。两者原生PG55455，原模型/材料/额度，created.json防重复。只读观察`.tmp/parse-1349-live-inspect.py --convergence`。
>
> **新发现待修复：跨库配额锁误算**。商务1452排队无模型请求，是`adapters/pg/repositories/analysis/runtime.py`的_OCCUPIED/_FIRST_WAITING/_REAP/_REQUEUE/_CANCEL五条pg_locks查询未过滤database，另一库开标1451的锁误匹配本库旧1451，max_inflight被误占。不是业务源文件或模型故障。开标结束释放锁后商务可自然开始。已添加`test_other_database_advisory_lock_cannot_occupy_or_protect_local_run`，使用现有postgres库的独立命名空间锁；claim/reap/requeue/cancel四例均稳定失败（原反例）。**尚未修改生产SQL**，待当前语义验收终态后加current_database()过滤并复验、统一检查和安全加载。原业务43保持取消，模型参数/300秒/新增app/WSL/自动提交约束保持。

> **2026-11-14 18:25 续接**：最终商务报告45/run1451仍运行（63849），初审5/11；开标已用冻结business.dump的第二独立库`parse_1349_other_acceptance`启动最终轮，报告44/run1450、exec **53738**，产物`.tmp/parse-1349/live/opening_requirement_parsing/final/`，脚本`.tmp/parse-1349-live-other.py`。两轮源指纹仍7f4591fc…，禁止重复启动；`.tmp/parse-1349-live-inspect.py`同时只读更新两轮状态、账和输入一致性。开标约3分钟进入4请求初审，草稿混有旧纸质地址，必须等审查修复后逐项验收。商务范围已全部确认common，初审保留质量合格并追到c208，待核对缺件收敛。
>
> 另外已复现**缺件问题合并丢依据**：`quality.merge_issues`先read后provide_input时只升级action，丢失missing_input并保留旧补读detail。新增`test_cross_topic_missing_attachment_keeps_confirmed_details_and_proof`两种顺序反例，当前1失败/1通过，**尚未修改src**，待两轮自然结束后补上确认说明及依据，再统一检查。原始八专题回放`.tmp/parse-1349/coverage-diagnostic.json`确认项目概况的互相deferred在现代码已无跨包责任；否决qualification及保证金refund仍有同范围跨包，需继续真实验证，不放宽门禁。

> **2026-11-14 18:12，13:49批次故障修复续接（最新状态，未提交，已加载）**：项目16／报告43已于16:36取消，原运行1437–1449均终止；下文14:07“报告43仍运行”已过时。本轮修复最终供应商批次工具schema丢失、关键词被余弦阈值错误过滤、首次规则读取误算空转、发布与独立审查语义冲突、大块重复扩邻域及坏审查回执二次崩溃，区分排队和执行耗时。随后真实轨迹再修复章节归属丢失、补充包重复核对、旧复核问题未带原文、累计错误ID平方反馈及纯哈希错误文案。完整现场`.tmp/parse-1349/`，工程23/24记录根因和原文基准。
>
> 最终统一后端**1712通过／13跳过**（100.67秒），Ruff、五项分层及协议／真实装配mypy通过，`.tmp/parse-1349-backend-acceptance.log`；最终PG全量235通过、3项旧id/text夹具失败，同步章节字段后3项复验通过（7.41秒），`.tmp/parse-1349-pg-delivery.log`及`-pg-fixtures-fixed.log`。初版全量238通过留在`-pg-full.log`。相关exec测试句柄均已回收。27个改动文件严格UTF-8与diff通过（后续文档更新应再核对），`.tmp/parse-1349/file-audit.json`。
>
> **最终商务验收正在执行，禁止重复启动或修改src干扰此轮验证**：当前业务库完整副本`parse_1349_acceptance`，原生PG55455，项目16／报告45／run1451，exec会话**63849**，脚本`.tmp/parse-1349-live-final.py biz_standard_parsing`，产物`.tmp/parse-1349/live/biz_standard_parsing/final/`。源码指纹`7f4591fc9218b8b217df27b24187eae3b81c32cf24829f571f47b76cadf79ea6`。约两分钟已从c63提取合同签订起两年、质量合格及预付款28天发票条件，继续研究。`progress.json`可读，必须结合exec会话判断是否在途；只读诊断脚本`.tmp/parse-1349-final-progress.py`保存当前状态。尚须核对真实商务附件转引c208、完整付款条件、矛盾缺口消除及最终引用；不自动resume或重复收费。
>
> 原商务诊断轮报告44/run1450已于18:05自然completed/needs_review，44分52秒、7发布／11草稿、22问题，48模型尝试（29ok／13error／6unknown）、24工具（23ok／1error），无pending预占及活动报告，54850已回收；终态code_unchanged=false。两年期限补出后仍留“期限未找到”、空白合同格式误称专用前附表，3条付款被缺比例整体否决，准确性未通过；`semantic.json`已记录。最终规则另明确独立缺金额不得否决正确付款时点。原文`.tmp/parse-1349/source-blocks.json`：c10/c63/c265为两年，c218是合同格式；四附件转引c142/c208/c263/c280。14问题离线复核重放责任／事项／证据全部完整，`repair-replay.json`；计划9→11，实际效率待最终轮。
>
> **18:12已安全加载最终业务服务**：前后六类活动均0，0022已应用且仅更新说明，config_item除description外及全部config_release指纹相同，API健康。正式脚本新PID api35988、documents45044、scheduler37552、poller32240、analysis38836、beat41340；日志`.tmp/parse-1349-business-final-load.log`及`runtime-before/after.json`，迁移前后原快照另存`runtime-migration-before/after.json`。隔离63849持续运行。下一步继续最终商务及其他代表性专题真实验收、逐条语义和定位核验、更新文档。5分钟仅性能预期，不加300秒限时；不改模型，不新增测试app、不启动WSL、不自动提交。解析goal仍active，真实完整准确与效率目标尚未达成。

> **2026-11-14 14:07 审查问题修复交付（未提交，业务活动期间未加载）**：用户要求修复四个审查问题。已按专题自身输入签名保留局部restart后其他needs_input专题的新增资料信号，页面input_changed与resume事务统一，执行器保存完整项目／参考快照；短问答引文按完整大块字符范围构建真实单页／跨页定位；非对象missing_input转为既有模型协议错误；前端定位、PDF角标及反查按来源／版本／批次／元素／页码／bbox去重，同元素不同区域独立、同区域合并。大块ID及入库规则保持。
>
> 最终统一后端**1688通过／13跳过**（110.74秒），Ruff、五项分层及协议／真实装配mypy通过，日志`.tmp/review-fixes-backend-delivery.log`。最终全量真实PG**238通过**（252.34秒），`.tmp/review-fixes-pg-full.log`；后端专项67通过、执行器兼容及完整快照37通过、真实PG事务／模块输入变化／跨页定位16通过，前端类型与67单测通过。已补齐代表生产契约的旧执行器报告夹具，并加入暂不可读及参考资料签名断言。
>
> 14:07业务库仍有项目16／报告43运行（13:49创建）：run1437项目概况running，1438–1449其余十二专题pending；job/模型测试/index/answer活动0，API健康。现六服务PID api40980（实际8300监听14140）、documents39868、scheduler9144、poller38752、analysis44688、beat42260，**不得中断此报告或直接Force重启**；本次补丁尚未安全加载。只读现场`.tmp/review-fixes-final-inspect.json`，全部67个未提交文件严格UTF-8与diff通过。无新迁移／索引规则修改，不需重建索引、不调整模型或300秒限时，不追加测试app、不自动提交。后续待业务活动全部结束后，再只读核对并使用正式脚本安全加载；工程23已同步。

> **2026-11-14 13:23 大块切片入库与索引重建交付（未提交）**：用户明确要求切片入库时处理好，后续检索、模型选证和定位统一使用合并大块，不要求模型识别内部原始小块。现`domain/knowledge/text.py`按明确章节、编号、相邻正文与表格引导句合并，目标1800字符／最多12个解析片段；`locations`在入库前合并各页真实坐标及文字范围，跨页继续使用同一大块ID。新索引只存大块，ID为`s{source}r{run}g2c{ordinal}`；分析研究、独立审查、发布和定位沿用最终大块选证。历史小块ID不重新解释，旧attempt恢复保留旧身份，重新解析使用新版本。原文转换不重跑；模型不需要输出引用原文或内部元素ID。
>
> 最终统一检查 **1679通过／13跳过**（101.48秒），Ruff、五项分层、协议／真实装配mypy通过，`.tmp/knowledge-context-loaded-backend.log`。最终全量真实PG **233通过**（240.07秒），`.tmp/knowledge-context-delivery-pg-full-fixed.log`；选证过滤与跨页定位专项6通过。旧夹具的两个相邻同文段现在正确合为一块，因此将最终选证过滤场景改为两个有明确编号的独立条款，保留真实过滤和坐标断言，没有调整生产规则迁就旧小块数量。
>
> 13:21安全加载前只读核对report/run/job/模型测试/index/answer活动均0，业务迁移0020→**0021_knowledge_context**完成，加载六服务：api26292（实际8300监听41756）、documents14560、scheduler20584、poller42920、analysis43924、beat40920。旧索引由正式调度重建，索引17–26均completed。当前项目15/source13/run6的新索引**23／版本2／320块／嵌入模型4／1024维**；历史索引16／1130块保留。新旧原文按顺序对照无文字丢失，块数减少71.7%，50字符以下823→96。实际业务库检索只返回g2大块ID，52个跨页块的128处页级定位全部回查通过，`.tmp/knowledge-context-live-smoke.json`；配置绑定保持原值。加载及迁移日志`.tmp/knowledge-context-services-load.log`、`-business-migration.log`，终态业务活动均0、API健康。前端3000继续复用，按用户要求不追加测试app；5分钟仅作快模型预期，不设置300秒限时。
>
> 本次大块版本的真实供应商分析冷启动／补跑与完整资料13专题三次验收仍待继续，不能把上轮小块版本轨迹计为当前版本验收。旧delivery项目概况报告45及开标报告43均已completed，项目概况保存resume-noop，开标目录没有resume记录；相关旧会话已结束，不要沿用下文“仍活动”的历史状态。完整资料基线仍缺四份转引附件，继续依据既有验收目录收集与核对，不覆盖旧记录或自动提交。

> **2026-11-14 解析全面修复续接（未提交，最终真实验收进行中）**：继续用户批准计划。补齐研究与审查收敛：当前有效审查已无问题时关闭旧受阻任务、转引和空主题；不伪造公共范围或不适用证明。已审主题的待核对列表只消费审查问题账，清理旧关键词／覆盖／主题等程序缺口；异常工作账记录执行异常。新协议把摘要中的已支持事实与独立缺失说明交给独立审查，不再按“未载明”等关键词整条删除；授权仍由代码校验，纯不存在断言仍需审查支持。失败提交清理悬空草稿索引，保留待办。新增5项语义回归及真实形状反例，专项20项通过；上一版统一1654/12及PG50通过，最终统一和全量PG继续。
>
> 用户最新要求：不追加测试app流程，Chrome正常使用即可；5分钟只作模型快时的预期，不新增300秒限时、不作为验收门槛。Chrome142.0.7444.176桌面1440×900／手机390×844真实报告42的四组开标业务列及PDF第24页p24b1定位均正常，无溢出和浏览器异常，`.tmp/analysis-overhaul-chrome-web.json`及截图。
>
> 12:03最新统一1657通过／12跳过，Ruff／五项分层／协议与真实装配mypy均通过，`.tmp/analysis-overhaul-final-backend.log`。全量PG228通过（启动早于最后历史缺口清理），最终代码核心PG会话78139仍执行，`.tmp/analysis-overhaul-final-pg.log`。当前最终源指纹`d62038a6ca5fa620027c6b54a9cf16d6b7d2c0ea66701a78ec26397e33cec0a0`，`delivery`冷启动均应使用此版本。最新补丁尚须安全加载；不得重复启动当前basic delivery，opening converged仍在初审。
>
> **12:06最新现场覆盖上述待办**：最终代码PG核心50通过（117.89秒），`.tmp/analysis-overhaul-final-pg.log`；41个改动文件严格UTF-8及diff检查通过，源码仍d62038a6…。12:04–12:06加载最终全部六服务，前后业务report/run/job/llm_test均0，API健康；PID api33152（实际8300监听44476）、documents31692、scheduler44064、poller26280、analysis22520、beat20856，`.tmp/analysis-overhaul-final-load.log`。前端继续复用3000。
>
> 为保留旧opening的在途调用，创建独立冻结库`overhaul_opening_delivery`，使用复制的`.tmp/analysis-overhaul-opening-delivery.py`运行最终opening `delivery`，会话58539、报告43/run1431，目录`opening_requirement_parsing/delivery/`，原文1130块及模型/参数/3600秒/额度与原冻结一致。**不要用原`.tmp/analysis-overhaul-live.py`重复启动此opening目录或改写已有created.json。** 当前最终basic `delivery`会话82994、报告45/run1433，约7分半初审1/2；最终opening约2分钟研究。旧opening `converged`会话67470约26分钟初审3/4，继续自然结束，不能作为最终验收。三个真实会话均保持在途，不取消；最终两脚本各自结束后自动尝试resume（verified或确认缺件同输入保存no-op），配置/材料/代码变化则停止。尚须真实成果逐项语义、问题、用量、恢复及定位核对，更新工程23/24/交接，完成最终UTF-8/diff检查，不提交。
>
> 11:44–11:46安全加载前后业务report/run/job/llm_test均0，六服务健康：api29352（实际8300监听20464）、documents7468、scheduler7048、poller28648、analysis35976、beat41420。该进程版本早于后续缺失语义及历史缺口清理，最终检查后须再次安全加载。日志`.tmp/analysis-overhaul-convergence-load.log`。原生PG55455保持；保护已有库及收费调用，不重导入、不取消。
>
> `converged`轮启动代码7f68b24c…，之后发现上述根因，不能作为最终代码验收。项目概况报告44/run1432已completed，17发布/18草稿，4个真实问题，因指纹变化未补跑；opening报告45/run1433约18分钟研究／修复仍活动，会话67470，结束后指纹检查停止。**最终项目概况`delivery`轮已从零启动，会话82994，目录`.tmp/analysis-overhaul-acceptance/project_basic_info_parsing/delivery/`，代码含全部当前修复；不要重复启动。** 等opening在途结束再启动其`delivery`轮；脚本自动补跑同目录且配置/材料/代码必须一致。首个有用量回执Nemotron35仍basic5940、opening5389，最早无回执尝试保持未知。
>
> 最终统一会话53333，日志`.tmp/analysis-overhaul-final-backend.log`；全量PG会话8936，日志`.tmp/analysis-overhaul-delivery-pg-full.log`（启动早于最后历史缺口清理）。真实结束后收集语义、问题、用量、耗时和定位，更新工程23/24及交接，UTF-8/diff检查，不提交。完整资料13专题连续三次仍需四附件完整基线；已异步询问使用哪个已有项目或本地目录，当前继续两专题缺件场景。

> **2026-11-14 解析模块全面修复实施（未提交，11:28已加载，真实验收继续）**：按用户批准计划新增restart/resume，restart事务清理所选专题及自身报告汇总，新attempt/线程不继承旧状态；resume保留有效证据、草稿及公开ID，旧未决问题重新进入研究，新增材料失效旧缺件／审查缓存和旧版回退。执行status与quality_status分开，正常审查结束可completed＋needs_review/needs_input；容量及服务故障仍为执行未完成。问题身份按类型／范围／事项／规范目标稳定，跨主题合并责任，独立缺口及待补材料不撤销无关结论。
>
> 模型只输出摘要与必要块ID，逐事项候选和包内交付分别校验；内部审查完整原文，展示摘录由代码匹配并保留条件例外，失败时保留真实块入口。前端仅冻结业务列和title_column、无额外重复列；完成／质量／历史模式分别展示，缺件同输入禁用自动补跑，定位直接打开原文。
>
> 最终统一后端`.tmp/analysis-overhaul-backend-terminal.log` **1652 passed/12 skipped**，Ruff／五项分层／协议和真实装配mypy通过。全量PG原轮224通过、3项旧接口断言失败，改显式resume后最终核心74通过；清理与新attempt原子入账、故障回滚和新增附件恢复6通过。前端类型检查、65单测、桌面／手机80项synthesis E2E通过。记录工程14/21/23/24，禁止自动提交。
>
> 11:28加载前及11:30后业务report/run/job/llm_test均0，六服务健康；PID：api30312（实际8300监听44844）、documents28484、scheduler39148、poller31480、analysis36156、beat43824；前端3000复用。用户补充：5分钟是模型较快时接近的性能预期，当前不配置300秒限时、不作为验收门槛；冻结3600秒／模型／参数／额度保持。
>
> 原生PG55455复用既有冻结库并创建`overhaul_tests_clone`、`overhaul_basic`、`overhaul_opening`，保护旧验收数据；失败的pg_restore库`overhaul_tests`保留。真实探索首轮两个隔离库均报告43/run1431：项目概况约15分钟初审4/9，开标约15分钟修复复核2/3，**不得取消在途收费调用或重复启动同轮**。脚本`.tmp/analysis-overhaul-live.py`会保存restart-result/visible/records；启动后补了转引缺口支持性边界，首轮不是最终代码验收，结束后因指纹变化停止，不自动补跑。最终版本可用同脚本第三参数`final`建立新输出目录，务必等对应探索终态后启动，避免脚本取消尚活动的隔离报告；最终冷启动结束后脚本自动尝试resume（缺件同材料或全部verified时记录no-op）。活动会话basic20938、opening99176；目录`.tmp/analysis-overhaul-acceptance/<module>/`。最早供应商用量回执Nemotron35：basic5940、opening5389输入token，之前无回执尝试保持未知。仍须最终代码两专题真实冷启动／补跑、语义／定位核验、最终源指纹及UTF-8/diff检查、更新交接与工程23/24；完整材料13专题三次需四份缺失附件的完整基线。

> **2026-11-14 补跑异常及前端表格、定位修复收尾（未提交，已加载）**：对应项目15、报告42。范围预校验返回公开id、工作及证据定位，要求更新原草稿；无效事项集合减少时重置连续失败计数，持续三轮未减少才停止并保存具体记录。补跑提示将长任务目标及逐项审查原因移入按需分页，动态提示估算run1431为8845→6668、run1433为9316→7146、run1435为2453→1886；原供应商首请求分别12673、11821、4149 token，不能把动态提示估算当作新供应商完整用量。审查移除“复核修复期间变更及影响”伪问题，检查方向以项目实际原文要求为准；停止问题按描述、事项与目标去重，开标20条问题记录对应14项待核对，不同事项的同类问题分别计数。
>
> 前端恢复按分组及冻结列名展示表格，不同原文位置分别点击图标直接打开PDF高亮，partial明确显示执行已结束。最终统一后端 **1633 passed / 12 skipped**（122.78秒），Ruff、5项分层、协议及真实装配mypy通过；7项新回归通过。前端类型检查、64项单测及桌面/手机 **76项synthesis E2E通过**；真实报告42在1440×900、390×844均有4组开标表格，定位PDF第24页p24b1，无页面溢出或浏览器异常。日志`.tmp/reparse-issues-backend-final.log`、`.tmp/reparse-issues-web-e2e-delivery.log`，现场与回放`.tmp/reparse-issues-snapshot.json`、`-replay.json`及`-live-web.json`；详见工程14/23。
>
> 10:03–10:04加载前后只读核对活动report/run/job/模型测试均0，使用`scripts/start-backend.ps1 -Force`重新加载最新全部后端代码，六服务正常、healthz为ok。当前PID：api29912（实际监听38888）、documents33184、scheduler44932、poller21508、analysis35832、beat44000；前端复用3000开发服务。历史原文c110/c116/c118包含办公场地租赁及2018年纸质递交公告，c138为2023–2024年通信工程监理网上开标前附表，实际项目归属与有效日期仍需核清，历史partial保持。本轮未发起真实模型补跑或提交。

> **2026-11-14 按用户要求提交取证与审查效率优化及审查修复**：本次提交收录常规补读窗口、完整依赖原子入账与归属、共享证据合包及冻结恢复、范围前置纠错、模型用量DEBUG诊断，以及续读回执覆盖、审查依赖超额读取和mypy参数匹配修复，包含回归测试与工程文档。提交说明为“优化解析取证与审查效率并修复续读及容量边界”，提交号以git log为准；此段覆盖下方对应改动的“未提交”状态。
>
> 沿用最终统一后端 **1626 passed / 12 skipped**（178.51秒），Ruff、5项分层、协议及真实装配mypy通过；源码均早于验证记录，提交前全部24个文件严格UTF-8与差异检查通过。运行服务尚未加载本轮修复；后续完整成果及300秒目标继续依据工程23的六轮真实验收轨迹推进。

> **2026-11-14 续接未提交改动审查修复收尾**：已读取会话`01a1d782-6b7c-7bb0-87a8-f58601c3724d`及其续接分段，完成两处P2修复的最终验证。旧窗口兼容层合并底层续读位置并保留软容量提示，research-v2/v3的未交付锚点在工具回执和研究账中均保留；审查依赖确认超额立即停止，4块额度/1000块条款的仓储读取从1000次降为4次，失败证据与缓存不变，提前容量需求标记`lower_bound=true`及“至少”。恰好满额、重叠锚点和探边块回归通过。
>
> 上轮两次统一检查已结束并因`research.py`的`**applied`与新增布尔容量参数的mypy匹配失败；本轮改为显式传入窗口参数。针对性取证/工具/类型检查 **23 passed**，最终统一后端 **1626 passed / 12 skipped**（178.51秒），Ruff/5项分层/协议及真实装配mypy通过，日志`.tmp/analysis-efficiency-review-fixes-final-backend.log`；全部24个改动文件严格UTF-8和差异检查通过，工程14/23已同步。改动保持未提交，业务运行服务尚未加载本轮修复。后续效率工作继续以已保存六轮轨迹为基准，完整成果及300秒目标仍待达成。

> **2026-11-14 05:03 取证与审查效率优化交付收尾，六轮真实验收未通过**：两个专题各3轮已全部结束，顺序会话97616/45339均exit0，未追加收费轮次。basic第三轮报告46/run1434为partial，3600.068秒、10发布/46草稿、47请求全Qwen46，已知输入1158365/输出185950（1次未知）；31块证据、常规补读10次新增15块、审查14逻辑窗口/16实际请求。初审12/12完成，复核1/10到原截止，review_complete=false；10条发布逐项回读原文并保存3/semantic.json，项目身份、预算、完整四标段及关键日期等未完成。全部轮次的原attempt、截止与成功结算一致，没有pending预占。
>
> 六轮完整成果和300秒目标均0/6通过。同模型三轮观察中位数：basic3600.129秒、49请求、已知输入1353889/输出193803；DQ3170.892秒、58请求、输入1656891/输出155202。启动代码分别deafbd5b、03a66613、7916f43c；最终两项边界修正a9f82485仅离线验证通过。最终统一后端1621通过/12跳过（167.33秒），Ruff/5项分层/协议及真实装配mypy通过；完整PG前一轮221通过，最终恢复/真实运行专项32通过（155.80秒）。同轨迹回放宽补读新增119→28块、审查28→27次/原文619→615次，收益集中在补读，审查去重仍有限。工程23六轮表格、工程24、delivery-summary.json及tool-diagnostics.json已更新。
>
> 05:01业务只读检查无活动报告/run/job/模型测试；业务API/Worker保持原进程，代码未部署或提交。05:03正常停止本轮原生PG55455，端口无监听，数据`.tmp/analysis-efficiency-pg/data`完整保留。后续应基于此次固定轨迹先减少检索等待、研究/综合纠错往返和审查重复，再讨论阶段推理参数；当前快模型下5分钟目标尚未达到。继续使用已保存结果做只读分析，不重导入测试库覆盖验收数据。

> **2026-11-14 04:29 DQ三轮已全部结束，basic第3轮尚活动**：DQ第3轮报告45/run1433 failed，3170.892秒（52分51秒）、0发布/35草稿、48请求全Qwen46、57工具，已知输入1656891/输出155202，用量完整。57块证据、13次常规补读新增28块，9审查逻辑窗口/10实际请求，原文逻辑90/31唯一/59重复、计重试105/74重复；复核4/4，保留8未决问题，procedure/qualification单项容量及点对点/算术修正细则。c1125未取证，c1127与c483–c485保留；9条有效支持缓存有相关未决问题不能恢复发布。3/semantic.json与结算核对已保存，三轮均未达完整成果及300秒门槛，同模型耗时中位3170.892秒。DQ会话45339 exit0，没有新增第4轮。**basic会话97616继续第3轮报告46/run1434，约31分42秒初审5/12；不得取消或重复启动。** 最终源码仍a9f82485、1621/12与PG32通过有效，最终只读回放已重跑`.tmp/analysis-efficiency-replay-delivery.log`，指标不变。收费完结后须收集basic3、逐项核对和最终对照、更新工程23/24/交接、UTF-8/差异与业务活动检查；本轮未部署或提交。

> **2026-11-14 04:20 用户新增性能目标**：快速模型下，从模块启动到完整审查并发布约5分钟，已写入工程24及交付统计，现有收费验收继续且原3600秒截止/模型/参数/额度保持。第2轮basic固定轨迹49次文本请求、3331.181秒文本等待、约268.972秒其它耗时；即使每次文本请求10秒仍约759秒。工具日志8次批量检索累计241.860秒、13次原文补读1.717秒、10次submit含6次错误，5分钟目标还需减少检索等待与模型/纠错往返，不能仅靠收窄补读。DQ第2轮15次检索累计342.151秒。新增只读`.tmp/analysis-efficiency-tool-diagnostics.py`及交付摘要脚本，不调用模型。实际重试交付已另列：basic首/次轮267/114个逻辑原文交付，对应296/139次实际请求原文交付。业务活动核对`.tmp/analysis-efficiency-acceptance/business-active-delivery.json`04:10读取无活动报告/run/job/llm_test，尚未加载进程，最终加载前须重查。

> **2026-11-14 04:08 效率优化最终离线边界补齐，第三轮收费验收继续**：已补长元素前邻块挤掉锚点、同主题不同范围的依赖误归属，两项反例先失败，另补未交付锚点续读回归。统一`.tmp/analysis-efficiency-backend-delivery-boundaries.log` **1621 passed/12 skipped，167.33秒**，Ruff/5项分层/真实装配mypy通过；最终PG合包及真实运行恢复`.tmp/analysis-efficiency-pg/delivery-boundaries-runtime.log` **32 passed，155.80秒**。最终源码指纹`a9f82485124f83124fb5f0725aa72be8c2e116753115139f9535911af381cf34`已保存final-code.json。两第三轮均早于本次补丁启动，仍用`7916f43c...`，不得当作最终代码三连通过，也不追加第4轮。
>
> basic第2轮报告45/run1433已partial（3600.153秒），13发布/42草稿，49请求全Qwen46，已知输入2008196/输出193803，1次用量未知；59块证据、13次常规补读新增23块、初审完成9/15调用，10逻辑窗口/12实际审查请求、114原文交付/48唯一/66重复。发布保留资金、2年服务、预算及提问截止；项目身份、K100%、四标段及明确递交开标时间等未完成，2/semantic.json已逐项核对。DQ第2轮2/semantic.json同样已保存，0发布不计草稿为成果。结算、attempt1及原截止核对通过。basic第3轮报告46/run1434约9分钟综合；DQ第3轮报告45/run1433约36分钟修复复核2/4。**收费顺序会话97616/45339继续，禁止取消或重复启动。** 尚须两轮结束后收集与逐项核对、按模型/版本分列汇总、重跑最终只读回放、更新工程23/24及交接、严格UTF-8/差异检查及业务活动任务检查；没有部署或提交。

> **2026-11-14 最新收费验收状态：basic第2轮、DQ第3轮仍活动**：DQ第2轮报告44/run1432已failed，2106.978秒（35分7秒），0发布/32草稿、58请求全部Qwen46、82工具，已知输入2028839/输出106575（用量齐全）；120块证据、28常规补读/新增53块、5审查请求、78原文交付/66唯一/12重复。初审后修复有procedure/qualification/response三主题单事项完整依赖超过12000输入估算容量，复核0请求，保留3个拆分问题；不是160块总额超限。离线只读缓存核对cache-audit.json：当前32草稿无满足当前指纹的历史有效判定，不能强行恢复旧发布。结算及attempt1核对通过。DQ第3轮报告45/run1433已自动启动，约22分钟初审3/5；basic第2轮报告45/run1433约55分钟初审8/15，之后自动第3轮。收费顺序会话仍97616/45339，禁止取消或重复启动。最终源码7916f43c...及1618/12、最终PG恢复10的记录有效；资料/参数/绑定/额度都保持。尚须三轮全结束后semantic逐项核对与同模型/版本分列汇总、更新工程23/交接、严格UTF-8/差异检查、业务活动任务检查及安全加载。无部署或提交。

> **2026-11-14 第三轮前补齐合包预取进度（最终代码7916f43c...）**：第二轮basic实际已成功一笔并保存3份合包/投影回执，但completed_calls仍为0，原因是首主题预取多组后才统一更新。现每组投影校验后、原保存点前调用_update_call_progress；不改变请求体、分组语义、审查结果或数据库保存次数。反例明确assert 0==1失败，修复后效率审查11通过。最终统一`.tmp/analysis-efficiency-backend-final-progress.log` **1618 passed/12 skipped，95.65秒**，Ruff/5项分层/真实装配mypy通过；最终PG恢复`.tmp/analysis-efficiency-pg/final-progress-recovery.log` **10 passed，21.86秒**。最终指纹`7916f43c609b918a5435a717f01eed88c49860e63798dd466ffb1c8276877565`写入`.tmp/analysis-efficiency-acceptance/final-code.json`；工程14/21/23/24同步。第二轮basic报告45/run1433，初审15调用（40条草稿/59块）；DQ报告44/run1432，初审5调用（研究时99块），均约30分钟仍执行。**收费会话97616/45339继续，各自结束后自动第3轮，不要取消或重复发起。** 第2轮指纹03a66613...、第3轮7916...，不能声称3轮相同最终代码验收。尚须结束后逐项语义核对、统计及上线活动任务检查；不提交、不重载活动业务Worker。

> **2026-11-14 效率验收首轮已结束，第二轮正在收费运行**：basic首轮报告44/run1432为partial（3600.129秒），24发布/31草稿，79实际请求全Qwen46，输入1353889/输出214040，1次用量未知；67证据、常规补读新增55块/52次，13审查逻辑窗口/15实际请求，267次原文交付/67唯一/200重复。DQ首轮报告43/run1431为partial（3600.104秒），6发布/22草稿，62请求全Qwen46，输入1596280/输出155311，1次用量未知；88证据、补读新增43块/27次，7审查窗口/7请求，134原文交付/84唯一/50重复。两者原3600秒截止、attempt1、成功账一致且无预占遗留。两轮均未通过工程24语义门槛：basic发布缺K≤100%、完整四标段、服务2年及提问截止；DQ发布事项15367bb7-399f-52c1-8f2f-a1eb75143b50引用c117办公租赁公告作为本监理项目common，已回读c110/c117/c118确认。各目录result/metrics/quality/postflight/semantic已保存。
>
> 两笔第二轮已由顺序脚本启动（basic报告45、DQ报告44，进度见各2/progress.json）；仍由basic会话97616、DQ会话45339执行，**不要取消收费调用或另行重复发起**。脚本等第2轮结束后收集，再自动执行第3轮，总计各3次，无额外第4次。第二、三轮使用最终指纹03a66613...；首轮为旧代码探索样本。模型46审查首轮已知推理basic178819/输出187368（95.4%）、DQ118798/输出121854（97.5%）；DQ单笔供应商报告输出33554/推理32519。原参数/30000请求预算保持，没有擅自调参。继续逐项核对最终版本两轮，汇总相同模型/相同代码口径、更新工程23及本交接、差异/UTF-8检查、核对业务活动任务后处理加载；尚未部署/提交。最新离线1617通过/12跳过与最终PG恢复10通过有效。原首轮工具会话53541/87021已exit0。

> **2026-11-14 效率优化最终代码检查通过，真实收费验收继续中**：在前一实施记录基础上，真实项目概况首轮发现预算包误报其它包的标段三/四正文遗漏，补上checks的本包record_ids及navigation_record_ids，合包同步责任；同时修复冻结计划在复用前被新版容量规则重新分包，恢复只重建定位/投影上下文，旧请求体和隐式合包身份保持。两个反例先失败后通过，49项审查专项通过。最终统一`.tmp/analysis-efficiency-backend-delivery-final.log` **1617 passed/12 skipped，100.85秒**，Ruff/5项分层/真实装配mypy通过；最终PG恢复`.tmp/analysis-efficiency-pg/final-responsibility-recovery.log` **10 passed，23.30秒**，完整PG前一轮221通过。源码指纹`03a66613e8be6033a9cc4067ee4ce90eb5baf31f0329394ec523c4022c694213`存于`.tmp/analysis-efficiency-acceptance/final-code.json`，工程14/24已更新，无前端、迁移、配置修改或提交。
>
> **不得中断在途收费调用，也不得重复启动已有轮次。** 首轮basic报告44/run1432会话53541，约41分钟初审5/10；否决报告43/run1431会话87021，约43分钟初审3/8，均Qwen46。顺序续跑脚本`.tmp/analysis-efficiency-sequence.py`已启动：basic会话97616、否决会话45339，等首轮result.json出现并核对终态后收集metrics/quality/postflight，再各自执行授权剩余第2、3轮；日志`.tmp/analysis-efficiency-<basic/disqualified>-sequence.log`。后两轮启动前`.tmp/analysis-efficiency-live.py`核对最终源代码指纹、原绑定/参数及材料；本轮总计每专题3次，首轮仅为探索，不额外补第4次。尚须跟踪费用调用、核对每轮原文基准、汇总中位数、更新工程23/交接并核查业务活动任务；没有部署或最终质量通过结论。
>
> 已收到用量：项目概况一笔输出22331/推理21158，否决一笔输出24913/推理23962，约95%–96%为推理。本轮保持供应商默认参数，单笔仍可能较慢。第一轮旧指纹`deafbd5b...`、历史run1418用Nemotron35，不能与当前Qwen46或后两轮相同代码验收混为改善比例。最终静态回放`.tmp/analysis-efficiency-replay-final.log`仍为宽补读119→28新增块、完整依赖并集107、旧160+8原子失败/200额度168完整保存；旧审查28→27次、619→615原文交付，最终草稿静态重建13次/277原文/125唯一块，口径不同不计算改善比例。

> **2026-11-14 解析取证与审查效率优化实施中（不自动提交）**：用户已明确授权实施并执行两个专题各3次隔离真实验收；沿用karpathy-guidelines，当前Default模式可修改。已实现常规补读每侧1块/长元素完整补齐/0窗口回读、草稿提交前原子准备真实依赖、实际锚点归属、稳定共享证据合包及冻结调用分组/预算/进度、旧隐式合包请求身份恢复、unknown范围预审纠错、修复工作收敛和四协议一次性DEBUG model.usage。HTTP/数据库结构、模型参数/绑定/预算保持。工程14同步；本轮源文件与新增回归均未提交。
>
> 离线失败反例：取证4失败/1通过、用量10失败；新增专项及真实装配mypy已通过。统一后端最新完整记录`.tmp/analysis-efficiency-backend-final.log`为1615 passed/12 skipped（108.05秒），但之后补了研究账requested/truncated和已保存合包回执零请求预留，必须最终再跑统一入口。完整原生PG `.tmp/analysis-efficiency-pg/integration-final.log`221 passed（272.85秒）；后续当前/旧冻结合包恢复及同attempt专项10 passed（`.tmp/analysis-efficiency-pg/legacy-recovery-final.log`）。前端无改动，不扩大前端验证。
>
> 隔离数据库原生PG55455，数据`.tmp/analysis-efficiency-pg/data`，使用`.tmp/synthesis-postgres/pgsql/bin`；本轮业务只读快照`source.dump`76091466字节。业务报告42/run1420仍活动（准备时），不得重启业务Worker。三个测试库postgres/efficiency_basic/efficiency_disqualified，两个真实验收库由同一快照恢复。原文项目15/source13/version3/parse_run6/index16共1130块。脚本`.tmp/prepare-analysis-efficiency.py`、`prepare-analysis-efficiency-acceptance.py`、`analysis-efficiency-live.py`、`analysis-efficiency-metrics.py`，数据库URL只在进程环境传入本地55455，勿打印凭证或启动WSL。复制库运行ID相同会被旧pg_locks查询混淆，验收脚本只隔离QUOTA_NAMESPACE（basic+100000、disqualified+200000），不改变业务额度。
>
> 首轮正在运行：basic库报告44/run1432，约9分35秒61–62次请求进入synthesis；disqualified库报告43/run1431，约11分40秒37次请求/10条左右草稿仍研究。第一次basic报告43只排队、零模型请求，因复制库锁身份冲突停止隔离等待进程后取消并重建；未中断收费调用。工具会话basic53541、否决87021，日志`.tmp/analysis-efficiency-basic-1.log`/`analysis-efficiency-disqualified-1.log`，快照`.tmp/analysis-efficiency-acceptance/<module>/<round>/`。两个专题各3次尚未完成；后续需逐次冷启动脚本、生成metrics/quality与原文基准对照，再记录中位数和交付。真实首轮主要Qwen46返回；历史报告42项目概况49次全部Nemotron35，不能把供应商不同造成的耗时/Token差异归因代码优化。当前完整检查后又有小幅兼容/账务补丁，最终代码指纹需记录，首轮应标为探索验收。
>
> 只读物理轨迹回放`.tmp/analysis-efficiency-replay.json`：5次宽补读原新增119块，新窗口新增28块（48唯一补读块）；41检索块、47草稿锚点、77必要依赖并集107块。旧160+8反例真实复现，失败证据账完全不变、测试200时168块完整准备。原28个审查包直接合包27个/615次原文，不能承诺10次；最终草稿按工作重建归属的静态计划13次/277次原文，不能把这一轮重建与历史两轮619次直接作同口径比较。回放脚本`.tmp/analysis-efficiency-replay.py`，不调用模型。

> **2026-11-14 只读诊断否决条件证据容量失败**：报告42/run1419于00:58:08失败，实际执行9分36秒、17次模型请求/40次工具计数、30条草稿、0条发布，尚未进入模型独立审查。研究已保留160块达到max_evidence_blocks=160；47个引文锚点的必要邻域共77块，其中8块未保留，已有证据与必要依赖并集168块（91个旧块不属于本次引文邻域，但不能直接删除其它查漏证据）。按索引16实际ordinal/element_id只读重算，缺少c1059/c1061/c1108/c116/c118/c322/c325/c463。当前流程研究与审查补读共用额度且未预留审查空间，容量保护如实拒绝半截依赖；相同160额度补跑仍会超限。临时200足以容纳本次已知168块依赖，长期应把依赖准备/容量预留前置并按真实完整条款管理，不能取消完整性护栏。未擅自更改额度、补跑收费任务或重载服务。现场快照`.tmp/disqualified-evidence-snapshot.json`、计算`.tmp/disqualified-evidence-capacity.json`；报告仍running，后续商务模块已开始，操作前需再核对状态。

> **2026-11-14 按用户要求只读诊断最新项目概况解析**：报告42/run1418已于00:48:29失败，执行44分18秒、49次实际模型请求（44逻辑调用＋5次重试），已记录输入797737/输出293886 token；1次断流缺用量。审查28调用占34分36秒/264372输出（初审13包＋修复15包），19包无待审事项；125块原文在全部审查包及上下文累计交付619次。20条最终草稿范围均unknown、0条正式成果、63条剩余问题，不能把全范围默认改为common绕过保护。供应商推理用量已由Agent消息验证：研究成功输出29002中推理22302；一笔11157含推理9547。最高单次21779的审查正式JSON仅907字符（cl100k估算581 token），审查端未保存reasoning分项，因此不能精确拆其推理占比。模型35参数为空、采用供应商默认推理，模块研究/审查共用30000输出上限。建议先降低/明确阶段推理预算、共享证据合并审查、问题定向复核及范围前置纠错；本轮用户要求分析，未改这些策略或配置、取消任务、重启服务或重新付费调用。快照与指标在`.tmp/latest-analysis-snapshot.json`、`.tmp/latest-project-basic-detail.json`、`.tmp/latest-project-basic-metrics.json`；截至00:52:35报告42仍running、run1419否决项正在执行，后续需重查活动状态。
>
> 用户此前要求`model.response_timing`降为DEBUG已完成，唯一源码改动在`adapters/llm/response_timeout.py`；直接捕获确认DEBUG，统一后端1588 passed／12 skipped（155.01秒）、Ruff、5项分层及协议/实际装配检查通过，日志`.tmp/response-timing-debug-backend.log`。源码未提交，运行进程未重载，服务加载后生效。

> **2026-11-14 按用户要求提交报告协议兼容性修复**：提交说明为“修复解析报告协议兼容性误判”，提交号以git log为准。收录详情接口修复、6项单元回归、取消后重解析集成断言及交接记录；沿用统一后端1588 passed／12 skipped和PostgreSQL专项4 passed，源码均早于验证记录，提交前差异与严格UTF-8检查通过。本段覆盖下方该修复的“未提交”状态。

> **2026-11-14 修复报告协议兼容性误判并单独加载API（未提交）**：用户反馈报告42提示“解析协议已升级”，取消后重解析入口仍禁用。业务库41/42均保存当前research-v3及当前runtime；get_report先pop掉skill_snapshot再做兼容性判断，导致现行报告也返回false。现保留局部快照用于判断、继续从响应剔除私有提示词；旧协议、缺少快照及旧runtime仍禁用。新增6项测试，修复前3失败/3通过，修复后兼容性与补跑专项16通过；统一后端 **1588 passed／12 skipped**（116.45秒），Ruff、5项分层及协议/实际装配mypy通过，日志`.tmp/report-compatibility-backend.log`。隔离PostgreSQL取消/锁释放/重解析/旧协议保护4项通过（15.40秒），日志`.tmp/report-compatibility-pg.log`。
>
> 单独替换API进程（pid18804，已更新`.tmp/backend-pids.json`）；五个Worker/Beat保持原PID，未取消、重发或重置运行任务。现场API确认41为canceled、42为running，execution_compatible均为true且响应不含skill_snapshot；run1418保留attempt1及原01:04:11截止，前后核验在`.tmp/report-compatibility-live-before.json`与`-after.json`。刷新页面即可移除错误协议提示；当前报告取消并等待执行退出后沿原规则重解析。本轮API重载也加载已提交的审查修复，Worker仍待安全时段加载。独立Windows PG55454正常停止；旧55453恢复过慢，本轮已停止，数据仍保留。未提交或启动WSL。

> **2026-11-14 按用户要求提交模型超时优化及审查修复**：本次提交收录四类文本协议的有效增量响应间隔、可选单次请求总时限、功能绑定截止删除与旧窗口恢复、模型测试续租、0020迁移、API/前端配置同步，以及流内错误兜底和Anthropic累计用量修复、测试与工程文档。提交说明为“优化模型响应间隔超时并修复流式错误与用量统计”，提交号以git log为准；此段覆盖下方对应改动的“未提交”状态。
>
> 提交前确认44个改动文件严格UTF-8与差异检查通过，源码均早于各自最终验证记录：沿用统一后端 **1582 passed／12 skipped**、Ruff、5项分层及协议/实际装配mypy，PostgreSQL集成220通过，前端类型检查、64项单测及18项设置页回归。业务库已应用0020并完成配置/约束/API核验；本轮提交未重载进程，审查修复仍待运行服务加载。

> **2026-11-14 按用户要求完成业务数据库0020迁移**：目标为当前`apps/api/.env`配置的业务库`ledger_admin`（172.29.199.222:5432），迁移前后均无活动报告、模块、job或模型测试；Alembic由`0019_analysis_success_budget`升级至`0020_llm_response_timeout`。确认timeout_seconds为非空DOUBLE PRECISION，total_timeout_seconds与heartbeat_at可空、功能绑定deadline_seconds已删除，两项时限CHECK已校验；42个模型原超时/额外重试与5项功能请求/切换额度保持原值，已有模型单次总时限均关闭。API健康、模型、功能绑定和设置读取均返回200。
>
> 迁移前完整备份`.tmp/db-backups/llm-timeout-0020-20261113-235947.dump`（73874619字节），pg_restore目录校验通过，SHA-256、配置前后对照、实际约束及API核验记录在同名`.json`；核验按约束涉及的列选择，不依赖PostgreSQL自动生成名称。本轮未重载业务服务或提交；API已在本轮前加载新配置字段，2026-11-13审查修复仍需后续进程加载。此段覆盖下方“0020待应用”的现场状态。

> **2026-11-13 修复模型超时优化审查问题（未提交）**：普通文本收集器遇到无数字状态码或符号错误码的流内错误立即失败，覆盖四类协议、Responses独立error及终态错误对象，正常结束标记不能掩盖已有错误；沿用已知状态码分类，无状态码兜底不回显供应商正文。Anthropic Agent合并message_start和后续message_delta中的累计用量，保留首事件输入/缓存，null不清零、显式0覆盖，完整结束后只转换一次，避免漏记输入及重复累加输出。
>
> 新增15项回归在修复前均失败，修复后通过；补核原隐私契约和单次用量事件后专项22项通过。最终统一`scripts/check-backend.ps1` **1582 passed／12 skipped**（97.61秒），Ruff、5项分层及协议/实际装配mypy通过，日志`.tmp/llm-timeout-review-backend-final.log`；严格UTF-8与差异检查通过。运行服务尚未加载修改，0020仍待安全切换时应用；未中断活动任务、重载业务服务或提交。

> **2026-11-13 模型响应间隔超时优化（未提交，代码与验证完成，待安全上线）**：按用户修订方案，文本模型`timeout_seconds`改为有效模型增量响应间隔，新建及批量导入默认10秒、已有数值保留；新增可空`total_timeout_seconds`，单次请求总时限默认关闭。迁移0020将时限改为DOUBLE PRECISION并约束有限正数，删除功能绑定deadline_seconds及其表单/API/路由时间分摊，新增测试heartbeat_at。模块总预算、次数、指数退避和连接池配置沿用现有规则。
>
> 四种文本协议共用一个可续期的asyncio.timeout_at，发送前开始首增量等待，正文/推理/工具参数续期，心跳、空事件和元信息不续期；正常结束标记及原始工具JSON均通过后才返回和结算，SDK不能补齐半截工具参数后执行。完整JSON兼容路径沿用SDK消息转换。旧未结束窗口忽略自身旧截止，保留模块截止、请求身份、次数、有效结果与终态，旧timeout快照的单次总时限为空。模型测试每15秒续租、60秒失联收敛未知，终态与调用账同事务保存，迟到结果不能覆盖终态。
>
> 最终统一`scripts/check-backend.ps1` **1567 passed／12 skipped**（103.73秒），Ruff、5项分层及协议/实际装配mypy通过，日志`.tmp/llm-timeout-backend-final4.log`。随后完整JSON工具参数首增量与工具身份隔离补充复验5项通过。完整隔离PostgreSQL **220 passed**（232.71秒），日志`.tmp/llm-timeout-pg/tests.log`；迁移类型变化已补充ORM/DDL契约的ALTER COLUMN TYPE解析，未跳过类型校验。前端类型检查、64项单测及桌面/手机18项设置回归通过，日志`.tmp/llm-timeout-ui-final2.log`；已查看截图，零值拒绝、0.01秒保存及可选总时限清空通过。
>
> 最终业务库只读检查：analysis_report仍1个running，agent_module_run为1个running/5个pending，job无活动项。禁止中断活动任务后重载；0020尚未应用业务库，API/Worker尚未加载新规则，上线需在安全切换时段应用迁移并同步加载前端/API/Worker。独立原生Windows PG55453已停止并确认无监听，数据保留`.tmp/llm-timeout-pg/data`；退出检查点超过20秒后立即停止，下次启动会自动恢复。未启动WSL、调用真实供应商或提交。

> **2026-11-13 按用户要求提交解析工具恢复与阶段交接改造**：本次提交收录可恢复工具问题账、独立研究分组与回执重放、范围并存与稳定工作身份、受控收尾及审查预留、分包导航校验、完成阶段业务投影，以及本轮超长待办更新的分组隔离修复、测试和工程文档。提交说明为“完善解析工具恢复与阶段交接并修复研究增量隔离”，提交号以git log为准；本段覆盖下方对应改动的“未提交”状态。
>
> 沿用本轮统一检查 **1521 passed／11 skipped**，Ruff、5项分层及协议／实际装配mypy通过；提交前复核差异与UTF-8。补丁仍待运行服务加载，真实完整解析验收继续以原记录为准。

> **2026-11-13 修复审查发现的研究增量隔离问题（未提交）**：更新已有待办时，在应用分组副本前复用`TopicTask.detail`的1000字限制，超长输入转成带原始序号与工作ID的可恢复问题，其它主题的合法增量继续保存及返回回执；普通研究笔记保留2000字。两个真实图回归在修复前均因缺少分组回执失败，修复后通过，覆盖错误增量位于批次首尾、合法笔记与回执持久化、1000字修正后关闭问题账及后续审查发布。
>
> 统一`scripts/check-backend.ps1` **1521 passed／11 skipped**（132.33秒），Ruff、5项分层及协议／实际装配mypy通过；本轮5个修改文件严格UTF-8与差异检查通过。补丁待运行服务加载，业务库和模型配置保持原值。

> **2026-11-11 解析Agent最新验收结论：未达交付门槛**。隔离报告39/run1398在原3600秒截止自动partial：47条草稿，777.17秒进入首次审查，10/17包完成、修复未开始，仅1条“报价方式”核实成果保留，c135/c136原文定位逐项一致。模型34/66、工具33/37；已返回输入668626/输出59981 token，30次缺用量不计0。模型46/35超时合计2499.87秒，主候选9次无效额外重试耗810.04秒。无pending预占、成功账一致、同attempt和原截止保留，历史31未变。结果/指标/质量/结算在`.tmp/stable-agent-project-2/`。
>
> 本轮真实回执暴露的跨包导航否决及新增坏事项问题身份已修复；业务输入回执补具体字段路径。最新统一检查 **1519 passed/11 skipped**（73.98秒，`.tmp/stable-agent-backend11.log`），Ruff、5项分层及协议/实际装配mypy通过；完整PG上一轮211通过，新增身份/分包后的真实图/恢复60通过，最终字段补丁后恢复8通过。三个跨包反例、问题身份及字段反例均先失败后通过，当前补丁仍需新的真实冷启动验收。
>
> 下一步依工程23的最小提案讨论模型46的extra_retries从1改0，未擅自改配置或额度；历史失败轨迹可少等待810秒但须重新验收。四份附件原件也待补齐：已只读核实原DOCX哈希一致、无嵌入附件，不能改称“资料完整”。13专题/连续3次成功计数为0。业务库报告37仍有9条活动运行账，禁止中断后重载；API/Worker尚未加载补丁。未提交、启动WSL或改变产品入口。
>
> 本轮创建的原生PG55451已正常停止，端口无监听，数据保留`.tmp/stable-agent-pg/data`；后续可从此目录启动，勿重新导入覆盖验收结果。当前最终代码指纹及本轮启动指纹在`.tmp/stable-agent-project-2/final-code.json`，两者不同，必须冷启动重验。

> **2026-11-11 解析Agent稳定性代码改造（未提交，最终验收见上）**：research-v3增加显式可恢复校验类型、按对象/错误码/字段持久问题账、研究增量依赖分组隔离及回执重放，合法事项与其它问题不再被跨问题累计失败终止。研究完成、预算、空转、自然语言及重复工具统一受控收尾，经AnalysisTransitions推进独立审查；当前事项索引附范围/工作/问题，历史工作仅沿明确的唯一范围迁移衔接。审查预留复用实际分包并覆盖配置允许的复核；一次候选切换的总耗时不再重复预留给每包。
>
> 真实首轮报告38/run1397在首次综合前被研究期空转计数终止，已修正阶段计数交接及候选耗时预留。另修复发布前生成business_data造成已完成专题记录为空的问题，3条反例先失败再通过。最终统一后端 **1514 passed/11 skipped**（76.37秒），Ruff、5项分层、协议及真实装配mypy通过（`.tmp/stable-agent-backend7.log`）；完整隔离PG集成 **211 passed**（214.52秒，`.tmp/stable-agent-pg-final.log`），涵盖研究保存/草稿/审查回执中断恢复、原截止及幂等结算。旧集成夹具同步v3、服务端引文和读取事件，未放宽生产契约。
>
> 冻结原模型和额度，使用业务库只读快照复制的原生Windows PG55451（`.tmp/stable-agent-pg/data`）完成项目概况第二轮；最终partial及具体指标见顶部。日志`.tmp/stable-agent-live2.log`、快照/指标`.tmp/stable-agent-project-2/`。业务库原报告37仍running，9条运行账活动，禁止中断后重载；API/Worker尚未加载本次补丁。未启动WSL、修改模型/额度或提交。
>
> 已按连续原文建立 [13专题独立验收基准](docs/工程/24-解析Agent稳定性验收.md)。资料快照只有主文件；c455/c782/c883/c975引用的评标办法、商务规范书、技术规范书、报价表四附件均无专项正文。已异步向用户询问资料补齐及缺资料场景的后续安排；连续3次全量正常验收尚未开始。

> **2026-11-10 用户明确解析Agent的交付目标**：需要能稳定、正确完成解析任务的Agent，修掉单条异常或离线测试通过不能作为交付完成。后续必须围绕完整解析结果验收，并检查可恢复工具错误的处理、已有草稿进入审查的路径及失败后的自动恢复。当前链路审查确认：精简研究工具将预期参数／状态校验错误包装为通用ToolException后累计终止；报告37／run1384的43条草稿全部pending（29条unknown），审查轮次0，尚未形成可发布成果。此目标尚未达成；此前暂缓额外独立文件验收的决定继续有效。

> **2026-11-10 修复并存范围笔记导致解析终止（未提交，需重载后端）**：用户反馈报告37／run1384的`update_research`连续失败。对应档案已有43条草稿；程序把已确认范围的笔记或新增独立事项误作整个未知范围的替代，要求分配工具无法指定的5条旧事项。现仅在旧事项已完整分配时隐式迁移，未分配草稿、待办和转引保留在未知组；实际部分迁移及显式替代仍受原完整性校验约束。失败回执按单工具累计与连续失败中先耗尽的额度计算，终止时remaining_attempts为0。
>
> 新增6项回归，HEAD方法对照 **5失败／1通过**；修复后专项 **131 passed**。使用运行档案及两次原始失败调用离线重放均通过，43条草稿的正文与范围及4个未知组的原有待办／转引保留。统一`scripts/check-backend.ps1` **1499 passed／11 skipped**（103.23秒），Ruff、5项分层及协议／真实装配mypy通过。日志`.tmp/scope-update-before.log`、`.tmp/scope-update-targeted.log`、`.tmp/scope-update-backend.log`，重放`.tmp/scope-update-replay.json`。工程14／23同步；未重载业务后端或重跑报告37，真实完整解析尚待验证。

> **2026-11-10 按用户要求提交批量研究、整项审查及回归修复**：本次提交收录research-v3／combined-v3协议、关键词与向量候选融合、批量检索及子调用结算、稳定事项身份与原文定位、研究草稿复用、整项审查与依赖缓存，以及全局进展漏记和来源错误整批中断两项修复；前端保留原布局、模块标签和三个重解析入口，不兼容报告显示禁用原因。提交说明为“优化解析批量研究与整项审查并恢复重解析入口”，提交号以git log为准；本段覆盖下方对应改动的“未提交”状态。
>
> 提交前确认后端代码均早于最终统一检查日志，沿用 **1493 passed／11 skipped**、Ruff、5项分层及协议／真实装配mypy结果；前端沿用已记录的类型检查、64项单测及桌面／手机回归结果。提交前差异及UTF-8检查通过。补丁仍需后端重载；真实验收未通过及暂缓独立文件验收的状态保持。

> **2026-11-10 修复 research-v3 全局进展判断与批量来源错误隔离（未提交，需重载后端）**：批量检索沿用当前模型轮次登记工作账的真实进展，研究期通过预校验的新草稿和实质业务修改计入全局进展，避免持续取证或暂存时被提前转入综合；重复、改名和复核状态切换仍不能续期，旧 research-v2 研究期行为保持。来源参数错误在预取和串行入账阶段均按子查询隔离，保留其它合法查询的结果和成功结算；真实撤权、取消和执行中断仍终止整批。
>
> 新增8项回归，修复前 **7失败／1通过**，修复后专项 **107 passed**；统一 `scripts/check-backend.ps1` **1493 passed／11 skipped**（80.80秒），Ruff、5项分层及协议／真实装配mypy通过。日志 `.tmp/v3-review-fixes-before.log`、`.tmp/v3-review-fixes-targeted.log`、`.tmp/v3-review-fixes-backend.log`。UTF-8与差异检查通过；本轮未重载业务服务或重跑真实报告，前述真实验收待办继续保留。

> **2026-11-10 恢复重解析按钮，明确前端修改范围**：用户要求只修改解析结果的内容展示，保留页面布局、模块标签及原有操作。已确认上一轮按 `execution_compatible=false` 隐藏三个按钮导致入口消失；现恢复“重新解析本模块／补跑未完成模块／全部重新解析”的原位置。旧协议报告仍受后端409限制，三个按钮改为禁用，并显示“解析协议已升级，当前报告无法继续解析，请生成新报告。”；兼容报告保持原三种提交范围。后续结果展示调整不得扩大到页面结构、模块导航或操作入口。
>
> 反例先复现三个按钮缺失，再通过桌面／手机专项 **6项**，覆盖标签切换、三种请求范围、旧协议禁用原因及正文原文定位。前端类型检查、**64项单元测试**及设计检测通过，UTF-8与差异检查通过；已查看桌面／手机截图，产物在 `apps/web/test-results/report-actions-after/`。复用现有3000前端，未提交。

> **2026-11-10 research-v3／combined-v3 工程改造（未提交，当前文件真实验收未通过）**：本轮实施独立关键词／向量候选融合、批量检索与成功子调用结算、原始记录位置稳定身份、标题派生、block_ids回填定位、范围继承门禁、研究草稿复用、每工作每批无进展结算，以及完整事项合并审查与依赖缓存。新报告冻结新协议，旧报告继续读取；旧协议补跑在入队前409，前端按execution_compatible禁用入口并说明原因（本日后续修正：保留三个按钮）。无新增迁移。
>
> 最终统一`scripts/check-backend.ps1` **1485 passed／11 skipped**，Ruff、5项分层与协议／真实装配mypy通过，日志`.tmp/v3-backend-final13.log`。隔离原生PostgreSQL **68 passed**，日志`.tmp/v3-db-final5.log`，测试库55447已停止。最终运行专项109项通过，日志`.tmp/v3-final-runtime.log`；新协议专项34项在`apps/api/tests/unit/application/test_analysis_v3.py`。前端pnpm类型检查、64项单测、86项桌面／手机浏览器回归通过；后续仅修改后端，前端结果沿用。
>
> **真实效果未达标**：固定项目15／source13／version3／parse_run6／index16，只执行项目概况，沿用原模型和预算。旧33、新35～37均0成果；38因未加载分包补丁取消。39／run1375装包16包，1744.10秒仅审2包，0可发布；模型成功／尝试25／40、工具29／31，已返回实际输入／输出490426／51446 token，3／6批无新增证据。多次90秒超时与reviews类型错误，研究期间还因字符串容器及提前final丢掉有效提交；该轮已停止并保留用量，不能宣称效率改善。最后修复适配器按schema解码容器、工具逐项类型隔离及提前final保留草稿，真实被拒11条离线重放全部通过；最终补丁尚未重新冷跑。旧31哈希保持。材料指纹／冻结预算`.tmp/v3-acceptance-manifest.json`，全轮指标`.tmp/v3-acceptance-metrics.json`。费用无冻结计价；无用量的超时无法补算。当前文件完整13专题质量和同等质量效率对照仍未完成。用户已于2026-11-10明确**暂不执行第二步1～2份独立文件验收**。
>
> 隔离验收原生PG55449已正常停止，数据仍在`.tmp/research-v3-audit/data`；最终只读核对全库报告／run／job活动数为0，38／39无悬挂预占（`.tmp/v3-postflight.json`）。真实日志`.tmp/research-v3-live-5.log`，结果`.tmp/research-v3-live-5/`；详细原因见工程23。未重载业务服务、未启动WSL、未自动提交。

> **2026-11-09 按用户要求提交解析审查、成功额度与原文定位改造**：本次提交收录固定一轮完整审查与定向修复、成功调用额度及持久窗口（迁移0019）、审查问题缓存与耗尽恢复修复、服务端生成原文定位、统一精简校验反馈，以及前端成功统计／审查进度、生产示例、测试和工程文档。提交说明为“完善解析审查与成功调用预算并简化原文定位及纠错反馈”，提交号以git log为准；本段覆盖下方自上一提交ec6f7b9以来对应改动的“未提交”状态。
>
> 后端文件均早于最终统一验证日志，沿用 **1451 passed／11 skipped**、Ruff、5项分层及协议／真实装配mypy结果；前端桌面／手机浏览器沿用最后 **10 passed**，本次提交前补跑pnpm类型检查与 **64项单测**均通过。UTF-8解码与差异检查通过。最新补丁仍需重载后端；报告33真实验收失败及后续检索问题继续按下方交接处理。

> **2026-11-09 修复审查问题丢失与耗尽窗口恢复（未提交，需重载后端）**：审查全局问题独立保存关联内容、依据及依赖的输入指纹，修改其它事项不能清除未变问题，也不能被单项通过缓存覆盖；共享事项按各自主题生成稳定问题ID。定向复核跳过未变主题，剩余问题均未有效修复时直接保留并结束；兼容原v2缓存及JSON检查点恢复。
>
> 模型耗尽窗口保存并恢复错误类型与HTTP状态，保留原请求次数和截止时间；网络故障恢复后仍交给未完成收尾，有核实成果为partial，无成果为failed。旧窗口缺错误类型时按预算耗尽处理。耗尽标记使执行器直接收尾，跳过两次无效恢复等待。
>
> 新增11项回归覆盖同／跨主题未变问题、旧缓存、关联冲突解除、共享问题身份、耗尽窗口及成果收尾。反例先失败再通过；最终专项 **34 passed**，统一`scripts/check-backend.ps1` **1451 passed／11 skipped**（71.82秒），Ruff、5项分层及协议／真实装配mypy通过。日志`.tmp/review-fixes-targeted-final.log`、`.tmp/review-fixes-backend-final.log`。工程14／23同步；本轮未重载业务服务、调用真实模型、改写历史报告或自动提交。

> **2026-11-09 解析总结与原文定位分离、精简纠错反馈（未提交，需重载后端）**：用户明确解析只需AI总结及可定位出处，不应要求模型摘抄引文；可确定性生成的信息交给程序。解析提交的citations现在只含已读block_id，服务端从证据账生成原文、来源、版本、页码、坐标；兼容忽略旧请求的quote，改写或缺少quote不再导致三次提交失败。正文、条件与范围仍按业务语义审查。内部ID、text和排序继续由程序生成，提示要求省略空字段和默认值。38份生产示例、各阶段提示与审查规则已同步，不改历史报告。
>
> 反馈按字段合并诊断，相同原因集中列出事项／位置；常见类型及长度错误改为简短中文，不再追加整套提交协议。混合批次仍保存有效草稿，最后一批失败只提示修正及重新final=true。新增7项反例先失败再通过；旧的“错误引文”反例改为未读块，保留权限、有效批次隔离及原文定位校验。最终统一`scripts/check-backend.ps1` **1440 passed／11 skipped**（70.29秒），Ruff、5项分层及协议／真实装配mypy通过；失败修正专项71通过。日志`.tmp/source-locations-backend-final.log`。本轮没有重载业务服务、重跑报告、调用真实模型或自动提交。
>
> 用户追问scope／conditions用途：已核实scope参与标段筛选与关系适用性；conditions只用于展示和语义审查，没有自动条件判定。已建议必要范围保留、已知范围由上下文继承，条件写入总结以避免重复结构化输出；本轮尚未修改这两个字段的契约，继续工作时先结合用户后续决定。

> **2026-11-08 解析审查与成功额度改造（未提交，已迁移并加载）**：完整审查固定一轮，采用`combined-v2`的`reviews/checked_units/issues`，移除上下文索取循环。程序先准备连续原文和业务依赖，按完整语义索引及容量分包；默认12000估算token，额外预留2048纠错token。`analysis.max_review_repairs`默认1，可设0或更大；未变的通过／业务否决判定复用，修复无变化不再发送审查。标段原文指向前移至提交和旧草稿预校验；缓存、补跑、父节点／关系端点／相关标段失效和审查进度同步接入。
>
> 模型通过完整协议后才计成功，工具校验失败／未执行／未知不计成功，正常空检索及新调用缓存复用计成功，自动Skill仍计一次；实际尝试数及失败token保留。迁移0019新增成功列、调用预占结算及逻辑模型窗口表，两项配置已登记。额度核对成功＋在途，工具状态同事务结算，重复回执幂等；失联恢复补结算有效响应，其余记未知，未知工具重试使用新尝试身份。JSON／ID／引用纠错、连接重试、429及候选切换共用持久窗口，移除外层三次JSON及隐藏两次重试截断。页面显示包数／修复次数／具体缺口，停止说明按实际发布数量写，零成果明确提示；历史无成功列且无结果事件显示未记录，不从尝试数推算为0。
>
> 统一后端最终`scripts/check-backend.ps1` **1433 passed／11 skipped**（67.26秒），Ruff、5项分层及协议／真实装配mypy通过。隔离PostgreSQL运行专项 **26 passed**，后续恢复相关 **6 passed**、未知工具恢复 **1 passed**；历史缺失统计反例先失败，再与成功聚合专项 **2 passed**，测试库55447已停止。前端pnpm typecheck、**64项单测、10项桌面／手机浏览器**通过。工程14／21／23已更新。没有自动提交或启动WSL。
>
> **真实验收未通过**：项目15相同source13／version3／parse_run6／index16的新报告33，仅执行项目概况，沿用现有模型、超时和预算。run1353耗时554.64秒，状态failed、0条可发布；金额、日期及四标段与条件尚未验收。首次组合检索嵌入超时回退关键词，后续单关键词语义检索也无命中；资料库实际含1130块、52894字符，其中20块有“项目名称”，不能把空检索视为资料缺失。模型多次错用文件ID `13`作为原文块ID，已被拒绝。此次审查没有504。
>
> 5个主题包合并为1次完整审查请求，返回5个具体缺口，修复使用1／1；内容依据无变化，定向复核0次，没有重开全量审查。模型成功／尝试 **24／24**，工具成功／尝试 **14／22**；对账24个有效窗口、24次发送、8个工具失败均不扣成功额度、无悬挂调用。报告31原始报告／模块／运行字段哈希前后相同。报告32是验收脚本Windows事件循环错误、模型调用0次；修正脚本后创建33，保留32记录。
>
> 业务迁移head为`0019_analysis_success_budget`，API／四组Worker／Beat已重载并健康，最新停止说明与历史NULL显示补丁已加载。真实验收日志`.tmp/review-v2-live.log`，快照及对账`.tmp/review-v2-live/`，后台全库无pending／waiting／running。后续继续定位**真实检索空命中及空转交接**，再验收金额、日期、四标段与条件；不能以离线通过宣称实际解析完成。

> **2026-11-08 核实报告31部分完成与成功次数空白（未提交）**：run1342有31条草稿，budget处理后dates审查重复请求本包已有的5条完整事项，旧逻辑首次重复即终止；最终5条满足全部归属主题／依赖发布条件，另有4条标段引文缺少原文指向。当前API没有返回新增成功字段，页面因此空白；只读运行新仓储查询确认本次成功模型33次／工具33次，实际尝试48／39。
>
> 本轮页面兼容缺失／null字段显示“未记录”，真实0保留；审查提示澄清可用导航不表示缺失，首次重复追加具体ID及判定指引，只允许一次纠正，再重复按未完成收尾。反馈计入容量及持久化指纹，恢复复用，不放宽审查发布条件。工程14／23同步；没有重跑报告或改写历史状态。
>
> 后端两项反例先失败，专项36通过，最终统一`scripts/check-backend.ps1` **1403 passed／11 skipped**（66.70秒），Ruff、5项分层及协议／真实装配mypy通过；前端缺字段桌面／手机反例先失败，再通过**6项浏览器专项**，typecheck及64项单测通过。日志`.tmp/repeated-context-before.log`、`.tmp/repeated-context-targeted.log`、`.tmp/repeated-context-backend.log`、`.tmp/missing-count-before.log`、`.tmp/missing-count-after.log`。只读确认全库运行账／报告／job均无活动项后，使用既有脚本重载API、四组Worker和Beat，健康检查通过；API实测run1342成功33／33，partial及5条成果保持，摘要`.tmp/repeated-context-live-check.json`。未启动WSL或调用真实模型，未提交。

> **2026-11-08 运行记录仅展示成功调用次数（未提交，执行上限口径待澄清）**：用户明确只展示成功统计，但同条消息同时要求“执行上限仍按尝试次数”和“执行上限也只扣成功次数，失败另限”，已发起澄清。本轮完成两种策略共同需要的展示统计，上限仍沿用实际尝试数。报告查询按运行账聚合现有model_result(status=ok)、tool_result(status=success)及skill_loaded事件，新增successful_model_calls／successful_tool_calls；失败、未知及未完成请求不计成功，同工具回执重放不重复。页面只显示成功次数，移除与尝试上限混用的分母；无数据库迁移。
>
> 数据库及浏览器反例均先失败再通过。最终统一`scripts/check-backend.ps1` **1401 passed / 11 skipped**（81.09秒），Ruff、5项分层及协议／真实装配mypy通过；隔离原生PostgreSQL成功统计及预算恢复专项 **2 passed**（6.61秒），含自动Skill加载与重复保存边界；前端typecheck、**64项单测、4项桌面／手机浏览器专项**通过。日志`.tmp/success-count-db-final.log`、`.tmp/success-count-ui-after.log`、`.tmp/success-count-backend-final.log`。测试库55447已正常停止且无监听；API需重载后返回新增成功字段，未启停业务后端或启动WSL。工程14已同步。

> **2026-11-08 修复校验反馈审查发现的两处问题（未提交、未部署）**：共享引文提示改为按当前工具定义回读，避免问答误用解析工具的before／after参数；提交隔离保留完整有界诊断，整批失败汇总后统一限额，不再提前截成500字符。新增3项真实图回归覆盖问答回读后修正发布、六处引文错误在整批失败及部分暂存中的完整反馈，反例先失败再通过。针对性 **36 passed**；统一`scripts/check-backend.ps1` **1401 passed / 11 skipped**（80.24秒），Ruff、5项分层及协议／真实装配mypy通过。日志`.tmp/validation-review-fix-before.log`、`.tmp/validation-review-fix-targeted.log`、`.tmp/validation-review-fix-backend.log`；工程14／23同步。业务后端重载后生效。

> **2026-11-08 按统一校验反馈要求修复解析链路（未提交、未部署）**：用户指出校验器应普遍返回可执行修法，上一轮只修分类单点不完整。本轮检查并补齐输出列／单值／空值、知识引用、研究工作与证据ID、格式父节点／关系端点、独立合并审查、旧查漏及选证反馈，统一提供字段路径、失败原因、预期规则／允许值及修法；可独立判断的问题在更新前合并返回。新增application/shared/validation.py供解析和知识引用共用，最多6项／1800字符，候选有界且仅来自服务端索引，Pydantic错误不回显input／ctx。JSON语法报行列，重复键错误不再被通用JSON错误覆盖；三次重试保留原始协议与当前错误，移除已修正旧错误。纠错及发布规则沿用原上限。
>
> 新增20项回归，初始14项反例失败，补充根结构／重复键／非法kind类型场景；覆盖同轮多错误、原子性、引文真实路径、关系两端定位、查漏坏草稿不回显和JSON去掉旧反馈，独立审查收到精确修法后第二次模型请求即可完成。针对性（含上一轮5项及2项类型门禁） **27 passed**；最终`scripts/check-backend.ps1` **1398 passed / 11 skipped**（69.37秒），Ruff、5项分层、协议及真实装配mypy通过。日志`.tmp/validation-feedback-before.log`、`.tmp/validation-feedback-targeted.log`、`.tmp/validation-feedback-backend.log`；工程14／21／23同步。UTF-8与差异检查通过；业务后端尚未重载，未调用真实模型或自动提交。

> **2026-11-08 修复现场分类／内容键连续提交失败（未提交、未部署）**：报告31项目概况run1340实际14次模型／25次工具、608秒、0项，首次关系字段缺失，后两次把分类填在category并省略group、把具体事项当content键；原反馈只报“分类不符合”。协议精简遗漏group→分类title、content键→columns映射，工具字段也未解释。本轮补齐运行协议和字段说明，综合提示及参数校验错误提供按报告冻结声明生成的局部格式示例；分类与内容键同时错误一次反馈，候选分类只作诊断，不自动改写。整批失败按记录位置汇总不同错误并合并同类说明，部分失败仍保留有效记录，连续三次上限和独立审查规则未变。
>
> 新增5项反例先失败再通过，真实Agent图验证关系字段错误→分类／内容键错误→修正→独立审查发布，覆盖整批错误定位及部分有效事项隔离；工作上下文夹具改用真实冻结格式。针对性 **87 passed**；最终`scripts/check-backend.ps1` **1378 passed / 11 skipped**（68.70秒），Ruff、5项分层、协议及真实装配mypy通过。日志`.tmp/output-contract-before.log`、`.tmp/output-contract-targeted.log`、`.tmp/output-contract-backend.log`；工程14／23同步。未重载业务后端或调用真实模型；后端加载新代码后可沿用原报告冻结格式补跑，已有失败状态未自动改写。run1338为候选连接失败，不能归为本次格式缺陷。

> **2026-11-08 按用户要求提交解析资源优化及审查修复**：本次提交收录重复研究收敛、综合与定向修复预算预留、跨工作原文缓存、批量有界补读、共享证据主题合包审查、13份Skill取证指引、运行日志及配套回归。包含三处审查修复：合并窗口按仓储上限拆分、原块缓存正确关联本次主题、独立审查后允许使用修复额度。提交说明为“优化解析取证与审查调用并修复预算和缓存边界”，提交号以git log为准。本段覆盖下方两轮对应改动的“未提交”状态。验证沿用最终统一后端 **1373 passed / 11 skipped**、Ruff、5项分层及协议／真实装配mypy，以及隔离PostgreSQL解析专项 **79 passed**；业务后端重载后生效，新Skill需新建报告使用。

> **2026-11-08 修复未提交改动审查发现的三处问题（未提交、未部署）**：批量原文合并区间拆成每次最多12块的仓储读取，保留一次工具调用及整批验证，后段版本异常不保存半批证据；缓存命中重新按本次参数解析主题，修复原块回读沿用旧active_topics；审查定向补查使用已预留修复额度，最终收尾按受影响／变化主题分包加一次综合预留，至少保留两次模型及两次工具额度，时间结合剩余轮次与实测延迟，硬预算不变。预算与实际审查共用review_scope，未变主题不挤占修复机会。
>
> 新增8项离线回归及1项数据库回归，缺陷反例先6项失败再通过，真实Agent图覆盖审查补查至最终发布；真实PostgreSQL验证16块按12＋4读取。最终统一`scripts/check-backend.ps1` **1373 passed / 11 skipped**（70.13秒），Ruff、5项分层及协议／真实装配mypy通过；隔离原生Windows PostgreSQL解析专项 **79 passed**（164.11秒）。日志`.tmp/efficiency-review-before.log`、`.tmp/efficiency-review-targeted.log`、`.tmp/efficiency-review-backend.log`、`.tmp/efficiency-review-integration.log`；工程14／23同步。隔离测试库55442已正常停止且无监听，未启动WSL、启停业务服务或提交；业务后端重载后生效。

> **2026-11-08 修复解析重复研究与综合预算缺失（未提交、未部署）**：`research-v2`恢复综合／独立审查的次数和时间预留，依据已有内容分包及主模型实际耗时，到边界直接转综合；同响应后续未执行检索不侵占收尾工具额度，证据满额及旧终止标记也可综合已有原文。新证据或真实续页才豁免无进展，换词重复召回和缓存回读不再无限续期；保留完整核对项及实际缺口交独立审查。
>
> 原文缓存去除work／topic_keys，跨工作复用仍更新归属与修订影响；read_document支持最多4个已知ID，合并重叠窗口，按容量交付完整块，真实read_result及截断信息随研究账进入审查。共享原文和可补读上下文的小主题合包，其他主题保持分开；保留逐主题验证和持久缓存，中断恢复不重发已完成合包。13份生产Skill优先章节定位、连续阅读和具体缺口，日志增加新增证据量、执行类别及是否扣预算。
>
> 新增17项离线回归，固定双主题替身轨迹模型请求 **7→6**，6次硬预算可完整发布两条，4／5次仍不发布未审草稿；真实费用与准确率需新报告复测。最终统一`scripts/check-backend.ps1` **1365 passed / 11 skipped**（67.32秒），Ruff、5项分层及协议／真实装配mypy通过；隔离原生Windows PostgreSQL解析专项 **78 passed**（161.38秒）。日志`.tmp/analysis-efficiency-backend-final.log`、`.tmp/analysis-efficiency-integration-final.log`，工程14／20／23同步。测试库55442已正常停止且无监听；未启动WSL、启停业务服务、调用付费模型或提交。运行逻辑需后端重载，Skill在创建时冻结，新指引需新建报告使用。

> **2026-11-08 按用户要求提交解析流程精简、复盘归档及审查修复**：本次提交收录研究／综合／独立审查流程、轻量工作协议、上下文与细则按需加载、原文去重、终态复盘档案及到期清理、运行日志和前端进展展示，以及配套测试和文档；包含本轮审查发现的长事项全文补读和多标段跨批综合修复。提交说明为“精简解析研究与审查流程并完善复盘归档”，提交号以 git log 为准。本段覆盖下方对应改动的“未提交”状态。验证沿用最终统一后端 **1348 passed / 11 skipped**、Ruff、5项分层及协议／真实装配 mypy，隔离 PostgreSQL 解析专项 **63 passed**；前端沿用最近 **64项单测、70项桌面／手机浏览器专项**及类型检查结果。

> **2026-11-08 修复审查全文补读与多标段分批综合（未提交）**：长事项分包只在实际提供整项全文时登记为已加载；允许通过本事项`record:` ID补读完整上下文，补入后仍拦截重复请求并检查容量。首次综合保留初始unknown工作的`synthesis_work_origins`，跨批沿用原始工作ID拆分并存标段，每条事项绑定实际范围的当前工作ID；映射随检查点保存，显式重新研究或进入独立审查时撤销。提示只追加已迁移或退出当前索引的原始工作，避免重复工作清单。
>
> 新增8项回归场景，覆盖全文补读／重复请求、两／三标段不同分批、JSON状态与真实图检查点恢复、显式确认范围后的限制。修复前5项反例失败，修复后针对性41项通过；统一`scripts/check-backend.ps1` **1348 passed / 11 skipped**，Ruff、5项分层及协议／真实装配mypy通过。日志`.tmp/review-fix-before.log`、`.tmp/review-fix-targeted.log`、`.tmp/review-fix-backend-final.log`。工程14／23同步。

> **2026-11-08 按内容充分性结束研究并新增一天开发复盘档案（未提交）**：研究阶段恢复轻量`complete_research`出口，Agent边检索边理解，依据充分即可进入最后统一综合，无需逐项found、逐块examined或另写范围确认笔记。移除连续三批原文后的强制登记暂停；无新增原文的重复采集仍有独立额度，关闭采集不伪造语义缺失。完整核对清单、未处理线索和真实分页账交独立审查，不能凭研究总结发布。综合时可从unknown范围拆成多个标段，并绑定各范围当前有效的工作ID。审查指纹变化撤销完成资格，新增依据也能撤销没有业务正文的旧“未找到”结论；无关主题继续复用。
>
> 运行中研究账继续保存在数据库JSON和检查点中，按工作ID回读；模型检索原文保持`id/text`，定位元数据由代码回填。新增`ports/analysis/archive.py`、`adapters/analysis/file_archive.py`、`worker/analysis/maintenance.py`，通过`core/di.py`注入。数据库确认completed／partial／failed／canceled后导出UTF-8 JSON复盘档案，默认`logs/analysis`，包括项目／报告／模块身份、实际调用量、检索、原文、笔记、草稿和审查问题。`ANALYSIS_ARCHIVE_RETENTION_DAYS=1`，从数据库完成时间计时；目录及扫描周期也可配置，默认每3600秒清理，重启补清理、空闲Worker仍维护。仅非递归删除到期专用档案及遗留临时文件，不删除数据库研究账或业务引用。失去所有权不导出旧状态，写档失败不回滚业务终态；冻结配置和密钥不导出，异常脱敏。
>
> 最终统一`scripts/check-backend.ps1` **1340 passed / 11 skipped**（95.90秒），Ruff、5项分层及协议／真实装配mypy通过，新增归档实现和运行门面纳入持续类型检查；隔离原生Windows PostgreSQL解析专项 **63 passed**（151.30秒）。日志`.tmp/semantic-final-backend.log`、`.tmp/semantic-final-integration.log`。新增10项语义收敛回归、6项档案回归及6个终态／所有权／失败隔离数据库场景，现有长清单和恢复用例同步。工程14／20／21／23、调研03及`.env.example`已更新。隔离测试库55442已正常停止并确认无监听。本段替代下方“连续三批强制登记”的运行结论；本轮无前端修改，未自动提交、启动WSL、启停业务服务或调用付费模型，真实调用量与费用变化须另定样本验收。

> **2026-11-07 修复纠错误扣、连续采集空转并精简操作日志（未提交）**：只读核查worker日志，报告31项目概况17次模型／62次工具回执，实际研究32次，其中22次无新增原文。已知但关闭的短工作ID不再误扣参数纠错额度；一个查询关联多个主题时，显式work只扣自身额度。轻量工具顶层禁止未知字段，status／scope／work_ids须在每条updates中；错误反馈给对应工具的字段路径及最小示例，避免放错层级被静默按found执行。
>
> 连续未分析的采集批次达到max_no_progress_rounds后返回analysis_required，暂停该工作的扩展检索及邻段补读，先分析已有原文；不判定完整或耗尽，处理后仍能追踪例外和清单续段，可同响应先登记再检索。批次随检查点保留，改写笔记不能解除；关闭／暂停回执不再豁免全局无进展，真实采集轮数由独立工作账控制，不转嫁给下一次正常关闭反馈。所有可处理工作受阻时尝试进入综合，真正非法参数仍受既有硬上限约束。
>
> 移除task／report／module／review的start、end及module.queued，完成后记录result或失败／取消／重试结果；module.efficiency并入专题结果，agent.round在模型返回后记录DEBUG，skill.load保持INFO。新增6项离线回归及1项数据库回归。最终统一后端 **1325 passed / 11 skipped**（71.72秒），Ruff、5项分层及协议／真实装配类型检查通过；隔离原生Windows PostgreSQL解析专项 **57 passed**（143.28秒）。日志.tmp/convergence-before.log、.tmp/convergence-targeted-final.log、.tmp/convergence-backend-final.log、.tmp/convergence-integration.log。工程14／20／22／23同步，测试库55442已正常停止。本轮无前端修改，未提交、启动WSL、启停业务服务或调用付费模型；实际请求及token降幅须加载新代码后另行约定样本验收。

> **2026-11-07 修复本轮审查发现的三处问题（未提交）**：`research-v2`综合阶段通过预校验的新草稿及业务修改计入阶段进展，合法分批不再触发无进展误封锁；重复断言、改名及复核标记切换仍不续期。独立审查无法定位到记录的问题只扩大到当前子主题，并沿父子／关系端点撤销下游依赖；每个主题落库前重新应用全部已知问题，防止后处理主题覆盖待复核资格，无关子主题继续保留。补跑未完成模块按研究账存在与否保留状态，即使只有examined笔记、证据和待办也沿用工作ID，不重置同行恢复预算；显式新attempt仍按原边界重置执行额度。
>
> 新增7项离线行为回归及1项数据库回归，离线反例修复前全部失败、修复后通过。最终 `scripts/check-backend.ps1` **1319 passed / 11 skipped**（78.60秒），Ruff、5项分层及协议／真实装配类型门禁通过；隔离原生Windows PostgreSQL解析专项 **56 passed**（133.70秒）。日志 `.tmp/review-fixes-before.log`、`.tmp/review-fixes-progress-before.log`、`.tmp/review-fixes-backend.log`、`.tmp/review-fixes-integration.log`。工程14／23同步；隔离测试库55442已正常停止并确认无监听。无前端改动，未自动提交、启动WSL、启停业务服务或调用付费模型。

> **2026-11-07 工作级上下文、原文去重及细则按需加载完成（未提交）**：新增 `application/analysis/context.py`，按工作／范围读取短笔记、依据及成果，保留公共／重叠范围条件、未归档／待分析补遗、转引、父子与关系依赖。同一证据只保存／返回一份；研究增量累计短笔记与依据，后续待办继承产生它的线索，成果持久化自己的work_ids。get_research_context返回完整units，以片段序号分页，续页要求revision，来源版本、原文或内容变化拒绝旧游标。大内容分片有start／total，调整limit不跳段。
>
> 去重只认当前有效工具消息的同来源版本完整原文，多片段须连续覆盖。底层already_read、缓存及同ID重放均重新核对；摘要移除、部分读取及版本变化时恢复原文。重放不能依赖即将被替换的同ID旧消息。缓存始终保留完整响应；内部版本证明只留消息元数据，实际模型请求与预算计量均剔除。查询分数不改变来源版本身份。
>
> 27份Skill资源逐条标明显式topics关联，研究按当前工作／待分析补遗／读取依赖选择细则，未分类及未知业务规则常驻，自定义清单无法映射时完整保留；综合和独立审查使用全集。13份资源导航同步按阶段读取说明，不增加挑选规则的模型调用。工程14／21／23、调研03及mypy入口同步。
>
> 新增27项离线回归和1项数据库恢复回归。最终统一后端 **1312 passed / 11 skipped**（68.04秒），Ruff、5项分层及端口／真实装配mypy **62个源文件通过**；隔离原生Windows PostgreSQL解析完整专项 **55 passed**（136.62秒）。日志 `.tmp/work-context-backend-final.log`、`.tmp/work-context-integration-final.log`、`.tmp/work-context-types.log`；本轮无前端修改。首次数据库新增用例因测试夹具缺evidence_topics失败，补齐后6项复验及55项完整专项均通过。隔离测试库55442已正常停止并确认无残留监听。
>
> 多标段工作上下文样例cl100k估算 **676→367**（约减少46%）；57组单主题细则合计 **79545→73576**（约减少7.5%），属静态样例。固定预算／日期短轨迹仍7次模型、6次工具，历史输入估算21855、本轮约2.22万，新增协议说明有固定开销，不能据此宣称整体费用下降。真实准确率及费用另定样本与上限验收；指标 `.tmp/work-context-metrics.json`。未自动提交、启动WSL、启停业务服务或调用付费模型。

> **2026-11-07 继续精简模型参数与阶段上下文（未提交）**：在上一轮 `research-v2` 基础上，业务字段共用 `RecordContent`，模型提交不再包含服务端生成的 `text`、`sort_order`；首次顺序由程序分配，修改同 key 保留位置。保留 `structuring` 及全部条件、材料、评分、范围和关系属性，避免自动掩盖尚未核清的业务条件。检索只选工作短 ID 即可推导主题，支持一次查询关联多个工作，各项预算独立保持；模型工作索引按主题／范围分组，隐藏内部 task_id，研究登记回执仅返回 changed_works。
>
> 研究阶段只注入领域与品类规则，综合阶段增加事项组织和紧凑输出契约；去除重复示例、格式说明及 coverage 清单。完整规则文件与局部规则分别记账，摘要后仍允许按需读取；未知领域小节完整保留。独立审查补齐工作方法和事项组织约束。清理26份资源中的旧 coverage/gaps 与 topic_updates.references 登记指引，业务判断保持完整。工程14、调研03及工程23同步。
>
> 最终 `scripts/check-backend.ps1` **1285 passed / 11 skipped**（65.80秒），Ruff、5项分层通过；协议及真实装配 mypy **61个源文件通过**。隔离原生 Windows PostgreSQL 解析完整专项 **54 passed**（158.69秒），覆盖十三专题调度、引用定位、恢复、取消和预算。本轮新增23项回归（19项模型负载与4项新协议摘要参数用例）。日志 `.tmp/model-payload-backend-final.log`、`.tmp/model-payload-types.log`、`.tmp/model-payload-integration.log`。测试库55442已正常停止；本轮无前端改动。
>
> 相同固定离线轨迹仍为7次模型请求（主Agent5、审查2）、6次工具调用，cl100k输入估算 **22348→21855**（约减少2.2%）；主Agent输入减少553，独立审查因补齐必要规则增加60。指标 `.tmp/model-payload-metrics.json`，真实费用及准确率须另定样本与费用上限验收。未自动提交、启动WSL、启停业务服务或调用付费模型。


> **2026-11-07 解析 Agent 与 Skill 职责精简完成（未提交、未部署）**：生产执行协议替换为 `research-v2`，每专题一个主 Agent，程序初始化稳定工作ID，研究用轻量 `ResearchDelta` 记录短事实、范围、证据和具体待办，最后统一综合。每条成果独立声明 work_ids，程序派生覆盖、位置和展示字段；取消固定每批三条及逐批支持性调用。研究阶段隐藏业务提交，综合隐藏检索，具体缺口用reopen重开；日常仅提供工作／成果索引，完整笔记、旧成果及原文按需分页读取。未找到核对真实查询、资料范围及未读分页，移除固定查询次数；资料缺失、不适用及未找到分开保存。明确范围替代保留工作身份，受阻撤销旧完成发现。
>
> 新增 `protocol.py`／`review.py`：合并独立支持性、逐正文引文及完整性审查，稳定record／value／citation ID映射，严格拒绝缺项、越界及重复JSON键；按最终序列化容量分包并共享原文，超长事项逐单元审查，补上下文须具体ID且去重。每次执行最多完整一轮、定向修复复核一轮；指纹覆盖领域规则、原文版本、成果及父子／关系依赖，数据库恢复复用一致结果，变化拒旧资格。发布要求全部归属主题和依赖有效，未审草稿只留内部；权限、取消、owner、租约和硬预算边界继续生效。不兼容报告／检查点明确提示重新创建，无数据库结构迁移。同步13专题51份资源、前端研究／综合／审查提示及工程14／21／23、调研03。
>
> 最终统一检查 **1262 passed / 11 skipped**（67.82秒），Ruff、5项分层、端口／真实装配及新增协议／审查mypy通过；隔离原生Windows PostgreSQL完整集成 **190 passed**（201.85秒），包含十三专题真实调度、引用选择定位、持久审查复用及恢复／取消边界；pnpm类型检查、**64项单测**、**70项桌面／手机浏览器专项**通过，审查阶段截图已复核。日志 `.tmp/compact-backend-latest.log`、`.tmp/compact-integration-all-final.log`、`.tmp/compact-web-final.log`、`.tmp/compact-browser.log`。隔离测试库55442已正常停止，浏览器4414已退出，无残留监听。
>
> 十三专题人工编写样例验证结构、全部业务属性与引文传输，预算／日期标注样例核对条件、例外、范围和最终引用。固定离线轨迹模型请求 **11→7**（主Agent **8→5**，独立审查 **3→2**），工具 **9→6**，cl100k输入估算 **78897→22348**，完整原文重复出现字符 **542→236**；摘要／格式纠错在该轨迹均为0。指标见 `.tmp/compact-sample-metrics.json`，不作为真实模型费用或准确率结论。真实模型节省比例和准确率须另定样本、费用上限验收。本轮未启动WSL、启停业务服务、调用付费模型或提交代码。

> **2026-11-07 按用户确认改为先研究、后统一综合（未提交、未部署）**：新报告冻结 `__analysis_output_mode__ = "after-research"`，在既有topic-v1状态机内实现研究／综合阶段。Skill的checks初始化todo；`update_research`批量保存带真实项目证据的findings、待办和转引，一次检索可覆盖多个主题／字段，后续按具体缺口调整关键词。研究阶段拦截业务提交，研究完成不再要求先有业务记录；未找到须说明范围，服务端核对真实查询、授权项目资料和未读分页／截断，每个未找到核对项独立保留缺口。新增证据保留笔记并要求重新分析；按本待办发现／解决判断进展，重复换词和改写笔记不重置工作额度。研究完成后统一综合，可按最多三条分批校验暂存；最后一批final=true后进行一次完整查漏，最多一次定向修复复核。后续非final或无效提交撤销旧完成意图。研究和综合期间页面只展示阶段及进度，专题结束统一发布有效结果，部分发布仍核对权限、取消、owner、租约与锁。显式补跑即使只有研究笔记也保留，同行恢复和预算保持原边界。
>
> 同步13专题共51份Skill说明／样例、页面及工程14／21和调研03。新增17项真实图／状态行为回归和5项数据库回归，既有真实执行器场景改为新时序并覆盖4／5／40请求额度。最终统一后端 **1231 passed / 11 skipped**（79.25秒），Ruff、5项分层及协议／真实装配mypy通过；隔离 Windows PostgreSQL 研究／专题／恢复专项 **30 passed**（40.79秒）；pnpm前端类型、**64项单测**和桌面／手机浏览器专题专项 **70 passed**（5.7分钟）通过，新阶段截图已复核。日志 `.tmp/research-first-backend-final.log`、`.tmp/research-first-integration-final.log`、`.tmp/research-first-web-tests.log`、`.tmp/research-first-browser.log`。隔离测试库55442已正常停止、浏览器4413服务已退出，无残留监听。浏览器副本 `.tmp/research-first-web-20261107`。未启停业务服务、启动WSL、调用真实／付费模型、修改业务数据或提交。真实准确性及费用变化仍需约定样本和费用上限后验收。

> **2026-11-07 修复解析 Agent 全面分析发现的八类缺陷（未提交、未部署）**：新流程每轮持续提供领域知识、识别与品类细则，移除重复的通用 Skill 发现提示；摘要使用有效消息识别完整文件，处理无消息ID摘要和同轮压缩后的读取标记，避免丢失规则或用归档文件返回短回执。省略 `work` 使用独立主题探索账，不耗尽具体核对项；核对项只认自身完成，具体待办只认关联核实成果，不被同主题其他工作续期。正常关闭返回 `work_closed`，不占全局参数纠错账、不进入研究缓存；硬预算及相同调用限制继续有效。上下层查询缓存仅去首尾空白，保留内部空格和HTML实体。完整查漏保存各主题指纹，修复期间其他变更主题进入同次定向复核，最终签名覆盖全部主题；`target`持久化并进入工作提示，更新省略时保留。动态提示完成后统一计量消息与工具，预留输出和5%余量，不可压缩时保留部分成果。同attempt恢复读取持久模型恢复次数。
>
> 新增12项离线反例及3项数据库回归，最终统一后端 **1214 passed / 11 skipped**（62.13秒），Ruff、5项分层、协议与真实装配mypy通过；隔离 Windows PostgreSQL 新流程及恢复专项 **24 passed**（26.13秒）。日志 `.tmp/audit-repairs-backend-final.log`、`.tmp/audit-repairs-integration-final.log`。工程14与调研03同步；测试库 `.tmp/topic-v1-20261107-db`（55442）已正常停止。未启停业务服务、启动WSL、调用真实／付费模型或提交。稳定ID校验返回、结构覆盖索引、跨专题共享及阶段模型路由仍属调研建议，本轮修复聚焦八类明确缺陷；支持性校验的二维证据数组协议尚未重构。

> **2026-11-07 按用户建议简化 Skill 与增量协议（未提交、未部署）**：报告30项目概况运行约13分25秒，43次工具调用、30次搜索尝试；25次实际研究中19次无新增原文，三次提交均因未知范围绑定失败，最终保存0项。现允许记录和主题同为 `unknown` 时先保存核实正文，逐条确认范围时保留其他未知事实，完成及下游消费仍要求明确范围；提供具体范围确认工作。`topic_updates` 从真实记录、既有归属及引用自动补齐机械参数，业务checks仍由Agent声明；`work` 支持省略、工作ID、文字及数组，兼容分号，一次研究覆盖多个问题，各工作额度与分页门禁不重置。精简13份Skill及配套说明／示例，移除额外空提交示范，日常提示不重复固定协议；仅对当前上下文已有完整规则的读取返回短回执，摘要后的必要细则仍允许按需加载。页面改为正文前紧凑进展、正文后默认折叠核对详情，`blocked` 显示“研究受阻”，保留待复核正文与原文定位。
>
> 最终统一后端 **1203 passed / 11 skipped**（61.61秒），Ruff、5项分层及协议／真实装配mypy通过；隔离 Windows PostgreSQL 新流程专项 **18 passed**（19秒）；前端pnpm类型检查、**64项单测**及桌面／手机浏览器专题专项 **78 passed**（4.6分钟）通过，截图已复核。日志 `.tmp/protocol-backend.log`、`.tmp/protocol-integration.log`、`.tmp/protocol-browser.log`。工程14／23同步；隔离库 `.tmp/topic-v1-20261107-db`（127.0.0.1:55442）已正常停止，4412浏览器测试服务已退出，两端口无残留监听。浏览器在 `.tmp/protocol-web-20261107` 副本运行，原4400业务前端保持原进程。
>
> 本段为最新状态；后端加载新代码后使用修正协议，更新Skill由新报告冻结，报告30失败状态及旧快照不自动修改。未提交、启停业务服务、启动WSL或调用真实／付费模型，实际费用降幅尚无真实模型对照。临时脚本 `.tmp/simplify-skill-resources.py` 不可重复运行，避免重复插入说明。

> **2026-11-07 按用户要求提交检索收敛优化及四项审查修复**：本次提交包含具体工作检索门禁、稳定待办身份及独立额度、真实分页游标校验、关联主题保守复核、无进展收敛与部分成果保留、显式补跑及恢复边界、效率统计，以及配套回归和文档。提交说明为“优化待办检索收敛并修复复核范围与分页边界”，提交号以git log为准。本段覆盖下方本轮相应“未提交”状态；验证沿用最终统一后端 **1151 passed / 11 skipped**、Ruff、5项分层及协议／真实装配mypy通过，以及隔离 PostgreSQL 新流程专项 **17 passed**。提交前差异及UTF-8检查通过；未推送、部署、重启业务服务或调用真实模型。

> **2026-11-07 修复检索收敛审查的四处问题（未提交）**：新原文按关联主题保守复核，移除仅凭待办 `record_keys` 缩小影响范围的门禁，防止混合条款中的旧数量等继续成为有效部分成果；其他主题保留。耗尽核对项登记 `blocked_checks`、转引标记 `budget_exhausted`，只关闭相应工作，同主题剩余核对项、转引和待办继续处理。待办以服务端稳定 `task_id` 区分，新增省略ID、改名及更新沿用ID，空关联或同记录的独立待办不再共享额度；非法ID原子拒绝，恢复不重置工作账，显式补跑保留身份并开放所有受阻类型。分页须匹配同查询、同工具的真实 `has_more/next_offset`，合法后续页实际命中原文才豁免无进展计数；末页、空页和越界偏移不再续命。新增反例初始11项全失败，补齐后共新增14项离线行为回归及1项数据库回归；最终统一后端 **1151 passed / 11 skipped**（67.16秒），Ruff、5项分层及协议／真实装配mypy通过；隔离 PostgreSQL 新流程专项 **17 passed**（19.78秒）。工程14／23同步，本段覆盖下方“具体待办缩小复核”和“同事项共用额度”的旧实现说明；测试数据库已正常停止并确认无残留监听。日志 `.tmp/search-review-before.log`、`.tmp/search-review-backend.log`、`.tmp/search-review-integration.log`。本轮未提交、部署、重启业务服务、启动WSL或调用真实／付费模型。

> **2026-11-07 提交后继续优化检索收敛（后续优化未提交）**：前序增量解析及四项审查修复已提交为 `bab3293`（实现子主题增量解析并完善范围迁移与校验收敛）。本轮新增 `application/analysis/search_control.py`：检索／扩展补读通过 `work` 绑定具体核对项、待办、转引或待复核事项，已完成及受阻工作在缓存返回前拦截；同事项待办改名、换检索词及新增无关原文不重置无进展账，真正分页及新清单续段仍可继续。默认三次无进展后先分析最后一批原文，无进展却继续泛搜才保留受阻缺口；一个待办耗尽不封锁同主题其他待办。明确关联事项的新证据只复核这些事项及依赖，补遗／正文修订信号保守扩大；参数纠错耗尽停止扩展，引用原块回读继续核对权限。失败调用清除临时归因，同attempt恢复保留工作账，显式补跑重置本次研究额度及效率统计；有已知受阻内容时不再浪费完整查漏。新增 `module.efficiency` 汇总研究、重复证据、缓存及送审计数，供应商请求与token沿用原账本。新增30项离线行为回归及1项数据库回归；最终统一后端 **1137 passed / 11 skipped**（104.05秒），Ruff、5项分层及协议／真实装配mypy通过；隔离 PostgreSQL 新流程专项最终复验 **16 passed**（19.30秒）。复验前隔离库意外退出，已恢复、复验并正常停止，确认无残留监听；日志 `.tmp/search-control-backend.log`、`.tmp/search-control-integration-recheck.log`，工程14／21／23同步。后续优化保持未提交，未重启业务服务、启动WSL或调用真实／付费模型，实际费用降幅待约定样本验收。

> **2026-11-07 按用户要求提交增量解析及审查修复**：本次提交包含子主题增量研究、分批校验与实时展示、局部复核和独立查漏，以及三项 P2 和范围迁移 P1 修复。提交说明为“实现子主题增量解析并完善范围迁移与校验收敛”，提交号以 git log 为准。本段覆盖下方相应“未提交”状态；最终验证沿用统一后端 **1107 passed / 11 skipped**、隔离 PostgreSQL 新流程专项 **15 passed**，以及此前前端类型、64项单测和76个不同浏览器场景的结果。提交前差异检查通过，未推送或部署。用户同时授权继续优化检索收敛，后续改动另行保持未提交。

> **2026-11-07 继续修复 P1 范围确认及修订无法收敛（未提交）**：未知范围确认自动迁移证据、待办和转引，已明确范围通过同批 `topic_updates.replaces_scopes` 声明替代；旧事项须全部分配到目标更新，支持多标段拆分及部分事项保留原范围，真正并存的范围继续核对。目标范围重新确认 checks，迁移事项待复核后才能成为有效成果，旧范围证明不能直接复用；预校验失败时保留来源范围和修正待办，同批有效事项照常保存。替代关系随现有 JSON 状态持久化，恢复及纠正重提幂等，无迁移、不重置预算。新增13项离线回归及1项数据库回归；统一后端 **1107 passed / 11 skipped**（71.57秒），Ruff、5项分层及协议／真实装配 mypy 通过；隔离 PostgreSQL 新流程专项 **15 passed**（42.89秒）。测试实例 `.tmp/topic-v1-20261107-db`（127.0.0.1:55442，用户 `topic_test`，数据库 `postgres`）已正常停止。工程14／23同步，本段覆盖下方 P1 暂缓状态；四项审查问题均已修复，未启动WSL、启停业务服务、调用真实模型或提交。

> **2026-11-07 修复增量解析审查的三项 P2 问题（未提交）**：检索／补读缺失或错填 `topic_keys` 改为现有可纠正参数错误，沿用参数纠错计数；新证据首次关联相关主题时解除对应事项及不适用证明的旧拒绝门禁，包含已被移出暂存区的记录，保留累计纠错次数和硬预算，普通回读及其他主题不重开。重新核实成功后清除该事项旧拒绝缺口。批内预校验失败时隔离失败记录的进度关联、撤销其完成声明并保留具体待办，同批有效事项继续校验保存，修正时只送审失败项。新增11项真实图及状态回归，专题专项 **34 passed**；统一后端 **1094 passed / 11 skipped**（61.09秒），Ruff、5项分层及协议／真实装配 mypy 通过；隔离 Windows PostgreSQL 新流程专项 **14 passed**（20.37秒）。测试实例 `.tmp/topic-v1-20261107-db`（127.0.0.1:55442，用户 `topic_test`，数据库 `postgres`）已正常停止。本轮按用户范围暂不修改 P1 范围迁移问题；该问题发生在同次运行的范围核实／修订，与历史数据兼容无关。未启停业务服务、启动WSL、调用真实模型或提交代码。

> **2026-11-07 按子主题增量解析（未提交、未部署）**：新报告冻结 `__analysis_flow_version__ = "topic-v1"`，每专题仍为一个 Agent；按冻结 Skill 的具体核对项及适用范围维护进度、证据、事项和待办。有据事项每批最多三条，经结构、逐字引用及支持性校验后立即保存，页面沿用三秒轮询展示。新增相关依据只复核受影响成果，保留旧核实正文并标记待复核；跨主题复用已读证据首次关联也会触发复核，正式有效成果排除未复核记录。覆盖充分自动独立查漏，每次运行最多一次完整检查及一次修复后的定向复核；逐批指纹缓存随状态保存，恢复复用且不重置预算。新流程取消耗时四倍和剩余四分之一次数强制收尾，硬上限耗尽后保留有效成果为部分完成，无可用成果则失败；到期收尾仍核对授权、取消、owner、租约及锁。历史报告缺少标记继续旧流程，未提升全局版本，无数据库迁移，保留此前退避溢出修复。
>
> 最终统一后端 **1083 passed / 11 skipped**（56.65秒），Ruff、5项分层及协议／真实装配 mypy 通过；隔离原生 Windows PostgreSQL 完整集成 **171 passed**，最后边界修复后新流程专项复验 **14 passed**；前端 pnpm 类型检查及 **64项单测**通过。桌面／手机浏览器专题专项首次74项通过，另两项因夹具的报告与记录状态冲突失败；修正夹具后，两项及新增增量场景共 **4 passed**，全部76个不同场景均已通过。人工标注样本核对金额单位、精确时点、独立事项、A标段、电子递交前提、延期例外及引文，固定替身轨迹请求 **11→9**、工具 **9→6**（包含新流程两次查漏），输入估算 **78067→43520 cl100k_base tokens**；离线耗时141／93毫秒，不代表真实模型时延或费用。真实模型对照仍按用户要求另定样本及费用上限。
>
> 工程14／21／23已同步；隔离数据库 `.tmp/topic-v1-20261107-db`（127.0.0.1:55442）及浏览器4412服务均已停止，原4400业务前端保持运行。补丁待后续加载后用于新报告；本轮未启动WSL、重启业务服务、调用真实模型、写业务数据或自动提交。单批修订原文超过24000字符会明确部分完成，详见工程14。

> **2026-11-06 修复报告29长队列溢出并调整慢模型收尾（未提交、未部署）**：日志及用户堆栈确认11个尚未调用模型的专题在配额等待约100分钟后，因退避先计算巨大整数再转浮点而失败；等待与模型恢复现都在求幂前限制指数，原间隔、抖动、权限复核和预算不变。基本信息专题有50次检索、后期综合单轮约264—303秒，已核实10条却因一小时预算耗尽失败。专题现按已完成主模型请求最大耗时的四倍与旧基线取较大值预留收尾，统计随应用状态保存；排队、工具、请求前权限检查和失败请求不更新统计。最后一批可带records和final=true，经原预校验／支持性校验后结束，省去强制空提交；同步13专题的50份说明，运行时覆盖旧冻结Skill的空提交要求，不改写快照。另提示只追查具体未决问题，不以用满额度或证据块数量判断完成。新增8项回归，先复现溢出及缺失计时，再验证1100轮等待、极大轮次封顶、慢／快模型、恢复统计、失败请求和旧Skill非空final经校验直接结束；最终统一后端 **1059 passed / 11 skipped**（74.05秒），Ruff、5项分层及协议／实际装配mypy通过，3条structlog提示。工程14／23已同步，差异及UTF-8检查通过。未启动WSL、重启服务、调用真实模型、修改业务数据、自动补跑或提交；Worker加载后生效，历史失败及10条暂存成果不自动改为完成。真实完整性、调用数和费用仍待对照验收；四轮预留不能保证所有复杂专题都完成。

> **2026-11-06 按用户要求提交长队列与慢模型收尾修复**：本次提交包含领取配额及模型恢复的退避溢出修复、按已完成模型请求耗时预留收尾、最后一批非空final提交提示，以及相关回归与13专题说明。提交说明为“修复专题长队列退避溢出并优化慢模型收尾”，提交号以git log为准。审查后重新运行统一后端检查，**1059 passed / 11 skipped**（61.48秒），Ruff、5项分层及协议／真实装配mypy通过；提交前差异与UTF-8检查通过。本段覆盖下方相应“未提交”状态；未推送、部署、重启服务或调用真实模型，历史失败与真实完整性验收边界保持原记录。

> **2026-11-06 按用户要求提交日志格式与字段精简**：本次提交统一将警告展示为 `warn`，按事件省略重复阶段和指定默认值，报告来源数量只在报告开始记录；`skill.load` 保持INFO，工具参数继续完整记录并沿用脱敏和限长。复核发现自动异常摘要仅500字符，无已核实成果的失败分支最终改为显式 `error=error_detail(reason)`，避免丢失长原因末尾的后备模型错误，同时不重复 `reason`。加强真实执行器／格式器回归，验证500字符以后的原因仍在普通日志可见、原始SDK异常链不泄漏。最新统一后端 **1051 passed / 11 skipped**，Ruff、5项分层及协议／真实装配mypy通过，差异与UTF-8检查通过。提交说明为“统一警告日志格式并精简重复字段保留完整错误原因”，提交号以git log为准。本段覆盖下方相应未提交状态及仅依赖自动摘要的临时方案；未推送、部署或重启服务，相关API／Worker／Beat重载后生效。

> **2026-11-06 按事件精简重复日志字段（未提交、未部署）**：核验事件省略固定 `agent_phase=verification`，模型调用继续保留阶段；`module.start`／`review.end` 分别省略 `resumed=false`／`needs_correction=false`，true和其他0/False不变。报告共用来源数量只在 `report.start` 记录，无已核实成果的失败原因改由异常摘要和错误文件承载，取消及部分成果的独立原因保留。用户明确要求 `skill.load` **保持INFO、不降级**；工具参数继续完整记录并沿用脱敏和限长。日志专项 **74 passed**、20项JSON／文本格式核对通过；统一后端 **1051 passed / 11 skipped**，Ruff、5项分层及协议／真实装配mypy通过，差异与UTF-8检查通过。包含下方未提交的warn展示改动；未提交、重启业务服务、启动WSL、修改历史日志或调用真实模型，相关API／Worker／Beat重载后生效。

> **2026-11-06 警告日志统一输出 warn（未提交、未部署）**：仅在统一格式器将 WARNING 的展示名称改为 `warn`，控制台、JSONL及文本错误文件共用；内部仍使用 `logging.WARNING`／`logger.warning()`，配置仍写 `LOG_LEVEL=WARNING`，过滤和异常分流规则不变。同步既有HTTP、Celery重试及输出回归断言与日志文档；统一后端 **1051 passed / 11 skipped**，Ruff、5项分层及协议／真实装配mypy通过。未重启API／Worker／Beat、修改历史日志或提交；相应服务重载后生效。

> **2026-11-06 按用户要求提交日志精简**：本次提交包含项目/报告/专题上下文、七个内部日志字段省略、`agent.round`降为DEBUG，以及回归和日志文档。提交说明为“精简分析日志字段并直接关联项目和报告”，提交号以git log为准。沿用最新统一后端 **1051 passed / 11 skipped**、Ruff、5项分层和协议／真实装配mypy结果；提交前差异与UTF-8检查通过。本段覆盖下方日志精简改动的“未提交”状态；未推送、未部署，相关API／Worker仍需重载后生效。

> **2026-11-06 按用户要求精简分析日志（未提交、未部署）**：`agent.round` 降为DEBUG；控制台、JSONL和错误文件统一省略顶层`task_id/run_id/tool_call_id/invocation_id/thread_id/skill_path/sha256`，ID和Skill元数据仍保留于内部账本、协议、快照及检查点供执行与恢复使用。报告与专题上下文直接绑定`project_id/report_id`，专题继续用`module_key`区分；项目上下文支持线程和Celery消息头传播，不从任务参数猜项目。日志专项 **74 passed**；最新统一后端 **1051 passed / 11 skipped**，Ruff、5项分层与协议／真实装配mypy通过；多项目多专题并发、工具消息绑定、模型路由和恢复回归通过，格式回归验证JSONL、控制台及错误文件省略字段且保留项目/报告身份；差异与UTF-8检查通过。未重启业务服务、启动WSL、修改历史日志或调用真实模型，补丁待相关API／Worker重载后生效。

> **2026-11-06 按用户要求提交本轮优化与审查修复**：本次提交收录补跑工具预算重置、检索分页与并发缓存复用、客户端关闭容错及校验JSON压缩、模型默认启用和列表启停、全站固定导航与历史滚动恢复，以及配套测试和文档。提交说明为“优化解析检索与补跑预算并完善模型启停和页面滚动”，提交号以git log为准。验证沿用本轮统一后端 **1051 passed / 11 skipped**、独立Windows PostgreSQL集成 **162 passed**、前端 **63项单测**、开发／生产框架各 **10 passed**、类型检查与Webpack生产构建；提交前差异及UTF-8检查通过。本段覆盖下方相应改动的“未提交”状态；未推送、未部署，未启动WSL或调用真实模型。

> **2026-11-06 修复根视口历史滚动串页（未提交）**：新增 `AppViewport`，新导航回顶，浏览器前进／后退按历史条目恢复位置，同一URL多次访问互不覆盖；等待异步列表撑开后恢复，用户主动操作取消等待，正文锚点及工作台面板滚动保持可用。保留Next历史状态并处理浏览器先提交条目与Strict Mode重装时序；查询串监听单独包裹Suspense，避免业务正文重复挂载；历史键不依赖HTTPS。新增两个桌面／手机回归场景，其中延迟响应明确拦住返回页数据；开发模式框架 **10 passed**，最终生产构建后框架 **10 passed**，前端 **63项单测**、类型检查和Webpack生产构建通过，差异与UTF-8检查通过。临时前端验收服务已停止，未修改后端、业务数据或模型配置，未启动WSL、调用真实模型或提交；保留此前所有未提交改动。

> **2026-11-06 后端分页复用与校验输入优化（未提交、未部署）**：修复不同语义查询误用缓存、同查询并发重复召回、固定30条导致大页后续候选丢失，以及缓存未读完却催促改写查询；检索客户端关闭故障不再覆盖结果或关键词回退。召回／缓存统一共用五页窗口，阈值、权限和工具预算继续执行。支持性校验只压缩JSON格式空白，三个离线样本在两种分词器下输入token减少约2.9%—7.8%，不代表真实账单或准确率。新增14项回归并补齐既有生命周期夹具状态；最终统一后端 **1051 passed / 11 skipped**，Ruff、5项分层及协议／真实装配mypy通过，独立Windows PostgreSQL完整集成 **162 passed**。测试库55441已正常停止；未启动WSL、重启业务服务、改业务数据或模型配置、调用真实模型、提交或推送。保留此前全部未提交改动，详细证据见工程23。真实专题完整性及生产规模性能仍需验收，原文归属校验的全文读取等限制仍在。

> **2026-11-05 全站固定顶部框架（未提交）**：用户确认后已将AppRail统一放入根布局，移除PageShell、分析页及文档工作台的重复导航；根框架100dvh，下方内容视口独立滚动，普通页面按内容展开，工作台使用视口剩余高度并保留面板内滚动。手机菜单换行由Flex自动分配高度，不写死顶部偏移；客户端切页保留同一导航节点，正文回到顶部，键盘跳转与弹窗层级保持可用。同步设计06。新增桌面／手机框架专项 **6 passed**，页面、长表单、抽屉与原文跨页定位回归 **20 passed**，typecheck及Webpack生产构建通过；截图复核、差异与UTF-8检查通过。新增框架夹具补齐项目分页字段，避免旧通用夹具缺少limit而无限补页；未修改业务分页实现或旧通用夹具。保留此前预算与模型管理补丁，未提交、启动WSL、重启后端、调用真实模型或改写业务数据。

> **2026-11-05 模型默认启用与列表启停（未提交、未部署）**：手动创建明确发送enabled=true，确认配置后的导入也默认启用；模型列表提供启停开关，提交当前revision，成功后刷新，失败保留原状态。编辑表单移除启停项，不再回写旧状态；已有模型及重复导入的用户停用状态不被覆盖。同步模型设计与需求核对文档。前端typecheck与桌面／手机浏览器专项 **8 passed**；独立原生Windows模型管理／导入专项 **2 passed**，测试库已停止。最终统一后端 **1037 passed / 11 skipped**，Ruff、5项分层及协议／真实装配mypy通过，严格UTF-8检查通过。与下方预算修复一起保持未提交；未启动WSL、重启业务服务、修改存量模型或业务配置、调用真实模型。后端补丁仍需重载API后生效，当前模型列表可直接操作启停。

> **2026-11-05 修复补跑工具预算误判（未提交、未部署）**：报告27／项目基本信息模块第3次运行1276只用了26/100次工具，却因继承旧研究计数76、再执行24次读文达到100而失败。补跑现保留证据、检索过程和成果，但新attempt的研究工具计数归零；同attempt中断恢复仍累计，已完成模块显式重跑仍从头开始。新增4组回归先失败再通过，统一后端 **1037 passed / 11 skipped**，Ruff、5项分层及协议／真实装配mypy通过；独立原生Windows测试库的补跑／完整重跑专项 **3 passed**，测试库已停止。未启动WSL、重启业务服务、改写业务数据或模型配置、调用真实模型、提交或推送。现有API／Worker尚未加载本补丁，需重载后补跑；历史失败记录保持原样。

> **2026-10-28 按用户要求提交本轮后端修复**：本次提交包含解析失败排空与配额保留、成果校验边界、异步数据库调用及预占取消记账、有界原文补读、Redis超时、查询职责拆分与类型检查扩展，以及配套测试和文档。提交说明为“修复后端解析排空与异步记账并优化原文补读”，提交号以 git log 为准。验证沿用最终统一离线 **974 passed / 10 skipped**、此前六项修复的完整隔离 PostgreSQL 集成 **155 passed**，提交前差异及UTF-8检查通过。本段覆盖下方对应改动的“未提交”状态；未推送、未部署。

> **2026-10-28 修复复审发现的预占取消记账回归（未提交、未部署）**：模型路由在预占期间收到取消时，等待受保护的预占线程落定，再向同一调用账写入 `error` 与“未向供应商发送请求”，最后传播取消；重复取消不能打断收尾，预占提交后报错也会补终态，避免迟到的 `running` 覆盖结果。已发出请求后的取消继续记录 `unknown`。新增5项回归，其中预占取消4组先失败再通过；最终统一离线检查 **974 passed / 10 skipped**，Ruff、5项分层契约与协议/真实装配mypy通过，差异及UTF-8检查通过。本次仅修改应用路由、测试与说明，未重新运行数据库集成；下方155项数据库结果属于此前六项修复。未启动 WSL、数据库或业务服务，未调用真实模型、提交或推送。

> **2026-10-28 后端六项审查问题修复（未提交、未部署）**：解析超时、轮询预算耗尽和未知提交改为非终态 `draining`，保留首次错误、活动 ParseRun 与远端配额；只排空，不重提，确认远端停止后同事务失败收尾。取消/排空轮询不再受缺失 MiddleJson 阻塞，正常成果消费仍校验。异步接口及模型路由的同步数据库回调移入线程；专题/问答显式补读改为仓储窗口，旧索引流式扫描所需前缀，不为总数扫描全文。Redis 连接/读取超时均为0.5秒、禁重试，异常继续回源数据库。报告查询和检索模型配置查询按业务归位，保留联合事务；mypy 扩大到研究、检索、任务、分块及新拆查询模块，共56个源文件通过。统一离线检查 **969 passed / 10 skipped**，完整隔离 PostgreSQL 集成 **155 passed**，Ruff与5项分层契约通过；最终排空专项5项通过。独立原生 Windows 测试库（55439）已停止并确认无服务运行；未启动 WSL 或业务服务，未迁移业务库、调用真实模型、提交或推送。未知提交仍需人工核对；回退深 offset 仍扫描前缀、单条大元素仍读取该元素，支持性证据归属校验仍有全文路径，KnowledgeStore 与 Any/strict 覆盖仍有后续收敛空间。本轮没有真实供应商效果或生产规模压测验收证据。

> **2026-10-28 按用户要求提交后端审查修复**：本次提交包含任务取消生命周期、知识来源首次解析配置、部分重排候选保留及配套测试和文档，提交说明为“修复任务取消与知识解析配置并保留重排候选”，提交号以 git log 为准。沿用本轮统一离线 **960 passed / 10 skipped**、完整隔离 PostgreSQL 集成 **132 passed**，提交前差异检查通过。本段覆盖下方本轮修复的“未提交”状态；未推送、未部署。

> **2026-10-28 后端审查三项问题修复（未提交、未部署）**：取消中的运行任务改为非终态 `canceling`，保留配额与恢复能力；本地退出或远端终态后，同事务收敛 Job/ParseRun，阻止取消后创建版本、发布成果及重新提交。远端提交结果不明时保留占用并提示人工核对。知识来源首次处理改为读取活动配置的 tier/OCR；部分 top_n 重排保留其余合格候选与正确的截断标记。统一离线检查 **960 passed / 10 skipped**，完整隔离 PostgreSQL 集成 **132 passed**，Ruff、5项分层契约及协议/真实装配 mypy 通过。独立原生 Windows 测试库（55439）已停止；未启动 WSL 或业务服务，未迁移业务库、调用真实模型、提交或推送。接口及架构文档已同步；真实远端取消/解析效果没有新增验收证据。

> **2026-10-26 按用户要求提交后端架构修复**：本次提交包含文档恢复调度与配额、四组 Worker 隔离、数据库检索、用例归位、仓储窄端口、Agent 状态转换，以及迁移、测试和部署文档。提交说明为“修复后端任务调度与检索并完善架构边界”，提交号以 git log 为准。沿用本轮最终验证：统一检查 **952 passed / 10 skipped**、完整隔离 PostgreSQL 集成 **118 passed**，启动脚本44项、OpenAPI与迁移往返通过；提交前差异检查通过。本段覆盖下方本轮改动的“未提交”状态，未推送、未部署。

> **2026-10-26 后端七项架构问题修复完成（未提交、未部署）**：文档任务改为数据库持久调度与消息租约恢复，修复跨阶段配额、并发派发、迟到消息越过交接闸门及恢复扫描公平性；部署拆为调度、轮询、文档、分析四组 Worker。检索复用持久分块并在 PostgreSQL 内精确排序，仅返回有限候选。报告/索引/问答与模型路由业务已移入 application，仓储按调用能力拆窄端口，Agent 核心转换集中到 state.py。最终统一检查 **952 passed / 10 skipped**、完整隔离 PostgreSQL 集成 **118 passed**，Ruff、5项分层及mypy通过；启动脚本44项、66条路径的完整OpenAPI前后对照、Compose静态检查及0017迁移往返通过。本轮独立原生Windows测试库（55439）已停止，未启动WSL、启停业务服务、迁移业务库、修改模型配置或调用真实模型。上线需先应用0017，再加载四组Worker及后端进程；此前真实完整解析效果仍未获得新验收证据。详情见末尾与工程11/21。

> **2026-10-24 按用户要求提交当前修复**：本次提交包含流内错误分类、参数校验反馈、解析阶段交接及配套测试和文档，提交说明为“修复流内错误分类与解析阶段交接并完善参数反馈”，提交号以 git log 为准。沿用已完成的统一后端验证 **945 passed / 9 skipped**，相关测试复核 **142 passed**，提交前差异检查通过。本段覆盖下方对应补丁的“未提交”状态；真实完整解析仍未通过验收，未推送。

> **2026-10-24 最新续接：WSL已恢复、阶段交接修复已验证**：已读取最新有实质工作的同名会话 `01a16c77-7581-7b03-9163-173030ab2895` 及其续接分段，用户已自行启动WSL；下方“WSL关闭导致受阻”仅为历史。修复收尾阶段仍被旧补读错误指引牵引的问题，最后追加简短的当前工具／下一步通知，保留历史与首次项目检索前提，不重复完整Skill。统一后端 **945 passed / 9 skipped**。Nemotron保证金隔离验收已越过旧阶段卡点并登记研究，但497.22秒、35次模型调用后，因两次改写引文和收尾无进展退出，0项核实、无final；完整解析仍未通过。复核无活动任务后已重启后端三进程加载补丁，健康检查通过；补丁未提交，禁止自动启动WSL继续有效。详情见末尾最新记录。

> **2026-10-24 目标验收受阻**：连续三个目标轮次中，真实验收均受WSL关闭且用户禁止自动启动的同一条件限制。本轮再次只读确认无运行中的WSL实例，未启动WSL或重启服务。已完成可独立推进的日志诊断、局部修复与离线验证（**943 passed / 9 skipped**），但最新补丁的运行加载、完整真实专题成功、事项完整性和逐条引用验收仍无证据，目标不能标记完成。需用户自行恢复WSL／数据库后继续；恢复时先复核全库活动任务和当前模型绑定，再加载补丁并真实验收。最新流内错误与参数反馈修复仍未提交，既有提交为93144e4。

> **2026-10-24 补齐参数纠错的具体规则**：本地日志确认报告23的run1208／1209反复将common与非空lot_refs一起提交，旧反馈只指出scope路径，丢失冲突规则。现反馈保留字段路径和校验原因，排除原始input／ctx，最多6项、1000字符；非法数据仍拒绝，范围、逐字引用和预算不放宽。新增3项回归先失败再通过，统一后端 **943 passed / 9 skipped**，Ruff、分层及协议／真实装配mypy通过。只读 `wsl.exe --list --running --quiet` 确认无运行实例，**禁止自动启动WSL**继续有效；未启动WSL、重启服务、调用真实模型或提交，真实完整解析仍待验收。

> **2026-10-24 用户运行约束与流内错误修复**：用户已关闭WSL，明确要求**禁止自动启动WSL**，后续必须遵守，不能为验收自行恢复实例。关闭前只读确认报告23全部13个专题失败、全库无活动分析或文档任务，API／Worker仍早于最新补丁；没有重启服务。另修复HTTP 200流内503／429被原生适配器当永久失败，以及JSON校验流内403被当临时故障、根因丢失的问题；新增8项回归先失败再通过，最终后端 **940 passed / 9 skipped**，Ruff、分层及协议／真实装配mypy通过。新增修复未提交、未载入业务进程，真实完整解析仍待WSL由用户自行恢复后验收，详见末尾与工程23。

> **2026-10-23 按用户要求提交解析异常修复**：本次提交收录证据预算收尾、合法回读缓存、逐条提交与引用绑定复用、完成意图与不适用证明纠错、工具协议反馈及模型／日志错误摘要修复，包含配套回归和工程文档。提交说明为“修复解析收尾与重复校验并完善工具协议错误反馈”，提交号以 git log 为准。验证沿用刚完成的后端 **932 passed / 9 skipped**，Ruff、分层及协议／真实装配mypy通过；提交前差异与UTF-8检查通过。本段替代下方对应改动的“未提交”状态；未推送、未重启业务服务，真实完整解析仍待验收。

> **2026-10-23 修复审查发现的旧事项重复送审回归**：比较时两侧都排除内部 `output.citations`，新增其它事项及空提交收尾不再重审旧事项，保留全部已核实绑定；实际正文改写仍送审。新增真实校验器回归先失败再通过，统一后端 **932 passed / 9 skipped**，Ruff、分层及协议／真实装配mypy通过。未重启业务服务、调用真实模型或提交；真实完整解析仍待验收，详见末尾与工程23。

> **2026-10-23 继续审查解析提交与协议纠错**：另修复相同正文因服务端引用绑定而重复送审、同轮后续提交沿用旧final、不适用证明改写重置纠错次数，以及协议报错／重试丢失具体缺项并混入旧action协议。统一后端 **931 passed / 9 skipped**，Ruff、分层及真实装配mypy通过。用户当前绑定已改为Nemotron模型15；报告23仍在运行，未中断任务，本轮新增补丁尚未载入当前进程。真实完整解析仍未验收，未提交；详见末尾与工程23。

> **2026-10-23 解析异常诊断与修复**：已修复证据额度用完仍反复补读、合法重复回读误杀与日志摘要被框架附注覆盖；统一后端最终 **920 passed / 9 skipped**、Ruff、5项分层契约及真实装配mypy通过。用户确认基础设施仍在本机WSL，启动Ubuntu后PostgreSQL／Redis恢复。现有模型绑定存在下线404、隐私策略404及免费共享池429；用户在排查期间将首选改为Gemma，未覆盖该配置。Gemma／星辰简单工具探针通过，完整保证金专题均因连续429未进入检索，真实验收未通过。用户选择“我配置有额度的模型后继续”，目标仍未完成。详见 [工程23](docs/工程/23-解析异常诊断与修复记录.md)。未提交、未重跑历史业务报告。

> **2026-10-21 续接归纳展示与事项内定位去重**：已读取“优化解析结果展示并去重原文定位”原会话，完成其中未验收的改动：生成时归纳重点并保留实质约束；同一事项跨正文、跨列及补充依据去重定位且保留全部摘录；恢复被覆盖的反向定位函数及回归。后端 **912 passed / 9 skipped**，前端 **62项单测、22项桌面／手机页面回归、类型检查和生产构建通过**，截图已查看。未调用真实模型、重写历史结果或提交，真实模型归纳效果仍未验收。详见末尾记录。

> **2026-10-20 最新KV与定位展示调整**：字段／内容改为两列KV表格，数组按原顺序逐行展示，定位按钮只显示图标；同一位置不同摘录合并图标，文档只显示当前定位的单个3px深紫透明框及角标。前端 **58项单测、26项桌面／手机页面回归、类型检查和生产构建通过**，桌面／手机截图已查看。真实报告18接口当前返回服务错误，本轮未完成真实报告复验；未改业务数据、启停服务或提交。详见末尾记录。

> **2026-10-19 最新逐条定位与分析记录调整**：新结果逐条绑定原文，定位入口紧跟正文；分析记录展示每次开始／结束时间与失败／停止原因；单模块重新解析移到顶部刷新按钮之后；原文只描边，内部透明。用户明确不考虑旧报告展示，不补配旧数据。后端 **908 passed / 9 skipped**，前端 **58项单测、104项桌面／手机页面测试、类型检查和生产构建通过**。未提交、未重启业务服务、未调用真实模型或重跑业务报告；新绑定需要后端载入改动后再生成结果。详见末尾记录。

> **2026-10-18 提交解析结果展示与模块交互修复**：按用户明确要求，本次提交收录结果展示优化、模块标签及三种重解析入口、四处审查修复、字段单值约束兼容，以及配套测试与文档。提交说明为“优化解析结果展示并恢复模块标签与重解析操作”，提交号以 git log 为准。验证沿用刚完成的后端901 passed / 9 skipped、前端57项单测与92项页面测试、类型检查及生产构建结果；本次提交前差异检查通过。本段替代下方对应改动的“未提交”状态；未推送、未部署。

> **2026-10-18 最新审查修复与模块交互恢复**：按用户最新偏好，模块恢复标签铺开切换，单模块重新解析、补跑未完成模块、全部重新解析直接可用；修复未决关系误连、未知标段缺口合并、重复定位不滚动和父子筛选命中仍折叠四处问题。前端 **57项单测、92项桌面/手机页面测试、类型检查及生产构建通过**，真实项目15报告18已只读复验。本轮未改后端、未调用真实模型、未重跑业务报告、未提交；详见末尾记录。以下“重跑操作收进详情”的历史说明已被本次用户偏好替代。

> **2026-10-18 最新解析结果展示优化**：已按用户要求处理七类展示问题；专题正文为主入口，字段配对与历史复合记录区分、范围与修订关系、缺口分组、引用选择、筛选导航及原文宽度均已落地。后端统一 **901 passed / 9 skipped**，前端 **56项单测、82项桌面/手机页面测试、类型检查与生产构建通过**。真实项目15报告18已只读复验。此前适配已提交为 `14d20a2`，本轮未提交。详见末尾本轮交接。

> **2026-10-18 最新续接：综合交接与阶段提示**：已读取“改造解析 skill 以适配项目检索与输出”原会话。综合阶段持续提供主题发现、证据ID和缺口，并修复仍催促重新检索的阶段/收尾提示；研究登记回执返回实际缺口。最终统一检查 **899 passed / 9 skipped**。两组支持性对照未证明缩短或结构化去重提示有效，实验改动已撤回；当前首选为模型23 DeepSeek-V4-Flash，仍有格式、参数和语义错误。完整报价及13专题真实验收尚未通过。所有本轮检查与诊断已结束，未提交；详见末尾最新记录。

> **2026-10-18 最新范围与调用预算修复**：最终所选引文必须可定位具体lot_refs，防止模型误放行未引用的标段名单；专题为综合/校验预留最后四分之一模型与工具次数。统一检查 **897 passed / 9 skipped**。第五轮报价隔离验收已结束：36次模型、47次总工具、1项已核实限价，未收尾；独立检查仍发现数值边界误放行及正确引文被误拒绝。验收脚本现按正式控制器计入全部工具调用。所有进程已结束，尚未完成真实模型完整性验收，详见末尾最新记录。

> **2026-10-18 最新 Agent 纠错与模型复验**：使用专题摘要、送审空属性省略及明确的公共范围指导；补充同事项全部引文错误反馈、仅回读原块的纠错指导和新证据导致阶段失效的即时提示。最新统一后端 **891 passed / 9 skipped**，Ruff、5项架构契约及mypy通过。四轮报价真实模型均未完成完整验收；第四轮保留1项已核实限价及5项缺口后耗尽工具预算。已补报价与评分系数的检索边界；具体标段范围的支持性校验仍存在不稳定性。所有隔离进程均已结束，详见末尾本日追加记录。未提交。

> **2026-10-18 最新持续优化**：增加检索截断、关键词空召回提示及连续清单补读、条款归属核对规则；改进评分窄屏阅读、技术事项层次、页码入口和共享原文往返定位。统一后端 **888 passed / 9 skipped**，前端51项单测、18项桌面/手机专题页面测试、类型检查和构建通过。真实监理标书已建立核对清单；首轮真实模型隔离验收在600秒预算内保存1项已核实限价、登记4项转引缺口，未完成收尾，效果验收尚未通过。业务服务现场已在运行，本轮未启停、未写业务报告、未提交。详见末尾“持续优化检索覆盖与结果定位”。

> **2026-10-18 最新解析 Skill 适配**：13 个专题已按本项目检索、逐条 JSON 与独立引用协议适配，新增冻结的 JSON 格式声明，修正品类细则和输出规则冲突，保留旧快照兼容。统一离线 **884 passed / 9 skipped**，收尾专项100项通过；13个Skill及39个JSON示例通过检查。未调用真实模型、未启停业务服务、未提交。详见末尾“将解析 Skill 适配为本项目运行规则”。

> **2026-10-18 本地提交交接**：按用户明确要求，本次提交收录后端业务目录重组、端口与 Worker 边界、任务执行快照、自动类型检查、上传回归修复及配套文档和测试。提交说明为“按业务重组后端并完善任务边界与上传处理”，提交号以 git log 为准。最终离线811项通过、9项跳过；此前数据库边界修复的78项隔离集成通过。本段替代下方历史记录中的“未提交”状态；未推送、未部署。

> **2026-10-18 最新上传修复**：已修复审查确认的两处上传回归：读取内容前检查批次数量/总量，未知大小按剩余额度读取；单文件存储或领域错误不再中断批次，保留成功回执、失败清单与可重试标记。新增20项回归，完整离线811项通过、9项跳过，Ruff、mypy和5项架构契约通过。详见末尾“修复批量上传资源限制与部分失败回执”。未提交、未重启业务服务。

> **2026-10-18 最新后端边界修复**：已修复 Worker 直接 ORM、Protocol 无自动检查、文档执行预算随实时配置变化这三项问题。Worker 经端口访问 PostgreSQL；mypy 检查 ports 与真实装配并纳入离线测试；六项文档执行参数按任务冻结，调度并发/间隔继续实时读取。791项离线通过、9项跳过，78项隔离数据库集成通过。工程11/21及配置文档已同步，临时数据库已停止；详见末尾“修复 Worker 数据访问、协议检查与任务配置边界”。未提交。

> **2026-10-18 最新后端架构说明**：工程11已按当前源码重写为“当前后端架构与设计取舍”，覆盖进程、业务目录、ports/adapters、真实时序、事务与配置，以及尚未统一的边界。工程21继续维护文件树。此次仅更新文档，详见末尾“编写当前后端架构与设计取舍说明”。

> **2026-10-18 最新业务目录交接**：见末尾“在既有架构内按业务模块归组”。已按用户确认的规则完成业务目录分类（含单文件业务），技术基础设施保留技术分类。785项离线、75项隔离数据库集成通过，65条路径的OpenAPI全量一致。文件放置以工程21为准，未提交。

> **2026-10-18 最新架构交接**：见末尾“将职责分层归回既有架构并建立文件树规则”。service/crud/agent 是职责定义，已移除新增同义目录，归回 application/ports/adapters；后端文件放置以 docs/工程/21 为准。772 项离线与75项隔离数据库集成已通过，未提交。

更新日期：2026-10-15

> **2026-10-15 当前最新交接**：见末尾「修正 Agent 过程门禁与纠错误杀」。用户指出几乎所有专题因 complete_research 失败；已删除检索词精确复述要求，主题漏项、重复和覆盖证明缺项改为可展示缺口，修复空检索误判无进展及清空成果，清理旧格式解析器。最终离线 **608 passed / 9 skipped**，隔离 PostgreSQL **71 passed**，历史展示兼容补验 **2 passed**，Ruff、架构约束、前端类型检查及差异检查通过。临时数据库已停止；未启用业务服务、未调用真实模型、未提交或推送。

> **2026-10-15 最新交接**：见文件末尾「移除字段抽取并重构 Agent 证据汇总输出：实现与验收完成」。旧字段抽取链路已移除，13 个专题改为检索完成后按 Skill 综合输出 JSON；已补修 `analysis` 队列无人消费和报告切换残留状态。离线 **602 passed / 9 skipped**，临时 PostgreSQL 18.3 集成 **70 passed**，前端 **45 项单测、54 项页面测试、类型检查和生产构建通过**。业务数据库本轮未迁移，业务服务未重启，未提交或推送；旧运行环境暂不视为已启用新版。

> **2026-10-13 最新交接**：见文件末尾「ORM 落地第二、三步：端口/适配器分层与裸 SQL 收口」。ORM 替换已按用户要求推进到：第一步落地 typed declarative 模型 + 唯一引擎入口 + 模型↔DDL 契约测试；第二、三步落地 ports 协议 + adapters 仓储，`api/`/`worker/`/`application/` 的业务裸 SQL 已全部迁走（`text()` 只剩 `adapters/pg` 里 ORM 表达不到的系统目录查询）。离线验证 `tests/unit tests/contract` → 654 passed / 9 skipped，ruff 全过，`lint-imports` 5 kept / 0 broken。**后端本轮未重启（用户要求推迟）**；`tests/integration` 三个用例已改指新仓储入口并全绿（`TENDER_RUN_DB_TESTS=1` → 72 passed），期间修掉 `KnowledgeSession` 事务未真正提交的真实缺陷。数据库/Redis 网络中断已恢复，报告 #16 的 818 运行中、819–826 排队、814–817 待补跑。下面更早的提示保留作历史，当前状态以末尾为准。

工作目录：`G:\aicode\AI-tender`

> **新会话先读**：最新实现见文件末尾「2026-10-11 修复代码审查发现的四处业务数据问题」，提交说明见随后「2026-10-11 按用户要求提交单标段业务数据改造」。四处问题已修复并新增11项回归，后端 **615 passed / 8 skipped**。前一轮前端类型检查、77项单测、生产构建和新增8项桌面/窄屏交互通过，本轮未改前端。**业务库此前确认仍为 `0010_analysis_guards`，本轮未执行业务库迁移、未启用API/worker，真实供应商与新业务报告尚未验收。** 本次按用户要求提交，未推送；现场迁移和服务启用按此前约定需单独确认，禁止自动提交后续改动。

状态：此前前端重构和已提交事项保留作历史记录；当前单标段数据改造已完成代码与隔离验证，并按用户要求提交，尚待现场启用。以末尾最新记录为准。

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
### 24.10 新窗口续作：下线旧解析、取消可补跑、报告10补跑（2026-10-07 16:05）

本节覆盖24.9的状态描述；工作树另有一批未提交改动（清单见本节末），已全量验证，等用户确认后提交。

#### 用户本轮指令与落实

- 用户取消了报告9、10并上传了真实招标文件（项目15、报告10），随后反馈失败或未完成的报告不能重跑。已把 `retry_report` 状态门禁放宽为 `partial/failed/canceled`（取消不再是死路，可整体补跑未完成模块）；legacy 报告统一 409 `runtime_retired` 拒绝，要求重新发起分析。
- 用户要求 agent+skill 与旧固定字段解析不共存：legacy 解析链路整体下线。
  - `worker/knowledge.py` 删除 legacy 执行分支，只保留 runtime 校验；不再导入 `run_module/scan_document/MODULES`。
  - `application/analysis_skills.py` 删除 `SCAN_CONTRACT`、`COVERAGE_CONTRACT`、`read_reference`、`missing_outline_nodes`、`scan_document`、`complete_uncited_candidates`、`run_module`；`skill_snapshot()` 只返回 Skill 正文（不再注入协议键）。问答链仍用 `MODULES/REPORT_CONTRACT/DocumentTools/json_completion/verify_items`，不要误删。
  - `api/knowledge.py` 删除 legacy 分流，`get_report` 新增 `runtime_retired` 字段；`retry_report` 状态判定为 `pending`（retried 且 coverage.mode=agent_research）否则 `waiting`。
  - 前端删除 legacy 全文阅读覆盖文案与旧分支；补跑按钮条件为 failed/partial/canceled（整报告）与 failed/canceled（无模块重试），`runtime_retired` 时禁用。
- 用户要求 `analysis.context_tokens` 不设上限：`config/schema.py` 的 bounds 改 `dict[str, tuple[int, int | None]]`，上界允许 None，仅保留 ≥4096；新增单测 `test_context_budget_has_no_upper_bound`（262144 通过、4095 拒绝）。

#### 验证（2026-10-07 16:00 前后）

- 后端全量（删 legacy 后）：`TENDER_RUN_DB_TESTS=1 uv run pytest -q` → 461 passed / 7 skipped；`apps/api` 内 `ruff check .` 全过（仓库根 `scripts/` 的 2 处告警是既有问题，未动）。`ruff format --check` 存在历史未格式化文件，本次不扩大改动面。
- 前端：`pnpm typecheck` 通过、`pnpm test` 76 passed、`pnpm build` 生产构建通过。
- 报告10补跑前复核：`canceled`、`runtime_version=deepagents-0.7.22-v1`、`runtime_retired=false`、`coverage.mode=agent_research`、source13 ready；`POST /analysis/reports/10/retry` 返回 202，13 模块全部 attempt2/pending（`max_output_tokens=8192`、`timeout_seconds=1800`），快照 `.tmp/deep-flow-check-10/before-retry-2.json`。
- 取消后补跑已由集成用例 `test_canceled_report_retries_failed_and_canceled_modules` 覆盖（真实多连接环境，补跑后 attempt2 全 pending）。

#### 服务现场（15:53 用 scripts/start-backend.ps1 -Force 重启）

- API 12632、worker 33244、beat 32064；健康检查通过；前端 4400 在听（dev + HMR，新前端代码已生效，/knowledge 200）。
- 报告9残留：模块58/59 的 attempt3 run110/111 在 DB 仍是 running 且租约已过期，属用户取消前的在途记录；它们不持有 advisory 配额锁、不影响报告10补跑，暂不手工清理。

#### 未提交改动清单

- 后端：`api/knowledge.py`、`worker/knowledge.py`、`application/analysis_skills.py`、`config/schema.py`、`tests/integration/test_deepagents_runtime.py`、`tests/integration/test_knowledge_flow.py`、`tests/unit/application/test_knowledge.py`、`tests/unit/config/test_schema.py`。
- 前端：`src/components/knowledge/ProjectAnalysis.tsx`、`src/types/knowledge.ts`。
- 文档：`docs/设计/05-后端API设计.md`、`14-知识库与综合分析实现.md`、`16-DeepAgents标书分析运行时.md`。
- 迁移0008 的 runtime_version 默认 legacy 与既建列保留（历史列兼容）；新报告一律写 `deepagents-0.7.22-v1`。提交必须 `git commit -F`（PowerShell 5.1 直传中文消息会被引号转换拆断），中文、无作者。

#### 下一步

1. 轮询报告10到终态（`.tmp/poll-deep-retry10.py`）；终态后 `python .tmp/check-deep-report-10.py --brief`，再 `--final`。
2. 浏览器验收：`.tmp/deep-flow-browser-10.mjs --preflight`（运行中预检现在可跑），报告 completed 后跑最终脚本（仅桌面 1440）；项目问答只能创建一次，状态在 `.tmp/deep-flow-check-10/state.json`。
3. 逐模块人工核对事实与引用（基准见 24.9），模型 supported 不等于人工通过。
4. 全部通过后提交本批改动，建议信息：`重构：下线旧固定字段解析流程，取消后可补跑未完成模块`。
#### 16:45 追加修复与报告10实时状态（覆盖上一条下一步的执行进展）

- 新增可自纠正工具错误：`analysis_research.py` 引入 `ToolArgumentError(ValueError)`（检索问题长度、read_document 偏移/块数越界）；`deep_analysis.py` 中间件把 `SourceNotAllowed/ToolArgumentError` 回传为 error ToolMessage，模型可修正参数继续，不再击穿整个模块；动态撤销、工具/模型预算耗尽等仍原样上抛终止模块。单测新增 `test_out_of_range_tool_arguments_are_correctable_not_terminal`、`test_out_of_range_read_arguments_return_error_message_and_keep_module_alive`。
- 起因：attempt2 的 run172（项目概况）在 08:10:40Z 因一次越界 read_document 调用整块失败；同类错误此前已击穿 tech/deposit 两个模块尝试，属系统性缺陷而非偶发。
- 报告10 attempt2 现场：172 failed（越界参数，已修复）；173 failed（08:31:36Z 模型请求预算耗尽，主模型 60 秒超时频发）；174 biz_standard 16:31:37 启动，16:35:48 重启后于 16:40:59 恢复（requests_unknown 标记在途请求，deadline 09:01:37Z 不重置），修复已对该 run 生效；175-184 共 10 个模块 pending。
- 服务现场：16:35 重启后 API 35704、worker 15472、beat 31408；前端 4400 在听（HMR 已加载新前端代码）。
- 报告9残留 run110/111 仍是 running（无 advisory 锁、不占配额），不影响报告10。
- 下一步：等 174-184 跑到终态；用 API 补跑 172/173（attempt3，修复已在线）；再跑 `check-deep-report-10.py --brief/--final` 与浏览器 preflight/最终脚本；最后提交本批改动（等用户确认）。
#### 16:55 修复"补跑沿用旧配置"（用户现场问题）

- 现象：用户在配置中心把 `analysis.max_model_calls` 调到80、`max_tool_calls=100`、`context_tokens=200000`、`max_output_tokens=12000` 后，取消报告10再补跑（含界面单模块补跑），新 attempt 仍带创建时快照32/48/24000/4096，模块继续按旧预算执行（run173 即以32次预算耗尽失败）。
- 根因：`retry_report` 的 limits 直接取 `dict(report["runtime_settings"])`（创建时冻结），配置中心的后续调整不会进入新 attempt。
- 修复：补跑改为 `limits_snapshot(store(request))` 读配置中心当前值；`max_output_tokens/timeout_seconds` 显式参数只覆盖对应字段。报告创建时的快照与既有运行账仍不回写，每个 attempt 各自留存限值快照（前端展示的也是 run.limits）。新增集成用例 `test_retry_uses_live_config_and_keeps_report_snapshot_untouched`。
- 现场：16:54 取消报告10（用户16:46在界面单模块补跑的 attempt3 也是旧限值，一并取消）；16:55 重启后端加载修复（API 29480、worker 33708、beat 12632），随后整体补跑13模块 → 新 attempt（3/4）限值= `80/100/160/200000/12000/900`，与配置中心当前值一致；后端全量 464 passed / 7 skipped。
- 提醒：在途 attempt 的 limits 冻结是有意设计（审计与预算不可绕过）；若运行中再改配置，需要再次取消+补跑才会生效。
#### 17:10 证据块预算改为可自纠正 + 报告10现况

- 现场：补跑会继承历史证据（`research.seen`），叠加本轮新读取后，重试模块很快就会撞上160块上限；而 `_remember` 直接抛 ValueError 击穿模块（消息却写着"请基于已有证据完成分析"）。报告10 的项目概况（att4，159块）与否决项（att3，159块）正是这样失败的。
- 修复：新增 `EvidenceBudgetError(ValueError)`，与 `SourceNotAllowed/ToolArgumentError` 一起在中间件回传 error ToolMessage，模型可以继续基于已有证据完成分析；工具/模型预算耗尽仍为终止性错误，不能被纠正绕过。
- 测试：`test_evidence_budget_denies_new_blocks_but_allows_rereading_known_ones`、`test_evidence_budget_feedback_keeps_module_alive`；两个单测文件 26 passed，ruff 通过。集成用例 `test_retry_uses_live_config_and_keeps_report_snapshot_untouched` 覆盖配置修复。
- 报告10 现状（17:05）：13个模块全部为新的 attempt（3/4），限值=配置中心当前值（模型80/工具100/证据160/上下文200000/输出12000/时限900）；概况、否决项因当时worker还没加载证据预算修复而失败（159块）；商务运行中（seen=151）；其余10个 pending 且见证为0（干净重跑）。
- 待办：本轮结束后补跑概况与否决项（修复已在线，应能以已有证据收敛）；`max_evidence_blocks=160` 目前不在配置中心（AgentLimits 固定默认），若需要可加 `analysis.max_evidence_blocks`。
#### 17:40 修复 legacy 报告 stale 误报（本轮代码审查发现）

- 现象：`get_report` 删掉 `runtime_version != "legacy"` 守卫后，对所有报告比较参考来源快照；legacy 报告该列为空，只要知识库里存在其它项目的参考来源就恒判为 `stale`，前端显示"项目材料或分析设置已变化…请更新分析"，与只读提示互相矛盾。实测报告 1/2/5/7 的 stale 唯一原因都是 `reference_snapshot(refs=8,snap=0)`。
- 修复：`api/knowledge.py` 先算 `retired = report["runtime_version"] != RUNTIME_VERSION`，只对当前运行时报告比较参考来源快照（旧流程从不记录该快照），`runtime_retired` 复用同一变量。
- 测试：新增集成用例 `test_reference_snapshot_change_marks_only_current_runtime_reports_stale`（同一份报告：当前运行时因新增参考来源判 stale，标记为 legacy 后不再 stale）；`apps/api` 全量 `TENDER_RUN_DB_TESTS=1 uv run pytest -q` → 467 passed / 7 skipped，ruff 通过。
- 复核（真实库、进程内直接调 `get_report`，未重启服务）：报告 1-8 全部 `stale=False/retired=True`，报告 9/10 保持各自真实判定。
- 生效条件：需重启 API/worker 后界面才不再显示该误报；报告10仍在跑，未擅自重启。

## 25. 自行复现与修复解析失败（2026-10-07 20:26，进行中）

用户要求自行测试并修复多次解析失败；途中说明已延长等待、增加重试、禁止降级。沿用 DeepAgents 独立模块，不回退旧固定字段流程，不提交。已读取 karpathy-guidelines，未使用子代理。

### 本轮已确认和修复

- 后备模型返回自然语言会让图直接结束，丢失未提交分析。`ResearchMiddleware.aafter_model` 在同一图内进行有界纠正，必须经工具校验提交；以消息ID幂等记录纠正次数。
- 证据预算边界把整批读取拒绝，连已有原文都无法补读。`_remember` 现在返回预算内新块和已有块，报告省略数量；越权仍整批拒绝。未增大160块预算。
- `failover_limit=1` 仍可能因供应商冷却排序而选中后备模型，或429直接失败不等主模型重试。已固定首选启用模型，禁止降级时只能等/重试它；新增两种限流回归。
- 普通结果工具每批最多3项，格式大纲每批最多6节点，分别暴露对应schema。格式按先父后子分批、累计校验整棵树，同ID可修正，改动影响的子节点重新验证。
- `final` 默认改为false；只有显式true才完成，避免模型省略参数时只保留第一批。
- 连续错误计数在成功暂存后重置，累计错误与总预算保留；第三次失败原因也持久保存。引用错误带条目标题和块ID。
- 支持性校验每批3条，去掉坐标等无关元数据，允许不改变含义的同义改写；不放宽金额、单位、前提、范围或引文校验。新attempt清理暂存验证标记，重新验证携带的旧条目。
- `docs/设计/16-DeepAgents标书分析运行时.md` 已同步本轮行为。

### 当前真实配置与验证

- 用户设置的功能analysis/knowledge_ask：`failover_limit=1 / max_total_requests=10 / deadline_seconds=1200`，revision5；并发仍为1。
- 真实首选模型17 `qwen3.8-flash-next-262k` 单次原为90秒、额外重试1；真实校验两次90秒超时。已明确告知用户后按其延长等待要求，经管理API改为 **300秒/额外3次**，revision3。功能预算和绑定均未改。修改前后在 `.tmp/analysis-repair-10/model-17-*-budget-alignment.json`。
- 真实单条校验诊断走管理路由与调用账，87.5秒、8024输出token，返回具体无依据断言（不是服务完全不可用）；`.tmp/analysis-repair-10/verification-probe-1/`。不要重复同一探测。
- 后端完整：`TENDER_RUN_DB_TESTS=1 uv run pytest -q` → **478 passed / 7 skipped**；Ruff全量通过、5条分层契约通过、diff check通过。前端本轮没有修改。
- 桌面真实页面预检16项通过，PDF和引文高亮正常；这不是完整报告验收。`.tmp/deep-flow-check-10/browser-preflight/`。脚本旧文案仍误写“主文件与补充通知”，实际项目15只有一份文件。

### 真实报告与下一步（不得停在单测通过）

- 当前对象：项目15、报告10、source13，文件 **2023-2024年通信工程监理招标项目招标文件.docx**，137页、1130块、约5.3万字。与项目13的人工小样本不同，不能使用预算80万/45日等旧基准。
- 本轮先补跑开标352/格式353，两者均在支持性验证时两次90秒超时失败，证明等待配置层次不一致；历史快照保留。
- 20:23前后加载最新代码后，经API补跑全部12个未完成模块：run369–380（项目概况attempt6，评分/开标/格式attempt5，其余attempt4）。**当前running；369项目概况运行中，370–380排队。** 人员模块run247旧completed、3条保留。
- 本次attempt限值：模型80/工具100/证据160/上下文200000/输出12000/总时限1800秒（此次补跑显式延长到1800，配置中心仍900）。禁止改在途attempt限值；禁止再建报告/重传资料。没有其它活动报告。
- 后端通过现有脚本加载：API父13280、worker24980、beat33908；前端4400。PID须实时核验。模型和Ollama没有重启。
- 持续轮询 `.tmp/analysis-repair-status.py 10`，终态后按实际失败原因修复/补跑；目标是13模块真实完成且事实、引用通过，不能把running或假模型测试称为通过。
- 原文已只读导出 `.tmp/analysis-repair-10/source-13.json` / `source-13.md` 供人工核对。文件混有其他项目公告：c60附近施工项目，c86–118为2018广东办公场地租赁项目，不能把其金额、纸质递交、广州地址套到本监理项目。开标352未提交草稿已识别这一污染，但其引用仍不完整。
- 本项目明确事实：预算2130万元不含税、浙江省内、自合同签订起2年、4标段且最多中1个，标段预估监理费1130/400/300/300万元；同类监理业绩自2020-01-01起、累计600万元、框架合同看订单；不接受联合体；2023-05-16 10:00网上开标、纸质递交不涉及；保证金6万元不分标段；投标有效期180天。人员旧3条未包含公告c35的安全管理培训合格证要求，最终需核对是否漏项。
- 最终用 `.tmp/check-deep-report-10.py --final` 核对全部引用resolve；人工逐模块核对；完成后运行 `.tmp/deep-flow-browser-10.mjs`。项目问答尚未创建，只能创建一次并记录到state.json。脚本可能需修复旧文案，不能降低断言。

常用命令（PowerShell，UTF-8）：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONPATH='G:\aicode\AI-tender\apps\api\src'
& '.\apps\api\.venv\Scripts\python.exe' '.tmp/analysis-repair-status.py' 10
& '.\apps\api\.venv\Scripts\python.exe' '.tmp/inspect-analysis-checkpoints.py' 10 模块片段
# 仅报告终态后补跑；省略模块key表示全部未完成模块，先保存快照。
& '.\apps\api\.venv\Scripts\python.exe' '.tmp/retry-analysis-repair.py' 10 完整模块key
```

#### 21:30 追加修复：校验看不到章节归属、524 被当致命错误、人员模块假完成（覆盖上面的运行状态）

- 支持性校验原先只把短引文交给校验模型，导致“投标人须知前附表第1.4.1项”“第3.5条”“招标公告载明”这类**正确的章节/条号归属**被判无依据，370、371 因此在三次无效提交后失败。现在：
  - `citation()` 保留 `block_id`；`analysis_skills.verify_items` 新增可选 `evidence`，为每条引文附带 `block_context`（同块完整原文 + 前后已读块），提示词明确“邻近块只能核对条号、章节标题、公告/表格名称和资料归属；金额、条件、范围、否定、例外等事实仍须在引文或所在块中直接写出”。
  - 旧 attempt 的引文没有 `block_id`，按 `(source_id, parse_run_id, element_id)` 并用引文原文在分块间消歧回退，重试携带旧暂存条时同样能看到上下文。
  - 真实入口 `worker/deep_analysis.py` 的普通条目和关系校验都传入 `research.seen`；项目问答链路保持原载荷不变。
- 524 等非标准 5xx 原来落到“网关拒绝请求”（不可重试），run372 因此在 127 秒后直接失败、不重试也不等待。现改为 `status in {408,429} or status >= 500` 一律按可重试处理（`adapters/openai_chat.py` 的 `complete`、`adapters/agent_chat.py`），仍是同模型重试，不触发降级。
- 人员模块 **run247 属假完成**：最后一次 `submit_analysis` 只有 3 条、没有 `final`，`research_summary` 写着“测试提交（第一批）”，旧实现默认 `final=true` 把它当成整个模块。旧 3 条引用本身有效，但漏了公告 c35 的“安全生产监督管理机构颁发的安全生产管理人员安全培训合格证书（提供有效证书复印件）”。消息存档 `.tmp/analysis-repair-10/personnel_requirement_parsing-247-messages.json`。
  - 重做脚本（报告终态后执行）：`.tmp/requeue-analysis-module.py 10 personnel_requirement_parsing "旧实现提前完成，按修复后的提交协议重做"`。脚本先写前后快照，只把该模块置 pending、按最新 attempt 限值新建 run（空 state），**不改报告状态**；随后必须调用 retry 接口补跑失败模块，报告才会重新派发。禁止把“重做已完成模块”塞进产品补跑语义。
- 验证：`TENDER_RUN_DB_TESTS=1 uv run pytest -q` → **482 passed / 7 skipped**（新增用例覆盖校验上下文载荷、element_id 回退、524 可重试）；`ruff check` 通过。

运行现场（2026-10-07 21:30 实时核实）：

- 报告10 running；369 项目概况 completed（9 条，事实与引文已逐条人工核对）。
- 370 否决条件 failed（章节归属类，已修）；371 商务要求 failed（标题把“监理文件”扩大成“成果”、承诺函抬头类，已修）；372 技术要求 failed（HTTP 524，已修）。
- 373 评分办法 running（重启后按原 attempt 恢复）；374–380 pending；人员 247 假完成待重做。
- 停/起后端加载修复（`scripts/start-backend.ps1 -Force`）：API 38188、worker 34312、beat 37552；在途 373 由 `requeue_unlocked_runs` 恢复执行。模型等待仍是 300 秒/额外 3 次，功能 `failover_limit=1 / max_total_requests=10 / deadline_seconds=1200`，并发 1。
- 下一步顺序：报告终态 → 确认无在途 run → 人员重排队脚本（不加 `--activate`）→ `.tmp/retry-analysis-repair.py 10 <失败模块key>`（会统一把报告置 pending 并派发）→ 轮询到终态 → `.tmp/check-deep-report-10.py --final` → 人工逐模块核对（含 c86–118 广东租赁项目污染隔离）→ 启动前端跑 `.tmp/deep-flow-browser-10.mjs`（项目问答只能创建一次）。

21:40 补记（373 失败后的追加修复，已再次重启加载）：

- 373 评分办法失败原因是 **`LLM 网关返回空文本`**：上游慢请求被网关在约110秒后截断成 `200+空正文`，三次重发都拿到空正文。据此再改三处：
  - `openai_chat.complete` 的空正文不再当“可纠正的 JSON 格式错误”，改判 `ExtractionUnavailable(http_status=200)`，由路由按 `extra_retries` 同模型重试（不降级、不换模型）。
  - 支持性校验改为**按体量分批**（解释型每批≤3条且≤6000字符），避免长提示触发网关超时。
  - 引文上下文分级：任何引文都带同块原文 `block`；只有条目正文/表格里出现“前附表/公告/附件/封面/目录/格式/详见/载于/章/页/第”这类归属表述时才附 `before/after` 邻近块，且单次调用邻近块总量封顶8000字符。
- 全量测试仍为 **482 passed / 7 skipped**；`ruff check` 通过。
- 运行现场：报告10 running，373 已 failed（待补跑），374 开标运行中被本次重启打断后按原 attempt 恢复，375–380 pending，人员 247 待重做。最新进程：API 33944、worker 32136、beat 28184。

21:58 补记（上游 524 导致整个模块失败的问题）：

- 374 开标失败的直接原因是上游在 13:35–13:48 连续四次 524/空正文（每次约126秒）；同模型重试和空正文可重试都已生效，但**一次校验调用耗尽重试就终结了整个模块**，18 次模型调用、24 次工具调用和 124 块证据全部作废。
- 因此 `deep_analysis.submit_analysis` 现在捕获 `ExtractionFailed/ExtractionUnavailable`：校验请求被上游截断时不再抛出，而是回传“引用校验暂时不可用…请重新提交同一批结果”的可纠正错误，让同一个子 Agent 在自身预算内重交；测试 `test_transient_review_failure_keeps_module_alive_for_resubmission` 覆盖该路径。草稿内容错误仍走原有三次无效提交限制。
- 全量测试 **483 passed / 7 skipped**。最新进程：API 35960、worker 35084、beat 27704。
- 上游速度实测：13:27–13:50 期间所有请求约126秒后被截断；13:50 起恢复 2–6 秒。补跑应挑选上游快的窗口，并在失败后如实记录原因。

23:55 补记（章节归属与跨块续句校验窗口，报告10 首轮现场暴露的新问题）：

- 375 保证金、377 报价、370 否决的失败根因是**归属证据不足**：引文块只写“3.4.1 投标保证金”，而“投标人须知前附表”标题在 c132，模块从未读过它；旧窗口只给“已读块”，于是正确归属被反复判无依据。376 装订则是把“同页延续块”这类位置结论写进正文被否。
- 修复三处，全部在未提交工作区：
  - `worker/deep_analysis.expand_evidence`：校验窗口按引文所属资料补读整份原文（引文本身仍限定为模块读过的块，不放宽“只能引用读过的原文”）。读不到时退回已读块。
  - `analysis_skills.EvidenceWindows`：邻域按 offset 给出 `before/after`（含 page_no）；新增 `continuous`——只合并 offset 连续的块，且仅当上一块没有收句时向后接续（如 c276“并应符合投标人”+ c277“须知前附表的 规定。”），避免把“相邻出现”当依据。校验提示允许用“邻近标题块 + 引文块内条号”确认章节归属，事实仍必须由引文、同块原文或连续原文直接写出。
  - 格式大纲的程序生成字段（逻辑标/层级/上级路径）不再参与支持性校验：它们由 `outline_result` 的父子、循环、层级校验负责，只审名称/编制要求/引文。
- 验证：`TENDER_RUN_DB_TESTS=1 uv run pytest -q` → **486 passed / 7 skipped**；ruff 通过；`git diff --check` 通过。用真实原文预演确认 c136 载荷含 c132 标题（2.5k字符）、c276/277 拼接成完整续句。
- 现场：报告10 首轮跑完 = 3 completed（369 概况、378 公司业绩、人员 247 假完成）、10 failed（370–377、379、380；其中 376/377 是上游 524 慢窗口耗尽模块总时限，非逻辑错误）。已按维护流程重排队人员（run 500 / attempt 4，未改报告状态），并用 retry 接口补跑全部 10 个失败模块（run 501–510，timeout 1800、输出 12000、并发 1），报告重新进入 running。
- 最新进程：API 41272、worker/beat 见 `.tmp/backend-pids.json`（23:52 启动）；模型等待仍是 300 秒/额外 3 次，功能 `failover_limit=1 / max_total_requests=10 / deadline_seconds=1200`。
- 下一步：轮询到终态 → `.tmp/check-deep-report-10.py --final` → 桌面浏览器 `.tmp/deep-flow-browser-10.mjs` → 人工逐模块核对（含 c86–118 广东租赁项目污染隔离、c35 人员证书）→ 项目问答只能创建一次。仍禁止自动提交。

00:05 补记（基础设施中断；新会话先从这里读起）：

- **当前环境不可用**：2026-10-08 00:01 有一次后端重启（`.tmp/backend-pids.json` 记 API 10152 / worker 27980 / beat 40772），但 00:02–00:03 起 API `http://127.0.0.1:8300` 拒绝连接；worker 日志报 `redis.exceptions.TimeoutError: Timeout connecting to server`；Postgres `172.29.199.222:5432` 端口可连通但连接立即被服务端关闭（`server closed the connection unexpectedly`）。恢复动作：先修好 DB/Redis（远程主机侧），再 `scripts/start-backend.ps1 -Force`；启动时的 `requeue_unlocked_runs` 会恢复 run500 与 pending 的补跑。
- **中断前最后已知状态**（取自 `.tmp/analysis-repair-10/live.json`，时间戳 2026-10-07 16:02:42 UTC）：报告10 `running`；369 概况、378 公司业绩 `completed`；501–510（370–377、379、380 的补跑 attempt）全部 `pending`、尚未开跑；人员 `personnel_requirement_parsing` run **500**（attempt 4）`running`，18 次模型调用 / 30 次工具调用、160 块证据预算已耗尽。以上为最后一次成功查询，DB 恢复后需重新核对。
- **人员 run500 最后一次驳回暴露两个待决问题**（尚未修，代码保持现状）：
  1. 缺席性断言：模型把“未写明人数/未再写明学历职称”写进 text/cells；支持性校验按“未写明不能由单条引文证明”拒绝。模块规则本就要求缺席内容只进 `research_summary`，需靠模型自行收紧（或再给反馈措辞）。
  2. 章节归属超窗：`第一章招标公告 3.5` 的招标公告标题在 **c15**，被引的 3.5 条款在 **c35**，相隔 20 块，超过 before 窗口（6 块），校验无法确认归属。候选方案（未实现、需先决定）：a) 校验载荷向后扫描最近的“第X章”级标题并以显式章节标题字段提供；b) 要求模块在断言章节归属时同时引用标题块。
- 本地已核实原文（可用于上述判断，无需重查）：c15「第一章招标公告」、c18「2. 项目概况与招标范围」、c29「3. 投标人资格要求」、c33 资质、c34 业绩600万、c35 人员证书；c131「第二章投标人须知」、c132「投标人须知前附表」、c136 前附表 3.3.1/3.4.1、c137 前附表 3.5.3；c276「…并应符合投标人」+ c277「须知前附表的 规定。」为跨块续句样例。
- 本轮修复与测试结论（详见上一条 23:55 补记）：全文化校验窗口 + `continuous` 续句 + 大纲结构字段不参与支持性校验；`TENDER_RUN_DB_TESTS=1 uv run pytest -q` → **486 passed / 7 skipped**，ruff 与 `git diff --check` 通过。全部改动仍在未提交工作区。
- 恢复后的下一步顺序：DB/Redis 恢复 → `scripts/start-backend.ps1 -Force` → `.tmp/analysis-repair-status.py 10` 核对 run500 是否恢复、501–510 是否开始 → 轮询到终态 → 失败模块按现场原因继续修/补跑 → `.tmp/check-deep-report-10.py --final` → 桌面浏览器 `.tmp/deep-flow-browser-10.mjs` → 人工逐模块核对（含 c86–118 广东租赁项目污染隔离、c35 人员证书、投标有效期 180 天与前附表/正文 90 天的区分）→ 项目问答只能创建一次。仍禁止自动提交。

#### 2026-10-08 21:20 补记（当前现场；新会话从这里读起；覆盖 00:05 补记的运行状态）

- 环境已恢复：DB/Redis 可用；后端 2026-10-08 20:35:50 用 `scripts/start-backend.ps1 -Force` 重启并加载本轮全部未提交修复。`.tmp/backend-pids.json` 记录的是 venv 启动器 PID（API 29312、worker 25896、beat 29184），实际服务是它们各自的子进程（28440/28948/26088，miniconda python），属 venv 启动器结构，不是重复 worker，不要误杀。API `http://127.0.0.1:8300/docs` 200；前端 `pnpm --dir apps/web dev` 端口 4900（4400 被 Windows 保留端口占用）自 19:07 运行，`http://127.0.0.1:4900/projects/15` 200。
- 运行配置未变：模型等待 300 秒/额外 3 次；本 attempt timeout 1800、输出 12000、并发 1；功能 analysis `failover_limit=1 / max_total_requests=10 / deadline_seconds=1200`。不要频繁重启（模块预算与时限不重置），不要改在途 attempt 限值。
- 报告10 现场（2026-10-08 21:08 实时读取；脚本每次运行都会刷新 `.tmp/analysis-repair-10/live.json`，本轮快照 `live-check.json`）：报告 running；3 completed、1 running、5 failed、4 pending。
  - completed：369 项目概况（attempt 6）、504 评分办法（attempt 6）、378 公司业绩（attempt 4）。
  - running：506 保证金要求（attempt 5，已暂存 4 条）。
  - failed：500 personnel_requirement_parsing（attempt 4，总时长预算耗尽，恢复不重置时限）、501 disqualified_items_parsing（attempt 5，连续三次「引用校验暂时不可用」——旧计数逻辑所致，已修分类）、502 biz_standard_parsing（attempt 5，「证据支持性校验缺少逐项断言审查」——校验响应格式类，已改不再计无效）、503 tech_requirement_parsing（attempt 5，引用未支持的断言，内容类驳回）、505 opening_requirement_parsing（attempt 6，APIConnectionError）。失败 attempt 里的暂存条保留（501 六条、502 十二条、505 三条）。
  - pending：507 packaging_requirement_parsing、508 price_requirement_parsing、509 bid_format_outline_parsing、510 general_module_parsing。
- 本轮已修复（全部未提交，仍在工作区）：
  1. 章节归属：引文保留 `block_id` 并携带 `block_context`；校验载荷新增 `chapter_heading`（沿同一资料连续原文向前回溯最近的独立「第X章」标题，可超出 before 窗口）与 `section_heading`（「第X节」，遇到新章会终止上一章的节归属）；提示词限定邻近块只能核对条号、章节标题和资料归属，事实必须在引文或所在块直接写出。真实原文复核：c35 的「招标公告 3.5」现在能拿到 c15「第一章 招标公告」标题。
  2. 缺席性断言：反馈收紧为「未写明/未规定的内容只能写进 research_summary」，减少把缺席断言写进 items 后被反复驳回。
  3. 计数分类：校验服务不可用（模型连接失败/请求超时）与校验响应格式错误（如缺少逐项断言审查字段）不再计入「连续三次无效提交」；只有内容被驳回才计数，内容类三次上限与模块总预算保留。回归覆盖「连续三次服务故障后仍可继续提交同一批」。
  4. 传输异常：新增 `RemoteProtocolError` 等异常类型记录；已核实 61–62 秒断开是远端提前断开连接，不是本地 300 秒等待超时。
  5. 流式校验：兼容接口的校验请求改 `stream: true` + `stream_options.include_usage`，只有收到完整结束标记才进入 JSON 与证据校验；忽略 stream 的服务按整包 JSON 兼容处理。真实运行单次连续 222 秒未再断连。
  6. 输出截断：校验模型 12000 token 上限截断后，支持性校验改为逐条进行（每批仍 ≤3 条且 ≤6000 字符），截断反馈要求「拆成独立事实分批重交」。
- 验证记录：章节归属修复后跑了全量 `TENDER_RUN_DB_TESTS=1 uv run pytest -q` → 487 passed / 7 skipped，`ruff check`、`git diff --check` 通过；章节上下文 33 项针对性测试通过。之后的流式/计数/逐条校验改动只做了针对性回归（含 92 项适配器测试、节标题用例）——**最新改动尚未重跑全量，最终验收前必须补跑**。桌面浏览器预检 16 项是改动前结果，改动后尚未重跑 `.tmp/deep-flow-browser-10.mjs`。
- 工作区：全部改动仍未提交（禁止自动提交）。主要文件：`apps/api/src/tender/adapters/openai_chat.py`、`adapters/agent_chat.py`、`application/analysis_skills.py`、`application/analysis_research.py`、`application/deep_analysis.py`、`application/llm_routing.py`、`application/knowledge.py`、`api/knowledge.py`、`config/schema.py`、`worker/deep_analysis.py`、`worker/knowledge.py`、`apps/web/src/components/knowledge/ProjectAnalysis.tsx`、`apps/web/src/types/knowledge.ts`；新增测试 `apps/api/tests/unit/adapters/test_openai_stream.py`、`apps/api/tests/unit/worker/test_deep_analysis_evidence.py`；设计文档 `docs/设计/05-后端API设计.md`、`14-知识库与综合分析实现.md`、`16-DeepAgents标书分析运行时.md`。
- 下一步顺序（第一个动作即可执行）：
  1. `& '.\apps\api\.venv\Scripts\python.exe' '.tmp/analysis-repair-status.py' 10` 轮询到报告终态（当前 506 在跑，507–510 排队）。
  2. 终态后先补跑全量后端回归 + ruff，覆盖最新的流式与计数分类改动。
  3. 按失败原因补跑：`.tmp/retry-analysis-repair.py 10 <完整模块key>`（报告终态后才可用，会统一置 pending 并派发）。500 人员需新 attempt 才会重置预算/时限；501/505 属基础设施类失败，重跑即可；502/503 要看新 attempt 是否仍被内容驳回，再决定是否继续修反馈或规则。
  4. `.tmp/check-deep-report-10.py --final` → 人工逐模块核对（c86–118 广东租赁项目污染隔离、c35 安全培训合格证、投标有效期 180 天与前附表 90 天的区分）→ `.tmp/deep-flow-browser-10.mjs` 桌面验证（项目问答只能创建一次）。
  5. 全部模块完成且事实、引用通过前，不得称验收完成；不要新建报告或重传资料。

#### 2026-10-09 补记（新会话从这里读起；覆盖上面的运行状态）

用户本轮的两条明确要求：

1. 解析结果的 JSON 要满足展示需要：「解析字段名 + 该字段的结果值列表 + 每个结果的证据列表」；建议增加排序与分组字段；**不为旧报告保留兼容**（旧数据可直接删除）。
2. 「A/B 都在 agent 中完成，问答也可以用一个独立的问答 agent」：模块分析（A）与支持性验证（B）都要在 Agent 的提交工具内完成；问答（C）改为独立问答 Agent。此前 B 是 worker 里直接调 `verify_items` 模型、C 是 worker 里直接 `json_completion`，都不符合。

##### 已完成的改动（全部在未提交工作区）

- 报告结果结构（`items`）整体替换为字段数组：每项 `{field, group, sort_order, values:[{value, citations}], note}`；
  证据**逐值绑定**，同一字段多个值各自成项、各带自己的引用；`relations` 与 `research_summary` 不变。
  `_module_result`→`validate_items` 校验该结构，旧 `kind/title/text/presentation/cells` 协议彻底移除，无兼容分支。
- 支持性验证移入 Agent：`application/deep_analysis.py` 的 `submit_analysis` 内 `validate_support` 对字段逐项校验；
  最终批把关系断言包成字段单元一并验证，未通过字段回传可纠正反馈、未通过关系丢弃；`worker/deep_analysis.execute_module` 删除 worker 侧直接关系校验；`analysis_skills` 删除 `REPORT_CONTRACT`/`DocumentTools`。
- 新增独立问答 Agent：`application/qa_agent.py` 的 `answer_with_agent`，检索/补读/核对/作答在同一 DeepAgents 图内完成；
  `worker/knowledge._answer_question` 只注入检索器、读取器、授权回调，并把图内字段/关系与既有关系图谱合并。QA 复用模块 Agent 的路由、证据账、摘要与支持性验证，默认预算 16/24/80。
- 前端：`types/knowledge.ts` 用 `AnalysisField`/`FieldValue` 替换 `AnalysisItem`；`ModuleMarkdown`（新文件）按 `group` 分组、按 `sort_order` 排序、同字段多值或未通过校验时提示、每个值单独引用定位；`ProjectAnalysis`/`QuestionPanel` 改为遍历 value 级引用；删除 `ReportItems.tsx` 与旧 `.report-item*` 样式。
- 资源：13 个 parse_skills 的 SKILL.md / output_format.md / examples.md 同步新结构（outline 模块仍用 `submit_analysis(outline_nodes=…)`）。
- 文档：`docs/设计/05、14、16` 已同步字段值级结构、支持性验证内聚与独立问答 Agent。
- `api/knowledge.py` 补跑携带旧草稿时改用 `draft.fields`（原 `draft.items`），并移除旧 `items_verified`/`verified` 死引用。

##### 验证（2026-10-09 更新）

- 后端：`uv run pytest tests/unit -q` → **364 passed**；`uv run ruff check src/tender/` 全过；`uv run lint-imports` → **5 kept / 0 broken**。
- 前端：`pnpm typecheck` 通过、`pnpm test` → **76 passed**、`pnpm build` 生产构建通过。
- 集成测试（DB 已恢复后补跑）：
  - `TENDER_RUN_DB_TESTS=1 pytest tests/integration/test_knowledge_flow.py` → **10 passed**；
  - `TENDER_RUN_DB_TESTS=1 pytest tests/integration/test_deepagents_runtime.py` → **9 passed**。
    控制器用例最初失败：fixture `NativeRouter` 对全部 13 个模块统一按普通协议提交 `fields/relations`，
    而格式模块的 `submit_analysis` 绑定的是 `submit_outline`（必须提供 `outline_nodes`），导致
    `bid_format_outline_parsing` 连续三次参数校验失败、报告变 `partial`。已让 fixture 从
    `_routing_model` 的 `purpose`（含模块键）识别格式模块并改交 `outline_nodes`。
  - 全量：`TENDER_RUN_DB_TESTS=1 uv run pytest -q` → **495 passed, 7 skipped**。

##### 旧数据清理（2026-10-09 已执行）

用户已同意「不兼容旧报告直接删除」，本次在真实库 `ledger_admin` 上执行：

- `analysis_report` 1—8（legacy 运行时）及其 `analysis_module`（26 行）、`knowledge_relation`（4 行）全部删除。
- 报告 9（项目13）、10（项目15）虽标为 `deepagents-0.7.22-v1`，但生成于结构改造前，模块 `items`
  仍是旧 `kind/title/cells` 结构（分别 5、4 个模块），运行行 112 条、关系 13 条，一并删除；
  报告、模块、关系、`agent_module_run` 表现已全部清空，LangGraph `agent_runtime.checkpoints/
  checkpoint_blobs/checkpoint_writes` 孤儿检查点亦清空。
- 旧结构 `knowledge_answer` 2 条（项目问答）删除。
- **保留**：项目 13/15 本体、上传文件、解析版本、知识库 collection 与索引均未动；
  项目15 的招标文件解析状态为 completed，可直接重新发起分析。

##### 待办

1. 桌面浏览器验收（`.tmp/deep-flow-browser-10.mjs`）尚未在新结构下重跑：需先重新发起项目15 的分析、
   等报告 completed（前端 4400 / 后端 8300 当前未启动，只有 MinerU 在 8000）；
   注意脚本仍断言旧字段 `item.text`/`item.citations`，需先按 `values[].citations` 新结构改造脚本再跑。
2. 全部通过后再评估 goal complete；**禁止自动提交**。

#### 2026-10-09 代码审查修复补记

用户要求：P1 不处理，只修复本轮审查的五项 P2；本轮未修改 `.claude` 配置及其凭证，也未提交代码。

- 问答 `submit_analysis` 默认 `final=false`，已验证字段和关系按批累计；只有显式 `final=true` 才写入最终草稿并结束图，避免只保存第一批。
- 问答由模型工厂注入实际请求预算，原生对话、路由重试、摘要与支持性校验共用16次默认额度；全部工具共用24次额度，整个图与检索等待受900秒默认截止时间约束，超限终止并关闭模型客户端。
- 支持性校验载荷包含 `note`，邻域判断同时考虑字段名、分类及备注。业务断言和大纲父路径都须有引用支持；大纲派生关系也进入最终批验证，未支持关系不会进入图谱。
- 图谱扩展移入问答检索工具，关联原文受同一授权和80块默认证据预算约束；只有引用已进入证据账的关系才返回模型。答案统计和 `graph_used` 取实际工具结果，不再使用图外预检。
- 前端按 `group` 归组后，对组内字段按 `sort_order` 稳定排序；同序保留提交顺序，不修改调用方数组。

本轮验证：

- 后端单元测试：**375 passed**（新增11项，覆盖分批提交、实际请求及重试预算、提交工具预算、超时取消、图谱证据传递与预算过滤、备注送审及不支持的大纲关系过滤）。最后一处提示词调整后，相关45项再次通过。
- 数据库集成测试：`test_knowledge_flow.py` 与 `test_deepagents_runtime.py` → **20 passed**。新增“普通检索未命中、只有图谱关联才能取得的原文进入问答”回归。发现原知识流测试夹具未隔离 `agent_module_run`，清空旧报告后会触发真实表外键错误；已将运行表也改用临时表隔离。
- 前端类型检查通过、原76项测试通过；另验证组内排序、同序稳定性及输入数组不被修改。
- `ruff check`、`lint-imports`（5 kept / 0 broken）、`git diff --check` 通过。
- 本轮没有发起真实模型报告或问答，没有补做桌面浏览器验收；上方的真实报告验收待办仍保留。

#### 2026-10-09 优化实施补记（新会话从这里读起；工作区未提交、未验证）

用户要求：承接「900 秒是模块总时限而非单次请求」的结论，按建议优化——校验协议与反馈、分类重试上限、逐字段保存、失败仍能展示已完成成果、补跑继承、时间分配、原生调用流式接收。

##### 已实施（全部在本轮未提交工作区，12 个文件，见 `git status`）

- 校验结果结构前置校验：`application/analysis_skills.py` 的 `json_completion` 新增 `validate` 回调；`verify_items` 用 `validate_review` 在 JSON 重试循环**内部**检查 `reviews`/`supported` 结构，格式错误会带「每字段一条 review、多个 values 合并、必须恰好 N 条」的明确纠正提示重发，最多首次+2 次；`ModelOutputTruncated` 直接抛出，不再用同一输出上限重发。
- 分类重试上限：`application/deep_analysis.py` 的 `submit_analysis` 改为逐字段处理，单个字段结构/支持性失败记入 `state['field_failures']`（同一字段 3 次终止）；校验格式纠正失败在第 3 次以 `RuntimeError` 终止，不再回传「请重交同一批」；`ExtractionFailed`/`ExtractionUnavailable` 同样改为 `RuntimeError`，网络重试完全交给路由。`worker/deep_analysis.py` 传 `extra_retries_limit=2`，`worker/extraction.py::_routing_model` 支持按候选收敛 `extra_retries`。
- 逐字段保存与部分成果：每通过一项即写 `state['staged_items']` 并 `await save(state)`；`application/agent_runtime.py::save` 在 `state['staged_items_verified']` 时同事务把 `verification == "supported"` 的字段写入 `analysis_module.items`（运行状态与成果分离，检查点同事务）；`api/knowledge.py::get_report` 对**未完成**模块合并 `agent_module_run.state->'staged_items'` 展示；前端 `apps/web/src/components/knowledge/ProjectAnalysis.tsx` 对未完成但有成果的模块显示「已保存 N 项核实成果…补跑会保留」并去掉只遍历 completed 模块的限制。
- 补跑继承：`api/knowledge.py::retry_report` 把旧 `draft` 转成 `staged_items`/`staged_relations`/`staged_items_verified`，并清空 `field_failures`、`unavailable_submissions`，保证新 attempt 接着补齐而不是直接结束。
- 时间分配：`application/analysis_research.py::AgentLimits.timeout_seconds` 与 `config/schema.py` 的 `analysis.timeout_seconds` 默认值 900→1800；`application/llm_routing.py` 在存在 `remaining_seconds`（Agent 多轮）时不再把剩余时间按计划请求数切分；`worker/deep_analysis.py` 的 `budget_status` 新增 `seconds_remaining`/`finish_reserve_seconds`，进入收尾窗口时中间件提示提交并拒绝新的 `search_document`/`search_knowledge`。
- 流式接收：`adapters/agent_chat.py` 对 `openai`/`openai_compatible` + `chat_completions` 改用 `astream` 聚合（`stream_usage=True`），并校验 `finish_reason`，半截流不进提交工具；异常链改为取根因类型。

##### 已核对的事实（只读诊断，2026-10-09 21:07 SGT 前后）

- 报告 11（项目 15）：`status=failed`，`finished_at=2026-10-09 12:44:56Z`（20:44 SGT）；13 个模块全部 attempt1 失败——连接类 `APIConnectionError`/`RateLimitError` 7 项、模块总时限耗尽 3 项、模型调用时间预算不足 1 项；每个 run 的 deadline 都是 start+900 秒；**没有暂存成果**（旧代码不落部分成果）。
- 配置中心 active release id=8（company 1）：`analysis.timeout_seconds=1800`、`max_model_calls=80`、`max_tool_calls=100`、`max_output_tokens=12000`，已与新默认一致；报告 11 的限值快照 900 秒属历史记录，不回写。
- 运行中的进程：API(8300)/worker/beat 与前端(4400) 均于 19:15 启动，而本轮源码改动时间为 20:28–20:36，**进程仍是旧代码，验证前必须重启**；MinerU 8000 在跑。
- 只读语法检查（`ast.parse`）：10 个改动的 Python 源文件可解析（`worker/deep_analysis.py` 的 BOM 属 HEAD 既有，不影响编译）；**`apps/api/tests/unit/adapters/test_agent_chat.py` 第 107 行有语法错误**（`return … async def run():` 被并到同一行），当前测试无法收集。
- 本轮新增只读诊断脚本：`.tmp/status-report-11.py`、`.tmp/check-syntax.py`、`.tmp/check-config-limits.py`（均不写业务数据）。

##### 待办（按顺序执行）

1. 修 `apps/api/tests/unit/adapters/test_agent_chat.py:107` 的语法错误（把 `async def run():` 拆回独立行）。
2. 为新行为补测试：逐字段落库（`agent_runtime.save`→`analysis_module.items`）、未完成模块展示 `saved_items`、补跑 `draft`→`staged` 继承、`field_failures`/`unavailable_submissions` 上限、`extra_retries_limit`、`json_completion` 的 `validate`/截断分支、`agent_chat` 流式聚合。
3. 验证：`uv run pytest tests/unit -q`、`uv run ruff check src/tender/`、`uv run lint-imports`；DB 集成 `TENDER_RUN_DB_TESTS=1 uv run pytest tests/integration/test_knowledge_flow.py tests/integration/test_deepagents_runtime.py -q`；前端 `pnpm typecheck`、`pnpm test`。
4. 同步文档：`docs/设计/16-DeepAgents标书分析运行时.md` 第 19、124 行仍写「900 秒」，`05`/`14` 涉及限值的表述需一并复核。
5. 重启 API/worker/beat 后（记录新 pid），对项目 15 重新发起分析；失败时按「已保存成果」验证部分展示与补跑继承。
6. 桌面浏览器验收仍待做；`.tmp/deep-flow-browser-10.mjs` 仍用旧字段 `item.text`/`item.citations`，需改成 `values[].citations` 再跑。

**禁止自动提交**：本轮改动未经测试，提交前必须完成第 1–3 步。

#### 2026-10-09 校验架构与预算补记（新会话从这里读起）

用户反馈：报告11 第2次运行 `模型请求 80/80 · 工具调用 17/100` 失败，质疑「80次调用耗尽说明设计有问题」「80次模型调用只有17次工具调用不合理」，并给出架构要求：**工具内部发模型请求不对，AI 调用应由 Agent 来做**。已确认框架就是 deepagents：`apps/api/pyproject.toml` 固定 `deepagents==0.7.22`，模块子图与问答 Agent 都由 `create_deep_agent` 构建（`application/deep_analysis.py:771`、`application/qa_agent.py:198`），`RUNTIME_VERSION="deepagents-0.7.22-v1"`，venv 实测 0.7.22。

##### 诊断（只读，交叉验证）

- `llm_call_log` 80 行按 `invocation_id` 归并 = 68 次逻辑请求：主循环 12 次（13 行，1 次连接重试）+ 提交工具内部 56 次（67 行）。4 次 `submit_analysis`，旧实现逐字段 `validate_support`，且 `reusable` 依赖整轮才置位的 `staged_items_verified`，导致每轮整批失败、已继承字段重复送审（16+16+16+8）。
- 工具结果 17 条与 `run.tool_calls` 一致：read_document 8、submit_analysis 4、search_document 3、list_documents 1、read_file 1。

##### 改造（工作区未提交）

- `submit_analysis` 只做确定性登记（结构/引用归属校验、`staged_items`、`verification="pending"`、`pending_final`），返回 `awaiting_review`，不再调用模型。
- `ResearchMiddleware.run_review_step()` 在 `abefore_model` 执行：本批 pending + final 关系单元一次批量送审，未通过返回反馈消息让主 Agent 修正；字段纠错上限 3 次；全通过才 `build_draft`；`ModelOutputTruncated` 单独计入 `unavailable_submissions`，`InvalidModelOutput`/`ExtractionFailed`/`ExtractionUnavailable` 终止模块但保留已通过字段。
- 删除已死的工具内校验残留（`ReviewUnavailable` 类与 `review_unavailable` 工具错误分支），避免文档与实现不一致。
- `analysis_skills._verification_batches` explain 模式 limit 1→3、chars 6000；`build_module_agent(validate_support=...)` 改名 `review_support=...`。
- 限值：默认 32→40、`max_output_tokens` 4096→8192（`config/schema.py`、`analysis_research.AgentLimits`、alembic 0008 同步）。

##### 重跑暴露的新问题与修正（关键）

- 发布版本9（40/48/24000/8192/1800/并发1）后重跑：模块521（旧限值 80/12000）完成，22 字段全部 supported、5 关系、draft 生成，用掉 57 次模型/23 次工具；但模块522 在新限值下**失败**——连续三次 `模型输出达到token上限，工具参数或正文不完整`（ctok=8192，84~91 秒），报错来自 deepagents 的 `SummarizationMiddleware` 摘要调用（ptok≈10.5k 的整段对话提示）。
- 24k 上下文预算让 522 的 8 轮主循环里出现 4 次摘要压缩调用（输出 2k~6k token，且 1 小时窗口内该 run 只有 8 条带工具调用的 AI 消息）——摘要调用既烧次数又烧输出 token。checkpoint 里的 `_summarization_session_id` 证实压缩确实发生。
- 因此发布**版本10**：`analysis.max_output_tokens` 8192→**16384**（RetryInput/配置中心上限内），`analysis.context_tokens` 24000→**96000**（减少压缩次数）；其余 40/48/1800/并发1 不变。代码默认值仍是 8192，是否同步改默认待定（需要更长时间的真实数据）。
- 取消并补跑报告11：模块522 起的 12 个模块创建 attempt3，限值快照已是 16384/96000/40，522 重新运行中。

##### 验证

- `apps/api`：`uv run pytest tests/unit -q` → **384 passed**；`tests/contract` → 93 passed / 7 skipped；`ruff check src/tender/` 通过；`lint-imports` 5 kept / 0 broken。
- `docs/设计/16-DeepAgents标书分析运行时.md` 已同步：按批送审、`abefore_model` 校验步骤、40 次/8192（DDL 契约值）、摘要/截断处理表述。

##### 补跑限制收敛（同日追加）

用户反馈「只要不是正在跑，应该都能重新跑」。原实现只允许 failed/partial/canceled 报告补跑，且重置只作用于
失败/已取消模块，对已完成模块的 `module_keys` 请求会被静默忽略。现改为：报告处于 waiting/pending/running 时
以 `report_running` 拒绝（提示等待或先取消），其余状态都允许；未指定模块时仍只补跑失败/已取消模块（需有可补跑
模块，否则 `nothing_to_retry`），显式指定模块时已完成的专题也重新解析且**不继承旧草稿**（从零开始）。前端新增
「重新解析全部专题」（显式传全部模块键）与已完成专题内的「重新解析本专题」；已在跑的报告按钮保持禁用。
验证：`tests/integration/test_deepagents_runtime.py` 10 passed（新增显式重跑已完成模块的用例）、unit 384 passed、
ruff/lint-imports 通过、`pnpm typecheck` 与 76 项前端测试通过。

##### 运行现场与待办

- 后端手动重启（`.tmp/start-backend-manual.ps1`）：api=42876 / worker=33588 / beat=36064，uvicorn 实际监听 8300；`-Status` 不识别手动进程。
- 监控脚本 `.tmp/watch-report-11-cost.py`（已修 `analysis_module` 无 `attempt` 列的问题，改取每模块最新 run）；另有 `.tmp/inspect-*.py` 系列只读诊断。
- 待办：1) 观察 522–533 在新限值下的完成情况与调用数（目标每模块 ≤40，且主循环/校验/摘要三类请求可解释）；2) 完成后核对 `staged_items` 落库、draft、失败时前端「已保存成果」与补跑继承；3) 桌面浏览器验收（`.tmp/deep-flow-browser-10.mjs` 需改用 `values[].citations`，前端 4400 未启动）；4) 评估是否把 `analysis.max_output_tokens` 代码默认值同步到 16384；5) `.agents/memory/project.md` 指针已更新。
- **禁止自动提交**：改动未提交，提交前先完成上述验收。


#### 2026-10-10 表格展示与真实定位补记（新一轮会话）

用户要求：1) 解析结果改成 Markdown 表格展示，定位做成图标点击定位；2) 产出真实有用的数据，定位要是真实数据的定位，不要无关定位与重复定位。

##### 已实施

- 前端表格化（上一轮完成，本轮复验）：`ModuleMarkdown.tsx` 列为「字段 / 解析值 / 定位」，定位为 target 图标按钮，同一行内按
  `[source_id, element_id, page_no, quote]` 去重；`Icon.tsx` 新增 target，`globals.css` 新增 `.module-table*`。
  浏览器复验（`.tmp/check-table-render.mjs`，改用时间戳 profile 避免 DevToolsActivePort 残留）：3 列表头、行数正常；
  点击定位（新脚本 `.tmp/check-locate-click.mjs`）能打开右侧原文并显示对应摘录。
- 值级真实定位（`application/knowledge.py`）：`validate_items` 登记引用时调用 `align_citation`——摘录已含该值就保留；
  同块另有该值就收敛到值所在原文切片（表格里命中片段占值大半时收窄到单元格，只是零头时保留窗口避免摘掉金额等事实）；
  本块没有、其它已读块唯一含该值才改引；找不到时保持原引用交给支持性校验（值本身是概括时不能伪造位置）。
  引入 `match_text`（NFKC+去空白）与 `core_is_specific`（命中片段需 ≥6 字或占值 1/3，防止表头等短词把定位带偏）。
  同一字段内相同取值合并、同一处原文按位置去重。
- 字段级合并（`merge_field_entries`）：同一 `group:字段名` 的多个已核实版本在校验通过后合并成一行（值并集去重、
  引用去重、id 按合并内容重算），替代原先“新版覆盖旧版”的写法，分批补交不再丢值；`get_report` 对已完成模块同样合并，
  历史报告不再出现重复行。`visible_items` 顺带按元素原文回查收敛历史错位摘录（`resolve(with_content=True)`，按元素缓存）。
- 提示词收紧：提交侧提示“引用摘录必须包含该值本身的文字”，校验侧提示“同一块里的其它事实不能当作依据（如用单位名称
  的摘录支撑地址），应判 false”。

##### 验证

- `apps/api`：unit **391 passed**；`tests/contract` 93 passed / 7 skipped；`lint-imports` 5 kept / 0 broken；`ruff` 通过。
- 集成：`test_knowledge_flow.py` 13 passed（新增“同字段多版本合并 + 历史错位摘录收敛”用例）、
  `test_deepagents_runtime.py` 10 passed；合计 23 passed。
- 只读核对报告11 模块521 的完整存储引文（`.tmp/dump-521-full-quotes.py`）：多数摘录确含取值；确存的重复定位是
  element 571 的标段行被「分标名称/中标份额/分标预估监理费」三个字段共用（同一行确实同时写着三件事）。
  展示路径复算（`.tmp/diff-align-report11.py`）本轮对 521 改写 0 处——旧数据没有更多可确定性纠正的错位，
  新分析才会走新的收敛/合并逻辑（改定位不改取值，找不到就保持原引用）。
- 后端已用新代码重启（`.tmp/start-backend-manual.ps1`）：api=24056 / worker=23916 / beat=41408，8300 监听正常；
  报告11 的 523 运行行由 `requeue_unlocked_runs` 回到 pending 后从 checkpoint 继续，522 之后模块按新代码产出。

##### 待办

1. 观察报告11 剩余模块在新代码下的产出：定位应为值本身的原文（表格行收窄到单元格），同字段不再重复成行。
2. 前端表格在窄栏下的观感（`.tmp/table-check/analysis-table.png`）已可用；如需更紧凑可再收定位列宽度。
3. 桌面浏览器验收（`.tmp/deep-flow-browser-10.mjs` 需改用 `values[].citations`，前端 4400 在跑）。
4. `.agents/memory/project.md` 指针已更新；**禁止自动提交**，改动仍未提交。


#### 2026-10-10 晚间复核补记（表格/真实定位验收 + 两个单测失败定性）

##### 现场恢复

- 上轮会话结束 18 小时后，WSL 与后端均已停机：`wsl -d Ubuntu-22.04 -- true` 拉起容器，
  `powershell -NoProfile -ExecutionPolicy Bypass -File .tmp\start-backend-manual.ps1` 重启（api=23088 / worker=24188 / beat=24480），
  前端改用 `.tmp\start-web.ps1`（`pnpm exec next dev -p 4400`）重启，8300/4400 监听正常。

##### 两个单测失败的定性（都来自同一处去重语义，不改运行时逻辑）

- `test_knowledge.py::test_merge_field_entries_unions_values_and_locations`：夹具把不同块的 `element_id` 都写成 1，
  于是两处原文被当成“同一元素里互相包含的摘录”合并成一条。真实库里块与元素一一对应（`blocks()` 返回 `element.id`），
  夹具改为按块推导 `element_id`，用例本意（同值出现在两处就保留两条定位）保持不变。
- `test_analysis_outline.py::test_node_name_requirement_and_parent_must_have_read_evidence`：子节点窄摘录与父节点整块摘录
  来自同一元素，按新语义只保留更完整的一条，断言随之更新为 `[TEXT]`（关系引文仍复用校验后的引文行）。
- 保留“更完整的一条”而不是“更窄的一条”的原因：包含合并只在同一 `(source_id, element_id)` 内生效，更长的一条必然覆盖较短的一条，
  不会削弱证据；反之保留更窄的摘录可能让同一值在展示时指向不含该值的摘录。

##### 验证（本轮全部复跑）

- `apps/api`：`uv run pytest tests/unit -q` → **392 passed**；`ruff check src/tender/` 通过；`lint-imports` 5 kept / 0 broken。
- 集成（`$env:TENDER_RUN_DB_TESTS=1`）：`test_deepagents_runtime.py` + `test_knowledge_flow.py` → **23 passed**。
- 前端：`pnpm typecheck` 通过；`pnpm test` → 12 文件 / **76 passed**。
- CDP 复验：`.tmp/check-table-render.mjs` 三列表格正常（字段/解析值/定位，定位为 target 图标 + 页码）；
  `.tmp/check-locate-click.mjs` 点击定位打开右侧原文并显示摘录（`element 93` 与值同块）。截图在 `.tmp/table-check/`。
- 新代码首个完成模块 525（`.tmp/dump-module.py 525`）：6 行无重复；`分值构成`/`评分标准` 的每个分项各自命中一个元素，
  没有同位置重复；引文均为取值所在原文（含小节标题）。模块 521（旧代码）仍有历史噪音，属重解析后才消失的范围。

##### 报告11 现状与补跑口径

- 521 completed（旧代码 57 调用）｜522 failed：模型调用时间预算不足以再次请求｜523 failed：模块总时长（1800s）耗尽｜
  524 failed：证据校验请求输出达到 16384 token 上限｜525 completed（新代码 13 调用）｜526 卡在 running（停机前的租约，已被
  `requeue_unlocked_runs` 识别为过期，任务启动时复位）｜527–530 pending｜531–533 canceled；报告整体 failed。
- 活跃配置（release 10）：`max_model_calls=40`、`max_tool_calls=48`、`timeout_seconds=1800`、`context_tokens=96000`、
  `max_output_tokens=16384`（代码默认 8192 只是兜底值，实际生效已是 16384）。
- 补跑口径确认：`retry` 只拒绝 waiting/pending/running（`report_running`）；未指定模块只补跑 failed/canceled，显式指定可重跑已完成
  且不继承旧草稿。因此 522–524 与 526 现在都能重新分析，不需要先取消或等待。
- 待办：是否补跑 522–524（上次失败是预算/延迟原因，未调整运行时预算）以及重解析 521 以应用新的定位收敛与同字段合并——
  需要真实模型调用，交由用户决定后用界面「重新解析」或 `POST /analysis/reports/11/retry` 触发。

##### 补跑执行记录（2026-10-10 18:55，与上条同一会话内接着做）

- 已调用界面同一接口 `POST /api/v1/analysis/reports/11/retry`，显式指定 `disqualified_items_parsing`、
  `biz_standard_parsing`、`tech_requirement_parsing`（未指定时不会重跑已完成模块），返回 `{"id":11,"status":"pending"}`。
- 复跑后控制器按模块 id 串行执行：522–524 新建第 4 次尝试（`agent_module_run` 784–786，从暂存成果继续，
  不重复已核实字段）；526 因“恢复不重置时限”仍判失败（停机前那次运行已耗完 1800s，租约过期后再恢复必然再次超时）——
  它是 failed，本轮被跳过，需要在报告本轮结束后再补跑一次（补跑会新建 attempt，时限才会重置）；
  527 正在运行（本轮已 4 次模型调用），528–530 排队；531–533 保持 canceled 不动。
- 结论：卡在 running 的历史模块不会自动复活为有效运行，正确姿势是失败后走补跑（新建 attempt）。

#### 解析结果表格改为「字段 / 解析值 + 值后定位图标」（2026-10-10 19:20）

用户要求：不要单独的定位列，定位图标直接跟在取值后面。

- `ModuleMarkdown.tsx`：表格改为两列（字段 / 解析值）；`ValueLocates` 把某值的引用渲染成图标按钮放在该值末尾，
  按“资料 + 元素 + 页 + 摘录”在**该值内**去重（`valueCitations`）；图标 `title/aria-label` 仍给出文件、页码与摘录，
  点图标走同一条 `onLocate` 定位链路。
- 排版：`renderMarkdown(text, trailing)` 把图标接进最后一段 `<p>` 的行内末尾（单段值必然同行），
  列表结尾的值则在最后一块之后单独成行；`globals.css` 用 `.value-locates` 取代 `.field-locates`/`.module-table-locate`。
- 验证：`pnpm typecheck` 通过、`pnpm test` 76 passed；CDP 实测（`.tmp/inspect-row.mjs`、`.tmp/find-row.mjs`）逐标签确认
  图标父节点是值所在 `<p>` 且是段落最后一个子节点（`after: true`）；截图 `.tmp/table-check/analysis-table.png`。
  辅助脚本 `.tmp/check-table-render.mjs` 的选择器同步改为 `.value-locates`。

#### 2026-10-10 审查问题修复

用户要求修复上一轮审查确认的三处问题，已完成代码与回归测试，改动未提交。

- `deep_analysis.py`：最终提交标记只用于当前校验。校验不支持、截断或服务失败后不会让下一次补读/暂存提前结束；达到纠错上限前也先保存撤销标记后的状态。补跑接口同时清除历史 `pending_final`，新 attempt 必须重新确认完成。
- `knowledge.py`：自动换块仅限同一 `source_id`，原条款与补充文件分别证明修订前后状态，不能互相替换。提交与校验提示同步说明双边证据的作用，同一文件内的错位定位仍可纠正。
- `analysis_outline.py`：报告条目 id 按大纲节点 id 生成，同名同要求节点也能保持独立。运行时与报告展示统一跳过大纲的普通字段合并，保留不同父路径的材料节点；普通专题的同字段值合并保留。
- 回归覆盖：失败/截断后补读、`final=false` 纠正后再次 `final=true`；终止和补跑时撤销收尾标记；修订结论保留双边引用；不同父级下同名同要求节点的分批暂存；新旧报告的大纲展示。
- 验证：`uv run pytest tests/unit tests/contract -q` → **490 passed / 7 skipped**（unit 397 / contract 93）；`TENDER_RUN_DB_TESTS=1` 的 `test_deepagents_runtime.py` 与 `test_knowledge_flow.py` → **25 passed**；`ruff check src/tender/`、`lint-imports` 全部通过。
- 本轮验证采用模拟模型与隔离数据库测试表/schema；未重启业务服务、未补跑真实报告。报告11 的实时状态需另行确认，已落库且已被错误合并/遗漏的旧结果需要重新解析才能恢复。

#### 提交与下一步前端任务

用户明确要求先提交当前代码，本次提交包含分析运行时、成果暂存、报告表格与定位，以及三处审查问题修复和测试。
此前“未提交”均为当时状态；仍禁止未经后续明确要求自动提交新改动。

下一步用户要求全面审查并修复前端体验，优先使用成熟框架与组件。已明确的问题：新增/编辑表单在页面上方展开，当前滚动位置看不到变化；应改为可见的弹窗或抽屉，并系统检查其它交互问题。该前端任务尚未实施，不包含在当前提交中。

#### 2026-10-10 前端体验审查与修复（改用成熟组件）

用户要求：全面审查 `apps/web` 并一次性解决前端问题，明确要求使用成熟框架与组件，不要继续自造轮子。已知症状是新增/编辑表单在页面上方展开，用户停留在当前滚动位置时看不到任何变化。

改造要点（改动均在工作区，未提交）：

- 引入 `antd` 6 与 `@ant-design/nextjs-registry`（SSR 内联样式），新增 `AntdProvider` 统一中文文案、主题令牌与全局 message；补齐 `app/error.tsx`、`app/not-found.tsx`。
- 新增/编辑一律走 Modal：供应商、模型、项目、知识库创建与重命名；模型导入、配置版本详情、调用链改为 Modal/Drawer。提交中禁用控件避免重复请求，保存失败保留草稿，关闭脏表单前二次确认。
- 长列表分页：项目、知识库 12 条；模型 8 条；供应商、版本、调用记录走组件库分页，模型/供应商/配置表格在自身容器内滚动，窄屏不横向溢出。
- 反馈统一用 antd message（`useFeedback`）出现在视口内；区分「已提交但刷新失败」与「保存失败」，避免误导用户重复提交。
- 上传改用 `Upload.Dragger`：选文件不自动提交，多 ZIP、超限、批次数量在提交前拦截。
- 报告正文改用 `react-markdown` + `remark-gfm` 渲染，删除手写 Markdown 解析；定位图标仍追加在取值末尾，重复引用去重。
- `lib/config/draft.ts`：清空数值不再被 `Number("")` 当成 0 提交，改为提示补填，避免误发零并发/零超时配置。
- 调用链抽屉改为读全部分页（原先只取前 25 条却标称完整记录）。
- 新增 Playwright 端到端回归（`apps/web/e2e/`、`apps/web/playwright.config.ts`），API 全部 mock，不写业务库、不调用真实模型。

验证：

- `pnpm --dir apps/web typecheck` 通过；`pnpm --dir apps/web test` → 12 个文件 / 77 项通过；`pnpm --dir apps/web build` 通过（Turbopack，8 条路由）。
- `pnpm --dir apps/web exec playwright test` → desktop(1440×900) 14 项 + mobile(390×844) 14 项全部通过；覆盖长列表底部编辑、保存失败保留草稿与重复提交拦截、删除/重解析取消不发写请求、首次加载失败重试、版本详情抽屉换版本、调用链全量、窄屏无横向溢出。
- 真实后端只读冒烟（4400 dev + 8300）通过：`/projects`、`/settings/models`、`/settings/config`、`/knowledge`、`/projects/1`、`/projects/1/files` 均有内容、无未捕获异常、无横向溢出。
- 人工查看主要页面截图（`.tmp/frontend-shots/`），确认弹窗居中、页脚按钮位于视口内。

运行现场与待办：

- 当时 4400 dev server（pid 12292）与 8300 后端在运行，e2e 通过 `reuseExistingServer` 复用该 dev server；后续跑 e2e 前先确认端口占用。
- 本轮改动已按用户要求提交（改动集中在 `apps/web`、根 `.gitignore` 与 `pnpm-lock.yaml`）；后续改动仍禁止自动提交。
- 未做真实写入类验收（新建/删除/发布/回滚/上传真实文件）与真实模型调用；需要时单独确认后再做。
- antd Tabs 的隐藏面板在开发模式首帧可能短暂堆叠（CSS-in-JS 注入时序），生产构建样式内联无此现象，未做额外处理。

#### 2026-10-10 提交后的代码审查与待修复项

用户要求先提交当前前端改造，再修改审查发现的问题。前端改造已提交（提交 `fee563d`），审查确认的两处行为缺陷已修复但尚未提交：

- `apps/web/src/components/llm/ProvidersPanel.tsx`：新加的「搜索远端模型」输入框（约 443 行）位于 `Form id=import-models`（`onFinish={importSelected}`）内部，footer 的「导入 N 个模型」是 `htmlType=submit` 的默认提交按钮。已勾选模型后，在搜索框按 Enter 会触发隐式提交，直接发出导入（创建模型）的写请求。修法：把搜索框移到表单之外，或在搜索框上拦截 Enter 的默认行为。
- `apps/web/src/components/results/ResultPanel.tsx`：结果卡的 `busy` 由 `busyExtractionId === item.id` 改为 `busyExtractionId !== null`（约 386 行）。`busyExtractionId` 会一直持有到 `waitForJob` 返回，单字段重跑期间其它卡片的确认/修正/重跑/驳回全部被禁用。修法：卡片只在自己被提交时禁用，另用独立标记挡住并发写请求。

另需注意：仓库根目录存在未跟踪的 `pelican-bicycle.html`（与本项目无关的演示文件），提交时刻意未纳入版本库，勿误加。

修复方式与验证：

- 两处修复：导入弹窗在表单层拦截 Enter 的默认行为（表单只提供 Form 上下文，唯一提交入口仍是页脚按钮）；结果面板恢复「单条操作只锁自己那张卡」，批量确认改用独立的 `batchBusy` 做整面板加锁。
- `pnpm --dir apps/web typecheck` 通过；`pnpm --dir apps/web test` → 12 个文件 / 77 项通过。这两条路径都未被现有 e2e 覆盖，未重跑 Playwright。
- `pelican-bicycle.html` 已不在工作区（勿再补回）。

#### 2026-10-11 项目 Skill 适配与解析运行护栏

用户授权按前一轮方案实施，并明确要求参考 Skill 不能直接套用，需要优化后写入项目代码。

已完成（未提交）：

- 项目内 13 个 Skill 位于 `apps/api/src/tender/resources/parse_skills/`，保留领域规则、品类细则和覆盖清单；统一为本项目的检索、按 ID 补读、值级引用与分批结构化提交协议。根目录参考 Skill 未改。Skill 名称和虚拟目录改为连字符，数据库模块键、源码资源目录保持下划线兼容。
- `analysis_policy.py` 新增规则加载、模块 SHA-256、同事实纠错计数、实际进展签名与已核实重复事实的证据选择。运行时首次模型调用前通过 `load_skill` 工具读取冻结的 Skill 正文和输出清单；记录 `skill_loaded` 审计事件，核心规则保留在模型系统消息中。
- `analysis_research.py`：专题解析启用精简协议，检索/补读证据仅返回 `{id,text}`；诊断分数、来源与位置元数据留在服务端。`read_document(block_id,before,after)` 只允许从已读 ID 补读最多 12 块；拒绝跨检索范围混入资料。共享问答仍使用原有协议。
- `analysis_skills.py`：独立支持性校验同样只给证据 ID 与文本；返回每值 `evidence_ids`，校验数组形状、ID归属、非空/去重及跨来源必要证据。支持性针对所选证据集合判断，不依赖自报可信度或检索分数。邻域文本沿用裁剪预算，不恢复为全文。
- `worker/deep_analysis.py`：只对通过校验且最终选中的 ID 查询真实定位。不同批次相同事实选择一套已验证充分的引用，避免合并时重新累积重复定位；修订、冲突、不同标段的必要证据保留。
- `deep_analysis.py`：同参数只读调用复用但继续扣总预算；全局/单工具连续错误、无进展收尾、事实纠错和相同请求均有硬上限。错误返回结构化纠正信息。局部校验成功后，后续批次截断仍保留已核实事实；截断次数先持久化。自动恢复只处理本地连接/检查点临时故障，最多2次；模型路由耗尽不再重跑模块。恢复保持截止时间与失败账，主动补跑清理旧计数。
- 新增迁移 `0010_analysis_guards.py` 与配置中心5项限值（工具连续失败3、无进展3、同参数调用3、同事实校验失败3、子Agent自动恢复2），不改活动发布。配置种子契约测试已同步。
- 新增运行说明 `docs/工程/14-解析Skill与运行护栏.md`，说明协议、证据选择、错误/恢复边界、配置、发布及验证方法。

验证结果（最终代码）：

- `uv run pytest tests/unit tests/contract -q --tb=short`：508 passed / 7 skipped。
- `TENDER_RUN_DB_TESTS=1`，`test_deepagents_runtime.py` + `test_knowledge_flow.py`：27 passed；使用隔离schema和模拟模型，不修改业务数据。新增真实图的双候选证据→只选择一条→仅解析该ID→真实坐标落库，以及隔离配置迁移测试。
- 13个 Skill 均通过 skill-creator 的 `quick_validate.py`（`python -X utf8`），并有快照哈希、参考文件路径及真实加载回归。
- `ruff check`（源码、新增/修改测试、迁移）通过；`lint-imports`：5 kept / 0 broken。

部署和兼容性：

- 本轮未执行业务库 `alembic upgrade head`，未重启 API/worker，未跑真实供应商模型；现场仍需重新确认。
- 启用时在 `apps/api` 执行 `uv run alembic upgrade head`，再重启API/worker并新建分析报告。
- `RUNTIME_VERSION` 从 v1 升至 `deepagents-0.7.22-v2`。现有版本门禁会拒绝继续执行/补跑旧协议报告，旧成果可查看；不要手工改历史报告版本号来恢复旧检查点。需要使用新流程时重新发起分析。
- 前端未修改；没有自动提交、推送或启动子代理。

#### 2026-10-11 解析护栏审查问题修复

用户要求修复未提交改动审查中确认的两处问题。本轮改动未提交。

- `analysis_policy.py`：已核实事实的证据去重键加入备注，防止相同取值但主体、起算点等条件不同的两批结果合并后丢掉其中一方依据。
- 纠错计数保留字段维度；跨字段的事实维度改为取值、分组、备注与引文组合，不再仅凭共用引文累计失败。仅改字段名仍不能重置同一断言的额度，同字段修改取值也继续计数。使用新的 `fact:` 键，不继承旧 `evidence:` 的混合事实计数。
- 新增回归先复现失败再验证修复：真实 DeepAgents 图分批提交不同备注并保留双方引用；三个字段共用引文时各自获得三次校验机会；状态序列化恢复后额度不重置；分组/备注不同的断言不串账，同字段改值仍累计失败。
- 验证：`uv run pytest tests/unit/application/test_analysis_guards.py tests/unit/application/test_deep_analysis.py -q --tb=short` → **68 passed**。本轮使用模拟校验模型，未调用真实供应商、未修改业务数据库、未重启服务。

#### 2026-10-11 提交解析 Skill 与运行护栏

用户明确要求先提交代码，本次提交包含项目内 Skill 适配、解析运行护栏、配置迁移、证据选择、上述两处审查修复及相关测试和文档。前述“未提交”为当时状态；后续新改动仍须获得明确提交指令。本次不推送、不执行数据库迁移或重启服务。

#### 2026-10-11 修复解析结果停留在文件或章节转引

用户反馈评分标准等结果只有“详见某文件/章节”，要求追踪并直接提取真实招标要求。本轮修改未提交。

- 原因：原独立校验仅检查断言是否受原文支持，转引句逐字摘录即可被判为 supported；通用契约和评分 Skill 缺少追踪转引的明确流程，且“一句话内”的限制与完整评分档次、公式存在冲突。新增测试在旧代码上复现了转引句通过校验并使图提前完成。
- `deep_analysis.py`：所有专题共用的契约和每轮提示明确把转引当线索，按目标名称、条号、业务主题检索，跨文件核对授权资料并补读实质条款；解析值必须直接写出要求。允许同一评分项用多句/换行保留完整条件和公式。
- `analysis_skills.py`：专题解析的既有校验请求新增必填 `unresolved_references` 字符串数组，独立于原文支持性检查；存在未展开指向时，即使 supported=true 也退回字段，提供 search_document/list_documents/read_document 的纠正反馈。未通过的索引不进入精选定位与最终报告。缺失或非法响应沿用最多两次格式纠正，未增加模型请求层或无界检索循环。
- 评分 Skill、输出清单和跨文件关联 Skill 补充追踪规则。语义区分正常标准号、材料义务、修订关系与完整要求后的出处，不使用关键词一律删除。共享问答协议保持不变。
- 新增 16 项回归：纯索引、部分展开的评分细则、正常实质要求、校验响应缺失/非法、真实图跨文件检索及邻块补读、目标缺失只记缺口、循环转引有界停止并保留已核实成果。
- 验证：`uv run pytest tests/unit tests/contract -q --tb=short` → **529 passed / 7 skipped**；隔离数据库 `test_deepagents_runtime.py -k selected_evidence_resolves` → **1 passed / 11 deselected**；相关 Ruff、diff 检查及两个修改 Skill 的 `quick_validate.py` 均通过。模型调用均为测试替身，未调用真实供应商。
- 已有报告不会自动改写，需重新发起分析使用新的 Skill 快照；本轮未重启 API/worker、未执行迁移、未重新解析业务报告。

#### 2026-10-11 提交转引追踪修复与数据库迁移文档

用户明确要求先提交代码。本次提交的是 2026-10-11「修复解析结果停留在文件或章节转引」那一节的全部改动,加上新增的数据库迁移文档。

- 代码与 Skill:`deep_analysis.py` 契约与每轮提示、`analysis_skills.py` 的 `unresolved_references` 必填校验、三个 Skill 文件与输出清单的追踪规则、两份测试的响应补字段、新增 `test_analysis_references.py`(16 项)。
- 文档:新增 `docs/工程/17-数据库迁移.md`,README 索引、`07` 第 1.1 节与 `14` 第 8 节就近挂接。
- 提交前验证:`uv run pytest tests/unit tests/contract -q --tb=short` → **529 passed / 7 skipped**;新增测试单跑 16 passed。模型调用均为测试替身。
- 现场已变:本轮之后用户已在业务库执行 `alembic upgrade head`,`alembic current` → `0010_analysis_guards (head)`,即 0009 → 0010 的迁移**已应用**;`agent_runtime` 下 checkpoint 四表已存在,无需补跑 `agent_checkpoints`。尚未重启 API/worker。
- 部署与运行边界:**未重启服务**、未推送、未调用真实供应商、未重新解析业务报告。新 Skill 快照只对新发起的分析生效,已有报告不会自动改写。

### 2026-10-11 面向单标段编制的解析数据与下游接口改造(进行中,未提交,未接完)

本节是留给新会话的续接说明。**工作未完成,未经用户明确要求不要提交、不要重启服务、不要执行业务库迁移。**

#### 目标与已确定原则

用户要求把解析结果从"只给用户看"升级为"给后续生产流程用":解析阶段直接产出可复用的业务数据,并为大纲、正文、检查三种用途提供取数接口。真正的大纲生成、正文生成、投标文件检查留到后续实施,本轮只做数据契约、持久化、解析接入、标段治理、下游接口和页面接入。

- 覆盖项目全部招标材料,保留公共要求和各标段要求;**每次编制只允许选择一个标段**。
- 多标段必须由用户显式选择目标标段,服务端同样强制校验,不能默认取第一个。
- 继续沿用现有 13 个 DeepAgents 解析模块、检索、证据校验与运行护栏。
- Agent 直接提交业务数据,展示字段由程序生成,避免报告结束后再来一轮模型转换。
- 缺口默认返回"适用且已核实的数据 + 明确未解决事项",不增加整份报告人工批准的发布环节。
- 仅确定性合并内容、范围、条件都等价的记录;不同标段、主体、起算点和例外分别保留。

#### 数据模型与持久化

- 新增版本化 `AnalysisDataset`(数据版本 `DATA_VERSION = "1"`),包含 `lots / facts / requirements / format_nodes / relations / coverage / gaps`,业务结构定义在 `apps/api/src/tender/application/analysis_data.py`。
- 现有 `field / values / citations` 保留为展示投影,页面只接收投影和记录身份(`display_items` 去掉 `business` 内部属性)。
- 业务约定:范围分 `common / lots / unknown`,一条要求可适用多个标段但一次只取一个;条件保留比较符、数量、金额、单位、时间范围、起算点、且/或及例外,无法可靠拆解时保留原文并标 `structuring=partial`,不推测数值;评分项保留完整档次、分值、扣分和公式;原文支持性、结构化完整性、有效状态分开记录。
- 编号由服务端按"命名空间 + 稳定 key"生成(`record_identity`),分批修正沿用同一编号,下游用 `snapshot_id + record_id` 固定依据。
- 持久化沿用既有 PostgreSQL,新增迁移 `apps/api/alembic/versions/0011_analysis_data.py`:给 `analysis_module` 加 `business_data JSONB`、给 `analysis_report` 加 `derived_lot_ids BIGINT[]`,并新增不可变表 `analysis_data_snapshot`(report_id、revision、schema_version、manifest_hash、input_snapshot、data,唯一约束 report_id+revision 与 report_id+manifest_hash)。
- 快照发布在 `apps/api/src/tender/application/analysis_data_store.py`:`publish_data_snapshot` 在报告终态后按 manifest 指纹幂等发布(相同指纹不重复建 revision),`accessible_data` 在读取时按实时资料权限过滤,依据被撤销时返回 `source_unavailable` 并降为 `unavailable`。

#### 解析流程接入

- `deep_analysis.py`:运行时版本提升为 `deepagents-0.7.22-v3`,新增 `DATA_CONTRACT`,`build_module_agent` 在快照带业务数据版本时启用 `submit_business` 工具(提交 `records / coverage / gaps / research_summary`),旧快照继续走 `fields / outline_nodes` 老协议。
- `analysis_skills.py`:`skill_snapshot` 现在同时加载 `*.md` 和 `*.json`;支持性校验请求新增 `business` 语义载荷,要求标段、比较符、单位、分值、例外等结构化属性与展示文字一样被原文证据支持。
- `analysis_policy.py`:`load_module_skill` 追加模块 `references/coverage.json` 主题清单;`select_verified_repeats` 对带 `business` 的条目不再做基于展示文字的重复证据替换。
- `agent_runtime.py` 与 `knowledge.py`:模块落库同时写 `business_data`;暂存投影用 `display_items`;同名字段合并(普通字段与大纲)跳过带 `business` 的记录,避免不同标段/条件的要求被当成重复项。
- 13 个解析 Skill 均已改造成业务数据协议,每个 Skill 新增 `references/coverage.json`,定义必检主题;格式 Skill 改为用 `parent_key` 表达完整父子层级(不再按展示做三级截断)。
- 标段目录由项目概况模块提交(带证据),服务端在快照发布时创建或映射 `lot`,写入 `analysis_report.derived_lot_ids`;无法解析的指向进入 `unknown` 与缺口清单,不降级成公共要求。来源解析产生的标段目录不算"过期"触发条件(`get_report` 的 stale 判定已排除派生标段)。

#### 下游接口(已写,尚未接完)

- `GET /api/v1/analysis/reports/{report_id}/data`:返回最新或指定 `snapshot_id` 的正式数据快照(含标段目录、业务数据、覆盖与缺口、`readiness`),读取时执行实时权限过滤。
- `POST /api/v1/analysis/reports/{report_id}/context`:入参 `snapshot_id`、`purpose`(`outline / content / check`)、单个 `lot_id`、正文用途的 `requirement_ids`、`offset / limit`;返回该用途的适用范围数据、完整 `requirement_manifest`、分页 `next_offset`、未决 `unresolved` 和缺口。校验包括:多标段缺 `lot_id` 报 422、标段不属于快照报 422、正文要求必须属于同一快照与所选范围、报告未终态报 409、快照不是当前有效版本报 409、来源撤销报 409。正文用途会额外检索已授权企业和历史库参考片段,并再次校验关联。
- 前端:`AnalysisDataPanel.tsx` 已完成"编制依据与待核对事项"面板和"编制依据预览"抽屉(单选标段、实际调用 context 接口、分页加载),接入 `ProjectAnalysis.tsx`;`types/knowledge.ts` 已补数据类型。

#### 当前验证状态(必须如实转述)

- `apps/api` 下 `uv run pytest tests/unit/application/test_analysis_data.py -q` → **8 passed**(新增用例,覆盖多标段隔离、条件保真、完整清单分页、结构证据等)。
- `uv run pytest tests/unit tests/contract -q --tb=short` → **2 failed / 535 passed / 7 skipped**。失败项:
  1. `tests/unit/application/test_analysis_guards.py::test_project_skills_have_loadable_references_and_distinct_domain_rules`:断言格式 Skill 文本包含 `parent_id`,而改造后 Skill 已改用 `parent_key`(属测试与实现口径不一致,需确认是改测试还是补 Skill 说明)。
  2. `tests/contract/test_api_routes_match_docs.py::test_implemented_routes_are_documented_or_explained`:新增的 `GET .../data` 与 `POST .../context` 未登记进 `docs/设计/05-后端API设计.md` 冻结清单,也未写入测试里的 `_UNDOCUMENTED`。
- 迁移验证工具 `tests/integration/data_schema.py` 可在测试私有表上安装 0011(把 `ADD COLUMN` 改写为 `IF NOT EXISTS`、把建表改为 TEMP TABLE),不需要先升级业务库。
- 隔离数据库集成测试、Ruff、import-linter、前端 typecheck/test/build 与桌面交互回归**本轮尚未执行**。

#### 下一步(按建议顺序)

1. 修掉上面 2 项测试失败:确认 `parent_id` 口径(改测试或补 Skill 说明),把两个新接口补进 `docs/设计/05-后端API设计.md` 清单(或写进 `_UNDOCUMENTED` 并注明原因)。
2. 补跑 `tests/integration`(需要 `TENDER_RUN_DB_TESTS=1` 与隔离 schema)、`ruff check src/tender/`、`lint-imports`。
3. 前端 `apps/web` 执行 pnpm 类型检查、测试、构建与交互回归,验证 `AnalysisDataPanel` 的标段单选、分页加载和原文定位。
4. 补文档:API、DDL、运行说明与交接记录(至少 05、14、17 三处)。
5. 业务库执行 `alembic upgrade head` 到 `0011_analysis_data`、重启 API/worker、新建分析报告验证真实链路。这一步属于现场变更,需用户明确同意后再做。
6. 用人工核对样本检查解析质量:至少覆盖多标段、公共条款、补遗和证明材料;跨标段误混、无证据却标为已核实、转引占位通过都算验收失败。

#### 未提交改动清单(本轮新增/修改)

新增:`apps/api/alembic/versions/0011_analysis_data.py`、`apps/api/src/tender/application/analysis_data.py`、`apps/api/src/tender/application/analysis_data_store.py`、`apps/api/tests/integration/data_schema.py`、`apps/api/tests/unit/application/test_analysis_data.py`、`apps/web/src/components/knowledge/AnalysisDataPanel.tsx`、13 个 `references/coverage.json`。

修改(主要):`api/knowledge.py`、`application/agent_runtime.py`、`application/analysis_policy.py`、`application/analysis_skills.py`、`application/deep_analysis.py`、`application/knowledge.py`、`worker/deep_analysis.py`、13 个 Skill 目录下的 SKILL/输出清单/示例,`tests/integration/test_deepagents_runtime.py`、`tests/integration/test_knowledge_flow.py`、`apps/web/src/components/knowledge/ProjectAnalysis.tsx`、`apps/web/src/types/knowledge.ts`。数量级为 63 个文件、约 +956/-377。

#### 环境与服务现场

- 业务库当前迁移版本为 `0010_analysis_guards`,checkpoint 四表已存在;`0011_analysis_data` **尚未在业务库执行**。
- API/worker 未重启,仍运行已提交的旧代码;新 Skill 与业务数据协议只对新发起的分析生效,已有报告保持只读展示,不会自动回填业务数据。
- 本轮只跑了单元/契约测试与 `test_analysis_data.py`,未调用真实供应商、未修改业务数据、未重启服务、未推送、未提交。

### 2026-10-11 单标段数据改造续接：代码与隔离验证完成，待现场启用

本节覆盖上节的“未接完、两项失败、前端未验证”状态。用户要求读取交接后继续，本轮使用
`karpathy-guidelines`，没有启动子代理，没有提交或推送。仍只实现业务数据、持久化、标段治理和三种取数用途；
真正的大纲生成、正文生成与投标文件检查不属于本阶段。

#### 本轮接完与修复

- 格式 Skill 的测试口径改为模型输入 `parent_key`，最终 `parent_id` 仍由服务端生成；两个新接口正式登记到 API 文档。
- 展示投影携带 `record_id` 和适用范围说明，读报告时仍保留不同标段的同名要求；暂存条目中的内部 `business` 不泄露到页面。修正版本来源校验失败时保留上一版已核实成果。
- 业务记录按稳定身份和业务语义计算纠错额度，不同标段不串账；已核实的范围/条件修正算作进展，仅改标题不算。
- 主题覆盖按标段核对，A标段已提取不能代替B标段；具体标段的记录不能证明公共覆盖。不适用结论保存校验器最终证据并在读取时重新检查权限。
- 修订关系不能作用到端点不适用的标段；关系端点文字变化、父节点未通过等情况保留缺口。范围未知不会混入适用要求。
- 标段目录未核对完整、已有项目标段在解析目录中缺失，或存在未解决的分标指向时，不自动选择唯一已识别标段。普通“适用性待确认”仍与公共可用数据一起返回，避免所有缺口都阻断项目级草稿。
- 正式快照读取同时检查输入来源，撤销来源即使只被缺口说明引用也会隐藏内容；正文参考检索结束后再次检查报告状态、快照与来源，防止等待期间的撤销绕过校验。
- 指定历史快照仍可查看，但 `stale=true`；正在补跑的报告也不能提供新编制上下文。新增真实HTTP测试覆盖跨报告快照、分页清单、来源撤销和参考片段分离。
- 前端补齐业务类型，预览显示项目事实、适用要求和未决事项；切换标段/报告丢弃旧请求。原文入口复用 `resolveCitation` 权限校验。
- 把数据面板放入结果滚动区，修复展开长清单后窄屏原文区高度被挤为零的问题；保留桌面与移动端PDF定位。
- 补齐 `docs/设计/05-后端API设计.md`、`docs/设计/14-知识库与综合分析实现.md`、`docs/工程/14-解析Skill与运行护栏.md`、`docs/工程/17-数据库迁移.md`，并把0011加入DDL契约映射。
- 更正迁移文档的离线SQL说明：实际输出包含 `alembic_version` 更新；增量审阅可显式指定 `0010_analysis_guards:0011_analysis_data`。

#### 最终验证结果

- `apps/api`：`TENDER_RUN_DB_TESTS=1`、`PYTHONUTF8=1`，`uv run pytest tests/unit tests/contract tests/integration -q --tb=short` → **604 passed / 8 skipped**。数据库用隔离schema或临时表，模型为测试替身。
- 新增 `tests/integration/test_analysis_data_flow.py`：8项真实PostgreSQL与HTTP验证；真实DeepAgents集成用例同时断言业务属性送审、精选证据落库和报告终态发布快照。
- Ruff检查本轮源码、测试和0011迁移通过；`lint-imports` → **5 kept / 0 broken**；`git diff --check` 通过。
- 前端 `pnpm --dir apps/web typecheck`、`pnpm --dir apps/web test`（**12文件 / 77项**）、`pnpm --dir apps/web build` 全部通过。最后一次生产构建包含本轮最终布局与类型变更。
- 新增 `apps/web/e2e/analysis-data.spec.ts`：**8项全部通过**（1440px桌面和390px窄屏）。覆盖多标段显式单选、102项要求完整分页、旧请求丢弃、报告切换、过期快照、目录缺口、引用权限校验及PDF canvas显示。
- 全部浏览器用例：一轮 **35 passed / 1 failed**，失败是既有模型保存重试用例的按钮等待超时；原样单独复跑 **1 passed**。不要写成“36项一次全绿”。该用例对应的产品代码未改。
- 浏览器接口全部拦截，PDF使用仓库样本；没有执行真实新增、删除或模型请求。上述通过不等于真实模型解析质量通过。
- 最终桌面/窄屏截图均已人工查看：`.tmp/analysis-data-browser/analysis-data-多标段必须显式单选，分页完整加载，原文入口先校验引用-desktop/analysis-preview.png` 及同名 `-mobile` 目录。
- 离线SQL已渲染：`.tmp/analysis-data-migration.sql` 为整条链，`.tmp/analysis-data-0011.sql` 为0010→0011增量；两者都未执行到业务库。

#### 现场与下一步

- 只读检查 `alembic current` → **0010_analysis_guards**，`alembic heads` → **0011_analysis_data (head)**；业务库尚未应用0011。
- 本轮没有启动或重启API/worker，没有调用真实供应商，没有新建真实分析报告。测试所用前端已关闭，服务端口应在下次操作前重新确认。
- 首次Turbopack开发服务启动超过Playwright的120秒等待；验证改用 `pnpm exec next dev --webpack -p 4400`，默认项目配置未改。生产Turbopack构建通过。
- 需要用户单独同意现场变更后，再按迁移文档备份、`alembic upgrade head`、启用API/worker，并新建报告验证真实链路。旧报告不回填、旧版本检查点不能手工改号恢复。
- 真实质量验收尚待进行：至少核对多标段、公共条款、补遗、证明材料和评分档次；不能把模型替身测试替代人工核对。
- 所有代码与文档仍未提交。后续如用户明确要求提交，提交信息使用中文，不添加作者，不自动推送。

### 2026-10-11 修复代码审查发现的四处业务数据问题

用户要求修复未提交变更的审查问题，本轮沿用 `karpathy-guidelines`，没有启动子代理。

- **取消补跑后的旧快照**：发布和取数共用 `snapshot_manifest`，读取时核对当前运行账和模块业务数据。报告取消但模块尚未退出、或新快照尚未发布时，旧快照仍为 `stale=true`，编制取数返回409。最新 attempt 的 pending 也阻止发布；已被后续补跑替代的历史 pending 不永久堵住发布。
- **格式树部分回退**：新增累计结构检查，校验循环、缺失祖先和已核实父路径是否变化；最终提交发现问题时反馈模型修正。失败/取消时仍保留节点，但无效节点及其后代降为效力未知，放入 `unresolved / gaps`，不混入下游可用格式树。
- **多标段不适用证明**：证明 key 区分主题和范围，汇总按 `review_id` 查询证明；旧检查点中重复 key 的证明也都保留，各标段不会互相覆盖。
- **缺口无法清除**：分批 `final=false` 按 key 累积缺口，`final=true` 提交完整剩余清单，原文和结构校验通过后替换；全部解决时用 `gaps=[]`，最终校验失败不会清空旧缺口。运行时契约、13个模块的SKILL和输出清单、API及设计/运行文档均已同步。
- 新增11项回归，修复前新增的首批9项均失败复现；修复后全套 `PYTHONUTF8=1`、`TENDER_RUN_DB_TESTS=1`，`uv run pytest tests/unit tests/contract tests/integration -q --tb=short` → **615 passed / 8 skipped**。Ruff检查本轮源码与测试通过，`lint-imports` → **5 kept / 0 broken**，`git diff --check`通过。
- 测试使用临时表/隔离schema和模型替身，未修改业务数据、未调用真实供应商。未改前端，本轮未重跑前端检查；前轮验证结果保留。
- 未执行迁移、未启动或重启服务、未提交或推送。现场启用仍按上一节约定处理。

### 2026-10-11 按用户要求提交单标段业务数据改造

- 用户明确要求「提交代码」，本次提交包含当前业务数据契约、0011迁移、13个解析模块协议、快照发布与单标段取数接口、前端编制依据预览、测试及文档，以及上述四处审查问题修复。
- 提交信息：`实现单标段编制业务数据与快照取数并修复审查问题`，不附加作者说明，不推送。
- 使用上一轮已通过的验证结果：后端615 passed / 8 skipped，Ruff和5项依赖分层检查通过；提交前再次检查差异空白。
- 此次提交不执行数据库迁移或启用服务；真实供应商、新业务报告与解析质量验收仍待现场阶段完成。

### 2026-10-11 放宽分析输出预算并清查配置限制

- 用户要求解除 `analysis.max_output_tokens` 的 512–16384 限制，改为最小值 1、无最大值，并统一列出其他配置限制及修改建议。
- 已使用 UTF-8 读取交接文件并应用 `karpathy-guidelines`，没有启动子代理。
- 配置中心 `analysis.max_output_tokens` 现允许整数 ≥1，无人工最大值；补跑接口同名参数同步将下限从 512 改为 1。默认值仍为 8192；运行时仍取分析额度与模型自身 `max_tokens` 的较小值，供应商能力约束仍有效。
- 新增 `docs/工程/18-配置限制清单.md`，逐项覆盖配置中心全部 38 项，并列出补跑、模型/供应商、功能预算、协议参数、发布门禁的实际限制与建议。其余配置只清查、未改行为。
- 特别发现：补跑超时实际允许 0–3600，配置中心为 60–7200；两份设计文档原写 300–3600，本次改为实际范围。多项轮询、解析、预处理及抽取开关没有接入执行逻辑；解析页码和输出格式实际固定；模型 `max_tokens` 仍有 100000 的人工上限，Responses 适配器下限为 16。详情以新清单为准。
- 验证：配置单测、补跑输入单测、配置契约、模型路由单测共 **83 passed**；隔离数据库补跑集成验证 **3 passed / 9 deselected**，确认 262144 的新预算完整保存、旧 attempt 与报告快照保留。Ruff 与 `git diff --check` 通过；清单覆盖脚本确认 38 项无遗漏。
- 测试使用隔离数据库 schema 与模型替身，没有调用真实供应商，没有执行业务库迁移、启动或重启服务、提交或推送。代码生效需后续重载相关服务；既有 attempt 的预算仍冻结，补跑才取当前配置。


### 2026-10-11 统一配置范围来源并接通必要执行逻辑

用户授权按清单建议修改，随后明确：必要流程改造保留，质疑的是改范围必须修改太多文件。本轮继续采用 karpathy-guidelines，没有启动子代理，没有提交或推送。

- 配置中心范围/枚举统一由 `config/schema.py::value_rules` 定义，补跑请求复用 field_bounds；`/config/items` 返回 minimum/maximum/choices/readonly_reason，前端直接消费元数据。模型管理范围统一由 `model_profiles.py` 的 MODEL_FIELDS/FEATURE_FIELDS/协议参数声明定义，创建/修改/绑定 API 与 `/llm/settings` 共用。后续改人工范围不再需要同步修改表单或执行代码。
- 分析预算统一为整数 ≥1、无人工最大值；子代理恢复次数 ≥0。新增 `analysis.max_evidence_blocks`（默认160），共39项。模型输出、top_k/top_n、超时、额外重试、功能总请求和总时限移除人工最大值；模型超时允许有限小数。保留协议范围、比例0–1、最多10个候选和单嵌入/重排绑定等语义约束。其他并发 ≥0，0暂停新派发；重试 ≥0，0不重试。
- 未接入或协议固定的13项配置标为只读，并显示原因；写入侧同样拒绝。解析档位/OCR在任务省略参数时使用当前活动配置，显式参数覆盖；最终有效值冻结到任务快照。上传默认选项省略对应multipart字段。
- 必要执行接线保留：beat每秒唤醒并按配置节流；轮询初始/最大间隔及指数退避、次数预算、转换/解析累计时限、转换额外重试参与真实执行。job.progress持久保存首启时间与轮询次数，网络重试/服务重启/恢复不重置；转换适配器耗尽重试后不再由外层无限倍增。转换锁异步等待受总时限控制；解析提交超时按受理未知处理。轮询网络错误也使用配置退避，并消耗已持久记账的次数。
- 递归步数随模型/工具预算推导；压缩触发值至少1，避免context_tokens=1在构图时被零触发值拒绝。已有运行账与快照不回写。
- 新增0012_config_limits迁移，down_revision为0011；放宽旧数据库CHECK并登记证据块配置。DDL与种子契约、迁移文档、API/运行说明均同步。`docs/工程/18-配置限制清单.md` 已改为实施后39项，覆盖检查无遗漏。

验证结果：

- 后端最终全套 `PYTHONUTF8=1`、`TENDER_RUN_DB_TESTS=1`，`uv run pytest tests/unit tests/contract tests/integration -q --tb=short` → **673 passed / 9 skipped**。使用隔离schema/临时表与模型/网络替身。新配置集成覆盖6项，包括真实落库、默认值快照、持久次数/首启时间、网络重试及超时；适配器新增0额外重试只发1次转换请求的测试。
- Ruff检查全部本轮修改Python源码、测试与0012通过；`lint-imports` → **5 kept / 0 broken**；`git diff --check`通过。额外冒烟确认context_tokens=1的真实DeepAgents图可构造，不代表如此小的上下文能完成业务分析。
- 前端typecheck、test（**12文件 / 79项**）和最终build通过。
- 浏览器 `pnpm exec playwright test e2e/interactions.spec.ts` → **36 passed**（1440px桌面/390px窄屏），含新增8项配置/模型/功能大预算与上传默认值回归。首批新增测试曾因错误的标签页选择器和未切换L2页而失败，修正测试后全部通过；没有因此放宽产品校验。浏览器接口全部拦截，不写业务库、不调用真实模型。复用了当时已监听localhost:4400的前端测试服务，未重启API/worker/beat。
- 0011→0012离线SQL已生成于 `.tmp/config-limits-0012.sql`，未执行。只读检查业务库仍为 **0010_analysis_guards**，代码head为 **0012_config_limits**。

现场启用仍按既有交接约定另行授权：备份后升级至0012（当前起点会先执行0011），再启用API/worker/beat和新版前端。未迁移业务库、未调用真实供应商、未提交或推送。新配置范围只有重载对应进程后生效；分析预算在新建/补跑时冻结。

### 2026-10-12 配置入口、功能绑定及任务取消/补跑修复

用户报告：配置中心打不开，模型配置应集中在模型管理，功能绑定需要反映真实执行功能、优化排序，取消任务返回 internal_error、正在执行任务无法取消且无法指定模块重新解析。沿用 karpathy-guidelines；没有启动子代理，没有提交或推送。

#### 已定位与修改

- 配置中心实际返回404，后端配置项/版本接口正常；旧 `.next/dev` 中发现损坏的路由类型文件，以及混用的 Turbopack/webpack 资源。已停止前端并把旧缓存移至 `.tmp/next-dev-damaged-20261012`，重新生成后恢复。`pnpm dev` 与 Playwright 启动统一使用 webpack，生产构建仍为 Turbopack；本地启动指南已同步。
- 抽出共用的 `ConfigWorkspace`，将 `analysis.*`、`llm_aided.*`、`extract.max_inflight`、`extract.strategy.*` 放入「模型管理 → 分析参数」。配置键、范围元数据、保存/门禁和全局版本链保持一致；页面明确提示发布/回滚影响整个版本。刷新错误状态可恢复，正常刷新保留编辑草稿。
- 功能清单按代码消费者排序并提供中文说明：专题解析（含13模块、校验、压缩、补跑）、知识问答、向量索引/检索、重排、文件字段抽取、字段复抽/重跑。描述来自代码而非过期数据库种子。图片生成仍可在模型列表测试，但无业务消费者，`binding_available=false`，新增绑定/预算修改返回409，只允许清理旧绑定。嵌入/重排的语言路由预算在页面禁用。
- 优先级改为选择完整顺位，支持上移/下移/置顶/置底；仍按有序 model_ids 原子提交，保留每个功能的草稿和 revision 校验。顺位最多10项关闭虚拟列表；窄屏候选上限改为独立一行，避免标签竖排。
- `cancel_report` 用报告行锁与领取任务串行，立即取消未持有执行锁的排队/遗留运行；有执行者的模块由现有心跳中断、收尾并释放配额。报告详情与取消响应增加 `canceling`。补跑在旧控制器或模块仍持锁时返回409 `cancellation_pending`，避免旧 finally 改写新 attempt。取消幂等，保留已完成模块和历史运行记录。
- 前端在取消退出期间继续轮询并禁用补跑；失败响应后也刷新真实状态。已取消模块现在显示「补跑本模块」。取消发生在模块创建之前也能重新进入 waiting。选定模块补跑不触碰未选中的模块，已完成模块重解析仍从零开始。
- API、模型路由、配置限制清单与本地启动文档已更新。

#### 验证

- 后端最终：`PYTHONUTF8=1`、`TENDER_RUN_DB_TESTS=1`，`uv run pytest tests/unit tests/contract tests/integration -q --tb=short` → **679 passed / 9 skipped**。新增6项取消/快照回归，更新旧快照测试以分别覆盖“执行者仍退出”和“无执行者立即终止”，并保留旧快照不能重新生效的检查。测试使用隔离schema/临时表、模型替身，不写业务数据或调用真实模型。
- Ruff检查本轮改动与测试通过，`lint-imports` **5 kept / 0 broken**，`git diff --check`通过。
- 前端最终typecheck、单测 **12文件 / 79项**、生产build通过。生产构建明确包含 `/settings/config`、`/settings/models`。
- 浏览器完整 `e2e/interactions.spec.ts` **40 passed**（桌面1440与窄屏390），之后只调整候选预算的窄屏排版，对配置/排序/取消的6项关键交互再次全部通过。首次浏览器轮次受旧缓存、标签可访问名称变化与虚拟下拉选择器影响失败，已修正并完整重验，不能引用旧失败轮次作为最终结果。
- 真实配置页面读取正常；真实模型/分析参数页面1440与390检查无JS异常/无整页横向溢出，截图 `.tmp/settings-parameters-{1440,390}.png`、`.tmp/settings-bindings-{1440,390}.png`，窄屏绑定截图已人工查看。真实页面所用API仍是旧进程，因此新功能名称/说明需后端重载才显示。

#### 现场状态与剩余一步（尚未授权执行）

- 只读确认业务库仍为 **0010_analysis_guards**，代码head为 **0012_config_limits**。API日志明确记录缺少 `analysis_data_snapshot` 表；0011还缺 `analysis_module.business_data`、`analysis_report.derived_lot_ids`。这是当前业务环境取消后报错与分析数据读取失败的必要修复，不能仅靠重载前端解决。
- API/worker/beat仍是原进程，本轮尚未重启后端或迁移业务库。`scripts/start-backend.ps1 -Status` 最后显示API登记pid17420/监听子进程21552，worker28664，beat13660；执行前务必重新核验。
- 前端最终build后已用 `PORT=4400`、`API_PROXY_TARGET=http://127.0.0.1:8300`、`pnpm --dir apps/web dev` 恢复运行，使用webpack。
- 已从EDB官方获取PostgreSQL18.3便携客户端（可连接现场18.6），提取到 `.tmp/postgresql-client`。只读备份脚本 `.tmp/backup-before-settings-fix.py` 不包含密码，也不执行迁移；凭据仅从项目环境读取到子进程环境变量。
- 最新完整备份 `.tmp/backups/20261012-194832-before-0012.dump`（25,556,688 bytes），已用pg_restore目录校验确认关键表存在；同名 `.toc.txt` 为目录清单。只校验归档目录，未进行整库恢复演练。
- 增量SQL `.tmp/settings-fix-0010-to-0012.sql` 已渲染、尚未执行。0011增加业务数据列与快照表，0012放宽模型/功能预算约束并登记证据块预算。
- 已通过异步问题请用户确认“升级0010→0012并重启API/worker/beat、复核取消和补跑接口”，原因是此前交接明确要求现场启用另行授权。**确认尚未收到时不得执行迁移/后端启停。** 不自动发起新的真实模型解析，不自动提交。
- 获得确认后：重查运行任务和服务状态 → 停止后端 → 必要时再做新备份 → `uv run alembic upgrade head` → 通过原脚本启用后端 → 核验版本/接口，并对用户已取消但模块遗留running的报告执行幂等取消修复。新建或指定模块真实解析如需触发，依用户授权处理。


#### 2026-10-12 修复审查发现的两处回归

- 版本探测改为复用转换重试预算:上游启动时 `/version` 瞬时 503 会按同一退避额度重试,耗尽后才把可重试错误交给任务层;不再第一次探测失败就结束文件任务。
- 报告在模块尚未创建前被取消后补跑时,本次配置中心的预算和显式 `max_output_tokens` / `timeout_seconds` 会写回 `analysis_report.runtime_settings`,供 `prepare_report` 延迟创建首个运行账使用;已有模块时仍不改写报告旧快照。
- 新增适配器瞬时版本失败回归、模块创建前补跑预算继承集成回归。后端全套 `uv run pytest tests/unit tests/contract tests/integration -q --tb=short` → **681 passed / 9 skipped**;Ruff、`lint-imports` 5 kept / 0 broken、`git diff --check` 通过。
- 仍然是隔离 schema/临时表与测试替身,没有执行现场迁移、重启服务、真实模型调用、提交或推送。


#### 2026-10-12 修复分析卡死:僵尸运行饿死整份报告（已现场迁移并重启）

现场现象:报告 #16 一直停在「分析中」,13 个模块 0 完成,首个模块的计数冻结在模型请求 19/80、工具调用 26/100。

根因（数据库、检查点与 `pg_locks` 三方证据确证）:

- 业务库仍是 `0010_analysis_guards`,缺 `analysis_module.business_data`、`analysis_report.derived_lot_ids` 与 `analysis_data_snapshot` 表,而运行中的代码（`deepagents-0.7.22-v3`）已依赖它们。
- 模块运行 #930（project_basic_info_parsing）跑完检索、提交并通过校验,在 `AgentRuntime.save()` 发布已核实成果时因缺列报 `UndefinedColumn`;图节点异常退出,心跳随之停止（租约停在最后一次心跳 +45s）。
- 异常收尾走 `AgentRuntime.finish()`,但其中 `UPDATE analysis_module` 同样引用 `business_data`,报同一个错,把同一事务里的「运行终态」一并回滚——于是留下租约早已过期却永远 `status='running'` 的僵尸运行;LangGraph 检查点的 `pending_writes` 里至今留着这条 ProgrammingError。
- `claim()` 先选「本报告最靠前的、尚未持锁的运行」作为 first,僵尸 #930 虽然不持有配额锁却仍占着这个名次,同报告其余 12 个模块每次抢槽都被 `first != self` 拒绝;报告租约由仍活着的控制器每秒续期,`dispatch_knowledge` 不满足重派条件,而 `requeue_unlocked_runs` 只在控制器启动时执行一次——三重叠加成永久卡死。
- 同类僵尸在报告 11（run 807）、13（853）、14（904）、15（917）同样存在,是固定通路而非偶发:任何模块级异常都可能把整份报告卡死。

代码修复:

- `application/agent_runtime.py`:`finish()` 改为先用 `SELECT ... FOR UPDATE` 校验运行归属,成果发布移入 `begin_nested()` savepoint——缺列只回滚成果,运行与模块的失败终态照常提交,模块状态降为 `failed` 并写明「模块成果发布失败: ...」,另记 `publish_failed` 事件;新增 `_publish()` 承载成果与关系写入。
- 同文件 `claim()`:取 first 之前先收殓「租约已过期且无人持有配额锁」的僵尸运行,降级为 `pending` 交回争抢,既解除饿死也让僵尸模块自身能被重新领取。
- 新增 `application/schema_guard.py`:探测分析链路强依赖的列与表;`worker/knowledge.py` 的 `_analyze_project` 在版本校验之后、模型预算之前核对,缺对象立刻失败并写明「请先执行数据库迁移」,不再跑到发布成果那一步才炸。
- 新增两项集成回归:`test_stale_run_without_holder_returns_to_queue`、`test_publish_failure_still_records_terminal_run_state`。

现场变更（已获用户明确授权「按你的建议做,也能执行数据库迁移」）:

- 停止 API/worker/beat（原 pid 31408/5160/8732）;停止前确认无在跑任务、无残留 advisory 锁。
- 新备份 `.tmp/backups/20261012-233511-before-0012.dump`（26,191,873 bytes）,`pg_restore --list` 目录校验含关键表。
- `alembic upgrade head`:`0010_analysis_guards` → `0012_config_limits (head)`;迁移后 `missing_schema` 返回空列表。
- 收殓报告 11/13/14/15 上遗留的 running 运行（脚本复用 `cancel_unlocked_runs`,幂等,收殓后均为 0）;报告 16 保留原状交由调度自愈。
- 按 `scripts/start-backend.ps1` 重启三个进程（api 33300 / worker 32216 / beat 24772）,`/api/v1/healthz` 返回 `{"status":"ok"}`。

验证:

- 后端 `PYTHONUTF8=1 TENDER_RUN_DB_TESTS=1 .venv/Scripts/python.exe -m pytest tests/unit tests/contract tests/integration -q` → **683 passed / 9 skipped**;Ruff 检查本轮改动与测试通过,`lint-imports` **5 kept / 0 broken**,`git diff --check` 通过。
- 重启后报告 16 自动恢复:僵尸 #930 被收殓,模块 814 以「模块总时长预算已耗尽,恢复不会重置时限」明确失败并落终态;模块 815 正常开始并持续产生 model/tool 事件,模块 816 起排队——原先被饿死的位置已经打通。
- 待办:报告 16 的模块 814 需在界面用「补跑本模块」重跑,其余 12 个模块会依次执行完。

未做:未提交、未推送,未改动前端。

### 2026-10-13 ORM 落地第一步：模型与会话工厂（用户明确要求数据访问走 ORM）

背景：用户指出「我要求用 orm，这才是正确的工程设计，当前做法是不正确的」。核对结论：docs/工程/10 §3.6 本来就写明「SQLAlchemy 2.0 typed declarative + `Mapped[...]`」，§4.2 的目录约定也有 `adapters/pg/{session.py, models/, repositories/}`，但代码一直只有 Core 的 `text()` 直查——属实现欠账，不是设计分歧。本轮补齐地基；迁移体系不动（事实源仍是 设计文档 → 迁移 `_STATEMENTS` → 契约测试）。

本轮新增/修改：

- 新增 `adapters/pg/models/`：41 张业务表（483 列）的 typed declarative 模型，按域拆成 documents / projects / extraction / configs / jobs / llm / knowledge / analysis 八个模块。刻意不复制默认值、索引、约束、外键行级行为，也不声明 `relationship()`——理由写在 `models/base.py`：第二事实源必然漂移；写入时未赋值的列不进 INSERT，由数据库默认值补齐；仓储层写显式 join。
- 新增 `adapters/pg/session.py`：`create_pg_engine()`（全项目唯一引擎构造入口，默认 `pool_pre_ping=True`）、`create_session_factory()`、`pg_session()` 上下文管理器。
- 新增契约测试 `tests/contract/test_orm_models_match_ddl.py`：模型的表名/列名/可空性/类型与全部迁移顺序执行后的库逐一比对（43 个断言）；解析器失效会显式失败而不是静默空转。
- 引擎入口收口：`core/di.py` 与 6 个 worker（dispatch / regression / knowledge / extraction / exports / tasks）的 `create_engine(settings.database_url(), pool_pre_ping=True)` 全部替换为 `create_pg_engine()`（行为等价）；regression.py 不再需要 settings 导入。`agent_runtime.py` 的 NullPool 锁引擎未动：application 不能 import adapters（分层契约「application 与 adapters 互不引用」），要等装配点传参或仓储化（阶段 2）。

验证（离线）：`PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/unit tests/contract -q` → **654 passed / 9 skipped**；ruff 通过；`lint-imports` **5 kept / 0 broken**。

阶段 2/3 待办：

- ports 增加仓储 Protocol，`adapters/pg/repositories/` 提供实现，application 改为经 Protocol 取数（这是让 application 用上 ORM 的唯一合法通道）。
- 逐个替换 `text()` 调用点（大头：api/llm.py 55、worker/tasks.py 42、agent_runtime.py 35、worker/extraction.py 34、api/knowledge.py 33）。
- LATERAL / DISTINCT ON / 咨询锁 / 部分索引等复杂查询保留 SQL 形态，但同样收进 repositories。
- Alembic 是否切 autogenerate：现状是手写 SQL 逐字对应设计文档 + 契约测试守卫，默认不改，等用户决定。

现场状态提醒（2026-10-13 已恢复）：数据库/Redis 主机 172.29.199.222 的网络中断已由用户恢复（5432/6379 连通，延迟 0.00s），后端三进程按 `start-backend.ps1` 重启（api 14004 / worker 24896 / beat 8464），`/api/v1/healthz` 返回 `{"status":"ok"}`，worker/beat 日志不再有 ConnectionError。

恢复后报告 #16 的进展（全部由调度自愈，未人工干预）：

- 模块 816（run 932）被新版 `claim()` 收殓后重新领取，因 `deadline_at` 在 10-12 16:36 已耗尽、恢复不重置时限，立即失败并落终态（这与 814 同因，「模块总时长预算已耗尽」）。
- 模块 817（run 933）10:52:39 启动，10:52:59 失败：`Agent 模块运行失败回退不可用：ConnectError`——网络刚恢复头两分钟到模型服务（model_id 17）的连接不稳定，3 次调用全部 ConnectError。同一时间段 818 也出现过一次 ConnectError（10:53:44），随后恢复正常，可见是恢复期的瞬时抖动。
- 模块 818（run 934）10:52:59 起正常运行，模型/工具调用持续增长。
- 其余 819–826 排队中。818 与 819–826 的 `deadline_at` 均为新设，不受中断影响。

当前失败待补跑：814、815、816、817（前三个是修复前后遗留的时限耗尽，817 是恢复期瞬时连接错误）。报告到终态后在界面「补跑本模块」逐个重跑；未完成模块也可用省略模块 key 的补跑入口一次性重排。

未做：未提交、未推送，未改动前端。

### 2026-10-13 ORM 落地第二、三步：端口/适配器分层与裸 SQL 收口

承上一节「ORM 落地第一步」的地基（模型 + 唯一引擎入口），本轮按用户选择的方案落地 **ports 协议 + adapters 仓储**，并把生产代码里的 `text()` 直查全部迁走。分层契约仍是 **5 kept / 0 broken**。

新增端口（只有 `typing.Protocol`，是形状文档 + 语义命名，不含 SQL）：

- `ports/repository/knowledge.py`：`KnowledgeStore`（业务库取数）与 `KnowledgeSession`（一次业务库事务；发布快照、领取配额这类多语句原子提交，事务边界属于实现细节）。新增 `complete_index` / `claim_dispatchable` / `start_report` / `requeue_unlocked_runs` / `ensure_modules` / `ensure_module_run` / `agent_run_store` 等。
- `ports/repository/agent_runtime.py`：`AgentRunStore`（一次 `agent_module_run` 的状态机入口：`claim/guard/heartbeat/reserve/record_call/save/finish/abandon/event/release`），把配额锁、fencing、`pg_locks` 挡在用例层之外。
- 删除已无使用者的 `ports/repository/configs.py`（`ConfigValues` 无引用；预算上限改由 `db.resolved_config()` 读）。

唯一实现 `adapters/pg/repositories/`：

- `knowledge.py`：`KnowledgeStore` 全量实现（读 + 写回短事务 + `KnowledgeSession`）。写回方法一律 ORM：`update(Model).values(...).returning(...)`、`insert(Model)`、`delete(Model).where(...)`、`select(...).with_for_update(skip_locked=True)`、`func.make_interval(0,0,0,0,0,0,secs)` 表达 `interval 'N seconds'`。`complete_index` 整批替换 `KnowledgeChunk`。
- `agent_runtime.py`：`AgentRunStore` 实现 + 模块级函数 `lock_project` / `try_lock_report_execution` / `execution_active` / `requeue_unlocked_runs` / `cancel_unlocked_runs`。文件头写明为何此处必须用裸 SQL。
- `locks.py`：全项目 advisory lock 唯一入口（`acquire_lock`/`try_acquire_lock`/`release_lock`/`acquire_xact_lock`/`try_acquire_xact_lock`/`acquire_xact_lock_id`）。字符串键走 `hashtextextended(:key,0)`，整数键走 `pg_advisory_xact_lock(:id)`，哈希空间不同不会误撞；其它层不再各自拼 SQL。

用例层/worker/API 迁移（改为只依赖端口或 `adapters/pg/locks.py`）：

- `application/agent_runtime.py` 由 507 行裸 SQL 重写为薄门面（`limits_snapshot` / `check_report_access` / `AgentRuntime`），持久化委托 `db.agent_run_store(...)`。
- `application/schema_guard.py`、`application/analysis_data_store.py` 改依赖端口。
- `worker/knowledge.py`、`worker/deep_analysis.py` 去掉全部 `sqlalchemy`/模型直接引用，改走 `db.*`；`worker/deep_analysis.py` 的 `prepare_report` 用 `with db.transaction() as session:` 编排。
- `api/knowledge.py`、`api/projects.py`、`api/project_files.py` 装配改指 `adapters.pg.repositories`；`api/knowledge.py` 的 advisory 锁改调 `lock_project`/`execution_active`/`try_lock_report_execution`。
- 第三阶段收尾：`api/common.py`（`rerun:` 事务锁）、`api/config.py`（3 处 `config-release:`）、`api/parsing.py`（`extract:`）、`worker/extraction.py`（`_advisory_lock` + `conflict:`）、`worker/exports.py`（`job:`）、`worker/tasks.py`（`_advisory_lock`）全部改用 `adapters/pg/locks.py`。
- 删除 `application/knowledge_store.py`：死代码（src 无引用），也是应用层最后一段裸 SQL；其 `encode`/`ensure_project_collection`/`sync_sources` 已在 `application/knowledge.py` 与 `adapters/pg/repositories/knowledge.py` 有归宿。

现状（本轮结束时）：

- **`api/` `worker/` `application/` 已无业务裸 SQL**。剩余 `text()` 只在 `adapters/pg/locks.py`、`adapters/pg/repositories/agent_runtime.py`（`pg_locks`/`advisory` 元数据查询）、`adapters/pg/repositories/knowledge.py`（`information_schema` 结构门禁）——ORM 表达不到的系统目录，属刻意保留区，两处文件头都有说明。
- 契约测试 `tests/contract/test_worker_sql_columns_exist.py` 原扫描 `worker/`，迁移后 worker 已无带别名 SQL 而自失败空转（`assert 0 > 0`）。已改为扫描 `worker/` + `adapters/pg/`（裸 SQL 允许落点）并兼容简化别名（`FROM 表 别名`，适配层风格），回归继续对新落点生效。
- 新增契约测试 `tests/contract/test_orm_models_match_ddl.py`（第一步引入）：模型表名/列名/可空性/类型与全部迁移顺序执行后的库逐一比对。

验证（离线）：`PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/unit tests/contract -q` → **654 passed / 9 skipped**；`ruff check src/tender/` → **All checks passed**；`lint-imports` → **5 kept / 0 broken**。全部相关模块可正常 import。

集成测试修复与「事务所有权」缺陷（用户要求「这里的也修复」后完成）：

- 三个集成测试改指新入口：`tests/integration/test_{deepagents_runtime,knowledge_flow,analysis_data_flow}.py` 的 `tender.application.knowledge_store` → `adapters.pg.repositories.knowledge`，`tender.application.provider_cooldown` → `adapters.pg.repositories.provider_cooldown`，`application.knowledge.encode` → 保留在 `application.knowledge`。新增 `tests/integration/store.py` 的 `SqlStore`（继承真实仓储，只补两个直连测试 schema 的 SQL 手柄 `rows()`/`execute()`），避免给生产仓储加逃生口。
- **发现并修复真实缺陷：`KnowledgeSession` 的事务没真正提交。** `Session(bind=外部连接)` 默认以 savepoint 加入连接里已开始的隐式事务，`session.commit()` 只释放 savepoint，连接回池时整笔事务被回滚——发布快照的写入一直在静默丢失（`test_deepagents_runtime` 读不到快照即此因）。现在 `KnowledgeSession.__enter__` 用 `in_transaction()` 区分：引擎给空闲连接就自己 `begin()` 并由本会话提交；引擎给的是已有事务的连接（集成测试共享同一连接）就只借道、绝不提交别人的事务；`Session(..., join_transaction_mode="rollback_only")` 让 Session 只负责 flush。连带 `worker/deep_analysis.py` 的 `prepare_report` 也恢复真实落库。
- `adapters/pg/repositories/knowledge.py` 新增 `_entity_columns()`：`Session.execute(select(模型)).mappings()` 的键是实体类名（`{'AnalysisReport': <obj>}`）而非列名，凡必须在事务里按列取行的出口都显式列出列，键名回到与 DDL 一致的口径。
- `AgentRunStore.claim()` 的 `UPDATE ... RETURNING *` 取不到跨表的 `module_key`，改为 `RETURNING id` 后再 join `analysis_module` 回读整行。
- `tests/contract/test_worker_sql_columns_exist.py` 的扫描面扩到 `worker/` + `adapters/pg/`（裸 SQL 允许落点），兼容 `FROM 表 别名` 的适配层写法。

验证（全量）：

- `PYTHONUTF8=1 TENDER_RUN_DB_TESTS=1 .venv/Scripts/python.exe -m pytest tests/integration -q` → **72 passed**（此前 3 个文件无法收集）。
- `tests/unit tests/contract -q` → **654 passed / 9 skipped**；`pytest tests/ --collect-only` → 735 collected，无 collection error。
- `lint-imports` → **5 kept / 0 broken**；`ruff check src/tender/ tests/` 仅余 4 处 `E501`，都在未改动的 `tests/unit/application/test_{deep_analysis,knowledge}.py` 既有长行，与本轮无关。

未做：未提交、未推送，未改动前端；**后端未重启**（用户要求推迟，后台 `start-backend.ps1` 进程仍在运行，不要重复启动）。报告 #16 的 814–817 仍待补跑。

### 2026-10-14 继续修复「进程还在运行，但不再调用模型」

用户要求继续排查并全程使用中文。本轮先读取最新交接，保留已有 ORM 改造及全部未提交变更；没有重复执行已记录的迁移，也没有使用旧 PID 判断当前服务。

确认并修复两处仍存在的漏洞：

- `worker/deep_analysis.py` 的控制器原本等所有模块结束才 `gather` 检查异常。模块在写失败终态或释放资源时再次抛错后，其协程已经退出，但遗留运行仍可能占据队首，其余模块永久等配额，报告控制器仍持续续租。现在用 `FIRST_EXCEPTION` 等待，并在续租前读取已结束任务的结果；未处理异常立即进入原有报告失败收尾、取消并等待其余模块退出。普通业务失败已成功记账时仍允许其余模块继续，报告按原规则形成部分完成。
- `worker/knowledge.py` 原本先通过 ORM 读取报告全列，再检查数据库结构。未迁移 `derived_lot_ids` 时，全列查询已经报错，结构门禁无法登记可读原因。现在先使用已有的权限/状态查询，仅对可执行报告核对结构，再读取完整报告并核对运行时版本；缺表缺列在模型调用前明确登记迁移提示。

验证：

- 新增 `tests/unit/worker/test_analysis_lifecycle.py`，使用真实控制器与模块执行协程、可控运行账替身，复现收尾异常后的永久等待；修复前两个等待用例均因外层 3 秒截止失败，修复后及时退出并确认其余任务释放资源。
- 共 10 项新增回归通过，覆盖失败终态写回异常、释放异常、普通失败不阻断后续模块、结构门禁前置、不可访问/已结束报告不改写，以及正常结构继续分析。
- `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/unit tests/contract -q --tb=short` → **664 passed / 9 skipped**。
- 本轮源码及测试 Ruff 通过；`lint-imports` → **5 kept / 0 broken**；`git diff --check` 通过（仅已有 CRLF→LF 提示）。运行护栏文档同步更新。

本轮现场状态与限制：

- `scripts/start-backend.ps1 -Status` 显示 API、worker、beat 均已停止，8300 无监听；这覆盖上一节「后台仍在运行」的旧记录。
- PostgreSQL 只读连接 8 秒超时；随后按现有配置对 PostgreSQL 与 Redis 做 3 秒 TCP 探测，两者均超时。没有读取到报告 #16 的当前状态，不能据历史交接断言它仍卡在原模块或已完成。
- 没有执行需要数据库的集成测试、重启后端、发起真实模型请求、迁移、提交或推送。真实恢复验收仍需依赖服务恢复后继续；此前用户推迟重启的要求保留。

### 2026-10-14 修复未提交改动审查发现的两处 ORM 回归

按用户要求修复本轮代码审查确认的问题，保留其余已有未提交更改：

- `adapters/pg/repositories/knowledge.py` 的 `collection_overview()` 改为 `.mappings()` 逐行转字典。`Connection.execute(select(Model, count))` 返回模型各列与计数拼成的扁平行，不是二元组；原实现有知识库数据就会解包失败。
- `worker/tasks.py` 的解析元素写入恢复为 `connection.execute(insert(Element), rows)`，让驱动按批执行。此前 `.values([...])` 把整批拼成单条 SQL，4096 个元素 × 16 列产生 65536 个参数，超过 PostgreSQL 的 65535 上限。父子元素映射及解析终态写回保持不变。
- 新增 `tests/unit/adapters/test_pg_knowledge.py`：通过真实 SQLite Connection 验证空列表、完整字段、文件计数、公司/软删除过滤及既有排序。
- 新增 `tests/unit/worker/test_parse_persistence.py`：运行真实轮询任务的持久化路径，隔离外部服务，实际写入 0、2、4096 个元素并验证父节点与终态。SQLite 测试连接的单语句变量上限设为 65535，用于离线复现参数超限，不替代真实 PostgreSQL 集成验证。

验证：

- 修复前新增测试 **2 failed / 3 passed**，失败项恰为有数据的知识库列表与 4096 元素写入；修复后 **5 passed**。
- `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/unit tests/contract -q --tb=short` → **669 passed / 9 skipped**。
- 源码及新增测试 Ruff 检查通过；新增测试格式检查通过；`lint-imports` **5 kept / 0 broken**；`git diff --check` 通过（仅既有 CRLF→LF 提示）。

本轮未连接真实数据库、未执行数据库集成测试、未重启服务、未迁移、未提交或推送。依赖服务及报告现场状态沿用上一节的待核验说明，没有新增现场结论。

### 2026-10-14 执行真实 PostgreSQL 集成测试

用户要求执行真实 PostgreSQL 集成验证。本轮按当前配置连接数据库，使用现有测试的临时表或独立 schema 隔离业务数据，模型调用使用测试替身。

- 在 `apps/api` 下设置 `PYTHONUTF8=1`、`TENDER_RUN_DB_TESTS=1`、`PGCONNECT_TIMEOUT=8`，执行 `.venv/Scripts/python.exe -m pytest tests/integration -q --tb=short --maxfail=1`。
- 结果：**72 passed，耗时 71.58 秒，退出码 0**，没有失败或跳过。首次失败即停止的限制未触发，全部现有集成用例执行完毕。
- 本轮确认 PostgreSQL 已可连接，覆盖此前「数据库连接超时、集成测试未执行」的现场限制；未验证 Redis、业务服务或报告 #16 的当前状态。
- 本次执行的是现有 PostgreSQL 集成测试集；上一节新增的知识库列表与 4096 元素专项回归仍是 SQLite 离线测试，不将其记为本轮新增 PostgreSQL 用例。

未修改业务代码、未启动或重启业务服务、未调用真实模型、未执行业务库迁移、未提交或推送；迁移兼容性测试仅在隔离测试 schema 内执行并回滚。

### 2026-10-14 数据库迁移核验与提交范围

- 按用户要求对当前配置的业务数据库执行只读核验：`public` 的 Alembic 版本与代码 head 均为 `0012_config_limits`，没有待应用版本；41 张 ORM 业务表、483 个字段均存在。事务确认 `transaction_read_only=on`，未重复执行迁移。
- 用户随后明确要求提交代码，本次提交范围为已审查的 ORM 端口/仓储迁移、分析任务异常收尾与结构门禁修复、知识库列表及批量元素写入修复、对应测试与交接文档。
- 提交前验证结果：离线 **669 passed / 9 skipped**，真实 PostgreSQL 集成 **72 passed**，源码及新增测试 Ruff 通过，架构约束 **5 kept / 0 broken**。不包含推送、业务服务重启或真实模型调用。

### 2026-10-15 移除字段抽取并重构 Agent 证据汇总输出：实现与验收完成

承接用户指定会话及根目录同名任务文档。本轮读取原会话最后记录后继续已有改动，使用 karpathy-guidelines 技能；没有启用子代理。

用户要求与最终行为：

- 旧字段抽取、复抽、字段复核、冲突裁定、字段 Excel 导出及金标回放的业务实现、API、worker、前端入口、专属测试和样例已移除。文件流程只保留转换与解析，默认项目入口为 Agent 分析，`?view=document` 保留文档预览。
- 13 个专题加载冻结 Skill，先核对资料、全部 coverage 主题和转引，再经 `complete_research` 进入综合阶段。`submit_analysis` 使用 records/content，服务端校验专题分类与列名；原文引用独立保存，仅用于溯源。
- 技术专题展示项目背景、要求摘要与逐条关键要求；评分保留真实列名及各档次；格式保留父子材料层级。支持性校验包含正文和业务属性，校验失败保留已核实成果，补读新证据后重新确认检索和汇总。研究缺口随报告保留，旧报告只读展示。
- 新迁移 `0013_retire_extraction` 取消活跃旧抽取/导出任务，删除旧功能绑定、配置及8张旧表、2个关联列，保留解析、Agent、模型调用日志和历史配置版本。历史迁移不改，不支持通过重建空表伪装降级。

本轮补修：

- `scripts/start-backend.ps1` 原消费队列删掉 extract 后漏加 analysis，容器仍保留 extract/regression，导致新版 Agent/问答/索引无人消费。三个部署入口现统一 `tender,convert,parse,analysis`。新增 `tests/contract/test_worker_queues_match_routes.py`，比较生产者真实路由和部署消费列表；修复前三项失败，修复后三项通过。脚本 PowerShell 语法通过，UTF-8 BOM 保留。
- `ProjectAnalysis.tsx` 按 report.id 重新挂载依据面板；`AnalysisDataPanel.tsx` 新快照加载前清除标段，加载按钮无快照时禁用并固定可访问名称，防止报告切换沿用旧快照或预览请求。
- `synthesis.spec.ts` 改按 tabpanel 的语义名称定位，避开 Ant Design 内部类名。技术摘要、逐条要求、评分列、三层格式与真实 PDF 定位均已验收。
- 清理本次代码的3处 Ruff 长行和2处差异空白错误；内置技术输出模板保留背景摘要占位。

最终验证：

- 后端 `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest tests/unit tests/contract -q --tb=short`：**602 passed / 9 skipped**。
- `ruff check src/tender tests alembic/versions/0013_retire_extraction.py`：全过；`lint-imports`：**5 kept / 0 broken**。
- 前端 `pnpm --dir apps/web typecheck`、`test`：**45 passed**；`build`：通过；完整 `test:e2e`：桌面/390px **54 passed**。页面使用拦截 API 和合成 PDF，不代表真实供应商端到端验收。
- `pnpm --dir apps/web verify:sample`：6页 PDF 页面几何与全部块坐标校验通过。人工查看桌面技术与窄屏评分截图。
- `git -c core.safecrlf=false diff --check`：通过。
- 当前配置远程 PostgreSQL 首次集成连接超时，因此本轮改用缓存的 PostgreSQL 18.3 程序包创建临时本地实例（仅 127.0.0.1:55433），空库从基线应用到 `0013_retire_extraction` 后执行全部 `tests/integration`：**70 passed，71.87秒**。退役测试在独立 schema 构造含真实外键的历史数据，核对旧表/列/绑定移除、调用日志保留、解析任务不被取消，事务回滚后没有 retire_test/llm_test schema 残留。
- 测试库确认 head 为 `0013_retire_extraction`；ORM 当前 **33张表、384列**。测试实例已用 pg_ctl 正常停止，55433 端口已释放。

产物与下一步：

- 最新完整页面日志 `.tmp/synthesis-e2e-final.log`；截图与 trace 由 `apps/web/test-results/` 保存，属测试产物。
- 临时 PostgreSQL 程序、测试数据目录及日志位于 `.tmp/synthesis-postgres/`，服务已停止。未修改任何部署环境变量或 .env。
- 代码与隔离验收已完成，仍未应用到真实业务环境。沿用原会话推迟业务服务重启/业务库迁移的要求；后续现场启用需先恢复远程依赖，确认已有任务及备份，再按删数据迁移要求应用0013、启动新版并生成新报告验收。
- 未调用真实模型、未重启业务 API/worker/beat、未迁移业务数据库、未提交或推送。本轮临时实例的成功不能替代远程业务库连接与现场验收。

### 2026-10-15 修正 Agent 过程门禁与纠错误杀

用户反馈 complete_research 几乎全部失败，错误为「必须逐一交代全部主题」及「主题检索词必须来自实际成功执行的项目检索」，并强调目标是分析招标文档、产出分析结果和精确定位。沿用原会话，不启用子代理，使用 karpathy-guidelines，保留所有已有未提交修改。

原因与修复：

- 旧实现让模型精确复述主题 key 和 query，并在第一个校验问题处停止反馈；不同错误共用同工具三次失败计数。真实检索账已在服务端，重复复述没有业务必要。现 queries 可省略，仅为检索意图；真实 project_searches 直接来自成功工具事件，每轮向模型提供服务端资料和检索记录，压缩历史不会丢失过程账。
- 主题 key 和 Skill 中文名均可归档；重复说明合并，遗漏及无法确定归属的正式主题保留 unresolved 缺口。覆盖/转引证明缺项降为未决状态，不阻断有明确引用的正文。不同确定性错误组合分别计数，一次反馈全部 issues；同类错误仅更换虚构证据 ID 仍耗尽额度，检查点恢复不能重置计数。
- 移除 list_documents 调用顺序门禁；资料清单来自服务端，未检索补充资料写入缺口。无真实项目检索、虚构或越权证据仍拒绝。新的成功检索即使没有新命中也算进展；相同请求重放、改名及未校验草稿不算，总调用/证据/时限预算保留。
- 只有新增证据才要求重新汇总；空检索或只返回已读块时保留已核实成果，并更新实际检索账。coverage/gaps/research_summary 可以省略；清单漏项及关联失误降为 pending 并发布缺口。空说明补齐、长摘要截取，不因过程文案终止模块。
- 部分表格列缺失时保留有依据的内容；单条技术要求字符串整理为数组，摘要/要求用已提交内容互补，整理后的 content 与业务属性仍全部送支持性校验。格式分组可以嵌套，同批父子/端点不限顺序；循环、缺失父级及错误归属仍拦截。
- 标段 code 只存原文编号，无编号可以省略。目录用已核实名称作内部查找键，分析数据 code 仍为空；已修复按名称解析范围、补齐标段覆盖及前端类型，未新增迁移。
- 删除没有生产调用的 analysis_outline.py、旧协议和专属单测，其中包含“最多三级/分组只能为根/正文逐字摘录”的遗留约束。历史报告同名材料/父级路径读取测试直接构造历史形状，不再依赖旧生成器。
- 13个专题 Skill 和 docs/设计/19-Agent检索与专题汇总.md 同步新规则。新增 test_research_checkpoint_repairs.py，覆盖真实图的检索、修复、综合、缺口、已核实结果保留及定位身份；新增 PostgreSQL 无编号标段发布/幂等/HTTP读取测试。

验证：

- 新回归最初复现7项失败；修复与扩充后全部通过。最后全量 unit/contract：**608 passed / 9 skipped，23.50秒**。旧格式专属9项测试随死代码删除，旧清单硬失败断言改为验证 pending 与结果保留，不能仅按测试数量增减判断覆盖。
- 隔离 PostgreSQL 18.3 全量集成：**71 passed，55.81秒**；删除旧生成器、调整历史夹具后，两个父级路径兼容用例补验 **2 passed**。未用真实模型，未改写业务库。
- Ruff 全源码/测试通过；import-linter **5 kept / 0 broken**；前端 pnpm typecheck 与 git diff --check 通过。本轮只改前端类型，没有新增界面或重跑浏览器验收。
- 重用 .tmp/synthesis-postgres 的临时实例，端口127.0.0.1:55433，库为postgres、角色synthesis_test，确认head为0013_retire_extraction。实例已正常停止，端口无监听。新日志为 .tmp/synthesis-postgres/research-repairs-db.log。PowerShell向postgres单用户后端传stdin需用无BOM UTF-8；本轮只读查询角色/库名，没有改角色或数据。

业务服务与下一步：

- 本轮只完成代码修复与隔离验证，未检查远程业务服务现状、未重启业务服务、未调用真实模型、未迁移业务库、未提交或推送。此前推迟业务启用的约定保留。
- 若后续要求现场启用，先重新检查依赖、业务服务及在途任务，按已有迁移/备份约定处理；服务加载修复后补跑失败专题，验证真实模型输出与原文定位。不能将测试替身的通过称为线上失败已恢复。

### 2026-10-15 修复未提交更改审查发现的三项问题

用户要求修复本轮审查发现的问题，保留全部已有未提交更改，继续使用 karpathy-guidelines。

- `prepare_records` 先为整批生成归一化 content/text，再解析关系端点，消除同批顺序导致的空端点文本；发布后的 supersedes 关系与旧要求替代状态正常。工具协议与错误提示同步说明同批端点顺序不限。
- 最终提交省略 `gaps` 或传入 `null` 时沿用已登记缺口；只有显式清单才在校验通过后替换内容缺口。显式空数组仍可清除内容缺口，未解决的检索/转引缺口继续由服务端保留。设计文档同步此语义。
- 文件管理顶部“预览原文”改用 `?view=document`，修正旧 `?view=fields` 路由进入分析页的问题。
- 在 `test_research_checkpoint_repairs.py` 新增10项参数化回归，覆盖关系与两个端点的全部6种顺序，以及省略/null/空数组/显式剩余缺口清单。验证正式分析数据中的关系端点身份与 superseded_in，而不只检查工具接受状态。

验证：

- 修复前新增回归 **6 failed / 4 passed**；修复后相关分析与问答用例 **107 passed**，全量 unit/contract **618 passed / 9 skipped**。
- 本轮变更的 Python 文件 Ruff 检查通过，新增测试段格式检查通过；架构约束 **5 kept / 0 broken**；前端 `pnpm --dir apps/web typecheck` 与 `git diff --check` 通过。
- 复用4400端口的开发服务，用无界面 Edge 与拦截 API 点击文件管理顶部入口，确认 URL 为 `?view=document`，且出现文档预览标题和项目文件导航。此验证不代表真实资料或供应商端到端验收。
- 未重启业务服务、未迁移或改写业务数据库、未调用真实模型、未提交或推送。

### 2026-10-15 用户要求提交本轮代码

- 用户明确要求提交代码；提交范围包含字段抽取退役、Agent 综合输出重构、检索门禁修正、三项审查问题修复及对应测试、迁移、部署入口和文档。
- 采用中文提交信息，不添加作者说明或协作署名；沿用已完成的618项离线测试及前端、架构和浏览器定位入口验证，不重复运行同一验收。
- 本次仅提交到本地 Git，业务服务启用、真实业务库迁移和推送仍未执行。

### 2026-10-16 按解析 Skill 改为维度检索后逐条产出独立 JSON

用户明确要求：每个业务 subagent 是一个分析维度，先完成该维度检索，再统一分析；一条完整结果一个 JSON，避免模型一次生成大 JSON。父级只调度与保存，结果由 subagent 直接产出。读过根目录交接，使用 skill-creator 与 karpathy-guidelines；未启用开发子代理，未自动提交。

最终实现：

- submit_analysis.records 从最多24条改为最多1条，保留现有工具名；final=false 保存当前完整事项，所有事项完成后 records=[]、final=true 收尾。同一评分项档次、技术任务关键要求保留在该事项内，可综合多处引用；服务端 schema 拒绝大数组。13个运行时 Skill、格式输出参考和设计19均同步逐条协议。父节点和关系端点先逐条保存。
- 独立业务 JSON 存在 analysis_module.business_data.records，删除内嵌 citations，只保留 evidence_ids；原文及定位放在 business_data.evidence。module_records 仅在下游消费时回填，兼容历史内嵌引用；任何必要证据缺失时整条不可用，不用剩余引用冒充完整依据。现有报告显示与编制快照继续使用确定性投影，无父级模型重写结论。
- 新增 GET /api/v1/analysis/reports/{report_id}/modules/{module_key}/records，直接返回记录与独立证据集合，不从展示文本解析；检查公司/报告归属及实时原文权限，来源删除后 records/evidence 都为空，覆盖证明不会混入业务结果。设计05同步接口。
- load_module_skill 首次推理前加载冻结的输出格式、核心规则和项目/标段明确品类规则，覆盖混合品类，不默认当服务类。技术主 Skill 的领域边界恢复参考目录设计：项目背景、技术方案要求，排除纯参数清单；coverage 主题同步方案范围，旧参数参考不自动覆盖主规则。其余标准专题的领域知识与识别规则核对一致；工具、位置载体与逐条输出按用户要求适配，不机械搬回旧DOCX专属工具或Markdown整体输出。
- 无依据“未载明/未规定”等占位移入检索缺口，单条支持性纠正达到上限登记 rejected_records 与不可清空的缺口，保留其他已核实结果，收尾仍需显式 final。内容错误与未展开转引分开记账；新证据进入后清除旧汇总及旧拒绝状态，再研究与综合。
- 运行时更新为 deepagents-0.7.22-v5-records，旧报告只读，不混用旧线程协议。没有新增DDL迁移。

验证：

- 最终全量 tests/unit tests/contract：632 passed / 9 skipped，26.37秒。新增test_dimension_json_records覆盖先完整检索、多证据归并、逐条输出、大数组拒绝、独立引用、技术边界与缺证据不可用；工作树开始时已有未跟踪test_scoring_repair_flow保留并补完，未删除用户工作。
- 最终隔离PostgreSQL18.3全量tests/integration：72 passed，56.03秒。覆盖实际JSONB保存、独立JSON的HTTP读取与权限、快照修订和定位；测试数据运行在临时schema/表，不改写业务库。
- 最后格式Skill文案修正后补验相关护栏和新结果测试27 passed；Ruff全源码/测试、5项架构约束、git diff --check通过。本轮没有改前端代码，不重跑界面验收。没有使用真实模型，脚本化模型+真实Agent图和数据库验收不能称为真实供应商验收。
- 日志：.tmp/dimension-json-unit-final.log、.tmp/dimension-json-db-final.log。复用临时数据库127.0.0.1:55433，角色synthesis_test、库postgres，既有0013基线；实例已正常停止，端口释放。未修改.env或业务环境参数。

业务状态：

- 未重启业务API/worker、未迁移或改写业务数据库、未调用真实模型、未提交或推送。沿用交接里的推迟业务启用要求；本轮代码完成不表示业务服务已经加载v5。
- 后续若要求现场启用：检查依赖与在途任务，加载新版服务后新建报告验收逐条JSON；旧版本报告不直接混跑新版线程。
### 2026-10-16 前端接入独立专题 records：实现与验收完成

用户明确授权让前端接入新 records 接口。承接上一节逐条 JSON 后端实现，读取根目录交接并使用 karpathy-guidelines；保留所有已有未提交更改，没有启用开发子代理。

最终行为：

- 新版专题正文、成果计数及正反向原文定位直接读取 GET /api/v1/analysis/reports/{report_id}/modules/{module_key}/records，不再使用报告接口里的展示条目。报告状态、运行记录和研究缺口仍由报告接口提供；runtime_retired 或无数据版本的历史报告保留原展示。
- records 接口新增 output_schema，来自报告冻结的 Skill，前端按其分类、布局和列名组装现有 ModuleMarkdown 展示。独立记录保留 key、parent_key、node_type、sort_order，支持人员及格式的通配分类；证据经 evidence_ids 解引用，必要依据缺失时整条隐藏。
- 各维度并发请求，某个专题失败独立显示错误及重试入口，不回退报告旧条目，也不阻断其他专题。切换报告取消旧请求并清空新专题加载占位；序号保护防止延迟响应覆盖。运行中每三秒刷新，存在在途请求时等待其完成，详情状态和列表状态均参与运行判断。
- 复用原 Skill 展示组件，技术摘要与关键要求、评分档次和列名、格式父子树及 PDF 定位均已覆盖；未做界面风格重构。设计05和设计19同步接口字段及消费方式。
- Playwright 默认端口仍为4400，新增 PLAYWRIGHT_PORT 可覆盖。Windows 对4400返回 listen EACCES，本轮临时测试使用14400，不改业务配置。

本轮验证：

- pnpm --dir apps/web typecheck、build 通过；test：48 passed（8 files）。新增3项单元测试覆盖独立数据转换、证据缺失、冻结列顺序、历史兼容和单维度失败。
- 完整 pnpm --dir apps/web test:e2e：桌面及390px共60 passed，3.6分钟，退出码0。夹具报告 items 故意为空，正文仅来自 records，新增失败重试、运行刷新及依据撤销、报告切换延迟响应场景。浏览器验收使用拦截API与合成PDF，不代表真实模型或业务端到端验收。
- 后端 tests/unit/api tests/contract：150 passed / 9 skipped；隔离PostgreSQL tests/integration/test_analysis_data_flow.py：15 passed，包含冻结 output_schema 的实际HTTP读取断言。Ruff相关Python文件通过；import-linter 5 kept / 0 broken。
- 前一轮后端全量632 passed / 9 skipped和72集成通过已记于上一节，本轮未重复全量；最终 git diff --check 通过。
- 完整页面日志 .tmp/frontend-records-e2e.log；测试数据库日志 .tmp/synthesis-postgres/frontend-records-server.log。临时PostgreSQL127.0.0.1:55433已正常停止，14400测试Web服务已退出，端口无监听。

业务状态：

- 前端接入代码及隔离验收完成；未重启业务API/worker，未迁移或改写业务库，未调用真实模型，未修改.env，未提交或推送。代码完成不表示现场服务已加载新版本，沿用此前推迟业务启用的约定。

### 2026-10-16 专题检索增加相关度阈值与单次结果数量：实现与验收完成

用户要求相似度阈值和每次检索结果数量取交集，随后明确默认阈值0.6、默认最多6块。读取根目录交接，使用karpathy-guidelines，保留既有未提交更改，未启用开发子代理。

最终实现：

- 新增 analysis.similarity_threshold（number，默认0.6，允许0..1）与 analysis.max_search_results（int，默认6，正整数）。两项复用模型管理的“分析参数”动态编辑器、服务端范围元数据及发布链，不额外维护前端配置清单。
- AgentLimits增加对应字段，由既有limits_snapshot在新建或补跑时冻结；worker实际检索调用明确传入运行快照的阈值与数量，不读取执行途中发布的新值。
- rank_chunks先按相关度过滤，再融合排名；有与查询匹配的可用向量时使用原始余弦相似度，缺向量/索引不匹配/向量服务不可用时使用命中检索词数量除以检索词总数。沿用中文二字词的全文分词口径。RRF与供应商重排分数只是排序，不能当相似度；已有低分向量不能靠关键词命中绕过阈值。
- 过滤后保留足够候选用于可选重排，再限量；无足够达标结果时返回实际数量或空列表，不用低分补齐。自定义数量大于16时不会被原来的候选16块或工具12块截断；专题扩展也遵守单次数量，并先检查来源范围。
- 模型证据仍仅id/text，检索参数和过程保留服务端事件账。显式按已读ID补读邻近原文沿用默认5块/单次最多12块，不套用相似度阈值，以保留表头和跨块条件；专题累计证据默认160。知识库页面搜索及问答调用保留原行为，本轮配置仅作用于专题的项目/参考检索。
- 新迁移0014_analysis_retrieval仅登记两项配置，不修改业务表结构、历史配置版本或已有报告。设计19及质量08同步口径和配置入口。未修改13个Skill领域规则。

验证：

- 后端全量tests/unit tests/contract：652 passed / 9 skipped，18.27秒，exit0。新增test_analysis_retrieval_limits覆盖阈值边界、低分向量不能关键词旁路、中文/英文全文回退、100条命中最多6块、达标不足不补齐、自定义20块、重排低尺度分数与服务失败、工具输出仅id/text、扩展上限与权限；新增阈值配置边界9项测试。
- 隔离PostgreSQL18.3 tests/integration/test_config_limits.py：8 passed，8.67秒，exit0（原6项+本轮2项）。在独立事务schema执行全部迁移，核对配置种子与API范围、错误参数拒绝、实际文档仓储检索限量与阈值、报告参数快照不随新发布改变；不调用任何真实模型。
- 相关Python文件Ruff通过；import-linter 5 kept / 0 broken；alembic upgrade head --sql离线渲染至0014通过；前端现有配置类型/范围处理不改，pnpm test为48 passed（8 files）。界面组件未修改，本轮未重复生产构建或浏览器全页验收。
- 最终git diff --check通过。日志为.tmp/retrieval-limits-unit.log、.tmp/retrieval-limits-db.log、.tmp/retrieval-limits-migration.sql。
- 临时PostgreSQL127.0.0.1:55433在测试schema执行0014后回滚，public版本仍0013_retire_extraction，无llm_test_*残留；已用pg_ctl正常停止并释放端口。服务日志.tmp/synthesis-postgres/retrieval-limits-server.log。

业务状态：

- 未重启业务API/worker，未应用0014到业务库，未迁移或改写业务库，未修改.env，未调用真实模型，未提交或推送。沿用此前推迟业务启用要求；后续现场启用须加载新服务，并按既有迁移约定处理到0014，再新建或补跑验证。

### 2026-10-16 收尾纠正次数可配置：实现与验收完成

用户已找到检索参数，随后反馈第5次运行在8/80次模型请求、20/100次工具调用时失败，错误为“连续无进展且收尾纠正两次仍未完成，已保存通过校验的成果”，要求最大纠正次数可配置。读取根目录交接，使用karpathy-guidelines，并读取skill-creator同步一处Skill重试参考；保留既有未提交修改，未启用开发子代理。

定位与实现：

- ResearchMiddleware.abefore_model 原来在 no_progress_rounds >= max_no_progress_rounds + 2 时抛RuntimeError；额外两轮写死，并非请求预算耗尽。analysis.max_no_progress_rounds控制进入收尾，analysis.max_validation_failures控制同一事实校验，两者都不控制这两轮。
- 新增analysis.max_finish_corrections，int，默认2、允许正整数、无人工上限，中文说明“进入收尾后允许的连续无进展纠正轮数，耗尽时保留已核实成果并终止”。复用模型管理→分析参数动态编辑器，AgentLimits及既有limits_snapshot冻结，新建或用户补跑时生效。
- 停止条件改为运行快照的max_no_progress_rounds + max_finish_corrections；错误包含实际配置次数。每轮收尾系统提示显示剩余轮数与上限，并明确先完成检索确认、逐条提交可靠成果、空records+final=true收尾。
- 不新增另一套计数：继续复用幂等progress_message_id/no_progress_rounds及业务进展签名。同线程断点恢复不重置次数；新核实成果等有效进展重置连续无进展计数，finish_only仍限制扩展检索。用户补跑沿用既有新attempt清理逻辑并读取新配置。
- 仍须显式final=true完成模块；额度耗尽时保留可靠成果并报告未完成，没有自动将部分成果伪装为完成，也没有取消支持性或权限校验。未检查用户此次真实模型的完整工具反馈，不能声称频繁失败全部解决；本次解除的是固定两轮限制。
- 新迁移0015_finish_corrections仅登记配置项，不改历史配置/运行记录。设计19同步三个配置的职责、计数和生效语义；general_module_parsing/references/retry_policy.md不再将3/2轮写成不可调规则，以运行快照和剩余提示为准，其他领域Skill未修改。

验证：

- 后端全量tests/unit tests/contract：660 passed / 9 skipped，19.27秒，exit0。新增test_finish_corrections共7项，涵盖默认值/正整数范围、1/2/5轮耗尽边界及已核实成果保存、消息ID重放不重复扣额度、新核实事实重置连续计数；真实Agent图同一脚本在2轮下复现失败、5轮下显式final成功。
- 最后收尾提示文案整理后上述7项补验通过；相关Python文件Ruff通过，import-linter 5 kept / 0 broken，alembic upgrade head --sql离线渲染到0015通过；git diff --check通过。
- 隔离PostgreSQL18.3：tests/integration/test_config_limits.py及test_retry_uses_live_config_and_keeps_report_snapshot_untouched共10 passed，9.30秒，exit0。验证配置种子/页面元数据、0轮拒绝、配置发布、新报告冻结5轮不随8轮新发布改变、已有报告补跑从2轮切为5轮并保留旧记录。
- 临时数据库127.0.0.1:55433仅在独立测试schema执行0015，public版本仍0013_retire_extraction，无llm_test_*或test_agents_*残留；已pg_ctl正常停止，端口释放。日志.tmp/finish-corrections-unit.log、.tmp/finish-corrections-db.log、.tmp/finish-corrections-migration.sql、.tmp/synthesis-postgres/finish-corrections-server.log。
- 本轮前端组件未修改，未重复界面构建和浏览器验收；沿用动态配置通用显示/范围逻辑。

业务状态：

- 未重启业务API/worker，未应用0015到业务库，未迁移或改写业务库，未修改.env，未调用真实模型，未提交或推送。此前推迟业务启用要求保留。现场使用新参数须加载本轮代码并按既有迁移约定更新配置登记，再新建或补跑；用户现有在途任务未修改。

### 2026-10-17 失败调用显示上游详细响应：实现与验收完成

用户要求截图中的失败调用显示上游详细响应。开始时使用UTF-8读取交接，使用karpathy-guidelines；保留此前未提交改动，未使用子代理。

最终行为：

- Agent适配器从SDK实际HTTP响应正文或已解析body提取上游详情，HTTP 429等失败包含具体message/code/request_id及HTTP状态，不再只显示RateLimitError。JSON、普通文本和HTML均保留；没有响应的网络异常仍按类型展示，不把带请求的异常文本写入记录。补齐httpx.TransportError的可重试分类。
- 普通语言调用、模型目录、向量、重排、生图HTTP失败同步保留响应；新增core/error_details.py统一隐藏已知API Key和常见凭证字段。最长16000字符，超长明确标记截断。
- 路由落账、管理测试落账去掉原500字符截断；API读取去掉HTTP状态后截断，兼容已有带正文记录。复用现有TEXT列，无DDL迁移。历史记录未保存的正文不能恢复。
- 调用列表展开与完整调用链显示HTTP状态、响应换行及长文本自动换行。HTML始终作为文本显示，不执行上游脚本。同步设计12。

验证：

- 后端全量tests/unit tests/contract：669 passed / 9 skipped，18.64秒，退出码0。新增9项回归，并更新旧有不展示正文的断言，覆盖限流/鉴权/5xx具体响应及分类、单次HTTP无隐式重试、Retry-After、长正文落账、凭证隐藏、HTML/文本、无响应连接失败。
- 前端pnpm typecheck、test（48 passed / 8 files）与生产build通过。
- Playwright定向检查：桌面及390px共4 passed，49.8秒，覆盖完整调用链分页、列表和抽屉详细正文、700字符后request_id可见、换行、不执行HTML和窄屏容器无横向溢出。使用拦截API，不修改业务数据、不调用真实模型。
- 相关Python Ruff通过，import-linter 5 kept / 0 broken，git diff --check通过。临时测试端口14400的Web服务已由Playwright退出。

业务状态：

- 未重启业务API/worker，沿用此前推迟业务启用的要求；服务需加载新版后，新失败请求才会记录完整上游详情。未修改.env、未迁移或改写业务数据库、未调用真实模型、未提交或推送。

### 2026-10-17 修复审查发现的三处分析状态问题

用户要求修复未提交更改审查中的三个问题。开始时UTF-8读取本交接，继续使用karpathy-guidelines，保留既有工作区改动，未使用子代理。

修复：

- 覆盖证明kind=coverage没有title，record_gap改为使用topic；支持性或转引纠正耗尽时把对应覆盖状态改为pending，保留其它可靠成果。原样重提交已耗尽证明继续pending，不恢复“不适用”，不重复校验。
- 同key缺席性改写（如“质保期限未载明”）登记缺口的同时保留旧supported版本，避免已核实成果被continue分支删除。
- 重复complete_research合并保留rejected_records关联的缺口，不因刷新检索清单而丢失结构化诊断；真正新证据仍沿用invalidate_summary清理及重新综合。
- 新增test_analysis_review_repairs.py共4项真实Agent图回归，覆盖辅助证明内容/转引失败、重复检索确认及重提交、旧版本回退、拒绝事项缺口持久保留。同步设计19。

验证：

- 修复前新增回归4 failed；修复后相关59 passed。
- 加强覆盖证明重复确认场景后，全量tests/unit tests/contract：673 passed / 9 skipped，18.77秒，退出码0。
- 相关Python Ruff通过；import-linter 5 kept / 0 broken；git diff --check通过。
- 本轮只改后端状态逻辑与文档，不重跑前端或数据库验收。测试使用脚本化模型和真实Agent图，没有调用真实供应商。

未重启业务API/worker、未修改.env、未迁移或改写业务数据库、未提交或推送。沿用此前推迟业务启用的要求；生效须业务服务加载新版代码。

### 2026-10-17 后端质量审查（/simplify）：复用与效率收口

用户要求审查后端代码并修复质量问题。读取根目录交接，按复用/简化/效率/抽象层级四个角度并行审查，只改质量不改行为。

修复：

- records 端点不再自行生成证据 ID，直接引用 business_data.evidence，与写入时口径一致；所有记录一次调 visible_items，visible_items 在 output=True 时以 with_content=False 解析，避免渲染随即丢弃的 plain_text。
- 新增 core/error_details.raise_for_status 与 retry_after，5 个模型适配器共用失败分支与重试等待，openai_chat._retry_after 删除；agent_chat 不再延迟导入适配器函数。
- deep_analysis 抽出 rejected_record_gaps()，build_draft 与 complete_research 共用；analysis_data 装配不可用记录改为单趟登记缺口。
- rank_chunks 命中数与相似度各算一次，阈值过滤后按原索引重映射；analysis_data_store 一次发布只投影一次记录，assemble_dataset 增加可选 hydrated 复用；_remember 去重按元素分桶。
- analysis_policy 品类白名单改用 CATEGORIES；api/llm 删除与 error_detail 等价的 _error_summary。

跳过：

- analysis_output 的"总分构成"字面量尝试在 output_schema 落 allow_name_only，会扩大到所有评分标准节并导致 4 项测试失败，已回退；真正修法需要在 Skill 输出格式加声明位。
- Skill 参考文件改 manifest 声明涉及 13 个 Skill 目录打包格式；verification 三份列表合并会改检查点字段名；records 端点改仓储单行查询需动 ports 与 pg 适配器。均超出本次范围。

验证：

- 后端全量 tests/unit tests/contract：673 passed / 9 skipped，25.97秒，退出码0。
- Ruff 通过；import-linter 5 kept / 0 broken；git diff --check 通过。
- 本轮未跑 PostgreSQL 集成测试（只调整投影与查询次数，未改 SQL）；未重启业务API/worker、未调用真实模型、未迁移业务库。


### 2026-10-17 上游 429 降级的前端可见性

用户要求前端补上对应的限流界面。配置页本身按后端元数据渲染，两个新参数无需改界面；缺口在于冷却状态后端从未对外返回。

改动：

- api/llm.py：供应商查询附加 `rate_limit_remaining_seconds`（数据库时钟计算，`greatest(0, epoch(rate_limited_until - clock_timestamp()))`），`_provider_out` 输出到列表/新增/更新三处；模型输出不含该字段。
- 前端 types/llm.ts 增加该字段并说明为何用剩余秒数而非绝对时间；lib/llm/format.ts 新增 `countdownLabel`。
- ProvidersPanel 状态列在启用/停用标签下追加“限流冷却 X 分 Y 秒”，只读展示，不提供手动解除。
- CallLogsPanel：`http_status === 429` 的行标为“上游限流”（warning 色），详情同口径，避免把配额等待误读成请求失败。

验证：

- 后端 tests/unit tests/contract：683 passed / 9 skipped；Ruff 通过。
- 前端 pnpm typecheck 通过；pnpm test 48 passed / 8 files。

未部署：业务 API/worker 未重启，迁移 0016 仍未执行业务库，前端未构建发布；两个新参数在配置页出现依赖 0016 落库。

### 2026-10-17 简化专题的待核对提醒与分析过程

用户反馈“检索范围与未决事项”用途抽象、文字过多。开始时 UTF-8 读取本交接，使用 frontend-design 与 karpathy-guidelines，未使用子代理。

- 原混合区域拆开：结果前以浅橙提示显示“有 X 项内容待核对”，说明“分析时未能确认的内容，请核对原文或补充材料”。事项默认收起，展开后每项最多两行，长文通过 Ant Design Paragraph 的“展开说明 / 收起”查看全文；不改写、猜测或丢弃诊断内容。
- 完整 research_summary 移到结果下方的“查看分析过程”，默认收起。无缺口时不显示提醒，无过程说明时不显示过程入口，不把空列表当成全部已核实。
- 缩短未完成提示为“已保存 X 项已核实结果，分析尚未完成。补跑会保留已有结果”。沿用全部原始结果、接口及补跑行为；新增 ResearchGaps.tsx，只改前端展示。
- 切报告时重置展开状态，键盘可操作，窄屏长文换行；更新已有专题页面验收的旧入口断言。

验证：pnpm --dir apps/web typecheck、48 项单测、生产 build、git diff --check 通过；synthesis.spec.ts 桌面与 390px 共 12 passed。临时浏览器检查另覆盖失败但已有成果、3 条缺口及长说明、Enter 展开、全文展开/收回、过程全文、空缺口/空过程，1440/390/320px 全部通过，无页面异常及横向溢出。截图及临时检查脚本位于 .tmp/research-*。

首次尝试 14400 测试端口因已有 Next 开发服务持锁退出；随后复用已有 4400 服务完成拦截 API 的浏览器验收。未停止或重启现有开发服务，未访问真实模型或改写业务数据，未重启 API/worker、未迁移业务库、未提交或推送。前端生产构建已验证，未发布。

### 2026-10-17 统一五处界面文案与信息展示

用户在排查后明确要求处理五类问题：编制依据中的长篇待核对事项、分析操作名称混用、失败提示缺少处理指引、上传选项难理解、配置页暴露内部术语。读取交接后使用 frontend-design 与 karpathy-guidelines，保留上一轮改动，未使用子代理。

- 投标要求：原“编制依据与待核对事项”改为“投标要求汇总”，补充用于编写投标文件的用途说明；按标段查看入口、项目事实、待补读及归属/效力标题改为直观中文。两个额外缺口列表复用 ResearchGaps，显示适用标段并折叠长文，完整诊断保留。
- 分析操作：明确区分“生成新报告”“继续未完成专题 / 继续本专题”“重新分析全部专题 / 重新分析本专题”，同步状态与取消提示。接口、请求内容、已有成果保留规则和运行限制均未修改。
- 失败提示：新增 AnalysisFailureNotice，为已知连接、超时、限流、权限、运行限额错误提供简短原因和下一步；未知错误不猜原因，无错误正文时指向调用记录。完整原始响应放在“查看错误详情”；已取消专题使用信息提示。调用记录页的完整上游响应保持可见。手机端按钮置于说明下方，避免挤窄正文。
- 上传选项：解析方式改为快速预览 / 基础解析 / 标准解析 / 增强解析，文字识别改为自动判断 / 读取已有文字 / 识别图片中的文字，各有适用说明；与配置页共用 parseOptions，提交值仍为原枚举。上传后自动解析关闭时，摘要同步说明仅上传。
- 配置页：新增仅用于展示的 presentation，当前 37 项配置全部有中文名称和简短用途；内部键与原始说明收进“参数详情”。开启/关闭及解析枚举、默认值、版本差异、影响清单采用中文；保存校验错误也用中文名称。清单、范围、默认值、权限仍由服务端控制，未知配置回退服务端说明。发布前检查、发布操作、操作记录替代门禁/激活/审计，原逐项确认与发布接口保留。兼顾并发立即生效与专题运行参数下次使用的差别。

验证：

- pnpm --dir apps/web typecheck、48 项单测、生产 build、git diff --check 通过。原 3 条单测因错误文案更新而失败，已只更新预期文案；实际提交与校验规则保持原样。
- 完整 test:e2e：桌面与 390px 共 62 passed，3.7 分钟。覆盖标段选择、分页与原文定位、取消与继续、配置范围、上传默认值、报告切换和完整失败调用响应等。
- 临时 .tmp/plain-language-review.mjs：1440/390px 验证错误全文不丢失、两处缺口显示范围并可展开、上传增强解析/图片识别仍提交 advanced/ocr、中文开关提交布尔值、中文解析选项提交原枚举、未确认影响不可发布、确认后仍调用原 activate 接口。全部通过，无页面异常；版本加载的 Spin 弃用提示已同步修正。
- 末次窄屏布局修正后，.tmp/failure-layout.mjs 在 390/320px 确认按钮换行布局，截图已复核；随后生产 build 再次通过。相关截图位于 .tmp/plain-* 与 .tmp/failure-layout-*。

仅修改前端和交接文档，未修改后端或迁移；复用已有 4400 开发服务，所有浏览器操作均拦截 API，未改写业务数据、调用真实模型、重启业务 API/worker、提交或推送。生产构建完成，未发布。

### 2026-10-17 后端日志基础服务：规划确认与实现

用户先要求使用 grill-me 规划基础日志，不在各业务函数添加日志；随后确认推荐的技术方案、API/Worker/Beat 统一入口及文件/stdout 两种输出，并明确默认保留 30 天可修改、每日与 100 MiB 双条件切分。读取交接后使用 grilling 和 karpathy-guidelines；grilling 要求的只读事实调查使用了 logging_facts 子代理，编码与验证由主代理完成。保留此前前端及交接改动。

实现：

- 新增 core/logging：stdlib logging + structlog 25.5，幂等初始化、上下文绑定/恢复、UTF-8 文本终端与单行 JSON 文件、异常格式化、递归脱敏及单条 64 KiB 上限。提取 core/redaction，既有上游错误继续保留 16000 字符及原截断文案；长文本测试发现 DSN 脱敏正则回溯过慢，已限制协议名为短 ASCII 并通过回归。
- 文件默认 logs/{api,worker,beat}/日期.PID-启动标识.序号.jsonl。每日按 Asia/Singapore 切分，达到 104857600 字节另开分片，重启不覆盖；按文件日期保留包含当天的 30 天。启动和每小时清理，不依赖新日志；文件占用下次重试，正常并发删除不报错，不递归或清理其他文件。写入失败限频告警并回退已脱敏记录到 stderr。
- FastAPI 纯 ASGI 中间件生成/校验并回传 X-Request-ID，记录方法/路由模板/状态/耗时，支持流式响应；500 处理恢复关联 ID，Uvicorn 不重复打印堆栈。Celery 发布/执行信号传播已有上下文并恢复线程及嵌套任务状态，记录执行开始/结束/重试/异常，屏蔽默认返回值模板。task_id 与业务 ID 保持区别，不把执行 SUCCESS 当业务成功；未补 API→数据库→Beat 的持久化关联字段。
- 日志部署参数位于 core/settings.py 和两个 .env.example；LOG_RETENTION_DAYS=30、LOG_MAX_FILE_BYTES=104857600 均可改，启动时生效，未修改真实 .env。同步依赖/锁文件、分层约束、.gitignore、启动指南与工程20。
- Windows 启动脚本保留 UTF-8 BOM，复用 Python 解析日志配置，后台需要 file/both；不再覆盖固定 stdout/stderr 文件。Compose 默认 JSON stdout + Docker local driver 100m/5 文件，开启 file/both 时写 backendlogs 卷；镜像预建日志目录给应用用户，容器 Celery 使用 quiet 避免横幅混入结构化输出。

验证：

- 最终后端全量 tests/unit tests/contract：697 passed / 9 skipped，20.30 秒，退出码 0。
- 新增 14 项日志专项全部通过：跨天/大小切分、30 天日期边界、多分片、闲置定时清理、文件占用与并发删除、重启与幂等、多线程及两个真实子进程独立文件、脱敏/限长/回退、环境配置、真实 FastAPI 请求/500/流式响应、Uvicorn 去重、Celery 内存 broker 发布与 eager/嵌套/线程并发。
- 相关 Ruff 通过，import-linter 5 kept / 0 broken；19 项 PowerShell 进程身份回归通过；git diff --check 通过。
- Docker 命令不可用，已用 YAML 解析验证环境、卷和轮转设置，未构建或启动容器；未跑 PostgreSQL 集成测试或前端验证，本轮未改业务 SQL/模型或前端。

业务服务未重启，未迁移或改写业务数据库，未调用真实模型，未提交或推送。真实环境加载新版后生效。运行日志保留期不是停机时持续清理保证，单文件大小也不是总磁盘限额；初始化前直接标准流输出/终端横幅不长期保存，详见工程20。既有模型调用账本、Agent 事件与配置审计保持原职责。

### 2026-10-17 日志模块审查问题修复

用户要求修复未提交更改审查中的三个问题。读取交接后沿用 karpathy-guidelines，保留全部既有改动，未使用子代理。

- Windows 启动脚本将日志配置、后台输出模式及目录创建预检移到 `-Force` 停止旧服务之前；预检失败保留旧实例，`-Stop` / `-Status` 仍提前返回。保留启动与测试脚本的 UTF-8 BOM。
- API 模块级应用装配失败时，使用统一 logger 记录 `api_initialization_failed` 后重新抛出。日志初始化后的失败原因与堆栈可以落盘，隐藏窗口启动也可读取，退出码仍表示失败。
- Celery 任务失败信号区分字符串与真实 traceback：父进程提供的字符串直接进入统一异常字段，单列异常类型与原因，统一脱敏及限长；保留真实 traceback / None 原有处理及任务上下文恢复。
- 同步工程20和本地启动指南。每日切分、100 MiB 分片及默认包含当天的 30 天保留规则未变。

验证：

- 先用回归复现三个缺陷，再修复。API 使用两个真实子进程验证无效数据库 URL 与注入装配异常均非零退出且有脱敏日志，失败发生在外部连接创建之前。Celery 覆盖字符串、真实 traceback、None，并在 except 块之外发送真实任务失败信号，防止借用当前异常导致假通过。
- 日志专项 19 passed；后端全量 `tests/unit tests/contract`：702 passed / 9 skipped，39.57 秒，退出码 0。
- PowerShell 进程身份与启动预检共 32 项断言通过；所有停止、端口与目录操作均使用替身，未启停真实服务。
- 相关 Ruff 通过；import-linter 5 kept / 0 broken；UTF-8 BOM 与 `git diff --check` 检查通过。

未重启业务 API/worker/beat、未修改真实 .env、未迁移或改写业务数据库、未调用真实模型、未提交或推送。未改 SQL 或前端，本轮未跑数据库集成与前端测试。

### 2026-10-17 日志包实现移入 setup.py

用户要求将日志初始化等实现从 `core/logging/__init__.py` 移到普通模块。读取交接后按 karpathy-guidelines 做最小拆分，保留现有改动。

- 新增 `core/logging/setup.py`，承载初始化、logger 获取、关闭资源及内部状态；`__init__.py` 仅导出原有六个公共接口，外部导入路径与日志行为保持不变。
- 同步日志测试夹具的内部状态读取位置及工程20的文件职责说明。
- 验证：现有日志专项 19 passed（14.00 秒），Ruff 通过，import-linter 5 kept / 0 broken，`git diff --check` 通过。仅调整模块组织，未新增测试或重复运行全量测试。

未启停业务服务、未修改真实 .env 或数据库、未提交或推送。

### 2026-10-17 降低 worker 周期派发日志噪声

用户反馈 worker 循环日志持续刷屏，遮挡正常日志。读取当前 worker JSONL 尾部 300 条，全部来自 `dispatch_pending`（开始/结束各 140 条）与 `dispatch_knowledge`（各 10 条）；前者每秒唤醒，后者每 15 秒唤醒。

- `worker/logging.py` 仅将上述两个派发任务的开始及成功结束日志降为 DEBUG；默认 INFO 不再输出循环消息。业务任务生命周期、任务内警告、派发失败和重试照常保留。上下文绑定/恢复继续执行，避免静默任务丢失关联信息。
- 同步工程20与本地启动指南，说明调试时可设置 `LOG_LEVEL=DEBUG` 并重启 worker。
- 新增 4 项真实 Celery eager 探针回归，覆盖两个任务在 INFO/DEBUG 下的输出、警告/失败/重试保留、脱敏及上下文恢复，探针不执行业务派发。日志专项共 23 passed（14.28 秒）；Ruff、import-linter 5 kept / 0 broken、`git diff --check` 通过。

日志基础服务已在此前用户授权时提交为 `b023661`；本次降噪修改未提交。未重启业务服务、未改真实 .env 或数据库，运行中的 worker 需要重启加载新版后生效；此前前端改动继续保留。

### 2026-10-17 日志文件名改为可读时间

用户希望日志日期后的随机标识改为时分秒。读取交接后将 `core/logging/handlers.py` 的新文件命名改为 `日期.时-分-秒.PID.分片序号.jsonl`，如 `2026-10-17.21-42-03.24504.001.jsonl`。时间取文件创建时配置的时区，PID 区分并行进程，排他创建和递增序号处理同秒重启及同名冲突。

- 移除随机实例标识；跨天重置分片序号，大小切分继续递增。旧版随机标识文件不改名，清理器同时识别新旧格式，保持 30 天默认保留规则。
- 更新工程20、本地启动指南；扩展现有回归验证具体时分秒、跨天文件名、同 PID 同秒重新初始化不覆盖及新旧格式清理。
- 日志专项 24 passed（13.80 秒），Ruff 与 `git diff --check` 通过；既有多线程、两个真实子进程及轮转验证仍通过。

保留此前周期派发降噪与前端改动；未启停业务服务、未修改真实 .env 或数据库、未提交或推送。服务重启加载新版后，新创建的日志文件使用新格式。

### 2026-10-17 综合分析页默认预览首个文档

用户根据截图要求左侧默认展示第一个文档，不再等待点击引用。读取交接后复用现有阅读器，保留全部既有前后端改动。

- `ProjectAnalysis.tsx` 从按文件顺序返回的项目 sources 中选首个有 version_id 的文档作为默认预览，不依赖报告、解析批次或引用。已有手动引用选择优先，轮询不会抢回默认文件；文件转换完成后随原有轮询自动打开。无可预览版本时才显示加载/准备提示。
- `CitationViewer.tsx` 支持仅传文件版本与名称的普通预览，复用 PDF.js、工具栏及虚拟页，不伪造引用或高亮；引用模式继续保留页码定位、摘录和反向定位。手机端未点击引用时也能通过“文档预览”切换查看。
- 验证：pnpm typecheck 通过；synthesis.spec.ts 桌面 1440px 与手机 390px 共 16 passed（1.2 分钟），涵盖无解析/无报告默认预览、转换后自动显示、引用切换及轮询不抢焦点，原有报告展示与引用回归通过。两种尺寸的默认预览截图已查看，位于 apps/web/test-results/synthesis-默认预览首个文档，点击引用后轮询不抢回默认文件-{desktop,mobile}/default-document-preview.png。`git diff --check` 通过。

复用已有 4400 前端开发服务，浏览器 API 全部拦截，未调用真实模型或改写业务数据；未重启业务 API/worker/beat，未提交或推送。

### 2026-10-17 Agent 断连重试核查与诊断详情补全

用户询问 RemoteProtocolError 是否重试/降级，并反馈没有详细上游响应。读取交接后只读查询本地 API 的功能配置及最近 100 条分析调用记录，未改写配置或调用真实模型。

现场事实：

- analysis 功能 failover_limit=1、max_total_requests=10、deadline_seconds=1200；主模型 deepseek-v4.1-flash 的 extra_retries=1。前 3 个候选同属供应商 12，第 4 个来自供应商 1。级数 1 明确禁止使用后备模型。
- 报告18/人员要求/第4次运行中的 invocation c0cd3301-1eeb-42d5-bd40-70aa3edec776：调用7901和7903分别为首次和重试，耗时62061/62219毫秒，均为 RemoteProtocolError、status=unknown、http_status=null。重试已经发生；历史只有异常类型，无法确认具体断连原因或还原未保存的响应。

改动：

- `adapters/agent_chat.py` 记录经过统一脱敏与限长的最底层传输错误消息；未收到 HTTP 响应时明确说明无正文可记录。HTTP 错误继续保留实际响应或 SDK 解析的错误 body。
- 流式异常额外保留已收到的响应状态、已接收数据块数与白名单请求标识，避免 SDK 丢失已收到的响应头。流开始的200只用于诊断，不改判未完成请求成功；不序列化请求对象、请求正文、整份响应头或半截模型输出。
- 实际重试/故障转移策略未改，未调整线上配置；建议需要降级时将级数设为2以上，并将不同供应商模型放在靠前候选。
- 同步设计12；新增真实 SDK + httpx MockTransport 回归，覆盖连接前失败、流式0/1块中断、脱敏、同模型重试成功、耗尽后换源、级数1禁止换源以及0额外重试的边界，逐条检查调用落账。

验证：相关适配器/路由/装配测试60 passed（7.25秒）；后端全量 tests/unit tests/contract：714 passed / 9 skipped（41.17秒）；Ruff、import-linter 5 kept / 0 broken、`git diff --check` 通过。

新增诊断在业务 worker 加载新版后对新失败生效，旧记录无法补回。未重启业务服务、未修改真实 .env 或业务数据库、未提交或推送，保留此前日志及前端改动。

### 2026-10-17 接口访问日志按时间窗口限频

用户要求继续实现同一方法、路径和状态码的成功请求日志限频，错误和解析 Agent 关键日志逐次保留；随后明确默认值直接写在代码中，不需要写入配置文件。开始时 UTF-8 读取本交接，沿用 karpathy-guidelines，未使用子代理，保留既有改动。

- `api/logging.py` 的 `RequestLoggingMiddleware` 默认参数为 `access_interval_seconds=60`；装配时可用代码传参调整，0 关闭限频。已移除本轮暂存的环境变量接线，`core/settings.py`、两个 `.env.example` 和 Compose 不再包含访问窗口配置，未修改真实 `.env`。
- 正常完成的 2xx/3xx 按方法、实际路径和状态码分别计时，查询参数不参与分组；首条立即输出，重复访问不延长窗口，到期后再次输出。实际路径仅在内存中使用，日志仍记录路由模板；请求执行、响应及请求 ID 不受影响。
- 修复原草稿在超过 4096 个分组时提前淘汰有效窗口的问题，改为单调时钟与按输出时间排序的过期清理，线程锁保证并发检查与更新一致。每个 API 进程独立计时，内存随一个窗口内的不同分组数量增长；缓存清理后不补发历史计数，`suppressed_count` 只表示仍保留的累计省略数。
- 4xx、5xx、异常、断流和取消均绕过限频。已发送 200 后中断仍以 ERROR / interrupted 逐次记录，健康检查也不能按成功降为 DEBUG。已有 Agent 生命周期、工具、核验、模型请求/重试/换源日志继续保留；仅对 worker 一处过长的日志级别表达式换行以通过 Ruff。
- 同步工程20与本地启动指南，补齐默认窗口、代码覆盖、0 关闭、分组隔离、并发、过期边界、5000 路径及断流/取消的回归。

验证：最终后端 `tests/unit tests/contract` 为 **729 passed / 9 skipped**（38.31 秒），包含访问日志及已有 Agent 日志验证；有两条既有 structlog 异常美化提示，不影响通过。相关 Ruff、import-linter 5 kept / 0 broken、`git diff --check` 通过。

未重启业务 API/worker/beat、未改写业务数据库或调用真实模型，未提交或推送。API 加载新版后限频生效；本轮未改 SQL 或前端，未跑数据库集成与前端测试。

### 2026-10-17 按用户纠正改为轮询接口可选装饰器

用户明确上一轮理解有误：需要装饰器形式，只有前端循环查询的部分接口才限频，不能全局应用。本节取代上一节的全局默认窗口方案。UTF-8 读取交接后沿用 karpathy-guidelines，未使用子代理。

- `api/logging.py` 提供 `@throttle_access_log()`，默认 60 秒直接定义在装饰器中；`@throttle_access_log(15)` 可为单个接口调整，0 关闭。装饰器仅标记并返回原函数，不包装调用，保持 FastAPI 参数/依赖解析及同步/异步调度。
- 中间件根据实际匹配端点的标记决定是否限频，未装饰接口逐条记录，移除全局 `access_interval_seconds` 参数。不同窗口长度的缓存独立清理，沿用方法、实际路径、状态码分组与错误/异常逐次记录规则。
- 已逐条追踪前端轮询链路，只标记 11 个 GET：任务详情、项目详情、知识库详情、项目分析状态、报告详情、专题记录、问答结果，以及模型测试期间一起刷新的 LLM 设置/供应商/模型/功能四项列表。未标记上传、解析提交、报告操作、配置写入、文档读取、搜索或其他普通查询。完整路径与前端来源见工程20。
- 解析 Agent 的关键日志保持原样；同步本地启动指南、工程20及装饰器示例。无环境变量或配置文件新增项。

验证：访问相关专项 11 passed；最终 `tests/unit tests/contract` **731 passed / 9 skipped**（36.59 秒），覆盖同步参数校验和请求上下文、异步调用、未装饰 GET/同路径 POST、0 关闭、不同窗口互不干扰、实际路由选取范围、错误/断流/取消及原有 Agent 日志。相关 Ruff、import-linter 5 kept / 0 broken、`git diff --check` 通过。全量仍有两条既有 structlog 异常美化提示。

未启停业务服务、未修改真实 `.env` 或业务数据库、未调用真实模型、未提交或推送。API 加载新版后生效；本轮未改 SQL 或前端，未跑数据库集成与前端测试。

### 2026-10-17 按用户要求提交已审查更改

用户在审查全部未提交更改后明确要求提交。本次统一纳入轮询接口日志装饰器、周期派发降噪、可读日志文件名、Agent 关键诊断与断连详情，以及前端文档默认预览、待核对事项/失败提示和配置/上传文案改进，包含对应测试与文档。

提交前审查未发现明确新增缺陷；最近完整后端验证 731 passed / 9 skipped，审查阶段补验日志与 Agent 相关 69 passed、前端 48 项单测及类型检查通过。提交前差异检查通过，未重复运行已通过且代码未变化的测试。

使用中文提交信息，不添加作者说明；未推送、未启停业务服务、未修改真实配置或业务数据库。

### 2026-10-17 修正轮询限频按实际 URL 分组导致的重复摘要

用户反馈已加装饰器的接口仍在短时间内多次记录。UTF-8 读取交接后检查当前 API 日志：同一进程在一轮查询中为专题记录接口输出 13 条 200 摘要，路由模板完全相同。原实现按带 report_id/module_key 的实际 URL 分组，每个专题各获得一个窗口；测试此前也将不同资源各自记录当作预期，未覆盖用户需要的接口级合并。

- `RequestLoggingMiddleware` 改为按「方法 + 路由模板 + 状态码」计时，与输出字段一致。同一个已装饰接口下，不同项目、报告、专题以及查询参数共用窗口；不同接口、方法、状态码仍分别处理。
- 可选装饰器、默认 60 秒及代码传参规则不变。未装饰接口、4xx/5xx、异常/断流/取消及 Agent 关键日志保持原行为。
- 新增按业务 `include_router` 方式装配的真实 ASGI 回归：两份报告各 13 个专题并发查询，窗口内只记一条摘要；59 秒时更换参数仍不输出，60 秒边界重新记录，另一接口独立，业务查询日志及全部响应保留。修正原测试中“不同路径参数必须各记一次”的错误预期，同步两份日志文档。

验证：日志与 Agent 专项 **42 passed**（21.60 秒）；Ruff、import-linter 5 kept / 0 broken、`git diff --check` 通过。业务进程仍是无 `--reload` 的 API，未重启；加载新版后采用路由模板分组。未修改真实配置或数据库、未调用真实模型、未提交或推送。

### 2026-10-17 简化日志字段并记录北京时间与代码位置

用户希望减少日志冗余字段，缩短 request_id，记录北京时间及真实代码位置，接口访问摘要定位接口代码。UTF-8 读取交接后沿用 karpathy-guidelines，保留上一节按路由模板限频的未提交修复，未使用子代理。

- 统一格式化器的公共字段仅保留 `timestamp`、`level`、`event`、`location`。时间固定为 `Asia/Shanghai`，带 `+08:00` 并保留毫秒；服务目录和文件名 PID 继续区分服务及进程，不再逐条添加 `service`、`process_id`、`logger`。标准 logging 被其他 handler 格式化后附带的 message/asctime 缓存不再重复输出。
- 普通日志使用 LogRecord 的真实调用路径和行号，项目代码缩短为 `tender/...py:行号`。接口摘要从匹配端点读取定义位置，解开遵守 functools.wraps 的业务装饰器，支持同步与异步；包含路由装饰器时位置从定义前的装饰器首行开始，无匹配端点时回退到中间件调用处。
- 自动 request_id 改为 12 位 URL 安全字符（72 位随机值），响应头、请求状态及日志上下文保持一致。外部合法 ID 原样传递，真实任务与业务 ID 不截短。正常访问省略 `outcome=completed` 和零值 `suppressed_count`，中断与非零省略计数仍记录。
- 保留递归脱敏、异常堆栈、大小限制及 Agent 关键业务字段；同步工程20与本地启动指南。未新增环境配置项，文件切分时区仍由 LOG_TIMEZONE 控制，默认与北京时间均为 UTC+8。

验证：日志及 Agent 专项 **48 passed**（17.82 秒），覆盖北京时间跨 UTC 日期、JSON/文本格式、标准/结构化日志真实调用行、同步/异步/包装端点位置、404/405、短 ID 并发及外部长 ID 保留；原有限频、异常、轮转、并发与上下文回归通过。完整后端 `tests/unit tests/contract` **738 passed / 9 skipped**（34.99 秒），保留两条既有 structlog 异常美化提示；Ruff、import-linter 5 kept / 0 broken、`git diff --check` 通过。

未启停业务 API/worker/beat、未修改真实配置或数据库、未调用真实模型、未提交或推送。运行中的服务需重启加载新版后使用精简字段及修正后的轮询限频；本轮不涉及前端或 SQL，未重复执行前端与数据库集成测试。

### 2026-10-18 固定日志顺序、精简 Worker，并将堆栈写入同目录文本错误文件

用户继续要求解释并精简 outcome/suppressed_count，缩短 event，固定 Worker 字段顺序，未知异常保留堆栈；工作中明确堆栈应写入文本错误日志，且错误与普通日志必须位于同一目录。本节取代上一节继续输出省略计数及 JSONL 堆栈的约定。读取交接后沿用 karpathy-guidelines，保留全部未提交更改，未使用子代理。

- `api/logging.py` 删除 outcome/suppressed_count 输出与内部省略计数；访问事件使用 `http` / `http.abort`。保留按方法、路由模板和状态码的可选装饰器限频，4xx/5xx、中断/取消仍逐次记录。
- 统一格式化器按 timestamp、level、event、location、request_id、task_id、job_id、report_id、run_id、module_key、invocation_id 排序；其余业务字段按名称排序，堆栈最后展示。省略顶层 None/空字符串，保留 0/False。
- Worker 及 Agent 事件改为 task.start/end/fail/retry、report.start/end/abort、module.start/end/fail/cancel、tool.start/end/abort、model.request/response/retry/failover 等短名。任务名仅在开始/失败/重试显示，移除重复 execution_state、首次零重试次数及失败后冗余 INFO 结束记录；task.end 仍仅表示函数正常返回，不代表业务分析成功。
- 专题上下文保留 report_id/run_id/module_key，项目 ID 与 attempt 只在对应开始事件提供。模型功能与 purpose 仅在 model.start 提供；请求结果不再复制整份 CallRecord，模型/供应商快照仍完整写入调用账本，重试/路由行为未变。
- file/both 模式下，普通 JSONL 和控制台仅显示错误摘要；同一服务目录的 `日期.时-分-秒.PID.序号.error.log` 用 UTF-8 文本保存 ERROR/CRITICAL 及所有带堆栈记录（包含 WARNING 容错日志）。两类文件分别按相同日切、大小分片、保留清理规则管理，记录与整段堆栈不跨文件拆开。纯 stdout 模式继续输出堆栈，不创建文件。新错误文件未使用子目录。
- 补齐文件预处理、解析引用保存、索引、问答、派发、证据补读、模型客户端关闭和检索回退中的异常堆栈。API 兜底及 Celery 失败仍留存；Celery 没有显式 traceback 时取异常对象自身 traceback。长堆栈保留首尾及最终原因，其他字段过大时优先保留定位、关联和异常。保留既有未知凭证脱敏边界，未采集局部变量、文档或模型请求正文。
- 更新工程20和本地启动指南，包含字段顺序、事件名、同目录错误文件与查看命令。

验证：日志/Agent/相关 Worker 专项 **95 passed**（24.08 秒）；最终完整后端 `tests/unit tests/contract` **745 passed / 9 skipped**（35.90 秒）。覆盖字段顺序与空值、同目录两类文件及 stdout 摘要、WARNING 堆栈分流、错误文本切分/保留、长堆栈尾部、索引/问答捕获后先写日志再更新失败状态、API 与 Celery 堆栈关联及脱敏、stdout-only 堆栈保留；原有线程/进程隔离、限频和 Agent 回归通过。Ruff、import-linter 5 kept / 0 broken、`git diff --check` 通过。全量保留两条既有 structlog 异常美化提示。

未启停业务 API/worker/beat、未修改真实配置或数据库、未调用真实模型、未提交或推送。运行服务加载新版后产生新格式；已有日志保持原样。本轮未改前端、SQL 或启动脚本，未重复执行相应测试。

### 2026-10-18 同日跨重启追加共享日志分片

用户希望一天多次启动继续使用同一日志文件，去掉文件名时分秒并减少文件数，同时保留按天切分和大小分片。UTF-8 读取交接后沿用 karpathy-guidelines，保留此前全部未提交更改，未使用子代理。

- `DailyFileHandler` 改为 `日期.序号.jsonl` 与同目录的 `日期.序号.error.log`，例如 `2026-10-18.001.jsonl`。同一服务多个进程及同日重启共用最新分片，不再按启动时间或 PID 创建文件；跨天使用新日期，只有追加会超出大小上限时才递增分片。
- 初始化/跨天扫描当天新格式的最大数字序号；持续写入时跟进其他进程已创建的下一分片，并读取真实文件大小再决定是否分片。支持 999→1000 及重启后从 1000 继续追加，不覆盖或回填旧分片。
- 每个服务目录固定 `.write.lock` 协调文件，Windows 使用 msvcrt 字节锁，POSIX 使用 flock。写入完整记录、检查大小、切换分片和清理都在锁内执行；每条记录写完关闭句柄，异常进程退出由 OS 释放锁。锁文件不参与清理，也不随启动重新命名；等待超过 5 秒按现有错误回退路径写 stderr。无新增依赖或配置项。
- 旧版含时间/PID 或随机标识的文件保持原样，不迁移、不追加，仍按原保留天数清理。普通日志与错误文本继续分开、位于同目录，完整 JSON 记录和多行堆栈不跨分片拆开。更新工程20与本地启动指南。

验证：先验证日志/Agent 专项 **60 passed**（20.82 秒），随后补充进程绕过 finally 退出后的锁释放回归；最终完整后端 `tests/unit tests/contract` **751 passed / 9 skipped**（40.87 秒）。两个真实子进程同时写入，再换新进程重复运行，共 160 条摘要及堆栈；未达上限时两类日志各一个文件，低上限下分片连续、大小合规、条目无丢失且堆栈无交错。另覆盖同日不同时间重启、跨天、999/1000 边界、两类文件与新旧命名保留清理。Ruff、import-linter 5 kept / 0 broken、`git diff --check` 通过；全量仍有两条既有 structlog 异常美化提示。

未启停业务服务、未修改真实配置或数据库、未调用真实模型、未提交或推送。业务服务重启加载新版后开始使用共享文件；本轮未改前端、SQL 或启动脚本。

### 2026-10-18 修复日志审查发现的三处边界问题

用户要求修复上一轮审查确认的问题。UTF-8 读取交接后沿用 karpathy-guidelines，保留既有未提交更改，未使用子代理。

- 索引/问答入口对 `TenderError` 只格式化业务异常自身堆栈，避免展开原始 SDK 异常链、重新写出数据库供应商密钥；未知异常继续保留完整异常链。用实际问答 Agent、RoutingModel 和 AgentChat 配合离线 HTTP 429 响应复现等待预算不足，确认账本与错误文件都不含模拟密钥，堆栈仍保留调用位置和业务原因。
- 格式化器在字段收敛后检查最终 JSON/文本的 UTF-8 字节数（预留换行）；超限时继续缩短最大字段，堆栈保留首尾。覆盖长中文、表情、控制字符及 JSON 转义，两类分片均不超过配置的 64 KiB，后续记录仍正常写入。
- 共享分片在写锁内检查最后一个字节；尾部缺少换行时保留旧片，转入下一分片。覆盖同进程恢复与同日重启，以及半个 UTF-8 字符的残缺尾部，避免新日志拼入坏行。同步工程20及本地启动指南。

验证：新增回归先复现缺陷（10 failed / 1 passed），修复后相关专项 **13 passed**；最终完整后端 `tests/unit tests/contract` **762 passed / 9 skipped**（45.44 秒）。Ruff、import-linter **5 kept / 0 broken**、`git diff --check` 通过；保留两条既有 structlog 异常美化提示。完整验证后只调整注释、文档和测试换行，未再改执行逻辑。

未启停业务服务、未修改真实配置或数据库、未调用真实模型、未提交或推送。运行服务需重启加载修复；本轮未改前端或 SQL。

### 2026-10-18 收敛模型/工具调用日志并统一短 ID

用户要求模型与 Agent 工具只在完成时各记录一次；模型日志要带模型名、输入/输出 token 和耗时，工具日志要带名称、参数和耗时；Celery task_id 与 request_id 共用短 ID 生成规则。UTF-8 读取交接后沿用 karpathy-guidelines，仅修改相关运行日志、ID 生成与对应文档/既有断言。

- `RoutingModel` 每次逻辑调用在 finally 输出一条 `model.call`，包含最终模型名、跨本次重试/切换累计 token、整次耗时与状态。删除模型调用开始、逐 HTTP 请求、重试、切换、冷却、停止等运行日志；逐次请求记录仍写模型调用账本，路由、重试及预算行为不变。
- Agent 工具执行后只输出一条 `tool.call`，包括工具名、工具参数、状态、耗时及必要错误摘要；缓存重放也只记一条 `status=cached`。移除 start/end/abort 多次记录和额外证据计数。参数继续经统一脱敏与日志大小限制处理。
- 新增 `new_short_id()`，请求 ID 与 Celery 自动 task_id 共用 `token_urlsafe(9)`，均为 12 位 URL 安全随机字符；显式提供的 ID 保留。覆盖 Celery `send_task`、`apply_async` 和同步/eager `apply`。
- 更新工程20、本地启动指南及现有日志断言。后续审查发现 AgentChat 单测仍断言已移除的 `stream.*` 事件，已改为断言不产生独立流事件；同时清理流式适配器遗留的未使用导入、计时变量和过时注释。

静态检查：初次修改后的 Ruff、`compileall`、`git diff --check` 通过；本次审查修复后的 AgentChat 源码与单测 Ruff 通过，`git diff --check` 通过。未运行测试、未调用真实模型、未启停业务服务；加载新版需重启服务。

### 2026-10-18 按四层规范收敛 apps/api 代码边界

用户要求按「api 只做入口、service 承载业务、crud 只访问数据库、agent 管智能体」规范优化 `apps/api`。UTF-8 读取本文件后，保留既有未提交改动，未使用子代理，未自动提交。

- `api/` 路由只保留 DTO、依赖解析、调用服务和响应返回。`config.py`、`llm.py`、`knowledge.py`、`projects.py`、`jobs.py`、`project_files.py`、`versions.py`、`parsing.py` 中直接 SQL、事务和业务判断均已迁出；`api/` 不再 import `crud`/`adapters`/`worker`，也不执行 `select/insert/update/delete`。路由边界通过 `translate_service_errors` 统一保持成功返回、失败抛 `ApiProblem` 的既有直接调用契约。
- 新增 `services/`：项目、文件、版本、解析、任务、知识库/分析、配置中心、LLM 管理均有业务服务。服务负责权限与状态判断、版本冲突、事务编排、响应整形；不直接持有 ORM `Connection`，数据读写统一调用 `crud`。
- 新增 `crud/`：项目、文件、版本、解析、任务、知识库、配置、LLM 的 SQL、锁与事务方法集中在此层。配置审计/影响确认 SQL 从 `config/audit.py` 迁入 `crud/config.py`；LLM 的冷却表达式、测试账本、软删除、绑定替换和调用查询全部收口，CRUD 不判断“查不到意味着什么”。
- Agent 代码已迁入 `agent/`：`deep_analysis.py`、`analysis_research.py`、`analysis_skills.py`、`qa_agent.py`、`agent_runtime.py`、`agent_checkpoints.py`；`application/analysis_contract.py` 保留运行版本常量，避免 application 反向依赖 agent。服务、worker、集成测试和运行命令均已切换到新路径；`apps/` 与 `docs/` 中的源码、文档和命令不再引用旧 `tender.application.*` Agent 路径。
- `pyproject.toml` 分层契约扩展到 `domain ← ports ← application/adapters ← crud ← agent ← services ← api`；新增 AST 契约测试检查直接 import，防止 `forbidden` 契约沿正常调用链误报，也防止入口层或服务层日后绕过边界。

验证：`ruff check apps/api/src apps/api/tests` 通过；`lint-imports --config apps/api/pyproject.toml` **5 kept / 0 broken**；完整离线 `pytest apps/api/tests/unit apps/api/tests/contract -q` **766 passed / 9 skipped**（43.34 秒，保留两条既有 structlog 异常美化提示）；`test_deepagents_runtime.py --collect-only` 可正常收集 **19 个数据库集成用例**；`git diff --check` 通过（仅 Git 的 CRLF 转换提示）。

未启停业务服务、未连接数据库、未调用真实模型、未修改真实 `.env` 或业务数据、未提交或推送。本机 5432 端口无监听，`TENDER_RUN_DB_TESTS=1` 的隔离 PostgreSQL 集成测试本轮未重跑；配置与 LLM 管理真实数据库路径需在数据库可用时补验。

### 2026-10-18 将职责分层归回既有架构并建立文件树规则

用户明确说明 api/service/crud 是职责定义，上一轮将其理解为必须新建同名目录有误。本轮按用户要求归回现有端口与适配器结构，并提供后续文件放置规则。本节替代上一节“按四层规范”新增 services/crud/agent 目录的约定。

- 原 `services/` 的业务用例归入 `application/`；知识库管理流程使用 `knowledge_service.py`，原 `knowledge.py` 保留知识处理纯函数。原 `crud/` 的实现归入 `adapters/pg/repositories/`，类名改为 Repository；KnowledgeCrud 的方法直接合并到已有 KnowledgeStore/KnowledgeSession，不保留额外包装。
- Agent 编排文件归回 `application/`。原 `agent_checkpoints.py` 包含 PostgreSQL 连接与 DDL，按实际职责移至 `adapters/pg/checkpoints.py`；部署命令改为 `python -m tender.adapters.pg.checkpoints`，调用者与文档已同步。轻量运行版本契约保留在 `application/analysis_contract.py`。
- 用例构造函数接收 `ports/repository/` 协议，具体仓储与网关由 `core/di.py` 注入；不接收 Engine、不创建具体仓储、不导入装配点。新增 `ports/config_registry.py` 承载 ActiveConfig/ConfigReader，原 ConfigRegistry 仍为实现并兼容导出 ActiveConfig。
- 任务配置快照通过事务端口 `snapshot_for_job()` 与任务共用连接，连接只在仓储内传递；保留原配置快照与回源行为。LLM 完整性错误在仓储转换为 RecordConflict，业务重名提示与全局 409 回包保持原语义。既有 api/errors.py 仍允许导入 IntegrityError 做兜底映射，不执行 SQL。
- 分层契约恢复 api/worker → application → ports → domain、application/adapters 互不引用；AST 契约检查直接/相对导入，并禁止再次创建 services/service/crud/agent 并列目录。新增假端口回归验证配置读取在事务前、快照和任务同事务、冲突回滚与 409 映射。
- 新增 `docs/工程/21-后端文件树与放置规则.md`，含实际文件树、职责映射、依赖与事务规则、新功能示例、验证命令。根 `AGENTS.md` 增加后端必读及不得为错误目录放宽检查的规则；同步工程10、11、17、设计16及文档索引，删除工程10中过时的计划目录树。

验证：完整离线 `tests/unit tests/contract` **772 passed / 9 skipped**（51.07 秒），保留两条既有 structlog 提示。隔离 PostgreSQL 18.3 集成用例 **75 项累计通过（分批补验）**：配置/模型等26项、报告/Agent/知识库43项，最后6项针对旧引用修正后全过（8.76 秒）。集成中发现上一轮夹具未注入 configs、仍从 API 取内部函数/常量/异常；已改为正式配置装配及真实归属模块，不新增生产兼容包装。Ruff、import-linter **5 kept / 0 broken**、差异空白检查通过。

隔离数据库位于 `.tmp/layout-postgres`，仅绑定 127.0.0.1:55438；在该临时库执行迁移后验证，测试结束已停止。未启停业务 API/worker/beat，未改真实 .env、业务库或数据，未调用真实模型，未提交或推送。旧新增目录原内容移至 `.tmp/layer-refactor-before/` 备份；撤销了上一轮6组 Agent 错误移动的暂存记录，仅更新索引、不还原工作文件，本轮所有改动保持未提交。

### 2026-10-18 在既有架构内按业务模块归组

用户先要求业务分类，随后要求先独立分析合理性，明确不要迎合或收到方案立即执行；该偏好已写入 `C:/Users/wph98/.codex/AGENTS.md`。用户认可分析后授权开始改造，并进一步确认：已确定的业务即使只有一个文件也建目录，便于后续扩展。本轮据此实施，未创建空的预留业务目录。

- 一级架构保留 api/application/ports/adapters/domain/worker。API、用例、仓储协议与仓储实现统一使用 projects、documents、knowledge、analysis、llm、configuration、jobs 业务目录；每层通用代码放 shared。外部端口和适配器按模型、文档、配置、存储、任务归组；领域代码按 documents/knowledge/shared，worker 业务任务也已归组。
- core、现有 config 基础设施、数据库连接/锁和 ORM 表定义按技术职责保留。包初始化文件保持轻量，不加兼容转发或重导出旧入口。保留 KnowledgeStore 中紧密关联的知识/报告查询，不为目录对称复制 SQL 或套新 CRUD。
- 共迁移94个源文件；原知识库 HTTP 模块拆为 api/knowledge/routes.py 与 api/analysis/routes.py，共用严格 DTO 基类放 api/shared/dto.py。同步所有源代码、测试、脚本与当前文档导入。application/analysis/skills.py 的资源定位随目录深度调整，仍读取 tender/resources/parse_skills。
- Celery Python 注册模块已切换新路径，但既有消息名 tender.worker.tasks.*、tender.worker.knowledge.*、beat 名称和队列路由不变，历史消息继续可消费；新增回归实际运行假仓储派发并验证三类消息名与任务注册。检查点命令为 python -m tender.adapters.pg.analysis.checkpoints。
- 根 AGENTS.md、工程10/11/17及工程21文件树同步。工程21按实际源码生成目录索引，明确单文件业务也归组、技术基础设施例外、共享代码条件、业务依赖和事务边界。架构契约新增根目录禁止散落业务文件、跨层业务名一致性检查，原有依赖约束没有放宽。

验证：完整离线 `tests/unit tests/contract` **785 passed / 9 skipped**（49.05秒）；完整隔离 PostgreSQL `tests/integration` **75 passed**（58.13秒）。保留既有 structlog 提示。Ruff、import-linter **5 kept / 0 broken**、git diff --check 通过。迁移前后完整 OpenAPI 字典完全一致，共65条路径；94个迁移文件剔除导入后的 AST 对比，仅路由拆分与资源相对路径发生预期差异。

验证过程中修正了一处机械字符串替换影响动态 Celery 任务名的问题，并补充任务注册回归；日志测试中的旧文件位置与路由枚举已按实际新位置更新。上述修正均已包含在最终验证中。

迁移前文件快照、映射和 OpenAPI 对比位于 `.tmp/business-grouping/`。复用本轮隔离数据库 `.tmp/layout-postgres`，仅绑定127.0.0.1:55438，测试结束已正常关闭，pg_ctl 返回 server stopped，并确认测试进程退出。未启停业务服务、未改真实 .env 或业务数据库、未调用真实模型、未提交或推送。

### 2026-10-18 编写当前后端架构与设计取舍说明

用户在讨论 ports、adapters 与依赖注入后，要求提供完整文档解释当前后端架构及设计原因。本轮先核对交接、路由、用例、协议、仓储、Worker、配置和架构检查，再更新既有工程11，未新增重复的架构文档，未修改源码或检查规则。

- `docs/工程/11-架构设计.md` 重写为“当前后端架构与设计取舍”：13节、4张 Mermaid 图，解释进程拓扑、业务目录、Protocol 与依赖注入、创建项目/文档解析时序、专题分析、数据事务、配置快照、日志、部署、设计成本和开发指引。所有已确定业务继续按目录归组，包括单文件模块。
- 将旧稿中的固定字段抽取、旧队列及未落地流程从当前架构说明中移除，区分源码实现与现场部署状态。明确 Beat 发定时消息、Worker 执行派发；任务 SSE 当前轮询数据库；Celery 消息名不随 Python 路径迁移。
- 如实记录边界：Worker 仍有直接 ORM 操作和局部装配，config 的 registry/snapshot 仍含持久化；Protocol 不自动执行运行时检查，后端未接入 mypy/Pyright；配置采用快照与实时值混合语义；数据库与队列/存储/模型不具备全局事务保证。目录一致性测试仍要求当前七个业务存在，未擅自放宽，也不推广为所有新功能必须补齐各层。
- 工程21增加架构说明入口，将“调用方向”修正为代码依赖方向，并补充已有实现边界。文档索引增加当前实现入口和工程21表项，工程10中指向工程11坐标规则的小节引用已同步。

验证：4份工程/索引文档通过 UTF-8 解码、75个本地链接、40个源码路径、13个导航锚点和代码围栏检查；`git diff --check` 通过。未重新运行后端测试；工程11中的785项离线与75项数据库结果明确标记为此前目录改造记录。仅文档变更，未启停服务、未访问业务数据库、未调用真实模型、未提交或推送。

### 2026-10-18 修复 Worker 数据访问、协议检查与任务配置边界

用户要求把上一份架构文档揭示的三项问题一并修复。本轮按既有 ports/adapters 结构实施，未增加同义架构层，所有业务文件仍按业务目录归组。保留此前工作区累计改动，未使用子代理、未提交或推送。

- Worker 数据访问收口：文档任务的读取、认领、执行起点、版本及解析产物落库迁入 `adapters/pg/repositories/documents/pipeline.py`；派发查询/标记迁入 `jobs/dispatch.py`；模型候选、策略、账本与测试维护迁入 `llm/runtime.py`；任务锁通过 `ports/jobs/coordination.py` 与 PostgreSQL 实现接入。依赖经 `core/di.py` 装配，Worker 不直接导入 SQLAlchemy、`adapters.pg` 或配置持久化实现，并增加架构契约阻止回流。保持原有 SQL 条件、事务边界和历史 Celery 消息名称。检查点连接也移至装配点提供，但未声称所有非数据库客户端都已统一装配。
- 中立数据类型：`NormalizedElement` 移至 `domain/documents/element.py`，PDF 检查结果移至 `ports/documents/inspection.py`，避免仓储反向引用 application 或具体 PDF 适配器。
- 自动类型检查：dev 依赖加入 mypy 并更新锁文件，范围为全部 ports 和 `core/di.py`；使用 `follow_imports = "silent"` 读取真实实现类型。`test_protocol_types.py` 在常规离线测试中运行正向检查，并验证真实仓储的缺方法/错误签名确实报错，防止通过 skip/Any 绕过。修复 OfficeConverter 缺少关闭方法、KnowledgeStore 多余迭代声明、ProjectRepository.list 遮蔽内置 list 的注解问题。尚非全项目 strict，Any/字典内部字段仍需行为验证。
- 配置快照：`config/schema.py::document_execution_snapshot` 固定轮询初始/最大间隔、轮询上限、转换/解析超时、转换额外重试次数六项。项目文件上传、直接解析、知识资料处理三个入口写入 `job.config_snapshot.execution`，来源为 `created`，没有活动版本时同样保存默认值。旧任务优先从不可变完整快照补齐；没有历史快照时只固定首次执行配置并标记 `legacy_first_execution`，记录补齐时间，在行锁内复查避免并发使用不同值。事务内 snapshot_for_job 不再因显式 None 回源读取更晚版本。利用已有 JSONB 字段，无新迁移。
- 保留的必要边界：派发并发和间隔继续实时读取，取消/权限/部署连接与凭证不冻结；数据库与队列没有全局事务，原有提交前投递语义未扩展成 Outbox。旧任务缺少历史配置时无法还原创建时值，文档已明确这一限制。
- 文档与验证入口：更新工程11架构说明、工程21实际文件树、工程18配置限制、质量08配置生效语义以及根 AGENTS.md。新增 `scripts/check-backend.ps1` 统一运行 Ruff、import-linter、unit/contract（含 mypy）；脚本使用 UTF-8 BOM 兼容 Windows PowerShell 5，并通过同一 Python 的 UTF-8 CLI 输出中文契约名称。

验证：Worker/配置/边界专项55项通过；完整离线 **791 passed / 9 skipped**（52.71秒），mypy **40 source files 无错误**，Ruff 通过，import-linter **5 kept / 0 broken**。完整隔离 PostgreSQL 集成 **78 passed**（58.21秒），包括新增的配置变更不影响新任务预算、两类旧任务补齐三项回归。保留既有 structlog 提示；未调用真实模型或解析服务。

文档和脚本收尾后，补验全部契约 **160 passed / 9 skipped**（含 DDL 与 mypy）；4份文档通过 UTF-8、代码围栏、48个本地链接及134个源码文件树条目核对。验证脚本通过 PowerShell 语法、UTF-8 BOM、真实架构 CLI 正常/失败退出码检查；最终 Ruff 和差异空白检查通过。

现场：复用隔离库 `.tmp/layout-postgres`，仅绑定 `127.0.0.1:55438`，迁移版本为 `0016_rate_limit_wait`。验证结束已通过 pg_ctl 正常关闭并确认测试进程24524退出。未启停业务 API/Worker/Beat，未修改真实 `.env` 或业务数据库，未进行现场部署。源码/测试的本轮改动前快照在 `.tmp/worker-boundaries-before/`；临时迁移脚本不得重跑。虚拟环境此前额外安装的 openpyxl/et-xmlfile 在 uv sync 后已恢复。

### 2026-10-18 修复批量上传资源限制与部分失败回执

用户要求修复上轮审查确认的两处问题。本轮只修改项目文件 API、对应业务用例及回归测试，保留其他累计改动和现有目录结构，未使用子代理。

- `application/projects/files.py` 集中声明100个文件和1 GiB总量限制，提供同一纯校验函数供 API 预检和用例最终检查复用。`api/projects/files.py` 在调用任何文件读取前检查数量与元数据总量（包含 ZIP）；大小未知或低报时，每次读取不超过单文件上限与批次剩余额度的较小值，加一个超限探测字节。按已读字节累计，超限立即终止，不继续读取后续文件；空文件与单文件超限的 HTTP 错误保持原有映射，读取后关闭对应上传句柄。
- 批量用例恢复对 `TenderError` 和 `BlobStoreError` 的逐文件捕获，失败写入 skipped 后继续处理下一文件，已成功入库的 added/jobs 回执得以保留。整批均失败时，存在临时失败返回503/ingest_unavailable且retryable=true；均为永久失败则返回422/upload_failed。未知异常继续抛出，不伪装成可跳过的文件错误。
- 新增测试按业务归组：`tests/unit/api/projects/test_upload_limits.py`、`tests/unit/application/projects/test_batch_upload.py`。覆盖101个文件/已知总量超限零读取、ZIP纳入总量、未知或低报大小按剩余额度限读、恰好达到预算仍接受、上传及替换的空文件/单文件超限、部分失败保留回执并继续、全部失败的重试标记，以及未知异常传播。

验证：新增首批测试先复现 **14 failed / 2 passed**，修复后专项16项通过；随后补充4项单文件错误映射回归。统一入口 `scripts/check-backend.ps1` 完整通过：Ruff、import-linter **5 kept / 0 broken**、离线 **811 passed / 9 skipped**（47.91秒，包含mypy正向检查与反向探针）。保留2条既有structlog提示；本轮4个源码/测试文件通过UTF-8与空白核对，`git diff --check`通过。

未修改数据库操作、迁移、队列或前端；本轮无需重新启动隔离数据库。未访问业务数据库、对象存储或真实模型，未启停业务服务、未修改真实配置、未提交或推送。

### 2026-10-18 将解析 Skill 适配为本项目运行规则

用户指出参考 Skill 不能照搬，因为参考项目的检索来源和结果格式不同。先核对资源、实际工具、快照和消费接口；用户确认保留13个专题及当前分类、中文字段、逐条JSON接口，技术专题继续聚焦项目背景与技术方案要求，随后明确授权实施完整计划。

- 使用 skill-creator 和 karpathy-guidelines；未使用子代理。读取工程21并沿用现有目录。原先工作树干净，本轮未提交或推送。
- 13个专题增加 `references/output_schema.json`，原样保留既有 `version/sections/title/layout/columns` 的公开结构和值。`application/analysis/output.py` 直接验证冻结JSON，检查版本、布局、非空及唯一分类/列名和额外属性；存在但无效的声明直接报资源错误，不静默回退。只有没有声明的历史快照保留原Markdown解析和三个历史专题分支。
- `policy.py` 按声明是否存在区分资源包：新包的技术品类细则正常加载，混合品类逐一加载且不默认服务类；旧技术快照保持原跳过参数细则的行为。声明、细则和示例仍纳入现有快照及哈希，没有引入磁盘回源、数据库迁移或运行时版本变更。
- 主Skill保留专题目标和有用的领域识别规则，移除重复通用协议，改为授权项目/参考资料检索、按已读block_id补读、complete_research后综合事项、逐条提交及独立引用。输出说明和全部原有示例改为模拟blocks与按顺序执行的submissions，明确演示容器不能直接提交，示例ID不能作为实际依据。
- 全面修正主文件与细则的冲突：商务限定合同履约；否决不再“宁可多提疑似”或靠强制措辞、星号推断后果；技术工程/货物/服务细则均服务方案并排除纯参数清单；评分保留同项公式、档次和扣分；保证金未命中只留缺口，明示免收才成事实；不同标段金额分别声明范围；格式保留全部层级和逐节点父子提交，不再限制三级或要求整棵数组。
- 保留企业业绩、人员、价格、开标、保证金和封装中有用的核对维度，改正将行业常见材料、时间精度、资格或后果当作当前项目默认事实的表达。所有原文出处、范围、数值、材料组合及条件都以实际证据为准。
- 工程14按当前v5流程重写，设计19同步原生声明、资源取舍、示例及兼容。HTTP、前端消费类型与数据库结构不变；新报告采用新资源，旧报告展示、恢复和主动补跑继续使用冻结Skill，要采用新规则需新建报告。

验证：新增 `test_native_skill_resources.py` 共73项回归，保存真实旧模板与旧技术资源作为兼容夹具；覆盖13专题格式完全一致、损坏声明不回退、快照哈希和品类加载、全部示例的真实结构/连续引文/定位校验，并以可控模型跑实际Agent图验证缺口、跨块归并、多标段、评分、四层格式树、跨文件修订及证据独立保存。旧技术加载测试已改为新行为。

统一入口 `scripts/check-backend.ps1` 通过：Ruff、5项架构契约、**884 passed / 9 skipped**（52.80秒，含mypy正向检查及反向探针），保留2条既有structlog提示。收尾修正格式细则中的旧数组措辞后，相关专项 **100 passed**（6.61秒）。13个Skill通过skill-creator的quick_validate；83份Markdown（81资源+2文档）、39个JSON示例、资源引用及文档链接通过检查；git diff --check通过。

本轮资源从94个文件增加到107个，仅新增13份JSON声明。改前完整资源与格式备份在 `.tmp/parse-skills-before.json`；一次性资源生成脚本之后有人工收尾修正，不应重新执行覆盖最终内容。离线验证只证明结构与确定性行为，不表示真实供应商模型已正确遵循全部领域规则。未访问业务数据库或对象存储、未调用真实模型、未启停业务服务、未修改真实配置、未提交或推送。

### 2026-10-18 持续优化检索覆盖与结果定位

用户提出持续目标“帮我持续优化解析skill和agent，确保解析准确不遗漏，展示美观易定位”。目标保持 active；以下是阶段进展，不代表真实模型完整性已验收。沿用上一阶段13专题、中文字段、JSON输出和新旧Skill快照约定；未使用子代理。

- 检索截断：`application/knowledge/retrieval.py` 排名阶段多留一个达标候选，区分恰好N条和被截断；阈值和返回数量不变。`analysis/research.py` 合并检索与扩展裁剪状态，专题工具在截断时提供 `search_limited/search_hint`，提示按子主题或限定资料继续检索，相同查询不会翻页。不暴露额外原文、分数或位置，不替代证据预算警告，问答协议保留。
- 关键词空召回：真实模型实跑大量组合查询为空；窄化为“报价表”才命中附件转引。新增回归先复现缺少反馈，再在关键词回退真正空召回时提示拆为单一概念或原文短语；不降低阈值，已读块去重后为空、语义检索空结果不误用该提示。此修正发生在首轮模型验收启动之后，首轮未包含新提示。
- Agent系统说明：修正旧的“Markdown定义输出、技术细则按需加载”说法，以运行时schema和已加载核心规则为准。真实资料核对后增加连续编号/评分表/格式清单沿边界已读ID补读，以及同一文件夹带其他项目条款时核对名称、主体和编号的指导；不新增强制全书扫描或业务分类。
- 前端阅读：沿用现有紫色视觉，引用入口显示页码和序号、支持换行与键盘焦点；技术要求增加事项层次；720px以下表格逐条展开字段；文档页头显示实际滚动页码。
- 往返定位：新增 `apps/web/src/lib/analysis/citations.ts`，多个结果共享同一原文时优先返回刚点击的事项；引用身份同时比较source_id、version_id、parse_run_id、element_id，防止跨版本串定位。ModuleMarkdown传回事项ID，ProjectAnalysis保存并用于反向定位。
- 文档：同步工程14与设计19的工具反馈、连续清单、同文件适用性和展示定位说明；实际材料与核对产物仅保存在忽略目录 `.tmp/skill-real-audit/`。

验证：检索/研究/综合专项62项通过；空召回修正后检索专项14项通过，最新统一入口 `scripts/check-backend.ps1` **888 passed / 9 skipped**（47.41秒），Ruff、5项架构契约及mypy正反检查通过，保留2条既有structlog提示。前端 `typecheck`、`build` 通过；`test` **51 passed**；`test:e2e synthesis.spec.ts` 桌面和手机 **18 passed**。评分截图滚动调整后专项补验 **2 passed**，已人工查看最终手机评分截图，字段、档次与页码按钮清楚。后端后续只改系统规则和检索提示，未再改前端。工程14/设计19通过UTF-8、代码围栏与本地链接检查；git diff --check通过。

真实资料只读核对：项目15当前只有 `2023-2024年通信工程监理招标项目招标文件.docx`，无关联参考库；source_id=13、version_id=3、parse_run_id=6，1135元素/137页，正式分块得到1130块。

- 第59页评分规则转引附件1，第103页技术要求转引附件3，当前资料未提供对应附件，应保留缺口，不能把旧报告的失败当作新Skill效果。
- 第17页夹带办公场地租赁项目公告；其160元/平方米·月限价不属于通信工程监理项目。第22页本项目限价为各标段折扣率K（非下浮率）100%。
- 第124页监理大纲列出12项编写内容，默认邻域只覆盖开头；正式ResearchSession以返回的已读ID连续补读，1次检索+4次补读读全12项并确认下一节，尾项引文正确回填第124页/元素1552。
- 确定性关键词回退探测：监理大纲15个达标块、保证金30个、评标办法24个，均只返回前6个并提示截断；最高限价2个、技术规范书2个，无截断。“保证金”首批主要是后部格式，说明不能靠一次命中判断完整。此探测未调用向量、重排或生成模型，不代表现场语义检索或真实模型决策已通过。

可复现材料：`.tmp/skill-real-audit/CHECKLIST.md`、`probe.py`、`probe-results.json`、`elements.json`、`project-knowledge.json`。后续应基于清单做隔离的真实模型验收，检查金额与范围、缺附件行为、长清单和后置条件，不能重跑旧报告混入新资源。旧报告18为partial，多数旧运行受断连/限流/取消影响，评分等出现无进展收尾；不据此评价本轮规则。

随后已执行首轮真实模型隔离验收：`.tmp/skill-real-audit/model_eval.py price_requirement_parsing`，使用当前analysis首选绑定deepseek-v4.1-flash（模型21），真实Agent图与verify_items，检索使用正式关键词回退，禁用向量与重排。凭证经现有装配点和解密函数仅在内存使用；业务资料权限每次重查；检查点为内存，成果/请求/响应写临时目录，没有创建或修改数据库报告、模型配置、调用账。

- 运行产物：`.tmp/skill-real-audit/model-price_requirement_parsing-144332/`，保存完整请求、响应、Skill快照、research、state、calls和summary。会话41074已正常退出，无仍运行的模型请求；后端检查会话92629也已结束。
- 结果：600.09秒达到隔离时限，23次模型请求（包含压缩和校验，最后一次取消）、45次研究工具、77块证据；供应商报告输入227227/output27494 tokens。完成研究登记，保存1项supported限价记录和4项报价表转引缺口，未final=true，summary的records=0指最终稿未生成，verified_items=1表示仍保留已核实事项。不能称为完整报价验收通过。
- 正确观察：限价记录保留K（非下浮率）100%和超限否决，引用第22页；附件4报价表缺失没有被编造。该轮未充分覆盖夹带租赁公告的排除效果，也没有验证其他12个专题。
- 待改进：长组合关键词空召回导致多轮扩展检索；该反馈已修复并通过888项离线。两次实际生成耗时约164/166秒，多次上下文压缩；尚不能把总耗时全部归咎检索或确定为摘要回退。下一轮应使用新空召回提示，保留相同资料、模型和预算对照，核对能否完整逐条提交并完成收尾，再根据实际错误改进。不要为通过验收直接调大生产预算或改现有绑定。

现场只读检查时前端4400、后端8300及PostgreSQL5432已有服务。本轮没有启停业务服务、写入业务报告、改真实配置、提交或推送。此前历史“服务未启用”描述不作为当前状态；Windows PowerShell读取JSON可能默认乱码，接口核对使用Python按UTF-8解码。

### 2026-10-18 专题摘要、引文纠错与真实模型复验

持续目标保持 active。本阶段没有修改13专题分类、中文字段、HTTP接口、数据库结构或生产预算；没有启停业务服务、创建业务报告、改绑定或配置、提交或推送。

- `agent.py` 新增当前专题的摘要模板，保存条件、原样证据ID、提交状态与具体缺口，明确旧摘要不覆盖运行时状态，缺附件不作为获取未授权资料的前置条件。压缩阈值和保留消息数未变。实际模型仍会保留部分无关专题和缩写ID，不能声称完全服从摘要指令。
- `skills.py` 增加仅用于送审的 `_review_business`：省略根级空属性、默认空条件和空评分，防止将 `materials=[]`、父子属性空值误判为“原文必须证明没有该要求”。非空条件、范围、材料及评分（包括字符串零分）完整保留；持久结构与纠错指纹不变。运行时说明各标段共同适用可用common，具体lot_refs需要原文证明名称和范围。
- 真实第三轮发现一条报价构成的四处引文均由摘要改写；旧逻辑只报第一处。`knowledge/content.py::validate_items` 现一次返回同事项的全部错误块，逐字校验与未知来源拒绝保持不变。用第三轮原草稿确定性重放，已同时定位四处改写。
- 仅核对引文字面时，提示 `read_document(before=0, after=0)`，避免补读邻域意外使旧综合失效。必要的新条件仍需补读。综合后真有新证据时，工具当次返回 `phase=research` 与重新登记和综合全部事项的说明；旧暂存事项仍按既有规则失效，不绕过重综合。提示不进入读缓存，缓存重放不会误报失效。
- 新增/更新真实图回归：专题摘要后的阶段和引用保留；空属性送审与持久记录不变；同事项多处引文一次反馈；新证据阶段反馈及缓存重放；仅回读原块保留已核实成果。专项63项通过，统一 `scripts/check-backend.ps1` **891 passed / 9 skipped**（50.03秒），保留2条既有structlog提示。13个Skill前置元数据、工程14与设计19的UTF-8/围栏/本地链接通过。

真实模型隔离实验仍使用项目15单份监理招标文件、当前analysis绑定deepseek-v4.1-flash、真实Agent图与verify_items、正式关键词回退（禁用向量与重排）、内存检查点；模型/工具上限36/48次、600秒。产物全部在忽略目录 `.tmp/skill-real-audit/`，没有写业务报告和调用账。

- 第二轮 `model-price_requirement_parsing-153721/`：420.69秒耗尽36次模型调用，37次研究工具、81块证据，未final，0项supported。校验合理拒绝未引用的具体标段清单，但同时不合理地要求空属性独立依据；触发上述空属性修复。
- 同一历史片段的摘要重放：`summary-replay-155122/`，新模板输出1344 tokens/12.75秒，旧摘要3742 tokens，约减少64%。这是单片段对照，非完整Agent验收；实际仍有旁支信息和ID范围写法。
- 第三轮 `model-price_requirement_parsing-155631/`，会话80145已结束：230.20秒，33次模型调用、32次研究工具、63块证据，输入349733/输出11522 tokens。期间限价、折扣两项通过支持性校验；后续四处引文改写反复纠错，邻域新证据使旧综合与暂存清空，最后连续三次提交无效而ValueError终止，最终0记录/0缺口。不能称为完成或保留两项最终成果；该轮触发上述引文反馈修复。
- 第四轮 `model-price_requirement_parsing-160549/`，会话53819已结束：223.89秒，27次模型调用、48次研究工具、74块证据，输入288374/输出17677 tokens。保留1项supported限价和5项缺口，未final，最终draft records=0；工具调用预算耗尽终止。实际采用了仅回读原块的纠错方式，本轮没有因此清空已核实成果。多轮查询追踪了不属于报价专题的纯评分公式和系数，随后在价格Skill主文件补充同名报价折扣率/评分基准系数的区分及转引边界；此最后规则还未做新一轮真实模型验证。
- 独立支持性重放 `review-replay-160853/`（会话92450已结束）：common通过、K≤100%通过、错误K<100%被拒绝；未引用具体名单的lot_refs却被模型放行，说明范围校验仍有不稳定性，不能把送审提示视为确定性保证。脚本 `review_eval.py` 只读资料、四条候选、无业务写入。

报价清单已补足：元素814的报价修改同步要求；1029—1031的大小写、总单价修正、例外与书面确认（1032已是下一节）；1040的异常低价触发与证明；1128的专利/专有技术使用费及采用条件；1278—1280的合同费用范围、专用条款例外和另付费用。原文在临时CHECKLIST中索引，不能只验限价就称报价完整。

最后仅补价格Skill边界与文档，资源回归 `test_native_skill_resources.py` **73项通过**（4.73秒）；工程14/设计19的本地链接与围栏、git diff --check再次通过，无后续生产代码变更。

下一步继续核对具体标段范围的校验不稳定性，并验证价格专题能否聚焦正确的检索范围、完整提交算术修正、异常低价和费用条件；不再盲目重复相同完整模型运行。全部13专题的真实模型完整性尚未验证；本记录不会将持续目标标为complete或blocked。当前无仍运行的验收或检查会话。

### 2026-10-18 确定性标段指向检查与调用次数收尾预留

上一目标回合有代码、测试和真实失败证据，属于progress；本回合继续针对具体缺陷改进，目标仍active，无外部阻塞。没有使用子代理，没有修改业务报告/绑定/生产配置，没有启停服务、提交或推送。

- `skills.py::_missing_scope_refs`：在模型选出最终证据后，检查business.scope.lot_refs中的原文编号/名称是否出现在所选引文。比较忽略空白与全半角；不从context、被丢弃的名单引文或全局材料补依据。缺少指向时，即使模型返回supported也改为unsupported，具体问题进入verification_claim_issues，按内容问题纠正、不耗费格式重试。名称出现仅是必要条件，适用关系仍需语义验证；common/unknown不要求具体名单。
- 新增四种回归：名单只有context、名单引文被模型去重丢弃都拒绝；所选引文含原文名称（含全半角/空白）允许；公共范围无需名单。先失败复现两处误放行，再通过实际verify_items验证修复。
- `ResearchMiddleware.budget_needs_synthesis`：原来只有时间收尾预留；现在专题模型或工具剩余次数进入冻结总额最后四分之一时也拒绝扩展搜索，保留必要回读、complete_research、逐条提交、支持性校验及final收尾机会。依据正式运行账的全部调用数，硬上限不变；未完成主题仍登记缺口。问答没有output_schema，不新增次数门槛。两项真实图回归验证低模型/低工具余额时拒绝扩展但允许回读和提交；先失败再通过。
- 统一验证 `scripts/check-backend.ps1` **897 passed / 9 skipped**（59.35秒），Ruff、5项架构契约及mypy通过，保留2条既有structlog提示。工程14、设计19已同步，文档链接、围栏、git diff --check通过。

真实支持性复验（所有进程已结束）：

- `review-replay-161816/`，会话26473结束：common和K≤100%通过；未引用具体标段被新增确定性检查拒绝。但K<100%本轮被模型放行，与上一轮拒绝不一致。
- `review-replay-162441/`，会话43509结束：为排除裸比较式含义不明，将条件明确为“投标报价必须满足K≤100%/K<100%”；两项仍均被模型放行。实际原文最高限价100%允许等于，因此严格小于属于改变边界。当前语义校验仍不可靠，不应通过更多模型投票或业务硬编码掩盖。

第五轮完整报价隔离验收 `model-price_requirement_parsing-162227/`，会话35390已结束：

- 临时脚本此前reserve_tool为空，工具限制仅统计ResearchSession的检索/回读。现在按正式控制器计入Skill加载、研究登记、提交、回读及错误调用；budget.json保存总数，summary同时保留tool_calls（研究次数）和tool_calls_total。前四轮统计不能与本轮总工具数直接等比。
- 220.56秒；36次模型、41次研究工具、47次总工具、66块证据，输入375738/输出11464 tokens。1项supported限价；未final，最终records=0、business_gaps=0，RuntimeError为模型调用额度耗尽。没有变更原36/48/600秒隔离预算或8192输出上限。
- `profile.json`：Agent实际27次，138.45秒，输入338986/输出5075；摘要6次，53秒，输入25829/输出6091；支持性校验3次，13.23秒，输入10923/输出298。摘要不是全部问题，主要开销仍在检索与纠错。
- 第35次审查存在明确误拒绝：待审c734逐字含“由委托人另行支付”，模型却称引文缺失该句；c135/c136分别引用的跨页报价方式被误判为合并同一引用、夹有章节而不可综合。见response-34/35与request-35，后续应核对实际送审表示及模型推理能力，不能把原文正确事项删掉来通过校验。
- complete_research也有实质性错误：detail已承认附件4报价表本体未提供，却标记引用resolved、主题covered，最终无缺口；这不证明附件已读全。不能因形式门禁通过就称覆盖完整。
- 第一次Agent请求system内容约11565字符（content实际是两段列表），工具schema约10697字符；第36次system约13458字符。`context_size`以序列化字符数保守估计，不能简单按len(list)计算提示长度，也不能据此擅自调大生产上下文预算。

下一步：优先查支持性审查误拒绝/误放行的原因及首次已读事项未提交的问题，再做定向重放；不要盲目重复完整报价运行。仍需完整报价及技术长清单、评分、保证金等真实验收，全部13专题真实效果未验证。现有前端验证结果沿用此前51单测/18专题页面测试，本轮未改前端。当前无运行中的验收或检查进程。

只读核对当前analysis候选绑定：deepseek-v4.1-flash、qwen3.8-27b-262k、qwen3.8-flash-next-262k、glm-5.3-flash；temperature均为空，登记能力仅text_input/json_output，parameters未显式设置reasoning_effort/thinking或extra_body键。未改绑定。可以先对同一失败审查输入做已有候选模型的隔离对照，不把切换生产配置作为未经验证的修复。

### 2026-10-18 续接原会话：修复综合阶段交接与重新检索提示冲突

用户要求阅读“改造解析 skill 以适配项目检索与输出”会话并继续执行。已通过本机会话索引定位、读取原始用户计划及最近最终答复，结合本文件最新记录接续；原有13专题、中文字段、JSON协议、快照兼容和前端定位成果保留。使用skill-creator评估方法与karpathy-guidelines；未启动子代理。

本轮进入时只读查询的analysis首选已是模型23 `DeepSeek-V4-Flash`，其后为21、18、17、2；不能继续假定首选为21。本轮没有创建或修改模型、绑定、生产配置、业务报告及调用账，没有启停业务API/Worker/Beat，没有提交或推送。

保留到项目代码的改动：

- `application/analysis/agent.py`：综合阶段每轮提供研究登记中的主题发现、完整证据ID、转引状态和资料缺口，替换反复展开的检索流水。它们是待核对线索，不是已验证结论或可复制引文；暂存的已核实事项仍由现有状态提供。研究阶段仍提供真实检索账，权限与新证据失效规则不变。
- 进一步修复阶段指令冲突：此前即使状态为综合，每轮仍写“按当前Skill全部主题完成检索后complete_research”，真实诊断再次启动了全主题搜索。现按研究/综合阶段分别提示；低预算、连续无进展和搜索被拦截的提示也仅在尚未登记研究时要求先complete_research。综合优先提交尚未处理事项，单纯取引文按已有ID以before=0/after=0回读；实质证据缺口仍允许补查，未绕过新证据重新综合的规则。
- `complete_research`成功回执返回实际登记的gaps；`output.py`工具字段描述与系统规则明确：resolved必须读到目标实质条款，另一处索引/格式标题不代表附件已提供；主题部分未决时应使用unresolved。此项是语义指导，服务端仍不能只凭状态枚举证明模型覆盖判断正确。
- `test_analysis_synthesis.py`新增真实图回归：综合各轮的系统上下文始终保留独立事项线索和具体转引，停止重复研究指令与流水，登记回执和最终结果均保留缺口。工程14和设计19同步。

验证：初始交接回归先复现失败，修复后综合专项44项通过；最后阶段/收尾提示调整后，统一入口`scripts/check-backend.ps1` **899 passed / 9 skipped**（53.65秒），Ruff、5项架构契约和mypy正反检查通过，保留2条既有structlog提示。前端未变，沿用此前51单测/18专题页面测试。文档UTF-8、围栏、本地链接和git diff --check通过。

真实支持性对照：

- `.tmp/skill-real-audit/targeted-review-190856/`：模型23，原提示与“缩短说明+结构化去重”各8例，共16次请求。
- `.tmp/skill-real-audit/targeted-review-191230/`：模型21，原提示与“保留规则、只结构化去重”各8例，共16次请求。
- 原`omitted_trigger`反例的标题仍限定“委托人指定”，不能确定正文是否已扩大条件；已从两组评分排除，不据此报告误放行。其余每方案7例，同时检查协议、判定及拒绝理由是否正确：模型23两方案均2/7；模型21两方案均5/7。这是单次窄样本诊断，不是模型总体准确率或稳定性排名。
- 模型23明确误放行将100%上限改成90%的条件；多例返回JSON但不符合reviews/evidence_ids协议。模型21部分拒绝理由声称原文未含实际已引用的例外，或无理由要求每处独立引用单独支持完整事项。错误地返回unsupported也不算通过。
- 每例只允许一次实际请求，非法格式不额外纠正，因此结果不能等同于生产最多三次格式纠正后的表现。一次ModelUnavailable没有用量回执。两种实验提示未证明稳定收益；曾加入的原生送审去重辅助函数及对应测试已精确撤回，原有`skills.py`和`test_analysis_data.py`累计改动保留，未用git还原工作树。
- 按skill-creator自带generate_review.py生成静态交互记录：`.tmp/skill-real-audit/review-audit-20261018/model-23.html`与`model-21.html`；同目录README解释评分、排除项和限制，包含原始输入、响应及诊断原因，没有启动浏览器服务。

真实综合诊断：

- `synthesis-price_requirement_parsing-192053/`（会话8094已结束）：新建隔离诊断用例，以第五轮66块已读证据、主题交接和1项已核实限价为输入；上限18次模型/24次总工具/300秒。不是重置生产任务预算，也不是完整检索重跑。300.09秒，8次模型（最后一次取消）、21次研究工具/22次总工具，139494输入/3394输出tokens。模型重新检索并默认邻域补读，引入新证据使原暂存失效，最终94块、0项已核实成果、未收尾。该轮引出上述阶段提示冲突修复。
- `decision-price_requirement_parsing-192606/`（会话62276已结束）：修正阶段提示后，仅比较同输入的前两轮规划。30.42秒、2次模型、3次研究工具/5次总工具，36936输入/628输出tokens。先list_documents，再回读原有费用及算术修正规则；未search、未新增证据，保留原1项限价。一次read_document把before填成字符串`rent`，正式工具正确拒绝；其他回读仍使用2/2邻域，不能声称模型已遵守0/0指导。未提交新成果。
- 两轮探针在第三次模型调用前按设计停止；summary中的failed/RuntimeError是诊断边界，不应作为完整Agent终态统计。最后仅补阶段化收尾提示，属于之后通过899项统一检查的代码，没有再调用真实模型。

当前所有本轮模型和验证会话均已退出。完整报价、技术长清单、评分、保证金及其余专题真实效果仍未完成验收；不能标记完整目标完成。下一步应先确认当前模型对工具参数与支持性协议的稳定性，再验证实际完整事项提交；不能以调整提示长度、布尔判定正确或单项限价通过代替完整验收，也不要继续盲目重复完整报价运行。

### 2026-10-18 优化解析结果展示：七类问题已处理

用户要求自行分析前端解析结果展示，并将发现的问题全部处理。本轮执行前已读取交接和项目规则，使用 frontend-design、karpathy-guidelines；未委派子代理。用户后发的路径说明已按其要求忽略，不改变当前任务。此前“适配解析Skill的项目检索与输出并完善证据校验”已提交为 `14d20a2`；本轮没有新的提交授权，因此只保留工作区改动。

实现：

1. 事实按单个字段及内容成对展示。项目概况优先项目本身，长技术条款与评分档次完整展示，报价等保留对照表。历史字段数组没有可靠的配对声明，保留原标签和内容并明确提示核对，不根据数组等长推断。
2. 专题正文作为唯一主入口；移除重复综合正文与多套统计口径，运行/重跑操作收进详情。报告统计按信息、要求、材料节点与关联区分，筛选命中数与待核对分组数单列。
3. 原文默认36%宽度，桌面可调整25%—55%或收起；定位引用自动展开原文。手机保留原文/结果切换。常驻专题与筛选栏，统计和报告操作随滚动离开视口。
4. 事项标题、适用范围、条件与材料、修订和冲突关系可查看，关联入口清除筛选并跳转。格式树可折叠，深层搜索命中保留并展开祖先，祖先不计入命中条数。
5. 缺口保留原因、专题、主题、范围、记录身份，归组并去重相同说明；区分结构化缺口、分析进度与真实材料缺口，保留专题检查进度及跳回入口。记录级缺口缺少专题字段时按记录补归属。
6. 多引用先展开文件名、页码与完整摘录，再定位具体原文；相同引用去重，同页不同块与摘录保留。共享原文往返仍优先回到刚点击事项。
7. 所有专题均可选择（含空专题与状态），提供全文搜索、分类、精确范围与待核对筛选。选定标段包含公共要求、排除未知范围；正式有效条款仍由原 context 接口处理，快照过期或依据不足禁止编制预览。

新资源声明：项目概况、人员要求的 output_schema 增加 `scalar_columns: ["字段"]`。运行时按冻结声明拒绝字段数组，允许内容为条款数组；未声明的新属性不注入旧快照，旧报告按原协议恢复。重试旧报告仍使用旧Skill快照，采用单字段规则需新建报告。未做数据库迁移，没有自动修复或重新解析历史业务记录。

主要文件：新增 AnalysisResults、EvidenceReferences、useAnalysisSnapshot、presentation.ts、gaps.ts；调整 ProjectAnalysis、ModuleMarkdown、AnalysisDataPanel、ResearchGaps 与响应式样式。设计19及工程14同步当前交互与兼容规则。

验证：

- `scripts/check-backend.ps1`：901 passed / 9 skipped，Ruff、5项架构契约及端口/真实装配 mypy通过；保留2条已有structlog提示。新增新旧快照字段约束及声明校验。
- 前端56项单测通过，类型检查通过，生产构建通过。新增范围精确匹配、父链保留、历史字段、缺口去重和统计分型验证；旧投影测试同步为不再无条件显示“部分条件待核对”。
- Playwright：既有68项（synthesis、analysis-data、interactions）桌面/手机通过；另新增14项通过，共82项。覆盖引用精确定位、历史字段安全展示、材料搜索、修订跳转、缺口归属、依据不足限制、失败报告原因及原文收起/重新展开；未捕获浏览器异常。
- 真实项目15报告18只读检查：7条业务记录、13专题；1440×900和390×844均无页面横向溢出。最终截图位于 `.tmp/analysis-display-audit/final-1440-initial.png`、`final-1440-reading.png`、`final-1440-gaps.png` 及对应 `final-390-*`。快照仍有真实未完成缺口，前端不把它们隐藏或当作完成。

本轮所有检查结束，无后台验收进程；复用已有4400前端和8300后端，没有启停业务服务、调用真实模型、重跑报告、推送或部署。本轮完成的是这七类前端展示问题；旧记录未保存配对关系的限制仍如实保留，原交接中的真实模型全面效果验收未由本轮替代。

### 2026-10-18 修复四处审查问题并恢复模块标签与重解析操作

用户先要求修复未提交改动的审查问题，随后明确表示不喜欢改后的模块导航和操作布局，要求恢复按标签铺开模块、单模块重新解析、补跑未解析模块和全部重新解析。本轮按最新偏好恢复交互，保留结果正文与证据展示的修复；不再将专题改为下拉框或把重解析入口藏进详情。

实现：

1. 模块标签包含全部专题及各模块，空模块与状态照常展示。桌面换行铺开，手机横向滚动；支持方向键、Home/End，原文定位切换模块后同步展示当前标签。
2. 模块标题旁直接显示“重新解析本模块”，请求只传当前模块键；报告顶部直接显示“补跑未完成模块”（服务端选择未完成模块）和“全部重新解析”（显式传全部模块键）。运行中、取消中或正在提交时禁用重跑，旧流程报告沿用只读限制。刷新和取消也直接可用，运行细节仍可折叠。
3. 修订/冲突入口只使用快照已确认关系的 subject_id/object_id，不按可能复用的原始 key 回连新条款。关系未决或快照不可用时保留正文、引用和核对提示。
4. 缺口按原始 kind、lot_ids、lot_refs 区分范围，集合顺序不影响去重；未知标段显示原文指向，避免 A、B 标段的同名缺口合并。
5. 每次正向、反向定位递增请求标记，相同目标也重新展开并滚动。材料树使用实际筛选状态展开，父子同时命中也可见，仍允许手动折叠。

验证与现场状态：

- 四处问题先用回归复现失败，再验证修复。前端57项单测、类型检查通过；最终 synthesis、analysis-data、interactions 共92项桌面/手机交互测试一次完整通过（5.3分钟），包含三个重解析请求范围和标签键盘切换。较早一轮两项手机用例因开发服务短暂拒绝连接失败，定向补跑及最终完整运行均通过。
- `pnpm --filter @ai-tender/web build` 通过，包含 TypeScript 和全部页面构建；差异及 UTF-8 检查通过。设计19、工程14同步最新交互。
- 复用4400/8300，只读检查真实项目15报告18；1440×900和390×844标签数、末尾标签切换、滚动常驻及直接操作入口均通过，无页面横向溢出、无未捕获浏览器异常。截图位于 `.tmp/analysis-display-audit/tabs-1440-ready.png`、`tabs-1440-reading.png` 及对应 `tabs-390-*`，旧截图仅保留历史对照。
- 本轮没有后端代码变更，未重跑后端检查；工作区此前累计后端改动的901 passed / 9 skipped仍来自上一轮。所有验收进程均已退出，未启停业务服务、调用真实模型或重跑业务报告。未提交，用户此前提交授权已用于 `14d20a2`。

### 2026-10-19 逐条证据定位、历次分析信息与操作位置调整

用户要求每个正文条目末尾显示自己的定位信息；分析记录增加开始、结束时间和失败原因；“重新解析本模块”移到顶部“刷新结果”之后；原文定位只保留外边框。确认旧记录缺少逐条绑定后，用户明确“不考虑旧报告展示”。本轮只为新结果建立绑定，不猜配、不写回、不重新解析历史记录。使用 frontend-design、karpathy-guidelines，未启动子代理。

实现：

- `application/analysis/skills.py`：同一次支持性请求保留原整项值，附加每个内容列／数组单元并分别选证。整项的范围、条件、跨来源约束继续有效；正文单元只保留自己的来源。缺少单元、空证据或选择候选之外的 ID 时拒绝发布。送审扩展不写回公开 values，不制造多值冲突。
- `application/analysis/data.py`：新结果通过 `content_evidence` 保存按列及数组位置的证据 ID；正文与整项选中不同等价出处时均保存。报告投影把逐条额外出处加入既有可见性检查，防止整项可读却遗漏对局部引用的权限核对。无需数据库迁移或更改提交工具参数；单次支持性载荷随正文单元增加，继续遵守原调用与时间预算。
- 前端 `recordItems` 校验绑定数量和引用归属，`ModuleMarkdown` 在每条正文末尾渲染对应引用；多个来源直接并排展示页码和序号，文件名与摘录放悬停说明。新绑定的结果取消底部集中入口。报价表、评分档次、材料树均复用逐条绑定；不新增旧报告补配逻辑。
- `AnalysisResults` 在顶部刷新按钮之后提供单模块重新解析，始终使用当前所选模块键，全部专题视图禁用；补跑未完成模块和全部重新解析继续独立。历次运行按次显示状态、调用数、秒级起止时间及完整失败／停止原因，后续成功不覆盖旧原因；运行中显示“尚未结束”，缺失时间显示“未记录”。
- `EvidenceLayer` 去掉普通框、当前框和动画框的背景及阴影，只保留描边与外侧编号；坐标、页码过滤和重复点击动画不变。工程14和设计19已同步。

验证：

- `scripts/check-backend.ps1` 最终 **908 passed / 9 skipped**（77.42秒），Ruff、5项架构契约和端口／真实装配 mypy通过。新增7项验证逐条选证、不同等价出处保存、越权／空绑定拒绝、跨来源保护和局部出处失效；保留2条既有structlog提示。
- 前端类型检查、**58项单测**、生产构建通过。完整 Playwright（synthesis、analysis-data、interactions）**104项桌面／手机用例通过**（5.8分钟），覆盖逐条按钮归属、同页不同位置、透明定位框、表格／评分／材料树、历次失败原因、缺失／运行中时间和三个重解析范围。页面测试均使用模拟接口，未触发真实重跑。
- 已查看桌面和手机的逐条引用截图及描边定位截图。产物在 `apps/web/test-results/synthesis-正文每条后显示自己的来源，多出处直接定位且原文框保持透明-{desktop,mobile}/` 与 `synthesis-每次分析的时间与原因-最后一次成功仍保留各次失败原因，缺失时间不伪造-{desktop,mobile}/`；移动端历史截图受常驻筛选条遮挡，实际字段及布局由页面断言验证，不把截图裁剪误记为字段缺失。
- 只读核对真实项目15报告18的技术记录，确认既有数据只有整项证据 ID。复用已有4400前端与8300后端，未启停业务服务、未写业务报告或调用真实模型。所有检查会话均结束，未提交或推送。逐条定位在后端加载本次改动后生成的新结果中生效；真实供应商对新增逐条选证的语义效果未由本轮离线测试证明。

### 2026-10-19 修复逐条引用审查发现的两处问题

用户要求修复未提交更改审查中的两个 P2 问题：正文绑定后隐藏了仅支撑条件／材料等内容的额外定位入口，以及逐条送审重复展开全部候选引文与上下文。沿用“不考虑旧报告展示”的范围，不回填或重跑历史结果；使用 karpathy-guidelines，未委派子代理，未提交。

- `ModuleMarkdown` 仅扣除已有正文定位入口的来源，其余整项来源显示为“补充依据”，直接提供定位按钮。正文的逐条入口继续保留，不把已展示来源重新集中到底部；字段标签未渲染定位按钮时，其独占来源也保留。比较包含版本、解析批次、原文块、页码与摘录，防止同块不同句子的依据被误删。补充入口不推测出处与各详情条目的对应关系。
- `skills.py` 在同一项内按块 ID 和摘录归并候选集合，每个集合的引文和上下文只发送一次；值使用 `evidence_set` 索引指向 `evidence_sets`。任一共享值需要章节核对时保留该集合的邻域。输出仍逐值返回 `evidence_ids`，服务端仍用原始候选校验，不放宽跨来源、范围、空选择或越界引用限制；不增加模型调用步骤或预算，不修改持久化协议。
- 工程14、设计19同步补充依据与共享候选的行为。新增回归先复现缺陷：两个桌面页面用例无法找到补充按钮，12单元校验中每份原文重复26次。修复后验证来源不重复、精确定位、同块不同摘录、跨值候选拒绝以及每份引文／块上下文各保留一次。

验证全部结束：`scripts/check-backend.ps1` **911 passed / 9 skipped**（103.72秒），Ruff、5项架构契约及端口／真实装配 mypy通过，保留2条既有structlog提示；前端 **58项单测**、类型检查、生产构建通过；逐条引用、表格／评分／材料树、透明框及补充依据的 **12项桌面／手机页面测试通过**（55.1秒），包含本轮新增4项。未重复运行与本轮修复无关的全部页面用例。

离线载荷对照使用既有原文和实际 `prepare_records`／`verify_items`，由捕获模型返回合法协议，不请求真实供应商：同一12项监理大纲，修复前请求17999字符、168份重复候选，修复后6042字符、12份候选，均为一次请求；无逐条绑定的HEAD基线4567字符。9条长段落的纯载荷探针从73115降至25591字符，该探针不证明这些段落在业务上属于同一事项。上述验证证明表示压缩与确定性约束，未验证真实模型对新索引表示的语义准确率。

所有检查进程已退出。复用现有开发服务，没有启停业务服务、调用真实模型、修改业务报告或配置、提交或推送。

### 2026-10-20 KV逐行展示、纯图标与仅当前定位框

用户要求字段和内容一一对应地用KV表格展示、定位只保留图标；随后指出同一位置有两个图标，以及文档上非当前定位也出现框。保留此前内部透明的要求，沿用 frontend-design、karpathy-guidelines；未启动子代理。

- `presentation.keyValueRows`、`ModuleMarkdown`：字段与内容使用两列表格；多字段数组按原顺序逐行对应，单字段多内容保留同格。数量不一致保留全部项并标出缺失，加入待核对列表。每条记录使用一个tbody保持事项锚点唯一，拆行引用通过原内容序号获取，避免每行都定位第一条。桌面及手机均保留两列，无横向溢出。
- `EvidenceReferences`：各类触发按钮只显示定位图标，文件名、页码和摘录保留在提示中。按source_id/version_id/parse_run_id/element_id合并同一位置，包含不同quote的引用；全部摘录仍可查看，点击使用一条真实原始引用。同页不同块保留独立入口。补充依据仍按完整引用判断是否已在正文显示，不丢失条件／材料等独占摘录。
- `EvidenceLayer` 删除所有未选中框及当前位置的重复底框，只绘制当前页当前位置的一个3px深紫边框，内部透明且无阴影；没有块坐标时使用页级虚线框。`AnnotationLayer` 同样只保留当前位置可反向定位的角标。重复点击重播边框动画，切换位置／页码移除旧框，虚拟列表其他页不画框；减少动效偏好继续有效。
- 工程14、设计19已同步用户最新展示偏好，替代旧的页码文字按钮、字段数组不配对及全量框描述；底层数据和后端协议不改写。

验证：前端 **58项单测**、类型检查、生产构建通过。最终相关Playwright **26项桌面／手机回归通过（1.5分钟）**，覆盖KV逐行定位、同位置不同摘录合并、同页不同块、切换与重复点击不累积框、跨页无残留、页级定位、默认预览无框、评分往返及补充依据。已查看桌面／手机KV和描边定位截图，位于 `apps/web/test-results/synthesis-KV-每行仅显示定位图标，拆行后仍定位本行原文-{desktop,mobile}/kv-icon-locators.png` 与 `synthesis-正文每条后显示自己的来源，多出处直接定位且原文框保持透明-{desktop,mobile}/outline-only-location.png`。首次回归暴露新增测试误断言resolve请求携带整条引用（实际只提交身份）及旧往返测试与延迟滚动抢时序，测试已按协议和可观察行为修正，最终整组通过。

本轮只改前端与文档，未重跑后端；此前累计后端改动的 **911 passed / 9 skipped** 仍来自上一轮。UTF-8及差异检查通过。真实报告18接口只读请求返回“服务暂时无法处理请求”，因此本轮未完成真实报告复验，不将模拟页面验收当作真实业务验收。所有检查会话已结束；未启停业务服务、调用真实模型、重跑／写业务报告、提交或推送。

### 2026-10-21 续接原会话：归纳重点与同一事项定位去重

用户要求读取“优化解析结果展示并去重原文定位”会话并继续执行。通过本机会话索引读取原会话 `01a1597f-cafb-7fa3-9f8d-3dfa6b378d61` 的用户消息、助手说明和最后两次补丁：实际追加目标是让 AI 适当归纳解析值、改善格式，并进一步去重定位；该部分已写代码但尚未验证，未记录在此前交接中。本轮使用 karpathy-guidelines，未启动子代理，沿用旧报告不补配的范围。

完成内容：

- `agent.py` 在原生成环节要求去除套话、归纳重点，使用短句、字符串数组和少量 Markdown 加粗。金额单位、时间起算点、主体、范围、数量、且或、否定、前提、例外、材料及评分档次须完整保留；名称、编号、公式和材料标题不改写，“原文摘录”列保留原句。Skill 明确要求的来源列继续保留，其他正文不重复写来源。quote 始终逐字复制，结构化业务属性保持纯文本，不新增展示改写调用或调整预算。
- `skills.py` 支持性审查明确排版标记按语义核对，原有全部约束继续有效。新增经 prepare_records、verify_items、module_data 的往返测试，验证加粗归纳正文和逐字原文独立保存、逐条选证、单次请求；可控模型不证明真实模型的语义质量。
- `presentCitations` 以事项为边界，按资料、版本、解析批次和原文块分配定位入口；跨正文单元、跨列和补充依据只在首次出现的可见正文后保留一个图标。同位置不同摘录收进该入口，独立补充来源保留，不同事项各自可定位，同页不同块不合并。原始绑定与引用不修改，筛选和重渲染不消耗引用。
- 恢复此前补丁覆盖掉的 `findCitationResult` 及3项原有回归，保留共享原文返回当前事项和跨版本隔离。接续时 typecheck 已实际复现导出缺失；恢复后通过。
- 评分满分改为渲染轻量 Markdown，避免新生成的加粗标记原样露出。树节点回归按当前节点计数，避免将子节点入口混入父节点断言。工程14、设计19更新归纳规则和事项内去重范围，替代先前逐条重复放置入口的描述。

验证与现场状态：

- `scripts/check-backend.ps1` 最终 **912 passed / 9 skipped**（60.40秒）；Ruff、5项分层契约及协议／真实装配 mypy通过，保留2条既有structlog提示。首轮只有新增往返测试漏算既有列名前缀而失败，修正测试预期后完整重跑通过。
- 前端类型检查、**62项单测**和生产构建通过。Playwright **22项桌面／手机回归通过（2.2分钟）**，覆盖同事项跨条／跨列去重、不同事项独立入口、不同摘录合并提示、KV逐行、评分加粗、补充条件材料、默认预览、原文往返与跨页单框；未捕获浏览器异常。沿用模拟接口，没有重跑业务报告。
- 4400端口被Windows拒绝绑定，使用现有 PLAYWRIGHT_PORT 配置选取可绑定的临时3121端口；测试自建前端服务已退出。未修改业务端口或启停业务API／Worker。
- 已查看桌面／手机的去重正文与透明单框截图，以及手机KV截图；产物在 `apps/web/test-results/resume-analysis-20261021/`。生产构建包括TypeScript及全部路由构建，差异与严格UTF-8检查通过。

未调用真实供应商、修改业务数据／配置、重写历史报告、提交或推送。归纳指导在后端进程加载新代码后的后续生成中生效；本轮完成实现和离线交互验收，未证明真实模型在所有专题都能保留全部约束。此前真实报告18复验问题与13专题真实模型效果验收仍未由本轮替代。所有本轮检查会话已结束。

### 2026-10-22 修复审查中的专题错误隔离与手机摘录访问

用户要求修复当前审查发现的两处问题。已先读取交接与规则，沿用 karpathy-guidelines，未启动子代理。

- `loadReportRecords` 将请求失败与 `recordItems` 逐条绑定校验失败纳入同一专题级 catch。某个专题的绑定缺失、数量不符或非法引用只清空该专题并显示 `records_error`，其它有效专题继续加载；保留原有绑定校验及不回退旧投影的规则。
- `ProjectAnalysis` 按点击时的事项与 source_id/version_id/parse_run_id/element_id 收集全部不同原始摘录，随所选位置保存；定位图标仍直接打开原文。`CitationViewer` 对多摘录提供原生 details，可点击、触屏或键盘展开，固定高度内可滚到最后一段；各段保留原句，不拼接成引用，也不混入其它事项或位置的摘录。单摘录及默认预览沿用原展示。
- 工程14、设计19同步当前行为。新增专题错误隔离单测及两项桌面／手机页面回归：先实际复现未修复时单测抛错、页面无法找到全部摘录入口，再验证修复。

验证：前端 **63项单测**、类型检查及生产构建通过；两组相关 Playwright 共 **34次执行通过（32项不同的桌面／手机用例，含2项摘录用例加强断言后重跑）**，覆盖当前事项摘录去重、不同事项与位置隔离、滚到最后一段、键盘展开收起、KV、评分、材料树、加载重试、默认预览、报告切换、重复反向定位与跨页单框。页面未捕获未处理异常。已查看桌面与手机展开截图和手机末条摘录截图，位于 `apps/web/test-results/review-fixes-20261021/` 与 `review-fixes-navigation-20261021/`。

本轮仅修改前端与文档，未重跑后端；本次审查阶段的后端 **912 passed / 9 skipped** 为修复前验证且后端源码未变。复用已运行的4400前端，未启停业务服务、调用真实模型、修改业务数据／配置、重新解析报告、提交或推送。首次尝试3121被既有Next开发锁拒绝，确认4400正常后直接复用，未停止已有服务。全部本轮验证进程已结束。

### 2026-10-23 解析异常修复与真实验收待续

- 具体原因、实现与918项统一验证见工程23；新增6项回归先失败再通过。保持现有架构、预算、隐私策略和逐字／支持性校验，不提交。
- 本机WSL启动后数据库查询和Redis PING恢复。模型诊断仅写 `.tmp/parse-failure-20261023/`，未写业务数据／配置／调用账。
- 用户选择配置有额度模型后继续；用户已新增GLM模型30为首选，探针仍因余额约0.37元不足预扣1.60元而403。免费Gemma／星辰完整请求连续429，Laguna受隐私策略限制404，MiniMax免费版本已下线。
- 现场API／Worker／Beat已由用户启动，API正常；Worker早于最后一次agent.py修改启动。复核发现报告21在运行，未重启或中断现场任务。结束后需载入最终修复。
- 原始目标保持active，真实完整专题尚未通过，不能以离线全绿或简单工具探针当作解析成功。下一步是可用模型额度落实后，执行隔离专题验收、核对完整事项／缺口／引用和final收尾。

本轮最终续记：真实报告21最终全部失败，原因为供应商403余额不足、500渠道错误及超时。全库确认无活动分析后通过 `scripts/start-backend.ps1 -Force` 重启三进程，API健康检查通过，最终补丁已载入。新增首候选错误掩盖后备故障与极早收尾缺失首次检索两项修复，最终 **920 passed / 9 skipped**（53.09秒），Ruff／分层／mypy通过。所有本轮隔离验收与检查已退出，未提交。目标未完成，继续条件仍为有额度且稳定可用的模型；需要真实完整专题验收。

### 2026-10-23 继续检查并修复提交状态与工具协议纠错

- 用户要求继续检查，随后提供“模型工具名称或必填参数无效，请按JSON Schema完整返回”，要求直接处理代码设计。本轮未启动子代理，遵循既有后端分层；没有提交授权。
- 相同正文的内部 `output.citations` 差异不再导致重复支持性模型请求，复用已核实版本与逐条绑定；正文／业务／引用变化仍送审。
- 每个新提交撤销前一提交尚未完成校验的final意图；同一轮后续暂存或无效提交不能让旧final提前发布。相同调用ID重放不清除合法完成意图。
- 不适用证明按主题与范围固定身份，文字改写不重置纠错额度，恢复沿用旧证明ID，不同标段仍独立；失败立即标待核对。校验中断保留旧核实证明，但不能让它为本次新说明背书。
- 适配器给出schema中的具体缺项或当前允许的工具名单，未知名称／参数正文不回显；路由有界格式纠正保留脱敏错误。普通JSON纠正不再要求旧action结构。
- 新增与加强行为回归先失败再通过。最终 `scripts/check-backend.ps1`：**931 passed / 9 skipped**，74.15秒，Ruff、5项分层契约、协议与真实装配mypy通过；两条既有structlog提示。
- 只读复核当前分析绑定为模型15 Nemotron、28 Laguna、27星辰。报告23正在真实任务，读取时2个运行中、1个失败、10个排队，已有研究登记和支持性送审日志。没有擅自停任务、覆盖绑定、重跑报告或额外调用模型；当前API／Worker／Beat未载入本轮新增补丁，应在活动任务结束后载入并继续真实验收。工程14／23已同步，未改前端或数据库结构、未提交。

### 2026-10-23 修复审查发现的旧事项重复送审回归

- 用户要求修复未提交更改审查中发现的P1问题。沿用 karpathy-guidelines 和既有分层，仅局部调整综合条目比较；未委派子代理，未提交。
- 原比较只从旧版本删除 `output.citations`，但循环也遍历本次未重交且已含绑定的旧事项，导致它们被再次标为待审。本轮改为两侧都排除校验器内部绑定，继续比较正文、业务属性及原文引用，复用已核实条目和绑定。
- 新增使用真实 `verify_items` 的图回归：依次提交两条独立事项再空提交收尾，修复前送审数量为1、2、2，修复后仅两次各审一条；空收尾无额外请求，首条完整版本和两条正文引用绑定保留。既有正文改写仍送审回归继续通过。
- 专项综合流程 **52 passed**；最终 `scripts/check-backend.ps1` **932 passed / 9 skipped**（49.86秒），Ruff、5项分层约束及协议／真实装配mypy通过，保留2条既有structlog提示。工程14／23已同步，差异与UTF-8检查通过。
- 本轮未启停API／Worker／Beat、调用真实供应商、修改业务数据或模型绑定、重新解析报告、提交或推送。本次补丁未由本轮重启载入运行服务，真实完整解析尚未验收；此前现场报告状态仅为历史读取，下一轮应重新只读确认，避免中断活动任务。

### 2026-10-24 继续目标：流内错误分类与WSL禁止启动约束

- 原始目标继续active，上一轮中文提交93144e4已完成，工作区原先干净。本轮未获得后续自动提交授权，新增修改保持未提交。
- 关闭WSL前只读确认：报告23为failed、13项运行账全failed，全库agent_module_run／analysis_report／job均无运行或排队记录。运行进程仍始于10月23日21:51，未加载后续提交与协议修复。
- 报告23真实失败包含Nemotron连接／流中断、Laguna隐私策略404、星辰429、原文逐字引用错误和scope类型错误；不据此认为全是余额问题，也没有放宽引用、权限或预算。
- 真实日志还出现HTTP 200流中的 `{message: Service temporarily overloaded, type: service_unavailable, code: 503}`。SDK以无status_code的APIError上抛，原生适配器误判永久失败；JSON适配器则将所有流错误改成临时故障，403也会重试且真实原因丢失。
- 两条流读取路径现只采纳明确的400—599整数或三位数字字符串错误码，沿用现有503／429有界重试及403拒绝规则，保留已脱敏错误正文。错误摘要同时标出流内错误码与实际HTTP 200，不将建立连接误写成模型成功；半截正文仍不执行／发布，未知错误码不推测重试类型。没有增加预算或重试次数。
- 新增8项HTTP模拟回归先全失败，再修复通过；适配器、路由和错误详情专项86项通过。最终 `scripts/check-backend.ps1` **940 passed / 9 skipped**（50.95秒），Ruff、5项分层约束及协议／真实装配mypy通过，保留2条既有structlog提示。差异与UTF-8检查通过。
- 用户随后明确“我已关闭wsl，注意禁止自动启动wsl”。已接受该约束，未启动任何WSL实例、重启后端、调用真实模型、写业务数据／配置或重跑报告。真实验收依赖当前数据库和模型配置，需要用户自行恢复WSL后继续，不能凭离线全绿标记目标完成；恢复后先只读复核全库活动任务与配置，再载入补丁和验收。

### 2026-10-24 继续目标：参数校验错误保留具体原因

- 上一目标轮已完成流内错误分类修复，属于progress；原目标仍未完成。本轮继续只读本地日志，不依赖已关闭的数据库，不启动WSL或委派子代理。
- 报告23的run1208／1209实际将 `scope.kind=common` 与非空 `lot_refs` 同时提交。run1208连续两次获得仅含 `records.0.scope` 的提示，改正范围后又遇到逐字引用错误而连续三次提交终止；run1209此前两次还将records写成字符串。旧反馈省略校验原因，模型无法直接区分缺项、类型和业务规则冲突。
- `validation_feedback` 现保留字段路径和Pydantic校验原因，明确如 `common/unknown 不填 lot_refs`、必须列表及必填项缺失；排除input、ctx及帮助链接，最多6项、1000字符。不自动转换common为lots、不替换引用，不放宽权限、总预算或纠错次数。
- 新增3项真实图回归先失败，再验证具体原因和错误路径、错误参数正文不回显、非法提交不暂存／发布，以及修正后显式final收尾。综合与护栏专项 **85 passed**；最终 `scripts/check-backend.ps1` **943 passed / 9 skipped**（47.93秒），Ruff、5项分层约束及协议／真实装配mypy通过，保留2条既有structlog提示。差异与UTF-8检查通过。
- 只运行 `wsl.exe --list --running --quiet` 查看状态，成功返回空列表，确认当前无运行中的WSL实例，未启动任何实例。仍缺少运行服务加载最新补丁及真实完整专题验收，需要用户自行恢复WSL后先复核活动任务和当前配置。未调用真实模型、重启服务、改业务数据／配置、重跑报告或提交；不以离线测试代替目标完成证明。

### 2026-10-24 续接最新会话：阶段通知与保证金真实复验

- 用户要求读取较新的“继续排查解析模块问题”会话并继续。索引中 `01a16d66…` 是当前续接会话；最新有实质工作的原会话是 `01a16c77…`（13:52起，含17:53／18:05续接分段）。原会话中用户已明确自行启动WSL，完成14:19启动服务、14:20隔离复现及阶段提示对照；后来续接因上游会话资源错误中断，修复仅留下两项失败回归，交接文件未更新。不能继续沿用历史“基础设施尚未恢复”的结论。
- 只读复核PostgreSQL／Redis正常，全库分析报告、模块运行和文档任务没有运行／排队项，当前analysis首选仍是模型15 Nemotron，后备28／27；资料13／版本3／解析批次6未变。未覆盖绑定，未启动WSL，未委派子代理。
- 真实问题是进入收尾后仅提供 `complete_research`，历史工具报错仍要求修正 `read_document` 参数。修复为本次模型请求最后追加简短HumanMessage，列出过滤后的工具及下一步；历史工具消息保持原样，不写回图历史／检查点，不重复完整Skill或研究账。未做项目检索时明确先检索再登记；登记后逐条提交并显式收尾。权限、引用与预算不变。
- 适配器专项44项通过；解析护栏与综合专项87项通过。两项阶段回归先失败再通过，并加强短通知不重复Skill及首次项目检索例外。最终 `scripts/check-backend.ps1` **945 passed / 9 skipped**（54.33秒），Ruff、5项分层契约及协议／真实装配mypy通过，保留2条既有structlog提示。
- 新隔离验收目录 `.tmp/parse-failure-20261024/model-deposit_requirement_parsing-202052/`。使用真实图、当前首选模型、关键词检索回退，600秒／36次模型／48次全部工具硬上限；仅写临时目录，无业务报告、配置或调用账写入。第28次模型调用正确执行 `complete_research`，随后开始提交，证明本轮越过旧阶段卡点；不能据此声称完整成功。
- 最终497.22秒、35次模型调用、31次全部工具（22次研究工具）、90块证据、1项缺口，**0项核实、无draft／final**。第30次提交将综合改写塞进 `s13r6c136` 的quote，回读后第32次提交又在 `s13r6c966` 引文失败；第35次再次回读后触发收尾无进展2次上限。半截／错误引用均未发布，不增加预算、不代替模型补引文。
- 另核对到覆盖不足：研究摘要仍把默认合同金额10%当作履约保证金金额，但没有读取第24—25页前附表的专用标段金额（50／40／30／20万元）；已读第22页投标保证金为6万元、不分标段。前附表转引被错误概括成“正文未读取到”，实际已读部分前附表。该轮没有形成可校验业务结果，不将覆盖声明当作完整性证据。
- `.tmp/.../audit_run.py` 和运行目录 `audit.json` 保存阶段工具、引文身份检查及缺口供复核；因本轮没有核实事项，0项引文异常不代表引用验收通过。原会话末尾的 `InvalidModelOutput` 不能仅凭异常类型推断为非法JSON，需结合具体工具反馈。
- 隔离验收已退出；再次复核全库无活动任务后，使用 `scripts/start-backend.ps1 -Force` 加载补丁，API／Worker／Beat分别为PID 28804／34224／33548，启动及最终API健康检查均通过。严格UTF-8检查覆盖全部11个修改文件，差异检查通过，无残留本轮验收或测试进程。未提交、推送、重跑历史报告或修改模型配置；完整专题与13专题真实效果仍待继续核对，不能标记完成。


### 2026-10-25—26 后端架构审查七项修复

用户明确要求“修复全部问题”，本次连续工作完成已确认的七项架构问题。保持既有 application/ports/adapters 分层，沿用 karpathy-guidelines；未委派子代理，未提交。原工作区干净，基线统一检查为945通过/9跳过。

1. **任务恢复**：新增 `0017_document_recovery`（上一版0016），持久化 `job.next_attempt_at` 和 `dispatch_lease_until` 及索引。调度先恢复到期轮询或过期消息，再应用新增任务间隔与配额；仍持锁任务延后扫描，避免饿死后续任务。未知远端提交继续要求人工核对，不能自动重提。任务认领核对消息阶段，迟到转换消息不能恢复下一阶段的派发标记；提前消息不消耗预算。网络重试计数同事务持久化，恢复保留退避、累计时间与次数。
2. **配额一致性**：解析在途统计覆盖submitting/parsing/resubmitting，转换覆盖converting/probing/geometry；公司/资源咨询锁保护计数与差额派发。转换交接先释放旧资源，再等解析派发。
3. **Worker隔离**：四组分别消费convert,parse、tender、poll、analysis。新poll队列仅改变路由，既有Celery消息名保持；本地脚本、Compose、环境模板和指南同步，节点身份识别仍兼容旧Worker。
4. **检索路径**：已完成索引直接读knowledge_chunk；词法命中、余弦、阈值、同分次序、RRF及LIMIT在数据库执行，结果不传向量。未建成/旧分块版本保留原文回退，用单个JSONB参数避免绑定参数上限。查询实时核对公司和来源/文件/版本/解析批次。仍是精确扫描，未引入ANN；大语料仍需测量数据库负载。
5. **业务执行归位**：新增application/analysis/execution.py、knowledge/execution.py和llm/factory.py，移除原worker/analysis/controller.py与worker/llm/routing.py及本轮空置包；通过core/di.py注入仓储、模型、嵌入、重排与检查点，Worker接入消息、锁及用例。
6. **仓储窄端口**：按sources/retrieval/management/execution/dispatch/reports及共享生命周期、结构检查拆分；KnowledgeStore组合契约仅供装配。真实仓储保留联合事务，不复制SQL；新增契约防止application重新依赖组合接口。
7. **Agent状态转换**：AnalysisState/AnalysisTransitions集中处理新证据失效、暂存、核实、单次final消费、草稿发布与失败改写回滚；兼容原检查点字典、未知字段和重放账，不重置预算，不放宽引用与支持性校验。state.py加入持续mypy目标。

验证：

- 最终 `scripts/check-backend.ps1`：**952 passed / 10 skipped**（60.47秒），Ruff、5项分层、端口/真实装配/核心状态mypy通过。新增跳过项来自0017只有ALTER而无新表的DDL通用用例，不是跳过业务回归；保留2条既有structlog提示。
- 完整隔离PostgreSQL `tests/integration`：**118 passed**（76.28秒），包含13项文档恢复/配额/消息回归、26项检索语义/权限/有限传输回归，以及真实13专题图与PG检查点（可控模型）。一条既有structlog提示。
- 旧集成夹具同步当前正式协议：选证请求使用evidence_sets及逐值结果，业务JSON schema包含scalar_columns；未修改生产校验来迁就测试。
- 启动脚本44项身份/启动预检通过（拦截启停操作）；Compose YAML、四池队列、共享环境与迁移依赖静态检查通过。环境未提供Docker CLI，没有运行容器验收。
- HEAD与当前工作区完整OpenAPI一致，共66条路径。0017在隔离空库完成降级0016/升级head往返，列和索引核对通过；文档DDL契约已登记新增迁移。UTF-8、PowerShell BOM及差异检查通过。

运行边界：本轮独立原生Windows PostgreSQL位于`.tmp/architecture-review-db`、端口55439，已用对应pg_ctl正常停止；无需也未启动WSL。未启停API/业务Worker/Beat，未修改业务库、模型绑定或业务报告，未调用真实供应商，未提交或推送。新增代码尚未由本轮部署加载。上线先应用0017，再按指南加载API、四组Worker和Beat；旧Worker不消费poll队列。此前真实完整解析效果验收仍待继续，不能将本轮可控模型及离线结果当作真实模型成功。
