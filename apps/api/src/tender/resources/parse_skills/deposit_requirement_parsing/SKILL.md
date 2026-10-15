---
name: deposit-requirement-parsing
description: "保证金要求解析专家。从招标文件中分别提取投标保证金和履约保证金的金额、形式、提交、有效期及退还要求。"
---

# 保证金要求解析 Skill

## 适用场景
- 触发：项目控制器启动当前专题保证金要求解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：完成检索后按专题模板综合的 content JSON，逐条附独立的原文溯源引用。

## 领域知识

本模块统一处理以下两类保证金，但必须按适用阶段分别归类：

1. **投标保证金**：投标阶段用于担保投标行为，重点提取金额或比例、形式、提交方式、截止时间、收款信息、有效期、退还及不予退还情形。
2. **履约保证金**：中标或合同履约阶段用于担保合同履行，重点提取金额或比例、计算基数、形式、提交时间、有效期限、返还或解除及扣除情形。

质保金、质量保证金、农民工工资保证金和其他专项担保资金不属于本模块。原文明示不要求某类保证金时，必须保留该类完整结论；要求与不要求同时出现时，先按标段、主体和适用条件区分，禁止把两类保证金互相填充。

## 识别规则

关键词种子（可扩展，不限于）："保证金"、"投标保证金"、"履约保证金"、"履约担保"、"保函"、"保证金金额"、"退还"、"返还"

## 执行流程

1. **精确检索**：分别使用 `search_document` 搜索投标保证金、履约保证金及其同义表述
2. **扩展上下文**：根据命中位置使用 `read_document` 读取相邻条款
3. **类型与适用性判断**：根据投标阶段、中标后、合同金额等上下文区分类型，并判断要求、不要求及适用标段或条件
4. **提取要求**：按类型分别提取金额或比例、形式、提交方式和时间、有效期、退还或解除规则
5. **输出结果**：按本 Skill 的输出协议调用 submit_analysis；没有依据的条目省略。

## 输出协议

先核对资料清单，按 `references/coverage.json` 的全部主题检索主文件、澄清、补遗与附件。
遇到转引继续检索实际条款并补读，记录起点、目标、处理状态和依据。未找到或预算不足如实登记。
完成后调用 `complete_research(topics, references, research_summary)`：主题可用 key 或中文名称，
说明已读证据、covered/searched_not_found/unresolved 状态与未决事项；真实检索词由服务端保存，不用复述。
queries 仅为可选检索意图说明；遗漏主题自动记为待核对，重复说明合并。转引登记 resolved/missing/cycle/budget_exhausted。
未进入综合阶段不能提交结果；不能每找到一块证据就保存为最终条目。

综合全部已读证据，按 `references/output_format.md` 的分类、表格列和层级生成 content JSON。
`group` 为具体分类，`title` 为事项或任务名称，`content` 的键使用运行时输出 schema 中的中文列名。
技术方案要求包含“要求摘要”和逐条“关键要求”数组；格式条目使用“编制要求”数组，保留父子关系。
同一事项先归并、核对适用范围与冲突，再形成完整条目。摘要允许概括，门槛、公式、档次和例外必须完整。
`text` 由服务端从 content 生成，无需另填。缺少依据的内容省略，不能用“未提及/无”冒充事实。

通过 `submit_analysis(records, coverage, gaps, research_summary, final=false)` 按完整事项分批提交，
每批最多24条，最后明确 `final=true`。记录 `key` 是模块内稳定标识，纠正同一记录时沿用。
`kind` 为 fact/requirement/lot/format_node/relation；`scope.kind` 为 common/lots/unknown，
lots 的 `lot_refs` 填原文标段编号或名称。公共范围同样需要依据，未知不能推断为公共。
每条 `citations` 提供实际已读 block_id 与连续原文 quote，支持全部 content 及业务属性。
`conditions` 保留表达式、且/或、数值、单位、起算点及例外；`materials` 保留证明材料要求；
`scoring` 保留满分、公式、全部档次和扣分。不能可靠结构化时声明 `structuring=partial`。
只有项目概况模块提交 lot；code 只填原文编号，无编号时省略，title 保留原文名称。
格式模块用 format_node 与 node_type=group/section，分组可嵌套；用 parent_key 保留原文层级，同批不限制父子顺序。
关系端点可在同批提供，再填 subject_key/object_key 与 predicate。
supersedes 表示 subject 替代 object；修订和冲突须引用双方并明确适用范围，不按上传时间裁定。

