# 开标要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是按顺序调用 submit_analysis 的参数；研究期可用 final=false 暂存，已有草稿在 complete_research 后直接审查。
样例展示完整业务事项与 block_ids；work_ids 使用程序返回的工作ID，修改沿用回执 id。
正文由 content 承载，block_ids 指向实际已读原文；标题、身份与定位由后端补齐，整项审查通过后展示。条件、材料、评分和例外完整写入 content，不重复提交结构化属性。

## 远程开标与解密时限

以下展示局部业务事项。研究期间逐批暂存，明确受阻原因和适用范围；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

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
          "kind": "requirement",
          "group": "开标时间",
          "content": {
            "时间要素": "开标时间",
            "具体要求": "2026年11月2日9时30分"
          },
          "scope": {
            "kind": "unknown",
            "lot_refs": []
          },
          "work_ids": [
            "w1",
            "w2"
          ],
          "block_ids": [
            "example-1"
          ]
        }
      ],
      "final": false
    },
    {
      "records": [
        {
          "kind": "requirement",
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
