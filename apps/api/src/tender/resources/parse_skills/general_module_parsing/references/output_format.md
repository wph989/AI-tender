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

研究结束后统一综合。content 只使用本专题声明的中文键，citations 使用已读原文；业务范围、条件、材料和评分属性同样需要依据。
工作ID、分批及审查规则以运行时工具为准，样例中的 work_ids 须换为实际返回的ID。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是研究结束、进入 synthesis 后按顺序调用 submit_analysis 的参数，不是检索期间逐项输出。
样例展示综合阶段的 content 与引用结构；研究阶段登记轻量事实线索和具体问题；work_ids 使用程序返回的工作ID。
正文由 content 承载，citations 独立溯源；综合各批暂存，最后一批 final=true 后合并审查支持性与完整性并统一展示，无需另发空提交。

## 主文件与补遗的明确修订

以下仅展示综合阶段的局部输出结构。实际运行先完成本专题全部可处理核对项，明确受阻原因和适用范围，再统一输出；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

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
          ],
          "work_ids": [
            "w1",
            "w2"
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
          ],
          "work_ids": [
            "w1",
            "w2"
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
          ],
          "work_ids": [
            "w1",
            "w2"
          ]
        }
      ],
      "final": true
    }
  ]
}
```
