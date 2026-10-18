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

- 输入是授权资料清单及检索返回的 id/text 原文块。先核对主文件、澄清、补遗和相关附件，按 coverage.json 的业务主题继续检索；关键词只是线索，不保证完整召回。
- list_documents 返回资料ID与说明；search_document 检索本项目，search_knowledge 检索关联参考库。参考资料不能替代项目依据，参考建议也需要引用本项目相关要求。
- 遇到转引按目标名称、章节或业务主题继续检索，read_document 围绕已读 block_id 补读表头、脚注和条件；不猜测ID、磁盘路径或全文行号。未命中、缺失目标及预算不足如实登记。
- 完成主题核对后调用 complete_research，再综合同一范围内的完整事项。未命中不等于文件未约定；新增原文后重新确认检索和综合，空检索不要求重做已有事项。
- 按 output_format.md 逐条调用 submit_analysis，每次最多一条完整事项。content 承载业务内容，citations 独立提供已读ID及连续原文；不同标段或条件不强行合并。
- 全部事项处理后用空 records 和 final=true 收尾，保留未决 coverage/gaps。遇到工具错误按实际反馈和剩余额度纠正，不自行设定重试次数。
- 权限、调用预算、结构和支持性校验由运行时执行。read_file 只读取当前 Skill 的参考文件或会话历史；不读取招标文件磁盘路径，不递归委派子Agent。

## 参考文件

运行时首次推理前已加载正文、输出说明、核心细则和明确品类的规则；无需重复读取，示例按需通过 read_file 查阅。

- `references/output_schema.json`：本项目机器格式声明，运行时从报告快照读取。
- `references/output_format.md`：事项组织、字段含义和实际 JSON 提交示例。
- `references/coverage.json`：本专题检索覆盖清单，未解决主题保留缺口。
- `references/locate_rules.md`：格式正文及附件定位。
- `references/outline_extract_rules.md`：材料与父子层级识别。
- `references/toc_filter_rules.md`：导航目录与实际编制要求的区分。
