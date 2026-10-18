# 保证金 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `投标保证金`（table）：`项目`、`具体要求`
- `履约保证金`（table）：`项目`、`具体要求`

## 事项组织

- 投标保证金和履约保证金分别记录金额、形式、提交与退还等完整事项，不能跨类型借用条件。
- content 的“项目”写具体事项，“具体要求”保留金额、基数、账户、时点及限制；不生成空表或占位内容。
- 原文明示免收时，用对应分类的事实记录和引用表达免除要求。
- 检索未命中只登记 coverage/gaps；未命中不等于免收，不能生成“无相关内容”业务记录。
- 要求与免除适用不同标段或条件时分别记录，不合并成自相矛盾的结论。

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

## 明确免收与未确定的履约细节

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "本项目不收取投标保证金。"
    },
    {
      "id": "example-2",
      "text": "履约保证金为合同金额的5%。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "bid-exempt",
          "kind": "fact",
          "title": "投标保证金免收",
          "group": "投标保证金",
          "content": {
            "项目": "收取要求",
            "具体要求": "本项目不收取投标保证金。"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "本项目不收取投标保证金。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "performance-amount",
          "kind": "requirement",
          "title": "履约保证金金额",
          "group": "履约保证金",
          "content": {
            "项目": "金额、比例及计算基数",
            "具体要求": "合同金额的5%"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-2",
              "quote": "履约保证金为合同金额的5%。"
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
