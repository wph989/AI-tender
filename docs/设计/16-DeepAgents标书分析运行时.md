# DeepAgents 标书分析运行时

新报告使用 `deepagents-0.7.22-v1`。控制器先创建13个模块和独立运行线程，再并发调度真实 DeepAgents 子图；模块自主检索和补读，不做全文扫描分派或强制读取首批段落。历史报告的 `runtime_version=legacy`，只在处理历史快照时使用原流程。

## 执行与数据边界

每份报告固定项目资料、关联参考库资料、类别/专题/标段和只读 Skill。每个模块有独立上下文、证据账、工具结果、checkpoint thread_id 和 attempt。工具只暴露 list_documents、search_document、search_knowledge、read_document、read_file、submit_analysis；关闭通用递归子代理，没有 Shell、任意磁盘或网络工具。

每次模型请求、工具执行前后和检索返回后，检查公司/项目、实时知识库关联、资料身份和解析批次。撤销关联或替换资料立即停止当前执行；报告查询也隐藏撤销来源的结论。来源版本固定，不把新旧批次混合引用。

检索返回最多12块。按来源、批次、元素和规范化正文去重；不同文件保留各自依据。证据账存放于模块 state，与模型消息压缩分离。达到上下文预算80%触发摘要，压缩历史只写内存后端 `/conversation_history/**` 并随图持久化；摘要和 Skill 都不能作为引用来源。模块 Skill 及 references 只读。

## 配额、预算与恢复

配置中心 `analysis.max_inflight` 默认2，是同公司跨报告、跨 worker 的硬配额。调度使用数据库事务锁串行检查总占用，模块持有独立 PostgreSQL 会话锁直到清理结束。租约过期但会话仍持锁时不抢占；连接丢失后锁自动释放，旧 owner 的后续请求和写入被拒绝。配额连接采用独立 NullPool，避免占满业务连接池导致心跳无法续约。降低并发上限时等待已有运行排空，不超额接受新任务。

每个 attempt 默认32次模型请求、48次工具调用、160块证据、900秒总时长、24000上下文token预算、4096输出token上限。模型、工具、时长、上下文和输出可在配置中心调整；新报告固定配置快照，恢复不重置。模型路由在每个实际请求前预占持久次数，重试、故障转移、格式纠正、摘要和支持性验证全部计入，未知结果不退还请求次数；记录实际输入/输出token。SDK自动重试关闭，统一由既有有限路由控制。

恢复时调用图 `aget_state`，对未完成节点使用 `ainvoke(None)`；tool_call_id 对应结果可重放，已完成模块不重复执行。同报告优先恢复旧线程；失去会话锁的旧running重新显示为排队。支持性验证结果也保存在独立状态中。失败补跑仅为选中的失败/中断模块创建新 attempt，保留旧计数、证据及错误；并发点击补跑由行锁拒绝。控制器和模块均检查取消，清理客户端后释放锁。

## 汇总与接口

模块逐项验证引文连续原文及来源身份，在提交工具内做模型支持性验证，拒绝无依据推断并最多反馈两次修正；未通过的结果不能完成模块或进入已验证关系图谱。缺失条款只进入检索总结，修订结论同条目引双方，参考建议同时引本项目要求。汇总仅合并同 kind、title、text、cells 的等价断言，并合并引用和模块来源。不同断言及冲突保留，明确修订由模块同时引用原条款和补充条款，不按文件上传时间裁决。

支持性验证逐项审查标题、正文和表格值，先列出无依据断言，再返回是否支持；即使模型返回支持，只要列出了无依据断言也拒绝通过。审查不携带旧验证标签，具体原因反馈给子 Agent。跨条目的引用不能替本条补足金额、数量和范围。已完成后因质量问题拒绝的旧结果不得携带 verified 标记进入补跑；旧答案和账目保留用于审计，桌面只展示已完成模块的结论。

`GET /api/v1/analysis/reports/{report_id}` 返回 runtime_version、summary、各模块 runs（attempt、状态、预算、用量、时限），不返回原始中间消息/证据账。`GET /api/v1/analysis/reports/{report_id}/runs/{run_id}/events?after=0&limit=100` 分页查询审计事件，限定报告、公司和运行归属。原有创建/取消/补跑接口保持；新报告不再返回扫描覆盖百分比。

桌面分析页展示专题完成数、排队/运行/失败状态、每次运行用量及单模块补跑，引用仍使用原文定位组件。

失败补跑接口可显式提供max_output_tokens（512–16384），只作用于新attempt的limits，用于修复输出额度不足；省略时沿用报告配置。旧attempt、报告原配置和用量不回写，请求次数与总时限也不会随之扩大。

## 部署与验收

按顺序执行：

```powershell
cd apps/api
uv run alembic upgrade head
uv run python -m tender.application.agent_checkpoints
```

0008 仅创建业务表和隔离 schema；初始化命令在部署阶段显式调用 AsyncPostgresSaver.setup()。该框架 DDL 包含并发建索引，必须在 autocommit 连接中执行，不能嵌入 Alembic 事务。worker 不自动建表。Windows 两个入口使用 SelectorEventLoop，兼容 psycopg 异步连接。不要修改已应用的0005/0007。

验收复用项目13、来源9/11、关联库7来源12，不重新上传。旧报告7已于2026-10-07确认 canceled 后才允许启动 worker。仅验收桌面。单元/数据库假模型检查不代表真实模型质量已通过；最终结果在 HANDOOFF.md 记录。

上游408/429/500/502/503/504及连接超时使用有抖动的有限重试；每次请求均落账，超时结果标为未知。429按Retry-After的秒数或HTTP日期冷却，缺省30秒；0009新增供应商共享截止时间，跨模块、报告、worker和重启生效。优先使用未冷却的授权后备模型，全部冷却时等待最早恢复者，不为等待预占请求次数。等待受取消和模块总时限约束；冷却时间超过剩余预算时明确失败，保留checkpoint供补跑。SDK隐式重试关闭，防止重试次数相乘。

路由总时限取功能预算和模块剩余时间的较小值，再按剩余候选与重试机会分配单次等待上限；不超过模型配置的timeout。避免300秒的后备模型连续两次超时吃光600秒路由预算，使最后一个已配置候选仍有执行机会。

输出达到token上限且必填工具参数缺失，即使网关标记正常tool_calls也视为截断，记账后直接尝试后备模型，不反复用相同输出额度纠正。未达到额度的工具参数缺失走有限协议纠正，不占用业务结论的三次校验机会。不会把无效或不完整的输出写为已完成结果。

普通专题可通过submit_analysis(final=false)分批暂存少量已验证条目，最后final=true合并完成。暂存条目与独立证据账一起持久化，不占后续模型上下文；恢复和失败补跑可继续已有成果，新attempt清除旧工具调用缓存及纠错次数。格式大纲因父子引用需整体校验，仍一次提交节点。分批不改变模型/工具总预算，也不允许未完成的暂存结果进入报告。

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
