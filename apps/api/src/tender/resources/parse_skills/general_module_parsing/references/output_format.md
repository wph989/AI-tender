# 补充分析输出协议

## 输出协议

完成时调用 submit_analysis，参数包含 fields、relations 和说明检索范围及缺口的 research_summary。
每个字段包含 field、group、sort_order、values、note；values 中每个值包含 value 与 citations，证据逐值绑定。
每个值形如 {"value":"解析值原文表述","citations":[{"block_id":"实际读到的块ID","quote":"该块内的连续原文"}]}；group 可留空，sort_order 为非负整数展示顺序，note 可留空。
同一字段出现多个值时每个值各自成条并带自己的引用，不合并成一段文字；跨文件差异和冲突引用双方，前提不足的建议不能作为确定要求。
没有相关依据返回 空 fields/relations，并填写说明检索缺口的 research_summary，不补造“未提及”记录。
关系字段为 subject、predicate、object、scope、condition、citations。保留真实标段、主体和且/或/例外条件。
每条关系须有直接证据；无关系返回 relations=[]，无补充发现返回 fields=[]。