coverage、gaps 和 research_summary 可省略，由服务端沿用检索账并补齐待核对清单。
coverage 的主题可用 key 或中文名称；extracted 关联已核实 record_keys，searched_not_found 仅表示本次未找到，
pending 表示尚未解决，not_applicable 必须有原文引用并校验。可按标段分别登记。
最终 gaps 提供剩余内容缺口清单；complete_research 已登记的未决检索和转引由服务端保留，不能静默清空。
新检索或补读引入新依据后须重新 complete_research 并重新综合，旧批次不会与新证据混发。
来源、页码和坐标由服务端补齐；原文只作溯源，正文展示归纳后的业务内容。

## 参考文件
- `references/output_format.md`：本 Skill 专属输出模板和格式约束
- `references/extraction_rules.md`：两类保证金识别、金额精确提取、边界和自检清单
- `references/examples.md`：投标保证金与履约保证金联合提取样例

## 工具与证据

- 运行时先调用 `load_skill` 加载本文件及 `references/output_format.md`，无需重复读取；其余细则按需读取。
- `list_documents()`：返回授权资料的 id 和说明文本；资料 id 可填入检索的 source_id。
- `search_document(query, source_id?)`：检索本项目；`search_knowledge(query, source_id?)`：检索关联参考库。
- 检索证据只含 `id`、`text`。把证据 id 填入引用的 `block_id`；quote 必须是该 text 的连续原文。
- `read_document(block_id, before=2, after=2)`：围绕已读证据补读；before/after 合计最多11，均为0时只补读本块。不得猜测ID或扫描全文。
- `read_file(file_path)`：只读 `/skills/deposit-requirement-parsing/references/` 下当前任务需要的细则，或压缩历史；不能读取招标文件磁盘路径。
- `complete_research`：登记全部主题检索与转引，进入综合阶段。
- `submit_analysis`：综合全部证据后按完整事项提交，每批最多24条；`final=false` 暂存，核对完成后 `final=true`。

## 证据选择与纠错

1. 先按本专题的问题检索，再核对主体、标段、表头、脚注、条件和补充文件。上下文不足时按证据ID补读；不能用关键词命中代替事实判断。
2. 同一事实在相同适用范围内重复出现，选最直接、完整的一处。跨块条件、不同标段、修订前后和未决冲突所需的证据分别保留；检索相似度和自报置信分数不作为可信度。
3. 引用只提交ID和连续摘录，不生成页码、坐标、文件路径或来源元数据。服务端校验实际读取记录、资料权限和版本后，按保留的ID补齐定位。
4. 工具返回结构化错误时，按 `message` 和 `remaining_attempts` 修正；未补入新证据时只修正未通过事项；补入新依据后重新综合。更换名称或重复请求不会获得新额度。
5. 收到收尾提示就停止扩展检索，提交已有可靠结果并在 `research_summary` 记录缺口；不得声称缺口是文件未约定。不得再委派子Agent，服务故障与重试由运行时处理。

## 注意
- 金额数字必须**精确提取**，注意大写/小写金额的一致性
- 投标保证金和履约保证金必须分别输出，禁止合并金额、时间或退还条件
- 注意两类保函的格式、受益人和有效期要求
- 原文明确不要求某类保证金时不得为该类输出空的解析值
