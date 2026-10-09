---
name: bid_format_outline_parsing
description: "从全部招标材料的 PDF 原文块识别投标文件格式、逻辑标类型和三级章节关系，逐项附可定位依据。"
---

# 投标文件格式大纲解析

## 任务与输入

识别投标人需要编制的材料及组织关系。通过 list_documents 获取清单并按需检索原文，主文件、澄清、补遗及格式附件都要检查。
逻辑标类型是组织容器，不等同物理分册，不能因为单册装订就删除逻辑分类。

## 执行流程

1. 读取 references/locate_rules.md 和 references/outline_extract_rules.md。
2. 先 search_document 定位格式正文，再 read_document 扩展；根据问题查找分散附件和格式材料。
3. 对疑似导航目录读取 references/toc_filter_rules.md，区分目录与真正规定材料组成的正文。
4. 先确定逻辑标类型及管辖范围，再识别章节父子关系，保留一级至三级实际层级。
5. 根据 references/output_format.md，提交标类型、章节及其唯一父级；每节点单独引用。
6. 回看全部来源，核对遗漏附件、游离章节和补遗修改；冲突保留双方依据。

## 工具与证据

- `list_documents()`：获取本项目及关联知识库的授权资料清单。
- `search_document(query, source_id?)`：自主检索项目条款，可限定清单中的某个来源。
- `search_knowledge(query, source_id?)`：检索关联参考库，历史依据不能证明本次满足要求。
- `read_document(source_id, offset, limit)`：按命中位置扩展原文，每次最多12块；压缩后也可补读。
- `read_file(file_path)`：只读 `/skills/bid_format_outline_parsing/SKILL.md` 及其 references，或会话压缩历史。
- `submit_analysis`：提交本模块综合结果和检索总结。相同命中先去重，再分析条件、例外与修订。
不进行全文顺序扫描；基于本专题问题选择检索角度，核对各份相关补充文件。

## 输出

通过 submit_analysis 提交 outline_nodes，fields 留空，另填写 research_summary。
没有格式依据时 outline_nodes 为空。名称保留原文，归属按内容语义判断，不按编号机械建树。
每节点只填写一次 parent_id，不另外编写 fields、relations、层级或父路径。详细字段见 references/output_format.md。
