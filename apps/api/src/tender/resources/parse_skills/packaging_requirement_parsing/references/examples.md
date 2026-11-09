# 封装与递交 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是研究结束、进入 synthesis 后按顺序调用 submit_analysis 的参数，不是检索期间逐项输出。
样例展示综合阶段的 content 与引用结构；研究阶段登记轻量事实线索和具体问题；work_ids 使用程序返回的工作ID。
正文由 content 承载，citations 独立溯源；综合各批暂存，最后一批 final=true 后合并审查支持性与完整性并统一展示，无需另发空提交。

## 份数与盲标限制分别记录

以下仅展示综合阶段的局部输出结构。实际运行先完成本专题全部可处理核对项，明确受阻原因和适用范围，再统一输出；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "纸质投标文件正本1份、副本2份。"
    },
    {
      "id": "example-2",
      "text": "技术文件实行盲标，正文不得出现投标人名称；封面按指定格式填写。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "copies",
          "kind": "requirement",
          "title": "纸质份数",
          "group": "份数要求",
          "content": {
            "份数要求": "正副本",
            "具体描述": "正本1份、副本2份"
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
          "key": "anonymous",
          "kind": "requirement",
          "title": "盲标正文与封面",
          "group": "文件格式要求",
          "content": {
            "格式要求": "盲标",
            "具体描述": [
              "技术文件正文不得出现投标人名称",
              "封面按指定格式填写"
            ]
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
