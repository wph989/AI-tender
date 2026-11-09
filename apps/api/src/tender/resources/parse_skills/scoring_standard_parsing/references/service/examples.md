# 评分办法 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是研究结束、进入 synthesis 后按顺序调用 submit_analysis 的参数，不是检索期间逐项输出。
样例展示综合阶段的 content 与引用结构；研究阶段登记轻量事实线索和具体问题；work_ids 使用程序返回的工作ID。
正文由 content 承载，citations 独立溯源；综合各批暂存，最后一批 final=true 后合并审查支持性与完整性并统一展示，无需另发空提交。

## 完整档次及同项扣分

以下仅展示综合阶段的局部输出结构。实际运行先完成本专题全部可处理核对项，明确受阻原因和适用范围，再统一输出；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "技术评分：服务实施方案满分10分。方案完整可行得10分；基本可行得6分；不可行或未提供得0分。"
    },
    {
      "id": "example-2",
      "text": "服务实施方案每缺少一项风险措施扣1分，扣完本项得分为止。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "solution-score",
          "kind": "requirement",
          "title": "服务实施方案",
          "group": "技术评分标准",
          "content": {
            "评分项": "服务实施方案",
            "满分分值": "10分",
            "评分标准（原文摘录）": [
              "方案完整可行得10分；基本可行得6分；不可行或未提供得0分。",
              "服务实施方案每缺少一项风险措施扣1分，扣完本项得分为止。"
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
              "block_id": "example-1"
            },
            {
              "block_id": "example-2"
            }
          ],
          "work_ids": [
            "w1",
            "w2"
          ]
        }
      ],
      "final": true
    }
  ]
}
```
