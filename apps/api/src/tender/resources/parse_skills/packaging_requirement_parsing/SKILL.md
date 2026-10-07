---
name: packaging_requirement_parsing
description: "封装要求解析专家。从招标文件中提取封装/密封/标记要求、分册要求。当需要解析投标文件封装相关信息时使用本 Skill。"
---

# 封装要求解析 Skill

## 适用场景
- 触发：主 Agent 委派封装要求解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：submit_analysis 原生工具中的动态 JSON 条目，每条附已读取原文块的引用。

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

通过原生工具调用 `submit_analysis(items, relations, research_summary)` 提交结果。
每条 item 包含 kind、title、text、presentation、cells、citations；kind 可为 fact、judgment、suggestion、conflict、insufficient。
presentation 使用 paragraph、list、table；cells 为文字键值，每个表格行或列表项分别成项。
引用使用 {"block_id":"工具实际返回的块ID","quote":"块内连续原文"}；不能引用 Skill、压缩摘要或常识。
没有相关依据可提交空 items，但 research_summary 必须说明检索过的主题、缺口与不确定性。
补充文件明确修改条款时保留修改前后双方引用；参考库内容只作建议，不能替代本项目要求。

## 参考文件
- `references/output_format.md`：本 Skill 专属输出模板和格式约束
- `references/extraction_rules.md`：分册/密封/标记/电子版提取规则、盲标处理、严禁行为、自检清单
- `references/examples.md`：完整封装要求提取样例

## 工具与证据

- `list_documents()`：获取本项目及关联知识库的授权资料清单。
- `search_document(query, source_id?)`：自主检索项目条款，可限定清单中的某个来源。
- `search_knowledge(query, source_id?)`：检索关联参考库，历史依据不能证明本次满足要求。
- `read_document(source_id, offset, limit)`：按命中位置扩展原文，每次最多12块；压缩后也可补读。
- `read_file(file_path)`：只读 `/skills/packaging_requirement_parsing/SKILL.md` 及其 references，或会话压缩历史。
- `submit_analysis`：提交本模块综合结果和检索总结。相同命中先去重，再分析条件、例外与修订。
不进行全文顺序扫描；基于本专题问题选择检索角度，核对各份相关补充文件。

## 注意
- 封装要求是废标高频区域，必须**完整提取**
- 注意区分"正本"和"副本"的不同要求
- 注意电子标和纸质标的差异
