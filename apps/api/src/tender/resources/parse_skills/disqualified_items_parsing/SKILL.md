---
name: disqualified-items-parsing
description: "废标项解析专家。从招标文件中提取废标条件、否决投标条款、强制性要求清单。当需要解析废标项、否决投标条件、投标无效情形等关键信息时使用本 Skill。"
---

# 废标项解析 Skill

## 适用场景
- 触发：项目控制器启动当前专题废标项解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：完成检索后按专题模板综合的 content JSON，逐条附独立的原文溯源引用。

## 领域知识

废标项（又称否决投标条款、投标无效情形）是招标文件中的**强制性条款**，投标人必须全部满足，否则投标将被否决。常见类型包括：

1. **资格条件类**：资质等级不满足、营业执照过期、未缴纳投标保证金等
2. **技术要求类**：关键技术参数不达标、技术方案缺失等
3. **商务要求类**：投标有效期不足、报价超过最高限价等
4. **格式要求类**：投标文件未按要求密封、签章缺失等
5. **法律法规类**：存在关联关系、被列入黑名单等

## 识别规则

以下为关键词种子和表达模式；只有原文明确表达否决后果时才可提取：
- "废标"、"否决投标"、"投标无效"、"不予受理"
- "不通过"、"不合格"仅在明确属于本次投标否决判定时提取
- "投标人有下列情形之一的"、"出现下列情形之一的"
- 编号列表（如 1、2、3 或 a、b、c 形式的列举条款）

“必须、应当、不得”等一般强制措辞本身不等于废标。资格要求、技术参数、商务条款或格式要求如果没有明确关联废标、无效、否决或不予受理，必须排除。评分扣分项和建议性要求也必须排除。

## 执行流程

1. **精确检索**：使用 `search_document` 搜索"废标""否决投标""投标无效"等相关章节标题
2. **扩展上下文**：根据命中位置使用 `read_document` 读取完整条款；资格审查为列表时，必须覆盖列表起点、全部子项和列表后的结论句
3. **后果验证**：确认每条候选存在明确后果；列表后的“资格审查不通过则否决”等结论必须继承到列表中的每一项
4. **逐项分类**：先把资格、证照、业绩、人员、财务等复合条件拆成可独立核验的废标项，再按五类互斥归类
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

通过 `submit_analysis(records, coverage, gaps, research_summary, final=false)` 逐条提交完整事项，
每次最多一条完整事项，最后明确 `final=true`。记录 `key` 是模块内稳定标识，纠正同一记录时沿用。
`kind` 为 fact/requirement/lot/format_node/relation；`scope.kind` 为 common/lots/unknown，
lots 的 `lot_refs` 填原文标段编号或名称。公共范围同样需要依据，未知不能推断为公共。
每条 `citations` 提供实际已读 block_id 与连续原文 quote，支持全部 content 及业务属性。
`conditions` 保留表达式、且/或、数值、单位、起算点及例外；`materials` 保留证明材料要求；
`scoring` 保留满分、公式、全部档次和扣分。不能可靠结构化时声明 `structuring=partial`。
只有项目概况模块提交 lot；code 只填原文编号，无编号时省略，title 保留原文名称。
格式模块用 format_node 与 node_type=group/section，分组可嵌套；用 parent_key 保留原文层级，先保存父节点再保存子节点。
关系端点先逐条保存，再用 subject_key/object_key 与 predicate 提交关系。
supersedes 表示 subject 替代 object；修订和冲突须引用双方并明确适用范围，不按上传时间裁定。

coverage、gaps 和 research_summary 可省略，由服务端沿用检索账并补齐待核对清单。
coverage 的主题可用 key 或中文名称；extracted 关联已核实 record_keys，searched_not_found 仅表示本次未找到，
pending 表示尚未解决，not_applicable 必须有原文引用并校验。可按标段分别登记。
最终 gaps 提供剩余内容缺口清单；complete_research 已登记的未决检索和转引由服务端保留，不能静默清空。
新检索或补读引入新依据后须重新 complete_research 并重新综合，旧批次不会与新证据混发。
来源、页码和坐标由服务端补齐；原文只作溯源，正文展示归纳后的业务内容。

## 参考文件（按标类型加载）
根据任务 category 及 lots 中的类别覆盖，加载对应子目录下的参考文件：
- `references/output_format.md`：本 Skill 专属输出模板和格式约束
- `references/<type_dir>/extraction_rules.md`：详细的提取规则、分类编码、关键词种子清单、严禁行为、边界案例处理、自检清单
- `references/<type_dir>/examples.md`：输入原文 → 期望输出的完整样例
- category 取值：service（服务类）、engineering（工程类）、goods（货物类）；type_dir 使用相同值
- 类别由用户选择并由运行时提供；不能自行默认成服务类，标段有覆盖类别时同时参考对应规则

## 工具与证据

- 运行时先调用 `load_skill` 加载本文件及 `references/output_format.md`，无需重复读取；已明确品类和核心细则也在首次推理前加载；示例按需读取。
- `list_documents()`：返回授权资料的 id 和说明文本；资料 id 可填入检索的 source_id。
- `search_document(query, source_id?)`：检索本项目；`search_knowledge(query, source_id?)`：检索关联参考库。
- 检索证据只含 `id`、`text`。把证据 id 填入引用的 `block_id`；quote 必须是该 text 的连续原文。
- `read_document(block_id, before=2, after=2)`：围绕已读证据补读；before/after 合计最多11，均为0时只补读本块。不得猜测ID或扫描全文。
- `read_file(file_path)`：只读 `/skills/disqualified-items-parsing/references/` 下当前任务需要的细则，或压缩历史；不能读取招标文件磁盘路径。
- `complete_research`：登记全部主题检索与转引，进入综合阶段。
- `submit_analysis`：综合全部证据后按完整事项提交，每次最多一条完整事项；`final=false` 保存当前事项，全部事项完成后用空 records 和 `final=true`。

## 证据选择与纠错

1. 先按本专题的问题检索，再核对主体、标段、表头、脚注、条件和补充文件。上下文不足时按证据ID补读；不能用关键词命中代替事实判断。
2. 同一事实在相同适用范围内重复出现，选最直接、完整的一处。跨块条件、不同标段、修订前后和未决冲突所需的证据分别保留；检索相似度和自报置信分数不作为可信度。
3. 引用只提交ID和连续摘录，不生成页码、坐标、文件路径或来源元数据。服务端校验实际读取记录、资料权限和版本后，按保留的ID补齐定位。
4. 工具返回结构化错误时，按 `message` 和 `remaining_attempts` 修正；未补入新证据时只修正未通过事项；补入新依据后重新综合。更换名称或重复请求不会获得新额度。
5. 收到收尾提示就停止扩展检索，提交已有可靠结果并在 `research_summary` 记录缺口；不得声称缺口是文件未约定。不得再委派子Agent，服务故障与重试由运行时处理。

## 注意
- 废标项是投标合规的底线要求，必须**完整提取，不得遗漏**
- 后置否决结论只用于证明前置清单具有否决效力，不能代替前置清单本身
- 注意区分"废标项"（强制性）和"评分项"（加分/扣分）
- 执行前阅读对应类别 `references/<type_dir>/extraction_rules.md` 中的关键词种子清单和严禁行为
- 同一废标情形只能归入一个最匹配类别，不得重复
