# DeepAgents 标书分析运行时

新报告使用 `deepagents-0.7.22-v1`。控制器先创建13个模块和独立运行线程，再并发调度真实 DeepAgents 子图；模块自主检索和补读，不做全文扫描分派或强制读取首批段落。旧固定字段流程已下线：`runtime_version=legacy` 的历史报告只读展示，既不继续执行也不能补跑，需要最新结果时重新发起分析。

## 执行与数据边界

每份报告固定项目资料、关联参考库资料、类别/专题/标段和只读 Skill。每个模块有独立上下文、证据账、工具结果、checkpoint thread_id 和 attempt。工具只暴露 list_documents、search_document、search_knowledge、read_document、read_file、submit_analysis；关闭通用递归子代理，没有 Shell、任意磁盘或网络工具。

每次模型请求、工具执行前后和检索返回后，检查公司/项目、实时知识库关联、资料身份和解析批次。撤销关联或替换资料立即停止当前执行；报告查询也隐藏撤销来源的结论。来源版本固定，不把新旧批次混合引用。

检索返回最多12块。按来源、批次、元素和规范化正文去重；不同文件保留各自依据。证据账存放于模块 state，与模型消息压缩分离。达到上下文预算80%触发摘要，压缩历史只写内存后端 `/conversation_history/**` 并随图持久化；摘要和 Skill 都不能作为引用来源。模块 Skill 及 references 只读。

达到证据预算时，混合批次仍返回可容纳的新块及已读原文，显式报告省略数量；只剩超限新块时回传可纠正提示。整批权限检查仍然原子拒绝，不能因为预算已满而跳过越权结果。模型每轮可见剩余证据额度。

## 配额、预算与恢复

配置中心 `analysis.max_inflight` 默认2，是同公司跨报告、跨 worker 的硬配额。调度使用数据库事务锁串行检查总占用，模块持有独立 PostgreSQL 会话锁直到清理结束。租约过期但会话仍持锁时不抢占；连接丢失后锁自动释放，旧 owner 的后续请求和写入被拒绝。配额连接采用独立 NullPool，避免占满业务连接池导致心跳无法续约。降低并发上限时等待已有运行排空，不超额接受新任务。

每个 attempt 默认32次模型请求、48次工具调用、160块证据、900秒总时长、24000上下文token预算、4096输出token上限。模型、工具、时长、上下文和输出可在配置中心调整；补跑创建的新 attempt 重新读取配置中心当前值（每个 attempt 各自留存限值快照），恢复执行不重置当次已消耗预算。模型路由在每个实际请求前预占持久次数，重试、故障转移、格式纠正、摘要和支持性验证全部计入，未知结果不退还请求次数；记录实际输入/输出token。SDK自动重试关闭，统一由既有有限路由控制。

恢复时调用图 `aget_state`，对未完成节点使用 `ainvoke(None)`；tool_call_id 对应结果可重放，已完成模块不重复执行。同报告优先恢复旧线程；失去会话锁的旧running重新显示为排队。支持性验证结果也保存在独立状态中。补跑接受 failed/partial/canceled 报告，仅为选中的失败、已取消模块创建新 attempt，已完成模块保留，旧计数、证据及错误不丢失；并发点击补跑由行锁拒绝。控制器和模块均检查取消，清理客户端后释放锁。

## 汇总与接口

模块提交结果为字段数组：每个 field 含 `field`（解析字段名）、`group`（展示分类）、`sort_order`（展示顺序）、
`values`（解析值数组）和 `note`；每个 value 含 `value`（解析值原文表述）与 `citations`（`[{block_id,quote}]`）。
证据逐值绑定，同一字段的多个值各自成项、各带自己的引用，前端据此对每个值单独定位和判重。
`relations` 与 `research_summary` 保持原结构。汇总仅合并同 `field`、`group`、`note` 且 values 等价的字段断言，
按值级对齐合并引用和模块来源。不同断言及冲突保留，明确修订由模块同时引用原条款和补充条款，不按文件上传时间裁决。

模块逐项验证引文连续原文及来源身份，在提交工具内做模型支持性验证，连续提交失败最多反馈两次修正；成功暂存后重置连续错误数，总模型/工具预算不重置。第三次失败的具体原因仍写入工具记录。未通过的结果不能完成模块或进入已验证关系图谱；关系断言在最终批同样包成字段单元一并验证。缺失条款只进入检索总结，修订结论同条目引双方，参考建议同时引本项目要求。支持性验证完全在提交工具内完成，worker 不再直接调用模型核对结果。

支持性验证逐项审查字段名、展示分类、备注和每个解析值，先列出无依据断言，再返回是否支持；即使模型返回支持，只要列出了无依据断言也拒绝通过。备注不能补造免责或适用条件；大纲节点类型和层级数字是展示信息，但上级路径与逻辑标归属必须有原文依据，最终派生的父子关系同样送审。审查不携带旧验证标签，具体原因反馈给子 Agent。跨条目的引用不能替本条补足金额、数量和范围。已完成后因质量问题拒绝的旧结果不得携带 verified 标记进入补跑；旧答案和账目保留用于审计，桌面只展示已完成模块的结论。

