---
name: disqualified-items-parsing
description: "废标项解析专家。从招标文件中提取废标条件、否决投标条款、强制性要求清单。当需要解析废标项、否决投标条件、投标无效情形等关键信息时使用本 Skill。"
---

# 废标项解析 Skill

## 适用场景
- 触发：项目控制器启动当前专题废标项解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：submit_analysis 原生工具提交的字段（field/group/sort_order/values/note），每个值附已读取原文块的引用。

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

通过原生工具 `submit_analysis(records, coverage, gaps, research_summary, final=false)` 分批提交。
普通专题每批最多3条业务记录，格式专题最多6条。最后明确 `final=true`。
记录字段由工具 schema 定义，`key` 是本模块内稳定短标识，同一记录纠正时沿用。
`kind` 为 fact / requirement / lot / format_node / relation；`title` 为名称，`text` 直接写完整事实或要求。
`scope.kind` 必须为 common / lots / unknown；lots 的 `lot_refs` 填原文标段编号或名称。
不能因未写标段就认定所有标段适用。公共适用性同样需要原文或上下文依据。
`citations` 使用 [{"block_id":"实际读取ID","quote":"连续原文"}]，覆盖文本和全部业务属性。
`conditions` 保留 expression、logic(all/any/mixed/text)、terms(subject/operator/value/unit/time_basis)、exceptions。
日期起算点和类似项目定义不明时保留未知，不用常识填值。`materials` 列出 name 与 requirement。
`scoring` 保留 max_points、formula、tiers(condition/points)、deductions；评分项内部的全部档次属于同一项。
`structuring` 为 complete 或 partial，无法可靠拆解时用 partial 并保留完整 text。
仅项目概况模块提交 kind=lot，保留 code、title、aliases；其他模块直接填写标段原文指向。
格式节点用 kind=format_node、node_type(group/section)、parent_key；先父后子，完整保留原文层级。
修订/冲突用 kind=relation，predicate 为 supersedes/conflicts/requires/contains；端点先提交再填 subject_key/object_key。
supersedes 表示 subject 替代 object，双方证据和适用范围均须明确，不能按上传时间判断。

`references/coverage.json` 是运行时已加载的主题清单。每个主题登记覆盖状态：
extracted（关联 record_keys）、searched_not_found（只表示本次没找到）、pending、not_applicable（必须有引用）。
一个主题可按不同标段分别登记。未核对主题不会被当成完成，不为填满清单编造要求。
缺口用 gaps 提交 key/topic/scope/code/detail；code 为 unresolved_reference、unknown_condition、scope_unknown、
conflict、missing_source、incomplete_structure、search_exhausted。检索总结不能替代这些结构化状态。
转引只是线索，须检索实际条款并完整写进 text；预算耗尽或目标缺失时记录缺口。
缺口随 final=false 按 key 累积；final=true 须提交全部剩余 gaps，校验通过后替换旧清单。
全部缺口已解决时最终提交 gaps=[]；最终校验失败仍保留已有缺口。
来源、页码和坐标由服务端按校验保留的证据ID补齐，模型不生成定位。

## 参考文件（按标类型加载）
根据任务 category 及 lots 中的类别覆盖，加载对应子目录下的参考文件：
- `references/output_format.md`：本 Skill 专属输出模板和格式约束
- `references/<type_dir>/extraction_rules.md`：详细的提取规则、分类编码、关键词种子清单、严禁行为、边界案例处理、自检清单
- `references/<type_dir>/examples.md`：输入原文 → 期望输出的完整样例
- category 取值：service（服务类）、engineering（工程类）、goods（货物类）；type_dir 使用相同值
- 类别由用户选择并由运行时提供；不能自行默认成服务类，标段有覆盖类别时同时参考对应规则

## 工具与证据

- 运行时先调用 `load_skill` 加载本文件及 `references/output_format.md`，无需重复读取；其余细则按需读取。
- `list_documents()`：返回授权资料的 id 和说明文本；资料 id 可填入检索的 source_id。
- `search_document(query, source_id?)`：检索本项目；`search_knowledge(query, source_id?)`：检索关联参考库。
- 检索证据只含 `id`、`text`。把证据 id 填入引用的 `block_id`；quote 必须是该 text 的连续原文。
- `read_document(block_id, before=2, after=2)`：围绕已读证据补读；before/after 合计最多11，均为0时只补读本块。不得猜测ID或扫描全文。
- `read_file(file_path)`：只读 `/skills/disqualified-items-parsing/references/` 下当前任务需要的细则，或压缩历史；不能读取招标文件磁盘路径。
- `submit_analysis`：结构化提交，普通业务记录每批最多3条，格式每批最多6节点；`final=false` 暂存，明确核对完成后 `final=true`。

## 证据选择与纠错

1. 先按本专题的问题检索，再核对主体、标段、表头、脚注、条件和补充文件。上下文不足时按证据ID补读；不能用关键词命中代替事实判断。
2. 同一事实在相同适用范围内重复出现，选最直接、完整的一处。跨块条件、不同标段、修订前后和未决冲突所需的证据分别保留；检索相似度和自报置信分数不作为可信度。
3. 引用只提交ID和连续摘录，不生成页码、坐标、文件路径或来源元数据。服务端校验实际读取记录、资料权限和版本后，按保留的ID补齐定位。
4. 工具返回结构化错误时，按 `message` 和 `remaining_attempts` 修正；只补交未通过部分，不重交已保存事实。更换字段名或重复相同请求不会获得新额度。
5. 收到收尾提示就停止扩展检索，提交已有可靠结果并在 `research_summary` 记录缺口；不得声称缺口是文件未约定。不得再委派子Agent，服务故障与重试由运行时处理。

## 注意
- 废标项是投标合规的底线要求，必须**完整提取，不得遗漏**
- 后置否决结论只用于证明前置清单具有否决效力，不能代替前置清单本身
- 注意区分"废标项"（强制性）和"评分项"（加分/扣分）
- 执行前阅读对应类别 `references/<type_dir>/extraction_rules.md` 中的关键词种子清单和严禁行为
- 同一废标情形只能归入一个最匹配类别，不得重复
