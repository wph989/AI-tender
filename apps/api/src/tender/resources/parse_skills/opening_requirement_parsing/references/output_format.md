# 开标要求 JSON 输出

## 分类与内容键

`references/output_schema.json` 是冻结的机器声明，运行时直接用于结构校验和展示。以下分类与键保持项目现有接口：

- `开标时间`（table）：`时间要素`、`具体要求`
- `开标地点`（table）：`地点要素`、`具体要求`
- `开标方式`（table）：`方式类型`、`具体要求`
- `参与人员要求`（table）：`人员类型`、`具体要求`
- `开标程序`（table）：`程序步骤`、`具体要求`
- `公开程度`（table）：`公开要素`、`具体要求`
- `其他开标相关要求`（table）：`要求类型`、`具体内容`

## 事项组织

- 时间、地点保留原文已有精度，不换算相对日期或补齐缺少的地址。
- 远程平台、签到、解密及故障处理归入开标方式；参与者和携带材料按实际事项分类。
- 投标截止与开标时间仅在有依据时关联；变更保留双方引用，不按上传先后裁决。

## 提交方式

完成本专题检索和 complete_research 后调用 submit_analysis，每次 records 最多三条完整事项，final=false。
记录 key 稳定，纠正同一事项沿用原 key。content 仅填当前分类的中文键，缺少依据的键省略；多条并列要求用字符串数组。
同一事项可以综合多处原文，citations 分别填写已读 block_id 和连续 quote；不要填写服务端生成的页码、坐标、text 或 evidence_ids。
不能用无依据的“未提及/无”占位。所有事项完成后以 records=[]、final=true 收尾，未决事项留在 coverage/gaps。
通用 scope、conditions、materials、scoring 等结构以运行时工具 schema 为准，填写后同样接受原文校验。

## JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数，不是一次提交的大数组。
样例假定已按 coverage.json 完成主题检索和转引登记并调用 complete_research；实际仍须记录未决主题。
正文由 content 承载，citations 独立溯源；最后一次空 records、final=true 明确收尾。

## 远程开标与解密时限

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "开标时间为2026年11月2日9时30分，采用不见面开标。"
    },
    {
      "id": "example-2",
      "text": "投标人应登录示例交易平台，在开标后30分钟内完成解密。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "opening-time",
          "kind": "requirement",
          "title": "开标时间",
          "group": "开标时间",
          "content": {
            "时间要素": "开标时间",
            "具体要求": "2026年11月2日9时30分"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "开标时间为2026年11月2日9时30分，采用不见面开标。"
            }
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "key": "remote-opening",
          "kind": "requirement",
          "title": "远程开标及解密",
          "group": "开标方式",
          "content": {
            "方式类型": "不见面开标",
            "具体要求": [
              "登录示例交易平台",
              "在开标后30分钟内完成解密"
            ]
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "citations": [
            {
              "block_id": "example-1",
              "quote": "开标时间为2026年11月2日9时30分，采用不见面开标。"
            },
            {
              "block_id": "example-2",
              "quote": "投标人应登录示例交易平台，在开标后30分钟内完成解密。"
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
