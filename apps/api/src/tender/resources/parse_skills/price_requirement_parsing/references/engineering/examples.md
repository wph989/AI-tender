# 报价要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一次空 records、final=true 明确收尾。

## 同名限价按标段分开

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "东区标段最高投标限价100万元（含税），超过限价否决投标。"
    },
    {
      "id": "example-2",
      "text": "西区标段最高投标限价80万元（含税）。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "east-price",
          "kind": "requirement",
          "title": "东区最高投标限价",
          "group": "投标限价",
          "content": {
            "限价类型": "最高投标限价",
            "金额或范围（原文）": "100万元（含税）",
            "超限处理": "否决投标"
          },
          "scope": {
            "kind": "lots",
            "lot_refs": [
              "东区标段"
            ]
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "东区标段最高投标限价100万元（含税），超过限价否决投标。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "west-price",
          "kind": "requirement",
          "title": "西区最高投标限价",
          "group": "投标限价",
          "content": {
            "限价类型": "最高投标限价",
            "金额或范围（原文）": "80万元（含税）"
          },
          "scope": {
            "kind": "lots",
            "lot_refs": [
              "西区标段"
            ]
          },
          "citations": [
            {
              "block_id": "example-2",
              "quote": "西区标段最高投标限价80万元（含税）。"
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
