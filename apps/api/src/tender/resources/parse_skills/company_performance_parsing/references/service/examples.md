# 业绩要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一批可携带 records、final=true，通过校验即收尾，无需另发空提交。

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
