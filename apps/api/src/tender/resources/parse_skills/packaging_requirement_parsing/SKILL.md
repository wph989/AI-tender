---
name: packaging-requirement-parsing
description: "封装要求解析专家。从招标文件中提取封装/密封/标记要求、分册要求。当需要解析投标文件封装相关信息时使用本 Skill。"
---

# 封装要求解析 Skill

## 适用场景
- 触发：项目控制器启动当前专题封装要求解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：submit_analysis 原生工具提交的字段（field/group/sort_order/values/note），每个值附已读取原文块的引用。

## 领域知识

封装要求是招标文件中对投标文件制作和提交形式的规定，主要包括：

1. **份数要求**：正本/副本各需几份
2. **密封要求**：密封方式、密封袋要求
3. **标记要求**：封面标注内容（项目名称、编号、投标人等）
4. **分册要求**：技术标/商务标/价格标是否分开封装
5. **电子版要求**：U盘/光盘、文件格式
6. **装订要求**：胶装/活页、页码编排
7. **组成与签章**：文件组成、签字人资格、盖章位置和类型

本模块提取具体制作与提交要求，不提取投标文件格式大纲的章节树结构，也不把技术、商务或资格内容本身当作格式要求。

## 识别规则

关键词种子（可扩展，不限于）："封装"、"密封"、"装订"、"正本"、"副本"、"份数"、"标记"、"包装"

## 执行流程

1. **精确检索**：使用 `search_document` 搜索"封装""密封""装订"等章节
2. **扩展上下文**：根据命中位置使用 `read_document` 读取相邻条款
3. **提取要求**：提取组成、格式、签章、密封、份数、纸质版和电子版要求
4. **输出结果**：按本 Skill 的输出协议调用 submit_analysis；没有依据的条目省略。

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

## 参考文件
- `references/output_format.md`：本 Skill 专属输出模板和格式约束
- `references/extraction_rules.md`：分册/密封/标记/电子版提取规则、盲标处理、严禁行为、自检清单
- `references/examples.md`：完整封装要求提取样例

## 工具与证据

- 运行时先调用 `load_skill` 加载本文件及 `references/output_format.md`，无需重复读取；其余细则按需读取。
- `list_documents()`：返回授权资料的 id 和说明文本；资料 id 可填入检索的 source_id。
- `search_document(query, source_id?)`：检索本项目；`search_knowledge(query, source_id?)`：检索关联参考库。
- 检索证据只含 `id`、`text`。把证据 id 填入引用的 `block_id`；quote 必须是该 text 的连续原文。
- `read_document(block_id, before=2, after=2)`：围绕已读证据补读；before/after 合计最多11，均为0时只补读本块。不得猜测ID或扫描全文。
- `read_file(file_path)`：只读 `/skills/packaging-requirement-parsing/references/` 下当前任务需要的细则，或压缩历史；不能读取招标文件磁盘路径。
- `submit_analysis`：结构化提交，普通业务记录每批最多3条，格式每批最多6节点；`final=false` 暂存，明确核对完成后 `final=true`。

## 证据选择与纠错

1. 先按本专题的问题检索，再核对主体、标段、表头、脚注、条件和补充文件。上下文不足时按证据ID补读；不能用关键词命中代替事实判断。
2. 同一事实在相同适用范围内重复出现，选最直接、完整的一处。跨块条件、不同标段、修订前后和未决冲突所需的证据分别保留；检索相似度和自报置信分数不作为可信度。
3. 引用只提交ID和连续摘录，不生成页码、坐标、文件路径或来源元数据。服务端校验实际读取记录、资料权限和版本后，按保留的ID补齐定位。
4. 工具返回结构化错误时，按 `message` 和 `remaining_attempts` 修正；只补交未通过部分，不重交已保存事实。更换字段名或重复相同请求不会获得新额度。
5. 收到收尾提示就停止扩展检索，提交已有可靠结果并在 `research_summary` 记录缺口；不得声称缺口是文件未约定。不得再委派子Agent，服务故障与重试由运行时处理。

## 注意
- 封装要求是废标高频区域，必须**完整提取**
- 注意区分"正本"和"副本"的不同要求
- 注意电子标和纸质标的差异
