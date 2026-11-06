# 商务要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例展示 content 及引用结构；实际增量提交还须提供 topic_updates，登记子主题核对项、证据、事项 key 和未决待办。
正文由 content 承载，citations 独立溯源；各批独立校验，全部子主题处理后自动查漏，无需另发空提交。

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
