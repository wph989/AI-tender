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

子主题具备可靠依据即可调用 submit_analysis，每批 records 最多三条完整事项，topic_updates 同时关联主题、范围、已核对 checks、证据和事项 key。通过校验后实时展示。
记录 key 稳定，纠正同一事项沿用原 key。content 仅填当前分类的中文键，缺少依据的键省略；多条并列要求用字符串数组。
同一事项可以综合多处原文，citations 分别填写已读 block_id 和连续 quote；不要填写服务端生成的页码、坐标、text 或 evidence_ids。
不能用无依据的“未提及/无”占位。通过校验的事项立即保存；全部主题处理后自动独立查漏，final=true 只请求检查完成条件，未决事项留在 topic_updates 与 gaps。
通用 scope、conditions、materials、scoring 等结构以运行时工具 schema 为准，填写后同样接受原文校验。

## JSON 示例

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
