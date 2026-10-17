# 19 · Agent 检索与专题汇总

更新：2026-10-16

## 工作流

上传文件 → 转换与解析 → 13 个专题各自检索 → 确认检索覆盖与转引 → 综合输出 JSON → 支持性校验 → 展示并定位原文。

旧字段规则、复抽、人工字段复核、字段冲突裁定、字段 Excel 导出及金标回放已下线；文档预览、章节导航、知识检索和项目问答继续使用。

队列统一为 `tender,convert,parse,analysis`；知识索引、专题分析和问答投递到 `analysis`。
宿主机启动脚本、容器编排及启动说明必须消费生产者定义的全部队列，由契约测试核对，避免新分析永久排队。

## 检索和汇总协议

- 每个专题先加载冻结的 Skill，列出项目资料，并按 coverage.json 核对所有主题、主文件及澄清补遗。
- complete_research 登记主题证据和转引处理情况，再进入综合阶段。真实检索词、来源和证据 ID 直接取服务端工具事件；queries 只是可选的检索意图说明，不要求复述或精确匹配。
- 主题可用 key 或 Skill 中文名称。重复说明合并，遗漏和无法确定归属的主题记为待核对缺口，不因主题清单形式阻断已有依据的分析结果。
- 资料清单在服务端已知，不强制以 list_documents 调用顺序证明核对；未检索的补充资料明确显示范围缺口。
- 汇总按完整事项组织，允许同一条综合多处证据。content 是 Skill 对应分类和列名的 JSON，citations 独立携带已读 block_id 和连续原文 quote。
- 技术模块保留“项目背景”“技术方案要求”及“要求摘要”“关键要求”数组；价格与评分使用各自的列；格式模块保留父子 key 和编制要求。
- 原文没有依据的列省略；数值、逻辑条件、评分档次和独立任务不得在概括中丢失。
- 每个 subagent 负责一个分析维度，完成该维度检索后，每次只提交一个完整事项的 JSON，逐条校验保存；正文条目通过原文支持性校验且 final=true 后完成专题。coverage、gaps、research_summary 可省略；省略 gaps 时保留已登记缺口，最终提交显式清单时替换内容缺口。覆盖遗漏和关联错误降为 pending 并显示缺口，不阻断已核实的正文。
- 只有检索或补读引入新证据才要求重新确认和整体综合；未命中或只返回已读证据时保留已核实成果，并更新真实检索账。
- 单条技术要求的字符串整理为数组，摘要与要求可由已有内容补齐；部分表格列缺失时保留有依据的分析内容，不能为了凑齐模板编造值。整理后的全部内容仍送原文支持性校验。
- 格式分组可以嵌套，逐条提交时先保存父节点或关系端点；循环、缺失父节点、错误归属仍必须修正。标段只给名称时可省略 code，目录内部用已核实名称查找，分析结果不伪造原文编号。
- 未解决的检索和转引缺口由服务端保留。界面明确显示检索范围与未决事项，检索未找到不等于全文没有要求。

## 检索阈值与单次返回数量

专题检索同时使用 `analysis.similarity_threshold`（默认 `0.6`，范围 `0..1`）和
`analysis.max_search_results`（默认 `6`，正整数）。入口为模型管理的“分析参数”；保存后
新建或补跑采用当前值，已有运行保留参数快照，不在检索途中切换口径。

先过滤低于阈值的候选，再进行混合排名及可选重排，最后取前 N 条；没有足够达标结果时
返回实际数量或空列表，不能用低相关内容补齐。RRF 融合值和供应商重排分数仅用于排序，
不能冒充相似度。某块有与当前查询匹配的可用向量时，以原始余弦相似度判断阈值；缺向量、
索引不匹配或向量服务不可用时，以命中的检索词数量 / 检索词总数判断相关度。
检索词沿用全文检索分词规则（含中文二字词），该比例属于关键词覆盖度，不是语义概率。

