# 技术要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例展示 content 及引用结构；实际增量提交还须提供 topic_updates，登记子主题核对项、证据、事项 key 和未决待办。
正文由 content 承载，citations 独立溯源；各批独立校验，全部子主题处理后自动查漏，无需另发空提交。

## 独立任务与纯参数边界

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
