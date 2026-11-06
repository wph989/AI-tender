# 评分办法 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `评分总则`（table）：`总则要素`、`原文内容`
- `总分构成`（table）：`组成部分`、`分值`
- `商务评分标准`（table）：`评分项`、`满分分值`、`评分标准（原文摘录）`
- `技术评分标准`（table）：`评分项`、`满分分值`、`评分标准（原文摘录）`
- `综合评分标准`（table）：`评分项`、`满分分值`、`评分标准（原文摘录）`
- `价格评分标准`（table）：`评分项`、`满分分值`、`评分标准（原文摘录）`

## 事项组织

- 区分评分总则、总分构成与具体评分项；原文未分商务/技术时使用综合评分标准。
- 同一评分项的所有档次、条件、备注和扣分放在该记录中，“评分标准（原文摘录）”使用字符串数组。
- 价格评分的公式、变量、基准价、得分情形与上限保持在同一事项；不能把档次拆成独立评分项。
- 评分扣分保留，否决投标条件交给否决专题；不得根据常见分值补满总分。
- scoring 如填写，必须与 content 一致且被同一套引用支持。

## 提交方式

完成本专题检索和 complete_research 后调用 submit_analysis，每次 records 最多三条完整事项，final=false。
记录 key 稳定，纠正同一事项沿用原 key。content 仅填当前分类的中文键，缺少依据的键省略；多条并列要求用字符串数组。
同一事项可以综合多处原文，citations 分别填写已读 block_id 和连续 quote；不要填写服务端生成的页码、坐标、text 或 evidence_ids。
不能用无依据的“未提及/无”占位。最后一批可携带 records、final=true，通过校验即收尾；仅确认收尾时可用 records=[]，未决事项留在 coverage/gaps。
通用 scope、conditions、materials、scoring 等结构以运行时工具 schema 为准，填写后同样接受原文校验。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一批可携带 records、final=true，通过校验即收尾，无需另发空提交。

## 完整档次及同项扣分

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
              "block_id": "example-1",
              "quote": "技术评分：服务实施方案满分10分。方案完整可行得10分；基本可行得6分；不可行或未提供得0分。"
            },
            {
              "block_id": "example-2",
              "quote": "服务实施方案每缺少一项风险措施扣1分，扣完本项得分为止。"
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
