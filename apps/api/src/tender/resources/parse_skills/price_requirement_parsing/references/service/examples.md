# 服务报价事项 JSON 示例

示例为模拟资料，展示同一分类下独立事项的拆分，不代表任何实际项目。
运行时已完成主题检索；以下 blocks 是已读原文，submissions 分别作为 submit_analysis 的参数。

报价包含项与触发后另付的费用分别提交。计税附件缺失仅形成缺口，不能抹去已经明确的包含要求，也不能补出默认计税方法。

以下仅展示综合阶段的局部输出结构。实际运行先完成本专题全部可处理核对项，明确受阻原因和适用范围，再统一输出；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

```json
{
  "blocks": [
    {
      "id": "example-1",
      "text": "A标段报价包括驻场人员工资、日常交通费和国家规定的税金。"
    },
    {
      "id": "example-2",
      "text": "A标段因采购人书面要求增加异地踏勘的，新增交通和住宿费用由采购人另行支付。"
    },
    {
      "id": "example-3",
      "text": "A标段税金计算方法详见附件2《费用测算表》。"
    }
  ],
  "submissions": [
    {
      "records": [
        {
          "key": "included-service-costs",
          "kind": "requirement",
          "title": "驻场服务报价包含的费用",
          "group": "价格构成",
          "content": {
            "费用项": [
              "驻场人员工资",
              "日常交通费",
              "国家规定的税金"
            ],
            "计算方式或比例（原文）": "包括在A标段报价中"
          },
          "scope": {
            "kind": "lots",
            "lot_refs": [
              "A标段"
            ]
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
          "key": "extra-site-visit",
          "kind": "requirement",
          "title": "书面要求增加异地踏勘的另付费用",
          "group": "价格构成",
          "content": {
            "费用项": "新增交通和住宿费用",
            "计算方式或比例（原文）": "因采购人书面要求增加异地踏勘的，由采购人另行支付"
          },
          "scope": {
            "kind": "lots",
            "lot_refs": [
              "A标段"
            ]
          },
          "conditions": {
            "expression": "因采购人书面要求增加异地踏勘"
          },
          "citations": [
            {
              "block_id": "example-2"
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

同一包含要求跨多个原文块时，可以在一条记录保留多个 citations；独立的另付条件不应因属于同一费用分类而被并入。此示例没有税率依据，任何具体税率都不能进入输出。
