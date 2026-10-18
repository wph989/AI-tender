# 封装与递交 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一次空 records、final=true 明确收尾。

## 份数与盲标限制分别记录

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
              "block_id": "example-1",
              "quote": "纸质投标文件正本1份、副本2份。"
            }
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
              "block_id": "example-2",
              "quote": "技术文件实行盲标，正文不得出现投标人名称；封面按指定格式填写。"
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
