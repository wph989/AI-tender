---
name: bid-format-outline-parsing
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

- 运行时先调用 `load_skill` 加载本文件及 `references/output_format.md`，无需重复读取；其余细则按需读取。
- `list_documents()`：返回授权资料的 id 和说明文本；资料 id 可填入检索的 source_id。
- `search_document(query, source_id?)`：检索本项目；`search_knowledge(query, source_id?)`：检索关联参考库。
- 检索证据只含 `id`、`text`。把证据 id 填入引用的 `block_id`；quote 必须是该 text 的连续原文。
- `read_document(block_id, before=2, after=2)`：围绕已读证据补读；before/after 合计最多11，均为0时只补读本块。不得猜测ID或扫描全文。
- `read_file(file_path)`：只读 `/skills/bid-format-outline-parsing/references/` 下当前任务需要的细则，或压缩历史；不能读取招标文件磁盘路径。
- `submit_analysis`：结构化提交，普通字段每批最多3条，大纲每批最多6节点；`final=false` 暂存，明确核对完成后 `final=true`。

## 证据选择与纠错

1. 先按本专题的问题检索，再核对主体、标段、表头、脚注、条件和补充文件。上下文不足时按证据ID补读；不能用关键词命中代替事实判断。
2. 同一事实在相同适用范围内重复出现，选最直接、完整的一处。跨块条件、不同标段、修订前后和未决冲突所需的证据分别保留；检索相似度和自报置信分数不作为可信度。
3. 引用只提交ID和连续摘录，不生成页码、坐标、文件路径或来源元数据。服务端校验实际读取记录、资料权限和版本后，按保留的ID补齐定位。
4. 工具返回结构化错误时，按 `message` 和 `remaining_attempts` 修正；只补交未通过部分，不重交已保存事实。更换字段名或重复相同请求不会获得新额度。
5. 收到收尾提示就停止扩展检索，提交已有可靠结果并在 `research_summary` 记录缺口；不得声称缺口是文件未约定。不得再委派子Agent，服务故障与重试由运行时处理。

## 输出

通过 submit_analysis 提交 outline_nodes 和 research_summary；不传 fields、relations。
没有格式依据时 outline_nodes 为空。名称保留原文，归属按内容语义判断，不按编号机械建树。
每节点只填写一次 parent_id，不另外编写 fields、relations、层级或父路径。详细字段见 references/output_format.md。
