---
name: general_module_parsing
description: "检查招标文件补充发现与跨文件关联，覆盖专门模块之外的重要条件、例外、澄清及材料冲突，逐项引用原文。"
---

# 补充发现与跨文件关联

## 任务

在必检专题之外自主发现影响投标决策的重要内容，比较主文件、澄清、补遗及附件的范围和差异。
原文由检索工具按需提供 source_id、offset、block_id，无需访问磁盘。
本模块始终参与综合分析，不能因为有专门模块就跳过补充发现。

## 工作方法

1. 围绕补充条款、澄清、例外和跨文件差异自主检索，再按需补读其它版本和条件。
2. 查清是否同一标段、主体、时间和范围，保留且/或、例外、前提和否定。
3. 补充通知明确修改某条时同时引用原条款和修改条款；无明确关系则并列为冲突，不以上传时间裁定。
4. 未被专题覆盖的重要义务、不可抗力及关联风险可独立成项，不重复复制普通事实。
5. 事实、判断、建议、冲突、证据不足使用不同 kind。建议须引用事实前提。
6. 仅共同出现的实体不能形成关系；关系须有直接引用及范围/条件。

## 工具与证据

- `list_documents()`：获取本项目及关联知识库的授权资料清单。
- `search_document(query, source_id?)`：自主检索项目条款，可限定清单中的某个来源。
- `search_knowledge(query, source_id?)`：检索关联参考库，历史依据不能证明本次满足要求。
- `read_document(source_id, offset, limit)`：按命中位置扩展原文，每次最多12块；压缩后也可补读。
- `read_file(file_path)`：只读 `/skills/general_module_parsing/SKILL.md` 及其 references，或会话压缩历史。
- `submit_analysis`：提交本模块综合结果和检索总结。相同命中先去重，再分析条件、例外与修订。
不进行全文顺序扫描；基于本专题问题选择检索角度，核对各份相关补充文件。

## 输出协议

通过原生工具调用 `submit_analysis(items, relations, research_summary)` 提交结果。
每条 item 包含 kind、title、text、presentation、cells、citations；kind 可为 fact、judgment、suggestion、conflict、insufficient。
presentation 使用 paragraph、list、table；cells 为文字键值，每个表格行或列表项分别成项。
引用使用 {"block_id":"工具实际返回的块ID","quote":"块内连续原文"}；不能引用 Skill、压缩摘要或常识。
没有相关依据可提交空 items，但 research_summary 必须说明检索过的主题、缺口与不确定性。
补充文件明确修改条款时保留修改前后双方引用；参考库内容只作建议，不能替代本项目要求。
