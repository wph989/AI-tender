---
name: personnel_requirement_parsing
description: "人员要求解析专家。从招标文件中提取项目人员配置要求、资格、数量、专业。当需要解析项目团队人员相关要求时使用本 Skill。"
---

# 人员要求解析 Skill

## 适用场景
- 触发：主 Agent 委派人员要求解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：submit_analysis 原生工具中的动态 JSON 条目，每条附已读取原文块的引用。

## 领域知识

人员要求是对投标人拟投入本项目的具体岗位人员提出的可操作要求，主要包括：

1. **项目经理/负责人**：资质等级、从业年限、类似项目经验
2. **技术负责人**：职称、专业背景、资格证书
3. **其他关键岗位**：安全员、质量员、施工员等
4. **人员数量**：各岗位的最低人数要求
5. **社保证明**：是否需提供社保缴纳证明
6. **不得兼任**：哪些岗位不得由同一人兼任

候选条款必须满足：主语是具体人员或岗位，且至少包含人数、个人证书/职称/学历、明确年限或针对个人属性的量化评分之一。仅出现岗位名称、团队配置合理等模糊表述不得提取。

必须排除企业资质/认证、企业业绩、企业持有证书数量、报价与商务条款、投标文件格式、中标后抽测，以及人员行为规范、稳定性、管理制度、服务态度和责任承担等软性要求。要求提供社保、劳动合同等证明材料时可以提取，但一般性的依法缴纳社保不得提取。

## 识别规则

关键词种子（可扩展，不限于）："人员"、"项目经理"、"技术负责人"、"配备"、"团队"、"人员配置"

## 执行流程

1. **精确检索**：使用 `search_document` 搜索"人员""项目经理"等章节
2. **扩展上下文**：根据命中位置使用 `read_document` 读取相邻条款
3. **主语判定**：回答“投标人是否需要为此安排一个具体的人”，否则排除
4. **逐岗位归并**：提取数量、评分、个人证书、经验、专业、技能、证明和兼任限制
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
- `references/<type_dir>/extraction_rules.md`：逐岗位提取规则、社保要求、兼任限制、严禁行为、自检清单
- `references/<type_dir>/examples.md`：完整人员配置要求提取样例
- category 取值：service（服务类）、engineering（工程类）、goods（货物类）；type_dir 使用相同值
- 类别由用户选择并由运行时提供；不能自行默认成服务类，标段有覆盖类别时同时参考对应规则

## 工具与证据

- `list_documents()`：获取本项目及关联知识库的授权资料清单。
- `search_document(query, source_id?)`：自主检索项目条款，可限定清单中的某个来源。
- `search_knowledge(query, source_id?)`：检索关联参考库，历史依据不能证明本次满足要求。
- `read_document(source_id, offset, limit)`：按命中位置扩展原文，每次最多12块；压缩后也可补读。
- `read_file(file_path)`：只读 `/skills/personnel_requirement_parsing/SKILL.md` 及其 references，或会话压缩历史。
- `submit_analysis`：提交本模块综合结果和检索总结。相同命中先去重，再分析条件、例外与修订。
不进行全文顺序扫描；基于本专题问题选择检索角度，核对各份相关补充文件。

## 注意
- 人员资质要求需区分"强制性"和"加分项"
- 注意证书的有效期和等级要求
- 注意社保证明的时间要求
- 同时存在总人数和细分岗位时，以细分岗位为主，并将总人数写入相关岗位备注
