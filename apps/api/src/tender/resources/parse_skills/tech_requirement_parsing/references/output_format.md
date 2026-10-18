# 技术要求 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `项目背景`（list）：`背景`
- `技术方案要求`（list）：`章节来源`、`要求摘要`、`关键要求`

## 事项组织

- 仅有项目背景和技术方案要求两类。背景需有原文事实，不能从行业常识补写。
- 命名或编号的独立任务分别生成记录；一般技术要求可按主题归并。
- 技术方案要求的“要求摘要”概括任务，“关键要求”使用字符串数组保留必要约束和实施要求。
- “章节来源”仅在对应标题或条号已读取时填写；纯参数清单不形成独立条目。

## 提交方式

完成本专题检索和 complete_research 后，逐条调用 submit_analysis，每次 records 最多一条完整事项，final=false。
记录 key 稳定，纠正同一事项沿用原 key。content 仅填当前分类的中文键，缺少依据的键省略；多条并列要求用字符串数组。
同一事项可以综合多处原文，citations 分别填写已读 block_id 和连续 quote；不要填写服务端生成的页码、坐标、text 或 evidence_ids。
不能用无依据的“未提及/无”占位。所有事项完成后以 records=[]、final=true 收尾，未决事项留在 coverage/gaps。
通用 scope、conditions、materials、scoring 等结构以运行时工具 schema 为准，填写后同样接受原文校验。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一次空 records、final=true 明确收尾。

## 独立任务与纯参数边界

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "技术方案要求：任务一为数据迁移专项任务，应说明数据迁移、校核及回退方法。任务二为运行保障任务，应说明故障响应与恢复方法。"
    },
    {
      "id": "example-2",
      "text": "产品参数表：机柜宽度600mm，重量100kg。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "task-one",
          "kind": "requirement",
          "title": "数据迁移专项任务",
          "group": "技术方案要求",
          "content": {
            "要求摘要": "编写数据迁移专项任务方案",
            "关键要求": [
              "说明数据迁移、校核及回退方法"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "技术方案要求：任务一为数据迁移专项任务，应说明数据迁移、校核及回退方法。任务二为运行保障任务，应说明故障响应与恢复方法。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "task-two",
          "kind": "requirement",
          "title": "运行保障任务",
          "group": "技术方案要求",
          "content": {
            "要求摘要": "编写运行保障方案",
            "关键要求": [
              "说明故障响应与恢复方法"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "技术方案要求：任务一为数据迁移专项任务，应说明数据迁移、校核及回退方法。任务二为运行保障任务，应说明故障响应与恢复方法。"
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
