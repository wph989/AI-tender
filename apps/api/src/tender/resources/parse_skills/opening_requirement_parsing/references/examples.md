# 开标要求 JSON 示例

以下是模拟原文块与工具提交样例，名称、数值及证据ID仅用于说明，不能用于实际项目。
每个 JSON 容器的 blocks 表示检索/补读已返回的原文；submissions 是研究结束、进入 synthesis 后按顺序调用 submit_analysis 的参数，不是检索期间逐项输出。
样例展示综合阶段的 content 与引用结构；研究阶段登记轻量事实线索和具体问题；work_ids 使用程序返回的工作ID。
正文由 content 承载，citations 独立溯源；综合各批暂存，最后一批 final=true 后合并审查支持性与完整性并统一展示，无需另发空提交。

## 远程开标与解密时限

以下仅展示综合阶段的局部输出结构。实际运行先完成本专题全部可处理核对项，明确受阻原因和适用范围，再统一输出；final=true 声明本轮综合已提交完毕，运行时仍核验覆盖与查漏结果。unknown 不能作为公共或指定标段要求使用。

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
              "block_id": "example-1"
            },
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
