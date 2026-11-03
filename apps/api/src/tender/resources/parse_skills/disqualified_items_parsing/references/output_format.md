# 否决条件 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `主体资格类`（table）：`废标情形`、`具体描述`
- `投标文件形式类`（table）：`废标情形`、`具体描述`
- `实质性响应类`（table）：`废标情形`、`具体描述`
- `违法违规类`（table）：`废标情形`、`具体描述`
- `其他废标情形`（table）：`废标情形`、`具体描述`

## 事项组织

- 每条独立否决条件是一条记录，同一证件的等级、有效性等限定保持在该条件内。
- “废标情形”写具体触发原因，“具体描述”保留主体、门槛及否决后果；条件和后果跨块时一起引用。
- 按实际原因归入主体资格类、文件形式类、实质性响应类、违法违规类或其他废标情形。
- 资格审查不通过等结论不能替代资格明细；评分扣分和未证明否决后果的强制条款排除。

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

## 条件与后置否决结论共同引用

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "资格审查条件第1项：投标人须具有有效的保安服务许可证。"
    },
    {
      "id": "example-2",
      "text": "上述资格条件任一项不满足的，否决其投标。"
    },
    {
      "id": "example-3",
      "text": "建议配备专门联络人员。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "qualification",
          "kind": "requirement",
          "title": "资格条件不满足",
          "group": "主体资格类",
          "content": {
            "废标情形": "不满足第1项资格条件",
            "具体描述": "投标人须具有有效的保安服务许可证；不满足的否决其投标。"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "资格审查条件第1项：投标人须具有有效的保安服务许可证。"
            },
            {
              "block_id": "example-2",
              "quote": "上述资格条件任一项不满足的，否决其投标。"
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
