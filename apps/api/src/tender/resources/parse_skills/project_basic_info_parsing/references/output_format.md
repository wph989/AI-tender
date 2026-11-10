# 项目概况 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `甲方信息`（table）：`字段`、`内容`
- `代理信息`（table）：`字段`、`内容`
- `项目基本信息`（table）：`字段`、`内容`
- `分标信息`（table）：`字段`、`内容`

## 事项组织

- “字段”必须是单个事项名称字符串，不使用字段名数组。不同事实分别逐条提交；“内容”数组只保留同一事项的并列要求，不能用两个独立数组暗示字段和值一一对应。

- 甲方、代理与项目分类按原文角色填写，不能互相借用联系方式。
- 每个具体事实或标段一条记录；分标信息不得合并不同标段的值，标段目录使用 kind=lot。
- 标段 title 保留原文名称，code 仅填原文编号；未给编号的标段仍可保留。
- content 的“字段”写具体信息名称，“内容”写有依据的值；无依据字段省略。

## 提交方式

研究期间可暂存完整事项，已有草稿直接复用。content 只使用本专题声明的中文键，block_ids 只填写已读原文ID，后端生成原文定位；范围、条件、材料和评分同样需要依据。
工作ID、分批及审查规则以运行时工具为准，样例中的 work_ids 须换为实际返回的ID。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数；研究期可用 final=false 暂存，已有草稿在 complete_research 后直接审查。
样例展示完整业务事项与 block_ids；work_ids 使用程序返回的工作ID，修改沿用回执 id。
正文由 content 承载，block_ids 指向实际已读原文；标题、身份与定位由后端补齐，整项审查通过后展示。条件、材料、评分和例外完整写入 content，不重复提交结构化属性。

## 项目事实与独立标段

以下展示局部业务事项。研究期间逐批暂存，明确受阻原因和适用范围；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "项目名称：示例园区升级项目。"
    },
    {
      "id": "example-2",
      "text": "本项目分为东区标段与西区标段，东区标段编号A。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "kind": "fact",
          "group": "项目基本信息",
          "content": {
            "字段": "项目名称",
            "内容": "示例园区升级项目"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "work_ids": [
            "w1",
            "w2"
          ],
          "block_ids": [
            "example-1"
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "kind": "lot",
          "title": "东区标段",
          "group": "分标信息",
          "content": {
            "字段": "分标名称及编号",
            "内容": "东区标段，编号A"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "code": "A",
          "work_ids": [
            "w9",
            "w10"
          ],
          "block_ids": [
            "example-2"
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "kind": "lot",
          "title": "西区标段",
          "group": "分标信息",
          "content": {
            "字段": "分标名称",
            "内容": "西区标段"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "work_ids": [
            "w9",
            "w10"
          ],
          "block_ids": [
            "example-2"
          ]
        }
      ],
      "final": true
    }
  ]
}
```
