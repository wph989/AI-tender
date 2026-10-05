---
name: bid_format_outline_parsing
description: "投标文件格式大纲解析。完整阅读主 DOCX，定位格式正文，识别逻辑标类型及 1-3 级章节树，并输出可追溯 JSON。"
---

# 投标文件格式大纲解析 Skill

## 任务

从主招标文件提取投标文件组织结构：逻辑标类型写入 `package_types`，不属于标类型的顶层章节写入 `items`，章节最多保留三级。

标类型是 `level=0` 的逻辑组织容器，不等同于物理分册；单册装订的文件也可能存在标类型。`package_types` 与 `items` 允许同时非空。

## 总流程

1. 进入全文定位阶段，按下方路由加载定位规则，再调用 `read_docx_structure` 分页通读服务端绑定的唯一主 DOCX。
2. 使用定位结果重新精读目标范围，识别并排除目录区域。
3. 进入结构提取阶段，按下方路由加载提取规则；先划分标类型管辖区段，再在各区段内构建章节树。
4. 回到全文关系验证标类型遗漏、章节倒挂和错误归属。
5. 将定位阶段确认的结束元素写入 `section_end_element_index`，按输出契约生成最终 JSON。

禁止凭第一次通读的记忆直接建树。正文只能以 `read_docx_structure` 返回的原始 DOCX 元素为依据。Markdown 仅可用于了解文件清单，不作为投标文件格式定位或章节树提取依据。

## Reference 动态加载路由

- **开始定位正文前必须读取** `references/locate_rules.md`：用于建立全文业务地图、排除普通提及并确定完整边界。
- **目标范围疑似包含目录或重复章节时读取** `references/toc_filter_rules.md`：只处理导航区域判断；没有目录疑点时不读取。
- **开始识别标类型和章节前必须读取** `references/outline_extract_rules.md`：用于候选清单、逻辑标类型、管辖区段、层级和全文回看。
- **生成最终回复前必须读取** `references/output_format.md`：用于字段、层级和唯一合法输出格式。

必须在进入对应阶段时加载 reference，不能把尚未读取的文件内容当作已知规则，也不能因结果看似明显而跳过标记为“必须读取”的 reference。

## 工具和输出边界

- `read_docx_structure`：唯一正文读取工具；主文件由服务端绑定，不接受 `file_path`，必须按分页字段覆盖全文和目标范围。
- 名称和 index 必须来自原文；禁止改写、跨元素拼接或编造 index。
- 最终只发送 `references/output_format.md` 定义的一个 JSON 对象；除契约要求的
  `section_end_element_index` 外，禁止输出定位结果、推理、解释、Markdown 围栏或
  `<module_result>` 标签。
