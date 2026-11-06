# 项目概况 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例展示 content 及引用结构；实际增量提交还须提供 topic_updates，登记子主题核对项、证据、事项 key 和未决待办。
正文由 content 承载，citations 独立溯源；各批独立校验，全部子主题处理后自动查漏，无需另发空提交。

## 项目事实与独立标段

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
