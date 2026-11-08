# 技术要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是研究结束、进入 synthesis 后按顺序调用 submit_analysis 的参数，不是检索期间逐项输出。
样例展示综合阶段的 content 与引用结构；研究阶段登记轻量事实线索和具体问题；work_ids 使用程序返回的工作ID。
正文由 content 承载，citations 独立溯源；综合各批暂存，最后一批 final=true 后合并审查支持性与完整性并统一展示，无需另发空提交。

## 独立任务与纯参数边界

以下仅展示综合阶段的局部输出结构。实际运行先完成本专题全部可处理核对项，明确受阻原因和适用范围，再统一输出；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "技术方案要求：任务一为设备接口集成任务，应说明设备接入、接口兼容及联调方法。任务二为运行保障任务，应说明故障响应与恢复方法。"
    },
    {
      "id": "example-2",
      "text": "产品参数表：机柜宽度600mm，重量100kg。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "task-one",
          "kind": "requirement",
          "title": "设备接口集成任务",
          "group": "技术方案要求",
          "content": {
            "要求摘要": "编写设备接口集成任务方案",
            "关键要求": [
              "说明设备接入、接口兼容及联调方法"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "技术方案要求：任务一为设备接口集成任务，应说明设备接入、接口兼容及联调方法。任务二为运行保障任务，应说明故障响应与恢复方法。"
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
          "key": "task-two",
          "kind": "requirement",
          "title": "运行保障任务",
          "group": "技术方案要求",
          "content": {
            "要求摘要": "编写运行保障方案",
            "关键要求": [
              "说明故障响应与恢复方法"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "技术方案要求：任务一为设备接口集成任务，应说明设备接入、接口兼容及联调方法。任务二为运行保障任务，应说明故障响应与恢复方法。"
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
