# 商务要求 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `付款条件`（table）：`付款要素`、`具体要求`
- `交付要求`（table）：`交付要素`、`具体要求`
- `验收条款`（table）：`验收要素`、`具体要求`
- `质保与售后服务`（table）：`服务要素`、`具体要求`
- `违约责任`（table）：`违约情形`、`责任内容`
- `保险与担保要求`（table）：`担保类型`、`具体要求`
- `知识产权与保密`（table）：`条款类型`、`具体要求`
- `争议解决`（table）：`解决方式`、`具体内容`
- `合同变更与终止`（table）：`条款类型`、`具体要求`

## 事项组织

- 一条记录说明一个完整履约事项，分类由义务内容决定；付款、验收与质保的触发点不能混用。
- 保留期限、比例、基数、例外及责任；不同范围的同名条款分别记录。
- 人员、业绩、评分、报价构成、技术规格以及投标/履约保证金不在此重复收录。

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
