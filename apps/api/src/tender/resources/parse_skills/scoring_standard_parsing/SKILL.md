---
name: scoring-standard-parsing
description: "评分标准解析专家。从招标文件中提取评标评分细则、分值分配、评分方法。当需要解析评分规则、分值权重、评标方法等信息时使用本 Skill。"
---

# 评分标准解析 Skill

## 适用场景
- 触发：项目控制器启动当前专题评分标准解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：submit_analysis 原生工具提交的字段（field/group/sort_order/values/note），每个值附已读取原文块的引用。

## 领域知识

评分标准是招标文件中规定评标方法和分值分配的核心内容，主要包括：

1. **评标方法**：综合评分法、最低评标价法、性价比法等
2. **分值分配**：技术分、商务分、价格分的权重和分值
3. **评分细则**：每个评分项的评分标准（满分条件、扣分规则）
4. **价格分计算**：基准价确定方法、价格分计算公式
5. **加分/扣分项**：优惠政策、中小企业加分等

有效评分标准必须包含具体分值、计算公式或“评分项+评分细则”结构。仅有评标流程、资格/符合性审查、目录索引、供应商绩效考核、项目验收评分、合同条款或文件格式要求时不得提取。

## 识别规则

以下为关键词种子和重点章节名；应根据文档措辞继续扩展同义词：
- "评标办法"、"评标方法"、"评分标准"、"评分细则"
- "综合评分法"、"最低评标价法"
- "分值"、"权重"、"得分"
- 分值表格
- "价格分"、"技术分"、"商务分"

## 执行流程

1. **精确检索**：使用 `search_document` 搜索"评标办法""评分标准"等章节标题
2. **展开转引与上下文**：命中“详见第三章/某附件”“按前附表执行”等指向时，用文件名、章节名、条号加评分主题继续 `search_document`；跨文件先 `list_documents` 确认授权资料并限定 source_id。命中目标后用 `read_document` 补读评分表、表头、脚注和相邻条件；目录或转引句只作线索，不作评分结果
3. **有效性判断**：确认存在分值、公式或实质评分细则
4. **先总后细**：先提取评标方法、总分构成和总体公式，再完整提取评分表
5. **层级校验**：区分总分、评分项和评分档次；评分档次不得重复计为独立评分项
6. **结构选择**：原文分开商务/技术时分别输出，合并时输出综合评分
7. **输出结果**：按本 Skill 的输出协议调用 submit_analysis；没有依据的条目省略。

遇到多级转引继续追踪到实际规则；同一指向循环、目标文件未提供或预算耗尽时，将追踪路径和缺口写入 research_summary，不以“详见……”占位，不以历史资料或常识补齐。

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
- `references/<type_dir>/extraction_rules.md`：分值表提取规则、价格分计算方法、客观/主观分区分、严禁行为、自检清单
- `references/<type_dir>/examples.md`：完整评分样例
- category 取值：service（服务类）、engineering（工程类）、goods（货物类）；type_dir 使用相同值
- 类别由用户选择并由运行时提供；不能自行默认成服务类，标段有覆盖类别时同时参考对应规则

## 工具与证据

- 运行时先调用 `load_skill` 加载本文件及 `references/output_format.md`，无需重复读取；其余细则按需读取。
- `list_documents()`：返回授权资料的 id 和说明文本；资料 id 可填入检索的 source_id。
- `search_document(query, source_id?)`：检索本项目；`search_knowledge(query, source_id?)`：检索关联参考库。
- 检索证据只含 `id`、`text`。把证据 id 填入引用的 `block_id`；quote 必须是该 text 的连续原文。
- `read_document(block_id, before=2, after=2)`：围绕已读证据补读；before/after 合计最多11，均为0时只补读本块。不得猜测ID或扫描全文。
- `read_file(file_path)`：只读 `/skills/scoring-standard-parsing/references/` 下当前任务需要的细则，或压缩历史；不能读取招标文件磁盘路径。
- `submit_analysis`：结构化提交，普通业务记录每批最多3条，格式每批最多6节点；`final=false` 暂存，明确核对完成后 `final=true`。

## 证据选择与纠错

1. 先按本专题的问题检索，再核对主体、标段、表头、脚注、条件和补充文件。上下文不足时按证据ID补读；不能用关键词命中代替事实判断。
2. 同一事实在相同适用范围内重复出现，选最直接、完整的一处。跨块条件、不同标段、修订前后和未决冲突所需的证据分别保留；检索相似度和自报置信分数不作为可信度。
3. 引用只提交ID和连续摘录，不生成页码、坐标、文件路径或来源元数据。服务端校验实际读取记录、资料权限和版本后，按保留的ID补齐定位。
4. 工具返回结构化错误时，按 `message` 和 `remaining_attempts` 修正；只补交未通过部分，不重交已保存事实。更换字段名或重复相同请求不会获得新额度。
5. 收到收尾提示就停止扩展检索，提交已有可靠结果并在 `research_summary` 记录缺口；不得声称缺口是文件未约定。不得再委派子Agent，服务故障与重试由运行时处理。

## 注意
- 分值表格必须**完整提取**，保留原始分值和评分描述
- 每个评分项直接写出各档得分条件、最高分及适用范围；“技术方案20分，细则见附件”尚未完成解析。正文已读取时也必须将细则写入 value，不能只藏在 citations 中
- 同一评分项的多档条件、公式可用多句或换行完整保留，不为压缩篇幅而改成索引；明确的评标方法或独立分值构成可单列，但不能冒充评分细则
- 价格分计算公式需精确提取，包括基准价的确定方法
- 每个评分项的分值取满分值；发现子项合计不一致时重新核对层级，不得自行修正
- 价格评分只保留一个总分入口，不拆分为多个重复评分项
