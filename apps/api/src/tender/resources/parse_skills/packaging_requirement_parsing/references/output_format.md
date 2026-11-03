# 封装与递交 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `投标文件组成`（table）：`文件部分`、`具体要求`
- `文件格式要求`（table）：`格式要求`、`具体描述`
- `签字盖章要求`（table）：`签字盖章要求`、`具体描述`
- `密封要求`（table）：`密封要求`、`具体描述`
- `份数要求`（table）：`份数要求`、`具体描述`
- `纸质版要求`（table）：`纸质要求`、`具体描述`
- `电子版要求`（table）：`电子要求`、`具体描述`

## 事项组织

- 每条保存一个制作或递交事项，保留份数、签章主体、密封、标记及电子介质要求。
- 逻辑标类型不等于物理分册；不能自行推断独立装订或密封。
- 格式要求指文件制作方式，内部章节树由格式专题输出；盲标例外与限制完整保留。

## 提交方式

完成本专题检索和 complete_research 后调用 submit_analysis，每次 records 最多三条完整事项，final=false。
记录 key 稳定，纠正同一事项沿用原 key。content 仅填当前分类的中文键，缺少依据的键省略；多条并列要求用字符串数组。
同一事项可以综合多处原文，citations 分别填写已读 block_id 和连续 quote；不要填写服务端生成的页码、坐标、text 或 evidence_ids。
不能用无依据的“未提及/无”占位。所有事项完成后以 records=[]、final=true 收尾，未决事项留在 coverage/gaps。
通用 scope、conditions、materials、scoring 等结构以运行时工具 schema 为准，填写后同样接受原文校验。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一次空 records、final=true 明确收尾。

## 份数与盲标限制分别记录

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "纸质投标文件正本1份、副本2份。"
    },
    {
      "id": "example-2",
      "text": "技术文件实行盲标，正文不得出现投标人名称；封面按指定格式填写。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "copies",
          "kind": "requirement",
          "title": "纸质份数",
          "group": "份数要求",
          "content": {
            "份数要求": "正副本",
            "具体描述": "正本1份、副本2份"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "纸质投标文件正本1份、副本2份。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "anonymous",
          "kind": "requirement",
          "title": "盲标正文与封面",
          "group": "文件格式要求",
          "content": {
            "格式要求": "盲标",
            "具体描述": [
              "技术文件正文不得出现投标人名称",
              "封面按指定格式填写"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-2",
              "quote": "技术文件实行盲标，正文不得出现投标人名称；封面按指定格式填写。"
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
