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

完成本专题检索和 complete_research 后调用 submit_analysis，每次 records 最多三条完整事项，final=false。
记录 key 稳定，纠正同一事项沿用原 key。content 仅填当前分类的中文键，缺少依据的键省略；多条并列要求用字符串数组。
同一事项可以综合多处原文，citations 分别填写已读 block_id 和连续 quote；不要填写服务端生成的页码、坐标、text 或 evidence_ids。
不能用无依据的“未提及/无”占位。最后一批可携带 records、final=true，通过校验即收尾；仅确认收尾时可用 records=[]，未决事项留在 coverage/gaps。
通用 scope、conditions、materials、scoring 等结构以运行时工具 schema 为准，填写后同样接受原文校验。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一批可携带 records、final=true，通过校验即收尾，无需另发空提交。

## 保留四层目录与独立附件

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
          "citations": [
            {
              "block_id": "example-1",
              "quote": "投标文件的技术部分包括实施方案。实施方案包括迁移方案，迁移方案下设回退措施。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
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
          "citations": [
            {
              "block_id": "example-1",
              "quote": "投标文件的技术部分包括实施方案。实施方案包括迁移方案，迁移方案下设回退措施。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
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
          "citations": [
            {
              "block_id": "example-1",
              "quote": "投标文件的技术部分包括实施方案。实施方案包括迁移方案，迁移方案下设回退措施。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "rollback",
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
          "citations": [
            {
              "block_id": "example-1",
              "quote": "投标文件的技术部分包括实施方案。实施方案包括迁移方案，迁移方案下设回退措施。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "authorization",
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
          "citations": [
            {
              "block_id": "example-2",
              "quote": "另须独立提交授权委托书，不归入技术部分。"
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