独立问答 Agent 默认共用16次实际模型请求、24次工具调用、80块证据与900秒总时限。原生对话、模型重试、摘要及支持性校验通过同一路由扣除请求预算；提交与读取压缩历史也占工具预算。总截止时间覆盖整个图及检索等待，超限停止并关闭模型客户端。问答默认 `final=false` 暂存，显式 `final=true` 才合并全部批次并完成。

问答的图谱扩展在检索工具内执行，只访问本次检索范围的资料。普通检索先取最多12块，关联原文再加入同一证据账并受总块数预算限制；只有全部引用已进入证据账的关系才交给 Agent。回答中的检索统计、关联依据和 `graph_used` 来自实际工具结果。前端组内按 `sort_order` 稳定排序，同序字段保留提交顺序。

章节标题超出前后窗口时，校验载荷额外提供同一资料、同一解析版本中沿连续原文向前找到的最近独立章标题及其位置；遇缺块即停止回溯，不把目录行或正文中的章节引用当标题。该信息仅供结合条号核对章节归属，不能证明混入章中的其它项目公告适用于本项目，也不能补足结论事实。人员数量、学历、分值等未找到的信息只写入检索总结，无依据的值直接省略；原文明示“不要求”的条款仍保留。

校验服务暂不可用与结果内容无效分别记账：前者以 `review_unavailable` 工具错误类型持久化，不消耗或重置连续内容纠错次数；仍消耗实际模型、工具调用预算，仍受模块总时限约束。传输失败仅记录异常类型，区分请求超时和远端断连，不回显可能包含密钥或正文的原异常消息。

OpenAI Chat Completions 的结构化补全采用流式接收，避免网关在长推理期间因无响应数据而断连；原生 Agent 工具调用路径不变。适配器只拼接正式正文，不使用思考内容，收到完成原因和 `[DONE]` 后才交给原 JSON/支持性校验；断流或错误事件仍按暂不可用处理，输出达限仍拒绝，并保留已返回的 token 用量。兼容服务忽略流式请求而返回完整 JSON 时继续使用原校验，不更换模型。其它 API 协议沿用原请求方式。

解释型校验逐条调用，避免多条引文展开后产生过大的审查提示（普通非解释型校验仍按体量分批），避免长提示触发网关超时；输入包含结论、引文和来源归属，不重复传输定位坐标等无关元数据；引文本身仍限定为模块读过的块，但校验窗口会按引文所属资料补读原文，给出引文块完整原文、按 offset 排列的前后物理邻域和跨块连续原文，用于核对条号、章节标题、资料归属和被分块切开的续句；标题块与引文块分属不同块时归属可凭邻近标题加引文块内条号确认，金额、条件、范围、否定、例外等结论事实仍必须在引文、同块原文或连续原文中直接写出，offset 不连续的邻域块不能补足事实；旧 attempt 引文缺少块身份时按元素与引文原文回退定位。邻域与连续原文只对含章节/条号/归属表述的条目发放，单次调用总量封顶。网关返回 200+空正文按暂不可用同模型重试，5xx（含 524）不降级重试；校验期请求被上游截断时把“引用校验暂时不可用”作为可纠正反馈交回子 Agent，不终结整个模块。同义改写可以通过，但金额、时间、主体、范围、否定、前提和例外不得改变。连续返回自然语言而未调用工具时，在同一子图内最多纠正两次；自然语言总结不能直接作为已完成结果，纠正状态同样持久化。

`GET /api/v1/analysis/reports/{report_id}` 返回 runtime_version、summary、各模块 runs（attempt、状态、预算、用量、时限），不返回原始中间消息/证据账；旧运行时报告带 `runtime_retired` 标记，前端据此隐藏补跑入口并提示只读。`GET /api/v1/analysis/reports/{report_id}/runs/{run_id}/events?after=0&limit=100` 分页查询审计事件，限定报告、公司和运行归属。原有创建/取消/补跑接口保持；新报告不再返回扫描覆盖百分比。

桌面分析页展示专题完成数、排队/运行/失败状态、每次运行用量及单模块补跑，引用仍使用原文定位组件。

失败补跑接口可显式提供max_output_tokens（512–16384）和timeout_seconds（300–3600），只覆盖新attempt的对应字段；其余限值取配置中心当前值，用户调整配置后补跑立即生效。旧attempt、报告创建时的快照和用量不回写，请求次数也不会随之扩大。上下文预算 `analysis.context_tokens` 不设上限，可用范围由所绑定模型的窗口决定。

## 部署与验收

按顺序执行：

```powershell
cd apps/api
uv run alembic upgrade head
uv run python -m tender.application.agent_checkpoints
```

0008 仅创建业务表和隔离 schema；初始化命令在部署阶段显式调用 AsyncPostgresSaver.setup()。该框架 DDL 包含并发建索引，必须在 autocommit 连接中执行，不能嵌入 Alembic 事务。worker 不自动建表。Windows 两个入口使用 SelectorEventLoop，兼容 psycopg 异步连接。不要修改已应用的0005/0007。