单次数量上限作用于专题项目检索和参考检索，工具扩展也不能超过该上限。模型收到的每块
仍只有 `id/text`；评分、位置和实际检索参数保留在服务端事件账。显式按已读 ID 补读邻近
原文不套用相似度过滤，默认当前块加前后各两块、最多十二块，以保留表头和必要条件。
知识库页面搜索和问答沿用原检索协议；专题累计证据上限仍由 max_evidence_blocks 控制。

新增迁移 `0014_analysis_retrieval` 仅登记配置项，不改写历史配置版本、业务记录或运行快照：

```sql
INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.similarity_threshold', 'L1', 'number', '0.6'::jsonb, '专题检索最低相关度（0到1），有向量时用余弦相似度，否则用检索词命中比例', false),
('analysis.max_search_results', 'L1', 'int', '6'::jsonb, '每次专题检索通过阈值后返回的证据块上限', false);
```

## 纠错与进展

目的为分析结果和精确原文定位，过程清单是质量说明。检索门禁只阻断实际没有项目检索、虚构或越权证据等无法支撑分析的问题。
覆盖或转引证明缺项降为未决状态；空白过程说明可由服务端补充，过长摘要截取，不占用内容纠错次数。
确定性校验一次返回全部问题与服务端检索记录。不同问题组合分别计数；同类错误仅更换错误值不能重新获得额度，计数随检查点持久化。
新的成功检索即使没有新增原文也算研究进展；相同请求重放、改名和未校验草稿不算。总模型、工具、证据及时间预算保留。

连续无进展达到 `analysis.max_no_progress_rounds`（默认3轮）进入收尾；之后继续无进展
达到 `analysis.max_finish_corrections`（默认2轮，正整数）终止并保留已核实成果。
该参数位于“模型管理 → 分析参数”，新建或补跑时冻结；同一线程恢复保留已用次数。
每轮收尾提示显示剩余机会，有新的证据或核实成果等有效进展时连续无进展计数重新开始。
`analysis.max_validation_failures` 控制单一事实的校验失败额度，不能替代收尾额度。
模块仍须显式提交 final=true 才完成，耗尽时保留成果并报告未完成，不能将部分结果冒充完成。

迁移 `0015_finish_corrections` 仅登记新增参数，不改写历史运行与配置版本：

```sql
INSERT INTO config_item (key,layer,value_type,default_value,description,requires_gate) VALUES
('analysis.max_finish_corrections', 'L1', 'int', '2'::jsonb, '进入收尾后允许的连续无进展纠正轮数，耗尽时保留已核实成果并终止', false);
```
没有生产调用的旧 analysis_outline 解析器及其“最多三级/分组只能为根/正文逐字摘录”协议已删除；历史报告读取兼容测试直接构造历史记录，不再依赖旧生成器。

## 存储和兼容

运行时版本为 deepagents-0.7.22-v5-records。专题 JSON 与检索记录复用 analysis_module.business_data、items 和运行检查点，不另建字段抽取表。
位置由服务端回填，所有 content 与业务属性共同接受证据校验。引用失去访问权限时隐藏内容及检索说明。
旧报告只读展示，不将原文摘录伪装为新版综合结果；需生成新版结果时新建分析。

## 下线迁移

0013_retire_extraction 清理旧任务和功能绑定，移除旧数据表及关联列。历史配置版本和模型调用日志仍保留。
这是数据删除迁移，应用到业务库前须有可恢复备份；不支持以重建空表的方式降级。隔离测试 schema 内验证不影响业务库。
SQL 如下（与迁移逐字对应；不使用 CASCADE，未知依赖会触发事务回滚）：

