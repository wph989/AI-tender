---
name: general_module_parsing
description: "招标文件通用模块解析兜底参考。仅当没有专用模块 Skill 可用时，用于基于归一化 Markdown 文件检索、扩展上下文并返回结构化结果。"
---

# 通用模块解析 Skill

> 对应 v1 `lg_agent/tender_documents_agent/general_module_parsing`。
> 当前 12 个标准解析模块应优先使用各自专用 Skill，本 Skill 只作为兜底参考。

## 适用场景
- 触发：没有匹配的专用模块 Skill，或需要临时解析非标准模块。
- 输入：运行时文件清单中的归一化 Markdown 文件 + 模块配置列表（module_code / prompt_code / 模板内容）。
- 输出：各模块解析结果（结构化文本/JSON），直接作为最终回复返回，由父级代码统一入库。

## 执行流程

1. **发现文件**：使用 `list_extracted_files` 查看当前任务可用 Markdown 文件。
2. **构造检索词**：根据模块目标和 bid_type 的参考规则，整理章节名、字段名、同义词和强约束关键词。
3. **精确检索**：使用 `grep` 搜索关键章节或关键词；内置 grep 是字面量匹配，组合条件请拆成多个关键词分别检索。
4. **扩展上下文**：根据命中位置调用 `read_file(file_path, offset, limit)` 分页读取相邻上下文；命中不足时更换关键词或扩大读取范围。
5. **结构化输出**：仅基于检索命中和扩展读取内容提取结果，引用尽量标注文件名和位置线索。
6. **保存状态**：单模块完成后必须将完整结果直接作为最终回复返回；即使未找到有效内容，也要返回“未找到项”和检索说明。

## 工具
- `list_extracted_files`：列出当前任务可用 Markdown 文件。
- `grep`：在 Markdown 中执行字面量精确检索；具体路径、glob 和输出模式由运行时上下文与工具护栏约束。
- `read_file`：通过 offset/limit 围绕命中位置分页读取上下文。
- 无保存工具：模块结果直接作为最终回复返回。

## 输出规范
参见 `references/output_format.md`。

## 注意
- 不要默认读取整篇 Markdown；除非文件很小且确有必要，必须优先使用检索和分页扩展控制上下文。
- 不依赖 `manifest.json` 或 `chunks.jsonl`；当前解析链路通过 file_manifest.json 维护 original 与 Markdown 的 file_id 映射。
- ★ 提示词不在 .env 管理，就近放业务模块：本 Skill 相关的提示词放
  `app/agents/tools/parse/prompts/*.md`（工具层直调）或本 Skill 的 `references/`（Skill 渐进加载），
  经 `app/prompts.load_prompt("agents/tools/parse", <name>)` 读取（见 `app/prompts/README.md`）。
