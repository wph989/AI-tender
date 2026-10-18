# 报价要求 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `投标限价`（table）：`限价类型`、`金额或范围（原文）`、`超限处理`
- `价格构成`（table）：`费用项`、`计算方式或比例（原文）`
- `折扣/下浮`（table）：`下浮类型`、`范围或要求（原文）`

## 事项组织

- 每个价格事项一条记录；不同标段的金额分别记录 scope.lot_refs，不写入同一个单元格或用 HTML 分隔。
- 同属“价格构成”不代表同一事项。通常包含的费用、特定触发条件下另付的费用、报价修改与算术修正规则分别组织；每条保留自身完整条件和引用，不把整章拼成一个数组。
- 已明确“报价包含税金”但计税方法转引的附件未提供时，保留有依据的费用包含要求，计税方法另登记缺口；不默认税率，不把“详见附件”当作计算规则填入已完成事项。服务类的完整示例见 `references/service/examples.md`。
- 同一限价适用多个标段且原文明确时可以共用一条，不能把未明确范围当作 common。
- 数值、币种、税费、基数与比较范围保留原文，“超限处理”无依据时省略。
- 金额限价归投标限价，费用与报价方式归价格构成，比例下浮归折扣/下浮；同一事项不重复分类。

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
