# 否决条件 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例展示 content 及引用结构；实际增量提交还须提供 topic_updates，登记子主题核对项、证据、事项 key 和未决待办。
正文由 content 承载，citations 独立溯源；各批独立校验，全部子主题处理后自动查漏，无需另发空提交。

## 条件与后置否决结论共同引用

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "资格审查条件第1项：投标人须具有有效的保安服务许可证。"
    },
    {
      "id": "example-2",
      "text": "上述资格条件任一项不满足的，否决其投标。"
    },
    {
      "id": "example-3",
      "text": "建议配备专门联络人员。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "qualification",
          "kind": "requirement",
          "title": "资格条件不满足",
          "group": "主体资格类",
          "content": {
            "废标情形": "不满足第1项资格条件",
            "具体描述": "投标人须具有有效的保安服务许可证；不满足的否决其投标。"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "资格审查条件第1项：投标人须具有有效的保安服务许可证。"
            },
            {
              "block_id": "example-2",
              "quote": "上述资格条件任一项不满足的，否决其投标。"
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
