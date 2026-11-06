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

子主题具备可靠依据即可调用 submit_analysis，每批 records 最多三条完整事项，topic_updates 同时关联主题、范围、已核对 checks、证据和事项 key。通过校验后实时展示。
记录 key 稳定，纠正同一事项沿用原 key。content 仅填当前分类的中文键，缺少依据的键省略；多条并列要求用字符串数组。
同一事项可以综合多处原文，citations 分别填写已读 block_id 和连续 quote；不要填写服务端生成的页码、坐标、text 或 evidence_ids。
不能用无依据的“未提及/无”占位。通过校验的事项立即保存；全部主题处理后自动独立查漏，final=true 只请求检查完成条件，未决事项留在 topic_updates 与 gaps。
通用 scope、conditions、materials、scoring 等结构以运行时工具 schema 为准，填写后同样接受原文校验。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例展示 content 及引用结构；实际增量提交还须提供 topic_updates，登记子主题核对项、证据、事项 key 和未决待办。
正文由 content 承载，citations 独立溯源；各批独立校验，全部子主题处理后自动查漏，无需另发空提交。

## 项目事实与独立标段

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
          "key": "project-name",
          "kind": "fact",
          "title": "项目名称",
          "group": "项目基本信息",
          "content": {
            "字段": "项目名称",
            "内容": "示例园区升级项目"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "项目名称：示例园区升级项目。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "lot-east",
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
          "citations": [
            {
              "block_id": "example-2",
              "quote": "本项目分为东区标段与西区标段，东区标段编号A。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "lot-west",
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
          "citations": [
            {
              "block_id": "example-2",
              "quote": "本项目分为东区标段与西区标段，东区标段编号A。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [],
      "final": true
    }
  ]
}
```
