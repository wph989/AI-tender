# 投标文件格式 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `*`（tree）：`编制要求`

## 事项组织

- 每个节点使用 kind=format_node、node_type=group/section；title 保留原文材料名称，content 使用“编制要求”数组。
- group 是展示分类；node_type=group 才表示逻辑组织容器，两者不能混同。
- parent_key 指向已提交父节点，先父后子；保留原文明示的全部层级，不限制三级。
- 独立材料无已证实父级时作为根 section；同名、编号或相邻位置不能单独证明父子关系。
- 每个节点独立引用材料及归属依据；不能用目录导航代替实际编制要求。

## 提交方式

研究期间可暂存完整事项，已有草稿直接复用。content 只使用本专题声明的中文键，block_ids 只填写已读原文ID，后端生成原文定位；范围、条件、材料和评分同样需要依据。
保存草稿后由本Agent核对原文，记录自查结论；修改使用工具返回的id和version。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个JSON容器的blocks表示已读原文，submissions只演示草稿保存参数；完整自查、修订和最终提交方法见公共流程Skill。
样例展示完整业务事项与block_ids；修改沿用回执id和当前version，最终提交使用实际返回的草稿ID。
正文由 content 承载，block_ids 指向实际已读原文；标题、身份与定位由后端补齐，整项审查通过后展示。条件、材料、评分和例外完整写入 content，不重复提交结构化属性。

## 保留四层目录与独立附件

以下只展示局部草稿。先保存，再由本Agent自查和修正；单独最终提交时明确选择已自查的草稿ID。unknown不能作为公共或指定标段要求使用。

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "投标文件的技术部分包括实施方案。实施方案包括迁移方案，迁移方案下设回退措施。"
    },
    {
      "id": "example-2",
      "text": "另须独立提交授权委托书，不归入技术部分。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "technical",
          "kind": "format_node",
          "title": "技术部分",
          "group": "技术部分",
          "content": {
            "编制要求": [
              "包括实施方案"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "node_type": "group",
          "block_ids": [
            "example-1"
          ]
        },
        {
          "key": "implementation",
          "kind": "format_node",
          "title": "实施方案",
          "group": "技术部分",
          "content": {
            "编制要求": [
              "包括迁移方案"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "node_type": "section",
          "parent_key": "technical",
          "block_ids": [
            "example-1"
          ]
        },
        {
          "key": "migration",
          "kind": "format_node",
          "title": "迁移方案",
          "group": "技术部分",
          "content": {
            "编制要求": [
              "下设回退措施"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "node_type": "section",
          "parent_key": "implementation",
          "block_ids": [
            "example-1"
          ]
        },
        {
          "kind": "format_node",
          "title": "回退措施",
          "group": "技术部分",
          "content": {
            "编制要求": [
              "编制迁移方案下的回退措施"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "node_type": "section",
          "parent_key": "migration",
          "block_ids": [
            "example-1"
          ]
        },
        {
          "kind": "format_node",
          "title": "授权委托书",
          "group": "独立材料",
          "content": {
            "编制要求": [
              "独立提交，不归入技术部分"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "node_type": "section",
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
