# 开标要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例展示 content 及引用结构；实际增量提交还须提供 topic_updates，登记子主题核对项、证据、事项 key 和未决待办。
正文由 content 承载，citations 独立溯源；各批独立校验，全部子主题处理后自动查漏，无需另发空提交。

## 远程开标与解密时限

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "开标时间为2026年11月2日9时30分，采用不见面开标。"
    },
    {
      "id": "example-2",
      "text": "投标人应登录示例交易平台，在开标后30分钟内完成解密。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "opening-time",
          "kind": "requirement",
          "title": "开标时间",
          "group": "开标时间",
          "content": {
            "时间要素": "开标时间",
            "具体要求": "2026年11月2日9时30分"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "开标时间为2026年11月2日9时30分，采用不见面开标。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "remote-opening",
          "kind": "requirement",
          "title": "远程开标及解密",
          "group": "开标方式",
          "content": {
            "方式类型": "不见面开标",
            "具体要求": [
              "登录示例交易平台",
              "在开标后30分钟内完成解密"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "开标时间为2026年11月2日9时30分，采用不见面开标。"
            },
            {
              "block_id": "example-2",
              "quote": "投标人应登录示例交易平台，在开标后30分钟内完成解密。"
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
