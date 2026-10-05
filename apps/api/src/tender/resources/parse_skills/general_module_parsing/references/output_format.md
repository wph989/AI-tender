# 通用模块解析输出格式规范

> TODO: 定义各模块解析结果的结构化格式（字段、类型、JSON Schema）。

## 单模块结果
| 字段 | 类型 | 说明 |
|------|------|------|
| module_code | string | 模块编码 |
| final_result | string | 最终解析结果 |
| status | string | parsed / error |
| source_files | array | 使用到的 Markdown 文件名 |
| source_ranges | array | 引用来源范围，如文件名 + 行号范围 |
| search_queries | array | 实际使用的检索词，便于复核召回情况 |

## 保存字段（tender_interpretation_document）
- tender_code
- content_type（= module_code）
- content_text（= final_result）
- parse_status

## 未找到内容
如果当前模块没有在招标文件中找到明确依据，仍需在最终消息正文中返回结果，内容建议包含：
- `## 未找到项`：列出未找到的字段或章节。
- `## 检索说明`：列出尝试过的关键词种子、命中文件或未命中情况。
- `## 后续建议`：说明需要人工确认或补充文件的事项。