验收复用项目13、来源9/11、关联库7来源12，不重新上传。旧报告7已于2026-10-07确认 canceled 后才允许启动 worker。仅验收桌面。单元/数据库假模型检查不代表真实模型质量已通过；最终结果在 HANDOOFF.md 记录。

上游408/429/500/502/503/504及连接超时使用有抖动的有限重试；每次请求均落账，超时结果标为未知。429按Retry-After的秒数或HTTP日期冷却，缺省30秒；0009新增供应商共享截止时间，跨模块、报告、worker和重启生效。允许降级时优先使用未冷却的授权后备模型，全部冷却时等待最早恢复者。`failover_limit=1` 时固定最高优先级的启用模型，限流也只能等待和重试它，不能通过冷却排序换成后备模型。不为等待预占请求次数。等待受取消和模块总时限约束；冷却时间超过剩余预算时明确失败，保留checkpoint供补跑。SDK隐式重试关闭，防止重试次数相乘。

路由总时限取功能预算和模块剩余时间的较小值，再按剩余候选与重试机会分配单次等待上限；不超过模型配置的timeout。避免300秒的后备模型连续两次超时吃光600秒路由预算，使最后一个已配置候选仍有执行机会。

输出达到token上限且必填工具参数缺失，即使网关标记正常tool_calls也视为截断，记账后只在允许的候选范围内尝试后备模型，不反复用相同输出额度纠正。禁止降级时明确失败。未达到额度的工具参数缺失走有限协议纠正，不占用业务结论的三次校验机会。不会把无效或不完整的输出写为已完成结果。

普通专题每批最多3条，格式大纲每批最多6个节点；工具 schema 只暴露当前专题需要的字段。`submit_analysis` 默认 `final=false` 暂存，全部事项提交后显式 `final=true` 完成，避免遗漏参数时只保留第一批。格式节点先父后子，可用同一id修正，每批均对累计节点整体校验父级、循环、层级及引文。未变更且本attempt已验证的条目复用验证结果，父级变化影响的子节点重新验证。

暂存条目与独立证据账一起持久化，恢复和失败补跑可继续已有成果；新attempt清除旧工具缓存、连续纠错计数及暂存验证标记，不能仅凭历史supported标签跳过校验。分批不改变模型/工具总预算，也不允许未完成的暂存结果进入报告。

## 业务 DDL

checkpoint 表由固定版本的框架管理，限定 agent_runtime schema；以下是0008的业务DDL与配置种子。

```sql
CREATE SCHEMA agent_runtime;
REVOKE ALL ON SCHEMA agent_runtime FROM PUBLIC;
ALTER TABLE analysis_report
    ADD COLUMN runtime_version TEXT NOT NULL DEFAULT 'legacy',
    ADD COLUMN runtime_settings JSONB NOT NULL DEFAULT '{}',
    ADD COLUMN reference_snapshot JSONB NOT NULL DEFAULT '[]',
    ADD COLUMN summary JSONB NOT NULL DEFAULT '[]';
CREATE TABLE agent_module_run (
    id SERIAL PRIMARY KEY,
    module_id BIGINT NOT NULL REFERENCES analysis_module(id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL,
    attempt INT NOT NULL DEFAULT 1 CHECK (attempt > 0),
    thread_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','running','completed','failed','canceled')),
    owner UUID,
    lease_until TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    deadline_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    model_calls INT NOT NULL DEFAULT 0 CHECK (model_calls >= 0),
    tool_calls INT NOT NULL DEFAULT 0 CHECK (tool_calls >= 0),
    prompt_tokens BIGINT NOT NULL DEFAULT 0,
    completion_tokens BIGINT NOT NULL DEFAULT 0,
    limits JSONB NOT NULL,
    state JSONB NOT NULL DEFAULT '{}',
    error_message TEXT,
    UNIQUE (module_id, attempt)
);
CREATE INDEX ix_agent_module_run_active ON agent_module_run (company_id, status, lease_until);
CREATE TABLE agent_run_event (
    id BIGSERIAL PRIMARY KEY,
    run_id INT NOT NULL REFERENCES agent_module_run(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_agent_run_event_run ON agent_run_event (run_id, id);
INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.max_inflight', 'L1', 'int', '2'::jsonb, '同公司所有报告共享的 DeepAgents 子代理并发上限', false),
('analysis.max_model_calls', 'L1', 'int', '32'::jsonb, '每模块每次运行的实际模型请求上限，含重试和摘要', false),
('analysis.max_tool_calls', 'L1', 'int', '48'::jsonb, '每模块每次运行的工具调用上限', false),
('analysis.timeout_seconds', 'L1', 'int', '900'::jsonb, '模块从首次执行开始的总时限，恢复不重置', false),
('analysis.context_tokens', 'L1', 'int', '24000'::jsonb, '模块上下文预算，达到百分之八十时压缩', false),
('analysis.max_output_tokens', 'L1', 'int', '4096'::jsonb, '模块单次模型输出上限', false);
```

0009只追加运行状态列，不修改已应用迁移或模型绑定：

```sql
ALTER TABLE llm_provider ADD COLUMN rate_limited_until TIMESTAMPTZ;
```