```sql
UPDATE job SET status = 'canceled', error_code = 'feature_retired',
    error_message = '字段抽取流程已下线，请使用项目 Agent 分析',
    dispatched_at = NULL, finished_at = now(), updated_at = now()
WHERE stage IN ('extracting', 'exporting')
  AND status NOT IN ('completed', 'partial', 'failed', 'canceled');

DELETE FROM llm_feature_model WHERE feature_key IN ('extract', 'retry');

DELETE FROM llm_feature WHERE key IN ('extract', 'retry');

DELETE FROM config_item WHERE key LIKE 'extract.%';

INSERT INTO config_item
    (key, layer, value_type, default_value, description, requires_gate)
VALUES
    ('queue.priority.batch', 'L1', 'string', '"low"'::jsonb, '批量任务的队列优先级', false),
    ('render.crop_dpi', 'L2', 'int', '300'::jsonb, '页面裁剪图 DPI', true)
ON CONFLICT (key) DO UPDATE SET description = EXCLUDED.description;

ALTER TABLE llm_call_log DROP COLUMN extraction_id;

ALTER TABLE config_release DROP COLUMN regression_run_id;

ALTER TABLE field_instance DROP CONSTRAINT fk_field_instance_current_extraction;

DROP TABLE review_task;

DROP TABLE review_action;

DROP TABLE evidence;

DROP TABLE extraction_conflict;

DROP TABLE gold_item;

DROP TABLE extraction;

DROP TABLE field_instance;

DROP TABLE regression_run;
```

## 逐条结果与独立证据

- 先检索该维度全部主题、补读和转引，再调用 complete_research，之后逐条产出。一个事项可综合多处证据，评分档次和任务关键要求保持在各自事项内。
- submit_analysis 的 records 最多一条；final=false 保存当前事项。全部完成后 records=[]、final=true 确认结束，无需重发大 JSON。每条由该 subagent 直接分析，父级只调度、校验与存储。
- 持久化 business_data.records 仅保存业务内容与 evidence_ids，原文和位置独立放在 business_data.evidence。下游按需回填，历史内嵌 citations 可读取。
- GET /api/v1/analysis/reports/{report_id}/modules/{module_key}/records 直接返回独立记录和证据集合；不依赖报告展示文本，任何必要引用撤销时整条隐藏。
- 前端新版专题直接读取该接口，用返回的 output_schema 按冻结 Skill 的分类、布局和列渲染；原文定位通过 evidence_ids 回查 evidence。报告接口继续提供状态、运行记录及检索缺口，历史报告保留原展示。单维度读取失败显示重试，不回退报告旧条目；报告切换取消旧请求，运行期间轮询刷新逐条成果。
- 首次推理前加载冻结的输出格式、核心细则及已明确项目/标段品类规则；技术维度遵循参考 SKILL.md 的方案边界，旧纯参数参考不能覆盖主 Skill。
- 无依据占位只登记缺口；单条支持性纠正耗尽后保留其他已核实成果，显式收尾仍由 subagent 确认。
- 覆盖“不适用”证明纠正耗尽时按 topic 保存缺口，覆盖状态转为 pending；同一证明原样重提交不能恢复“不适用”。同 key 的无依据占位改写保留此前 supported 版本。重复 complete_research 仅刷新检索缺口，继续保留拒绝事项缺口；真正新增证据仍按原规则使旧综合及拒绝状态失效，再重新分析。

逐条提交示例（同一个技术任务的关键要求保持在一条 JSON 内）：

```json
{
  "records": [{
    "key": "migration-plan",
    "kind": "requirement",
    "title": "平台迁移方案",
    "group": "技术方案要求",
    "content": {
      "要求摘要": "制定平台迁移及切换方案",
      "关键要求": ["制定数据迁移方案", "说明切换及回退措施"]
    },
    "scope": {"kind": "unknown", "lot_refs": []},
    "citations": [{"block_id": "已读取的证据ID", "quote": "对应连续原文"}]
  }],
  "final": false
}
```

下一条结果由同一个子 Agent 继续提交；完成时只提交 `{"records":[],"final":true}`。
引用在入库后被拆入 evidence 集合，记录中的 evidence_ids 保留关联。
