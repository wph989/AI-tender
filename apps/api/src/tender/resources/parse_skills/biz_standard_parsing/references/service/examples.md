# 商务要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一次空 records、final=true 明确收尾。

## 跨块付款条件归并

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "阶段服务成果验收合格后支付合同金额的30%。"
    },
    {
      "id": "example-2",
      "text": "上述付款须先取得合规发票，收到发票后15日内支付。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "payment",
          "kind": "requirement",
          "title": "验收后付款",
          "group": "付款条件",
          "content": {
            "付款要素": "验收款",
            "具体要求": [
              "阶段服务成果验收合格后支付合同金额的30%",
              "取得合规发票后15日内支付"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "阶段服务成果验收合格后支付合同金额的30%。"
            },
            {
              "block_id": "example-2",
              "quote": "上述付款须先取得合规发票，收到发票后15日内支付。"
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
