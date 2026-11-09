# 保证金 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `投标保证金`（table）：`项目`、`具体要求`
- `履约保证金`（table）：`项目`、`具体要求`

## 事项组织

- 投标保证金和履约保证金分别记录金额、形式、提交与退还等完整事项，不能跨类型借用条件。
- content 的“项目”写具体事项，“具体要求”保留金额、基数、账户、时点及限制；不生成空表或占位内容。
- 原文明示免收时，用对应分类的事实记录和引用表达免除要求。
- 检索未命中只登记研究缺口，由程序派生覆盖与缺口投影；未命中不等于免收，不能生成“无相关内容”业务记录。
- 要求与免除适用不同标段或条件时分别记录，不合并成自相矛盾的结论。

## 提交方式

研究结束后统一综合。content 只使用本专题声明的中文键，citations 只填写已读block_id，由程序补齐原文定位，无需quote；业务范围、条件、材料和评分属性同样需要依据。
工作ID、分批及审查规则以运行时工具为准，样例中的 work_ids 须换为实际返回的ID。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是研究结束、进入 synthesis 后按顺序调用 submit_analysis 的参数，不是检索期间逐项输出。
样例展示综合阶段的 content 与引用结构；研究阶段登记轻量事实线索和具体问题；work_ids 使用程序返回的工作ID。
正文由 content 承载，citations 独立溯源；综合各批暂存，最后一批 final=true 后合并审查支持性与完整性并统一展示，无需另发空提交。

## 明确免收与未确定的履约细节

以下仅展示综合阶段的局部输出结构。实际运行先完成本专题全部可处理核对项，明确受阻原因和适用范围，再统一输出；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

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
              "block_id": "example-1"
            }
          ],
          "work_ids": [
            "w1",
            "w2"
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
