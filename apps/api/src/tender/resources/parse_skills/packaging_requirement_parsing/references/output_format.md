# 封装与递交 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `投标文件组成`（table）：`文件部分`、`具体要求`
- `文件格式要求`（table）：`格式要求`、`具体描述`
- `签字盖章要求`（table）：`签字盖章要求`、`具体描述`
- `密封要求`（table）：`密封要求`、`具体描述`
- `份数要求`（table）：`份数要求`、`具体描述`
- `纸质版要求`（table）：`纸质要求`、`具体描述`
- `电子版要求`（table）：`电子要求`、`具体描述`

## 事项组织

- 每条保存一个制作或递交事项，保留份数、签章主体、密封、标记及电子介质要求。
- 逻辑标类型不等于物理分册；不能自行推断独立装订或密封。
- 格式要求指文件制作方式，内部章节树由格式专题输出；盲标例外与限制完整保留。

## 提交方式

研究结束后统一综合。content 只使用本专题声明的中文键，citations 只填写已读block_id，由程序补齐原文定位，无需quote；业务范围、条件、材料和评分属性同样需要依据。
工作ID、分批及审查规则以运行时工具为准，样例中的 work_ids 须换为实际返回的ID。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是研究结束、进入 synthesis 后按顺序调用 submit_analysis 的参数，不是检索期间逐项输出。
样例展示综合阶段的 content 与引用结构；研究阶段登记轻量事实线索和具体问题；work_ids 使用程序返回的工作ID。
正文由 content 承载，citations 独立溯源；综合各批暂存，最后一批 final=true 后合并审查支持性与完整性并统一展示，无需另发空提交。

## 份数与盲标限制分别记录

以下仅展示综合阶段的局部输出结构。实际运行先完成本专题全部可处理核对项，明确受阻原因和适用范围，再统一输出；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "纸质投标文件正本1份、副本2份。"
    },
    {
      "id": "example-2",
      "text": "技术文件实行盲标，正文不得出现投标人名称；封面按指定格式填写。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "copies",
          "kind": "requirement",
          "title": "纸质份数",
          "group": "份数要求",
          "content": {
            "份数要求": "正副本",
            "具体描述": "正本1份、副本2份"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1"
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
          "key": "anonymous",
          "kind": "requirement",
          "title": "盲标正文与封面",
          "group": "文件格式要求",
          "content": {
            "格式要求": "盲标",
            "具体描述": [
              "技术文件正文不得出现投标人名称",
              "封面按指定格式填写"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-2"
            }
          ],
          "work_ids": [
            "w5",
            "w6"
          ]
        }
      ],
      "final": true
    }
  ]
}
```
