---
name: opening_requirement_parsing
description: "开标要求解析专家。从招标文件中提取开标时间、地点、流程、参与要求。当需要解析开标相关信息时使用本 Skill。"
---

# 开标要求解析 Skill

## 适用场景
- 触发：主 Agent 委派开标要求解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：submit_analysis 原生工具提交的字段（field/group/sort_order/values/note），每个值附已读取原文块的引用。

## 领域知识

开标要求是招标文件中规定开标仪式相关事项的内容，主要包括：

1. **开标时间**：具体日期和时刻
2. **开标地点**：详细地址、楼层、会议室
3. **参与人员**：投标人需派出的代表（法定代表人/授权代表）
4. **携带材料**：开标时需携带的证件、文件
5. **开标流程**：唱标顺序、确认签字等环节
6. **开标方式**：现场、线上、远程或不见面开标
7. **公开程度**：公开范围、见证人员及其他公开要求
8. **其他要求**：解密时限、迟到处理等开标相关规定

## 识别规则

关键词种子（可扩展，不限于）："开标"、"开标时间"、"开标地点"、"投标截止"、"递交截止"、"开标仪式"

## 执行流程

1. **精确检索**：使用 `search_document` 搜索"开标""投标截止"等章节
2. **扩展上下文**：根据命中位置使用 `read_document` 读取相邻条款
3. **提取信息**：提取时间、地点、方式、人员、程序、公开程度及其他要求
4. **输出结果**：按本 Skill 的输出协议调用 submit_analysis；没有依据的条目省略。

## 输出协议

通过原生工具调用 `submit_analysis(fields, relations, research_summary)` 提交结果。
每个字段包含 field、group、sort_order、values、note；values 中每个值包含 value 与 citations，证据逐值绑定。
引用使用 {"block_id":"工具实际返回的块ID","quote":"块内连续原文"}；不能引用 Skill、压缩摘要或常识。
同一字段出现多个值时每个值各自成条并带自己的引用，不合并成一段文字；一个值可有多条引用。
没有相关依据可提交空 fields，但 research_summary 必须说明检索过的主题、缺口与不确定性。
补充文件明确修改条款时保留修改前后双方引用；参考库内容只作建议，不能替代本项目要求。

## 参考文件
- `references/output_format.md`：本 Skill 专属输出模板和格式约束
- `references/extraction_rules.md`：时间/地点精确提取规则、远程开标处理、严禁行为、自检清单
- `references/examples.md`：标准开标、远程开标样例

## 工具与证据

- `list_documents()`：获取本项目及关联知识库的授权资料清单。
- `search_document(query, source_id?)`：自主检索项目条款，可限定清单中的某个来源。
- `search_knowledge(query, source_id?)`：检索关联参考库，历史依据不能证明本次满足要求。
- `read_document(source_id, offset, limit)`：按命中位置扩展原文，每次最多12块；压缩后也可补读。
- `read_file(file_path)`：只读 `/skills/opening_requirement_parsing/SKILL.md` 及其 references，或会话压缩历史。
- `submit_analysis`：提交本模块综合结果和检索总结。相同命中先去重，再分析条件、例外与修订。
不进行全文顺序扫描；基于本专题问题选择检索角度，核对各份相关补充文件。

## 注意
- 时间和地点信息必须**精确提取**，不得推断或猜测
- 注意区分"投标截止时间"和"开标时间"
- 注意是否有"远程开标""线上开标"等特殊安排
- 无实质内容的类别整段省略，不输出空的解析值
