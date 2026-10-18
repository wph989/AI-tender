# 人员要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一次空 records、final=true 明确收尾。

## 岗位资格与兼任边界

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "配备总监理工程师1名，具有有效的注册监理工程师证书。"
    },
    {
      "id": "example-2",
      "text": "该总监理工程师最多只能同时担任3项工程（含本项目）的相关岗位。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "person",
          "kind": "requirement",
          "title": "总监理工程师配置与限制",
          "group": "总监理工程师",
          "content": {
            "字段": "数量、资格与兼任限制",
            "内容": [
              "总监理工程师1名，具有有效的注册监理工程师证书",
              "最多只能同时担任3项工程（含本项目）的相关岗位"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "配备总监理工程师1名，具有有效的注册监理工程师证书。"
            },
            {
              "block_id": "example-2",
              "quote": "该总监理工程师最多只能同时担任3项工程（含本项目）的相关岗位。"
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
