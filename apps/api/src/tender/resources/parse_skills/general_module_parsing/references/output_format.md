# 补充分析输出协议

完成时调用 submit_analysis，参数包含 items、relations 和说明检索范围及缺口的 research_summary。
条目字段为 kind（fact/judgment/suggestion/conflict/insufficient）、title、text、presentation（paragraph/list/table）、cells（可选文字键值）和 citations。
每条独立引用：{"block_id":"实际读到的块ID","quote":"该块内连续原文"}。
跨文件差异和冲突引用双方，前提不足的建议不能作为确定要求。
表格每行、列表每项各是一个 item，不把整表放进 Markdown 字符串。
关系字段为 subject、predicate、object、scope、condition、citations。保留真实标段、主体和且/或/例外条件。
每条关系须有直接证据；无关系返回 relations=[]，无补充发现返回 items=[]。
