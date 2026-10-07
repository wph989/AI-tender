---
name: company_performance_parsing
description: "企业业绩解析专家。从招标文件中提取投标人企业类似项目业绩、时间范围、金额门槛、证明材料、业绩评分和行业业绩要求。"
---

# 企业业绩解析 Skill

## 适用场景
- 触发：主 Agent 委派企业业绩解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：submit_analysis 原生工具中的动态 JSON 条目，每条附已读取原文块的引用。

## 领域知识

企业业绩要求是招标文件中对投标人历史项目经验和能力的规定，主要包括：

1. **类似项目定义**：什么是"类似项目"（行业、规模、金额等界定标准）
2. **业绩数量要求**：需提供几个类似项目业绩
3. **时间范围**：业绩的时间窗口（如近3年、近5年）
4. **金额要求**：单个项目的最低合同金额
5. **证明材料**：需提供什么证明（合同、中标通知书、验收报告等）
6. **认定标准**：已完工/在建/已签约的不同认定规则

要求的主语必须是投标人企业的过往项目经验。企业资质、人员个人业绩、财务状况、设备设施、信誉、技术方案及其他资格条件必须排除。

## 识别规则

关键词种子（可扩展，不限于）："业绩"、"类似项目"、"同类项目"、"合同"、"中标通知书"、"验收"

## 执行流程

1. **精确检索**：使用 `search_document` 搜索"业绩""类似项目"等章节
2. **扩展上下文**：根据命中位置使用 `read_document` 读取相邻条款
3. **主语判断**：确认要求针对企业历史项目，而非人员或企业资质
4. **完整提取**：保留业绩类型、数量、时间、金额、认定口径、证明材料及评分规则
5. **输出结果**：按本 Skill 的输出协议调用 submit_analysis；没有依据的条目省略。

## 输出协议

通过原生工具调用 `submit_analysis(items, relations, research_summary)` 提交结果。
每条 item 包含 kind、title、text、presentation、cells、citations；kind 可为 fact、judgment、suggestion、conflict、insufficient。
presentation 使用 paragraph、list、table；cells 为文字键值，每个表格行或列表项分别成项。
引用使用 {"block_id":"工具实际返回的块ID","quote":"块内连续原文"}；不能引用 Skill、压缩摘要或常识。
没有相关依据可提交空 items，但 research_summary 必须说明检索过的主题、缺口与不确定性。
补充文件明确修改条款时保留修改前后双方引用；参考库内容只作建议，不能替代本项目要求。

## 参考文件（按标类型加载）
根据任务 category 及 lots 中的类别覆盖，加载对应子目录下的参考文件：
- `references/output_format.md`：本 Skill 专属输出模板和格式约束
- `references/<type_dir>/extraction_rules.md`：“类似项目”定义提取、时间窗口、证明材料、强制/加分区分、严禁行为、自检清单
- `references/<type_dir>/examples.md`：完整业绩要求提取样例
- category 取值：service（服务类）、engineering（工程类）、goods（货物类）；type_dir 使用相同值
- 类别由用户选择并由运行时提供；不能自行默认成服务类，标段有覆盖类别时同时参考对应规则

## 工具与证据

- `list_documents()`：获取本项目及关联知识库的授权资料清单。
- `search_document(query, source_id?)`：自主检索项目条款，可限定清单中的某个来源。
- `search_knowledge(query, source_id?)`：检索关联参考库，历史依据不能证明本次满足要求。
- `read_document(source_id, offset, limit)`：按命中位置扩展原文，每次最多12块；压缩后也可补读。
- `read_file(file_path)`：只读 `/skills/company_performance_parsing/SKILL.md` 及其 references，或会话压缩历史。
- `submit_analysis`：提交本模块综合结果和检索总结。相同命中先去重，再分析条件、例外与修订。
不进行全文顺序扫描；基于本专题问题选择检索角度，核对各份相关补充文件。

## 注意
- "类似项目"的定义是关键，必须精确提取
- 注意区分"必须提供"和"提供加分"
- 注意证明材料的具体要求（合同关键页还是全文）
- 业绩评分只提取评分对象明确为企业业绩的规则
