# 报价要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个JSON容器的blocks表示已读原文，submissions只演示草稿保存参数；完整自查、修订和最终提交方法见公共流程Skill。
样例展示完整业务事项与block_ids；修改沿用回执id和当前version，最终提交使用实际返回的草稿ID。
正文由 content 承载，block_ids 指向实际已读原文；标题、身份与定位由后端补齐，整项审查通过后展示。条件、材料、评分和例外完整写入 content，不重复提交结构化属性。

## 同名限价按标段分开

以下只展示局部草稿。先保存，再由本Agent自查和修正；单独最终提交时明确选择已自查的草稿ID。unknown不能作为公共或指定标段要求使用。

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "东区标段最高投标限价100万元（含税），超过限价否决投标。"
    },
    {
      "id": "example-2",
      "text": "西区标段最高投标限价80万元（含税）。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "kind": "requirement",
          "group": "投标限价",
          "content": {
            "限价类型": "最高投标限价",
            "金额或范围（原文）": "100万元（含税）",
            "超限处理": "否决投标"
          },
          "scope": {
            "kind": "lots",
            "lot_refs": [
              "东区标段"
            ]
          },
          "block_ids": [
            "example-1"
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "kind": "requirement",
          "group": "投标限价",
          "content": {
            "限价类型": "最高投标限价",
            "金额或范围（原文）": "80万元（含税）"
          },
          "scope": {
            "kind": "lots",
            "lot_refs": [
              "西区标段"
            ]
          },
          "block_ids": [
            "example-2"
          ]
        }
      ],
      "final": false
    }
  ]
}
```
