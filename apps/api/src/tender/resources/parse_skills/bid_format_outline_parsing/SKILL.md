---
name: bid-format-outline-parsing
description: "从全部招标材料的 PDF 原文块识别投标文件格式、逻辑标类型和完整章节关系，逐项附可定位依据。"
---

# 投标文件格式大纲解析

## 任务与输入

识别投标人需要编制的材料及组织关系。通过 list_documents 获取清单并按需检索原文，主文件、澄清、补遗及格式附件都要检查。
逻辑标类型是组织容器，不等同物理分册，不能因为单册装订就删除逻辑分类。

## 执行流程

1. 结合已加载的格式定位、层级与目录过滤规则识别编制材料。
2. 先 search_document 定位格式正文，再 read_document 扩展；根据问题查找分散附件和格式材料。
3. 对疑似导航目录读取 references/toc_filter_rules.md，区分目录与真正规定材料组成的正文。
4. 先确定逻辑标类型及管辖范围，再识别章节父子关系，保留原文实际层级。
5. 根据 references/output_format.md，提交标类型、章节及其 parent_key 父级；先父后子，每节点单独引用。
6. 回看全部来源，核对遗漏附件、游离章节和补遗修改；冲突保留双方依据。

## 本项目的检索与输出

按 coverage.json 核对业务内容，保留范围、条件、例外及完整清单。研究与提交协议以运行时工具为准；本文件只定义本专题的业务判断。

## 参考文件

运行时按阶段和当前工作提供规则；尚未提供的完整细则及示例可通过 read_file 按需查阅。

- `references/output_schema.json`：本项目机器格式声明，运行时从报告快照读取。
- `references/output_format.md`：事项组织、字段含义和实际 JSON 提交示例。
- `references/coverage.json`：本专题检索覆盖清单，未解决主题保留缺口。
- `references/locate_rules.md`：格式正文及附件定位。
- `references/outline_extract_rules.md`：材料与父子层级识别。
- `references/toc_filter_rules.md`：导航目录与实际编制要求的区分。
