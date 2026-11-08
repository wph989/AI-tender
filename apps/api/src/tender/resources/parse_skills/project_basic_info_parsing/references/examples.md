# 项目概况 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是研究结束、进入 synthesis 后按顺序调用 submit_analysis 的参数，不是检索期间逐项输出。
样例展示综合阶段的 content 与引用结构；研究阶段登记轻量事实线索和具体问题；work_ids 使用程序返回的工作ID。
正文由 content 承载，citations 独立溯源；综合各批暂存，最后一批 final=true 后合并审查支持性与完整性并统一展示，无需另发空提交。

## 项目事实与独立标段

以下仅展示综合阶段的局部输出结构。实际运行先完成本专题全部可处理核对项，明确受阻原因和适用范围，再统一输出；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "项目名称：示例园区升级项目。"
    },
    {
      "id": "example-2",
      "text": "本项目分为东区标段与西区标段，东区标段编号A。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "project-name",
          "kind": "fact",
          "title": "项目名称",
          "group": "项目基本信息",
          "content": {
            "字段": "项目名称",
            "内容": "示例园区升级项目"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "项目名称：示例园区升级项目。"
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
          "key": "lot-east",
          "kind": "lot",
          "title": "东区标段",
          "group": "分标信息",
          "content": {
            "字段": "分标名称及编号",
            "内容": "东区标段，编号A"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "code": "A",
          "citations": [
            {
              "block_id": "example-2",
              "quote": "本项目分为东区标段与西区标段，东区标段编号A。"
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
          "key": "lot-west",
          "kind": "lot",
          "title": "西区标段",
          "group": "分标信息",
          "content": {
            "字段": "分标名称",
            "内容": "西区标段"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-2",
              "quote": "本项目分为东区标段与西区标段，东区标段编号A。"
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
