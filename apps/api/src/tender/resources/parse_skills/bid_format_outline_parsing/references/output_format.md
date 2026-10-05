# 投标文件格式大纲输出格式

## 返回要求

- 最终回复只能包含一个合法 JSON 对象,不要输出解释性内容。
- 禁止使用 Markdown 代码围栏、`<module_result>` 标签或任何解释性文字。
- 顶层只能包含 `section_end_element_index`、`package_types` 和 `items`。
- `section_end_element_index` 必须是定位阶段确认的格式正文最后一个元素序号（1-based，包含）。
- `package_types` 存放标类型（level 固定视为 0）及其直属章节，`items` 存放不隶属任何标类型的顶层游离章节。
- 两者可以并存，也可以其中一个为空数组；全文确实不存在任何标类型时 `package_types` 为空，全部章节写入 `items`。

## 标类型与游离章节共存

`package_types` 存放标类型（level 视为 0）及其直属章节；`items` 存放不隶属任何标类型的顶层游离章节。两者可以同时出现，也可以其中一个为空数组。

```json
{
  "section_end_element_index": 40,
  "package_types": [
    {
      "name": "<标类型标题原文>",
      "package_type_index": 10,
      "chapters": [
        {
          "title": "<该标类型下的章节标题原文>",
          "level": 1,
          "element_index": 12,
          "children": []
        }
      ]
    }
  ],
  "items": [
    {
      "title": "<不隶属任何标类型的顶层章节标题原文>",
      "level": 1,
      "element_index": 30,
      "children": []
    }
  ]
}
```

## 全部为游离章节（无标类型）

```json
{
  "section_end_element_index": 40,
  "package_types": [],
  "items": [
    {
      "title": "<章节标题原文>",
      "level": 1,
      "element_index": 10,
      "children": []
    }
  ]
}
```

## 顶层组织分组必须转换为标类型

如果一个独立节点只负责统领后续具体材料，例如 index 1012 的“商务部分”统领 index 1014 的“一、类似业绩”，不得输出为 `items` 中 `level=1 -> level=2` 的普通章节树。应移除组织容器所占的章节层级并输出为：

```json
{
  "section_end_element_index": 1080,
  "package_types": [
    {
      "name": "商务部分",
      "package_type_index": 1012,
      "chapters": [
        {
          "title": "一、类似业绩",
          "level": 1,
          "element_index": 1014,
          "children": []
        }
      ]
    }
  ],
  "items": []
}
```

转换依据是“上位节点只承担组织分组功能并真实统领后续具体材料”，不是标题中出现了某个固定词。若节点自身命名一份需要编制的具体材料，则仍作为章节。

## 未找到

```json
{
  "section_end_element_index": null,
  "package_types": [],
  "items": []
}
```

## 字段约束

- 标类型对象只能包含 `name`、`package_type_index`、`chapters`。
- 章节对象只能包含 `title`、`level`、`element_index`、`children`。
- 找到格式正文时 `section_end_element_index` 必须是正整数，并且不能早于最后一个章节的 `element_index`；未找到时必须为 `null`。
- `title`、`name` 必须是 DOCX 元素最后一列 `text` 的完整原文，或在复合段落中按 `outline_extract_rules.md` 截取的连续原文片段；禁止改写、概括、跨元素拼接。
- `level` 只能是 `1`、`2`、`3`；标类型不写入 level 字段，其层级固定视为 0。
- `children` 必须始终为数组，没有子章节时使用空数组。
- 禁止输出 `reasoning`、`confidence`、`start_element_index`、`end_element_index`、目录索引和其他覆盖范围字段。
- 未找到时将 `section_end_element_index` 写为 `null` 并输出两个空数组，不解释原因。
- 标类型是分别领起各自章节组的独立顶层容器；若资格、商务、技术等名称只是在同一句/同一段中并列罗列（如“投标文件包括商务部分、技术部分、其他文件”），那是正文描述，不是标类型，不写入 `package_types`。
- 标类型必须根据全文组织语义判断；禁止使用固定关键词或编号模式直接决定 `name`、标题角色或标题层级。
