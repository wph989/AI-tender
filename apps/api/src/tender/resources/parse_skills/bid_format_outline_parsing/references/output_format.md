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
工作ID、分批及审查规则以运行时工具为准，样例中的 work_ids 须换为实际返回的ID。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数；研究期可用 final=false 暂存，已有草稿在 complete_research 后直接审查。
样例展示完整业务事项与 block_ids；work_ids 使用程序返回的工作ID，修改沿用回执 id。
正文由 content 承载，block_ids 指向实际已读原文；标题、身份与定位由后端补齐，整项审查通过后展示。条件、材料、评分和例外完整写入 content，不重复提交结构化属性。

## 保留四层目录与独立附件

以下展示局部业务事项。研究期间逐批暂存，明确受阻原因和适用范围；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

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
          "work_ids": [
            "w1",
            "w2"
          ],
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
          "work_ids": [
            "w1",
            "w2"
          ],
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
          "work_ids": [
            "w1",
            "w2"
          ],
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
          "work_ids": [
            "w1",
            "w2"
          ],
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
          "work_ids": [
            "w3",
            "w4"
          ],
          "block_ids": [
            "example-2"
          ]
        }
      ],
      "final": true
    }
  ]
}
```
