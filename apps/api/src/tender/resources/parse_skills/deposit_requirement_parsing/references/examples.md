# 保证金 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例展示 content 及引用结构；实际增量提交还须提供 topic_updates，登记子主题核对项、证据、事项 key 和未决待办。
正文由 content 承载，citations 独立溯源；各批独立校验，全部子主题处理后自动查漏，无需另发空提交。

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

## 本轮未检索到保证金条款

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "项目工期为90日历天。"
    }
  ],
  "submissions": [
    {
      "records": [],
      "final": true,
      "gaps": [
        {
          "key": "deposit-search",
          "topic": "amount",
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "code": "search_exhausted",
          "detail": "本轮已检索资料未命中保证金条款，不能据此认定免收。"
        }
      ],
      "research_summary": "示例假定已完成保证金主题检索并登记未命中；保留范围缺口。"
    }
  ]
}
```
