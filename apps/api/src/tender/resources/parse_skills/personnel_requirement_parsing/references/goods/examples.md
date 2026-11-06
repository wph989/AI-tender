# 人员要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例展示 content 及引用结构；实际增量提交还须提供 topic_updates，登记子主题核对项、证据、事项 key 和未决待办。
正文由 content 承载，citations 独立溯源；各批独立校验，全部子主题处理后自动查漏，无需另发空提交。

## 岗位资格与兼任边界

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "配备安装调试工程师1名，具有制造商出具的安装调试培训证书。"
    },
    {
      "id": "example-2",
      "text": "该安装调试工程师最多只能同时担任3项工程（含本项目）的相关岗位。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "person",
          "kind": "requirement",
          "title": "安装调试工程师配置与限制",
          "group": "安装调试工程师",
          "content": {
            "字段": "数量、资格与兼任限制",
            "内容": [
              "安装调试工程师1名，具有制造商出具的安装调试培训证书",
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
              "quote": "配备安装调试工程师1名，具有制造商出具的安装调试培训证书。"
            },
            {
              "block_id": "example-2",
              "quote": "该安装调试工程师最多只能同时担任3项工程（含本项目）的相关岗位。"
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
