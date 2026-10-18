# 业绩要求 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `类似项目业绩要求`（table）：`业绩要求`、`具体描述`
- `业绩时间范围要求`（table）：`时间要求`、`具体描述`
- `业绩金额要求`（table）：`金额要求`、`具体描述`
- `证明材料要求`（table）：`材料要求`、`具体描述`
- `业绩评分标准`（table）：`评分标准`、`具体描述`
- `特定行业业绩要求`（table）：`行业要求`、`具体描述`

## 事项组织

- 仅收录企业历史项目经验，人员个人业绩排除。
- 同一业绩门槛的定义、时间、数量、金额和证明要求可在一条中综合，不能拆散后丢失组合条件。
- 独立的时间、金额、材料或计分要求使用对应分类；同一内容不为填满分类而重复输出。
- 认定时间点、完成状态、联合体份额及证明材料的且/或关系均保留原文。

## 提交方式

完成本专题检索和 complete_research 后，逐条调用 submit_analysis，每次 records 最多一条完整事项，final=false。
记录 key 稳定，纠正同一事项沿用原 key。content 仅填当前分类的中文键，缺少依据的键省略；多条并列要求用字符串数组。
同一事项可以综合多处原文，citations 分别填写已读 block_id 和连续 quote；不要填写服务端生成的页码、坐标、text 或 evidence_ids。
不能用无依据的“未提及/无”占位。所有事项完成后以 records=[]、final=true 收尾，未决事项留在 coverage/gaps。
通用 scope、conditions、materials、scoring 等结构以运行时工具 schema 为准，填写后同样接受原文校验。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一次空 records、final=true 明确收尾。

## 企业业绩门槛与证明材料

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "投标人须提供2023年1月1日以来已完成的园区运维服务项目业绩至少2项，每项合同金额不低于100万元。"
    },
    {
      "id": "example-2",
      "text": "上述业绩以验收日期为准，须同时提供合同关键页和验收证明。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "performance",
          "kind": "requirement",
          "title": "企业类似项目业绩",
          "group": "类似项目业绩要求",
          "content": {
            "业绩要求": "已完成的园区运维服务项目",
            "具体描述": [
              "2023年1月1日以来至少2项，每项合同金额不低于100万元",
              "以验收日期为准，同时提供合同关键页和验收证明"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "materials": [
            {
              "name": "合同关键页和验收证明",
              "requirement": "须同时提供"
            }
          ],
          "citations": [
            {
              "block_id": "example-1",
              "quote": "投标人须提供2023年1月1日以来已完成的园区运维服务项目业绩至少2项，每项合同金额不低于100万元。"
            },
            {
              "block_id": "example-2",
              "quote": "上述业绩以验收日期为准，须同时提供合同关键页和验收证明。"
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
