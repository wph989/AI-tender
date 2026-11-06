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
