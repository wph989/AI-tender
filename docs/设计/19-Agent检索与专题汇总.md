# 19 · Agent 检索与专题汇总

更新：2026-10-15

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
- 汇总可分批提交，正文条目通过原文支持性校验且 final=true 后完成专题。coverage、gaps、research_summary 可省略；省略 gaps 时保留已登记缺口，最终提交显式清单时替换内容缺口。覆盖遗漏和关联错误降为 pending 并显示缺口，不阻断已核实的正文。
- 只有检索或补读引入新证据才要求重新确认和整体综合；未命中或只返回已读证据时保留已核实成果，并更新真实检索账。
- 单条技术要求的字符串整理为数组，摘要与要求可由已有内容补齐；部分表格列缺失时保留有依据的分析内容，不能为了凑齐模板编造值。整理后的全部内容仍送原文支持性校验。
- 格式分组可以嵌套，同批父子或关系端点不限制提交顺序；循环、缺失父节点、错误归属仍必须修正。标段只给名称时可省略 code，目录内部用已核实名称查找，分析结果不伪造原文编号。
- 未解决的检索和转引缺口由服务端保留。界面明确显示检索范围与未决事项，检索未找到不等于全文没有要求。

## 纠错与进展

目的为分析结果和精确原文定位，过程清单是质量说明。检索门禁只阻断实际没有项目检索、虚构或越权证据等无法支撑分析的问题。
覆盖或转引证明缺项降为未决状态；空白过程说明可由服务端补充，过长摘要截取，不占用内容纠错次数。
确定性校验一次返回全部问题与服务端检索记录。不同问题组合分别计数；同类错误仅更换错误值不能重新获得额度，计数随检查点持久化。
新的成功检索即使没有新增原文也算研究进展；相同请求重放、改名和未校验草稿不算。总模型、工具、证据及时间预算保留。
没有生产调用的旧 analysis_outline 解析器及其“最多三级/分组只能为根/正文逐字摘录”协议已删除；历史报告读取兼容测试直接构造历史记录，不再依赖旧生成器。

## 存储和兼容

运行时版本为 deepagents-0.7.22-v4-synthesis。专题 JSON 与检索记录复用 analysis_module.business_data、items 和运行检查点，不另建字段抽取表。
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
