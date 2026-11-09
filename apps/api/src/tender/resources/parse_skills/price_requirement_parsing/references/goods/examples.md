# 报价要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是研究结束、进入 synthesis 后按顺序调用 submit_analysis 的参数，不是检索期间逐项输出。
样例展示综合阶段的 content 与引用结构；研究阶段登记轻量事实线索和具体问题；work_ids 使用程序返回的工作ID。
正文由 content 承载，citations 独立溯源；综合各批暂存，最后一批 final=true 后合并审查支持性与完整性并统一展示，无需另发空提交。

## 同名限价按标段分开

以下仅展示综合阶段的局部输出结构。实际运行先完成本专题全部可处理核对项，明确受阻原因和适用范围，再统一输出；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

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
