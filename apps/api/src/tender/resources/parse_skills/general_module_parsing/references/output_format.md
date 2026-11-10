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

研究期间可暂存完整事项，已有草稿直接复用。content 只使用本专题声明的中文键，block_ids 只填写已读原文ID，后端生成原文定位；范围、条件、材料和评分同样需要依据。
工作ID、分批及审查规则以运行时工具为准，样例中的 work_ids 须换为实际返回的ID。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数；研究期可用 final=false 暂存，已有草稿在 complete_research 后直接审查。
样例展示完整业务事项与 block_ids；work_ids 使用程序返回的工作ID，修改沿用回执 id。
正文由 content 承载，block_ids 指向实际已读原文；标题、身份与定位由后端补齐，整项审查通过后展示。条件、材料、评分和例外完整写入 content，不重复提交结构化属性。

## 主文件与补遗的明确修订

以下展示局部业务事项。研究期间逐批暂存，明确受阻原因和适用范围；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

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
          "work_ids": [
            "w1",
            "w2"
          ],
          "block_ids": [
            "example-1"
          ]
        },
        {
          "key": "revised-date",
          "kind": "requirement",
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
          "work_ids": [
            "w1",
            "w2"
          ],
          "block_ids": [
            "example-1",
            "example-2"
          ]
        },
        {
          "kind": "relation",
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
          "work_ids": [
            "w1",
            "w2"
          ],
          "block_ids": [
            "example-1",
            "example-2"
          ]
        }
      ],
      "final": true
    }
  ]
}
```
