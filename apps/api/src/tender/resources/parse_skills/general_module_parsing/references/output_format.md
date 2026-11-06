# 补充发现与跨文件关联 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `补充发现`（table）：`事项`、`分析结论`
- `跨文件关联`（table）：`事项`、`分析结论`

## 事项组织

- 使用补充发现或跨文件关联分类，content 为“事项”“分析结论”，保留适用条件和例外。
- 明确修订引用双方；无明确优先关系的矛盾保留双方并登记 conflict 缺口。
- kind=relation 的端点先保存，使用 subject_key/object_key；supersedes 表示 subject 替代 object。
- 转引句只作为继续检索的线索，未找到目标登记缺口，不包装成补充发现。
- 参考建议需同时有本项目相关要求和关联参考资料依据；不得把历史项目要求写成本项目义务。

## 提交方式

子主题具备可靠依据即可调用 submit_analysis，每批 records 最多三条完整事项，topic_updates 同时关联主题、范围、已核对 checks、证据和事项 key。通过校验后实时展示。
记录 key 稳定，纠正同一事项沿用原 key。content 仅填当前分类的中文键，缺少依据的键省略；多条并列要求用字符串数组。
同一事项可以综合多处原文，citations 分别填写已读 block_id 和连续 quote；不要填写服务端生成的页码、坐标、text 或 evidence_ids。
不能用无依据的“未提及/无”占位。通过校验的事项立即保存；全部主题处理后自动独立查漏，final=true 只请求检查完成条件，未决事项留在 topic_updates 与 gaps。
通用 scope、conditions、materials、scoring 等结构以运行时工具 schema 为准，填写后同样接受原文校验。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例展示 content 及引用结构；实际增量提交还须提供 topic_updates，登记子主题核对项、证据、事项 key 和未决待办。
正文由 content 承载，citations 独立溯源；各批独立校验，全部子主题处理后自动查漏，无需另发空提交。

## 主文件与补遗的明确修订

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "主文件第8条：东区标段须在2026年11月2日交付。"
    },
    {
      "id": "example-2",
      "text": "补遗第1号：主文件第8条东区标段交付时间改为2026年11月9日，其余要求不变。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "original-date",
          "kind": "requirement",
          "title": "东区原交付时间",
          "group": "跨文件关联",
          "content": {
            "事项": "原交付安排",
            "分析结论": "主文件第8条要求东区标段在2026年11月2日交付。"
          },
          "scope": {
            "kind": "lots",
            "lot_refs": [
              "东区标段"
            ]
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "主文件第8条：东区标段须在2026年11月2日交付。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "revised-date",
          "kind": "requirement",
          "title": "东区修订交付时间",
          "group": "跨文件关联",
          "content": {
            "事项": "补遗修订",
            "分析结论": "补遗第1号将东区标段交付时间改为2026年11月9日，其余要求不变。"
          },
          "scope": {
            "kind": "lots",
            "lot_refs": [
              "东区标段"
            ]
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "主文件第8条：东区标段须在2026年11月2日交付。"
            },
            {
              "block_id": "example-2",
              "quote": "补遗第1号：主文件第8条东区标段交付时间改为2026年11月9日，其余要求不变。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "revision",
          "kind": "relation",
          "title": "交付时间替代关系",
          "group": "跨文件关联",
          "content": {
            "事项": "修订关系",
            "分析结论": "补遗第1号的交付时间替代主文件第8条东区标段的原交付时间。"
          },
          "scope": {
            "kind": "lots",
            "lot_refs": [
              "东区标段"
            ]
          },
          "predicate": "supersedes",
          "subject_key": "revised-date",
          "object_key": "original-date",
          "citations": [
            {
              "block_id": "example-1",
              "quote": "主文件第8条：东区标段须在2026年11月2日交付。"
            },
            {
              "block_id": "example-2",
              "quote": "补遗第1号：主文件第8条东区标段交付时间改为2026年11月9日，其余要求不变。"
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
