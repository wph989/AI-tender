# 商务要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个JSON容器的blocks表示已读原文，submissions只演示草稿保存参数；完整自查、修订和最终提交方法见公共流程Skill。
样例展示完整业务事项与block_ids；修改沿用回执id和当前version，最终提交使用实际返回的草稿ID。
正文由 content 承载，block_ids 指向实际已读原文；标题、身份与定位由后端补齐，整项审查通过后展示。条件、材料、评分和例外完整写入 content，不重复提交结构化属性。

## 跨块付款条件归并

以下只展示局部草稿。先保存，再由本Agent自查和修正；单独最终提交时明确选择已自查的草稿ID。unknown不能作为公共或指定标段要求使用。

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "阶段服务成果验收合格后支付合同金额的30%。"
    },
    {
      "id": "example-2",
      "text": "上述付款须先取得合规发票，收到发票后15日内支付。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "kind": "requirement",
          "group": "付款条件",
          "content": {
            "付款要素": "验收款",
            "具体要求": [
              "阶段服务成果验收合格后支付合同金额的30%",
              "取得合规发票后15日内支付"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "block_ids": [
            "example-1",
            "example-2"
          ]
        }
      ],
      "final": false
    }
  ]
}
```
