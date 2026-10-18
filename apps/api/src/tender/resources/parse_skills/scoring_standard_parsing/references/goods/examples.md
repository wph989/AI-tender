# 评分办法 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一次空 records、final=true 明确收尾。

## 完整档次及同项扣分

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "技术评分：安装集成方案满分10分。方案完整可行得10分；基本可行得6分；不可行或未提供得0分。"
    },
    {
      "id": "example-2",
      "text": "安装集成方案每缺少一项风险措施扣1分，扣完本项得分为止。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "solution-score",
          "kind": "requirement",
          "title": "安装集成方案",
          "group": "技术评分标准",
          "content": {
            "评分项": "安装集成方案",
            "满分分值": "10分",
            "评分标准（原文摘录）": [
              "方案完整可行得10分；基本可行得6分；不可行或未提供得0分。",
              "安装集成方案每缺少一项风险措施扣1分，扣完本项得分为止。"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "scoring": {
            "max_points": "10分",
            "tiers": [
              {
                "condition": "方案完整可行",
                "points": "10分"
              },
              {
                "condition": "基本可行",
                "points": "6分"
              },
              {
                "condition": "不可行或未提供",
                "points": "0分"
              }
            ],
            "deductions": [
              "每缺少一项风险措施扣1分，扣完本项得分为止"
            ]
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "技术评分：安装集成方案满分10分。方案完整可行得10分；基本可行得6分；不可行或未提供得0分。"
            },
            {
              "block_id": "example-2",
              "quote": "安装集成方案每缺少一项风险措施扣1分，扣完本项得分为止。"
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
