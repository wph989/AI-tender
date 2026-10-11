# scoring_standard_parsing 业务数据输出

## 输出协议

通过原生工具 `submit_analysis(records, coverage, gaps, research_summary, final=false)` 分批提交。
普通专题每批最多3条业务记录，格式专题最多6条。最后明确 `final=true`。
记录字段由工具 schema 定义，`key` 是本模块内稳定短标识，同一记录纠正时沿用。
`kind` 为 fact / requirement / lot / format_node / relation；`title` 为名称，`text` 直接写完整事实或要求。
`scope.kind` 必须为 common / lots / unknown；lots 的 `lot_refs` 填原文标段编号或名称。
不能因未写标段就认定所有标段适用。公共适用性同样需要原文或上下文依据。
`citations` 使用 [{"block_id":"实际读取ID","quote":"连续原文"}]，覆盖文本和全部业务属性。
`conditions` 保留 expression、logic(all/any/mixed/text)、terms(subject/operator/value/unit/time_basis)、exceptions。
日期起算点和类似项目定义不明时保留未知，不用常识填值。`materials` 列出 name 与 requirement。
`scoring` 保留 max_points、formula、tiers(condition/points)、deductions；评分项内部的全部档次属于同一项。
`structuring` 为 complete 或 partial，无法可靠拆解时用 partial 并保留完整 text。
仅项目概况模块提交 kind=lot，保留 code、title、aliases；其他模块直接填写标段原文指向。
格式节点用 kind=format_node、node_type(group/section)、parent_key；先父后子，完整保留原文层级。
修订/冲突用 kind=relation，predicate 为 supersedes/conflicts/requires/contains；端点先提交再填 subject_key/object_key。
supersedes 表示 subject 替代 object，双方证据和适用范围均须明确，不能按上传时间判断。

`references/coverage.json` 是运行时已加载的主题清单。每个主题登记覆盖状态：
extracted（关联 record_keys）、searched_not_found（只表示本次没找到）、pending、not_applicable（必须有引用）。
一个主题可按不同标段分别登记。未核对主题不会被当成完成，不为填满清单编造要求。
缺口用 gaps 提交 key/topic/scope/code/detail；code 为 unresolved_reference、unknown_condition、scope_unknown、
conflict、missing_source、incomplete_structure、search_exhausted。检索总结不能替代这些结构化状态。
转引只是线索，须检索实际条款并完整写进 text；预算耗尽或目标缺失时记录缺口。
缺口随 final=false 按 key 累积；final=true 须提交全部剩余 gaps，校验通过后替换旧清单。
全部缺口已解决时最终提交 gaps=[]；最终校验失败仍保留已有缺口。
来源、页码和坐标由服务端按校验保留的证据ID补齐，模型不生成定位。

## 内容检查清单
以下主题和字段用于检查覆盖，不要求逐项填满；只有原文明示且有引用的内容才输出。
- 解析结论只输出评标方法、总分构成、评分细则、价格分计算和加扣分规则。


## 评分总则
- 总则要素 / 原文内容
- 评标方法
- 总体规则/计算公式

## 总分构成
- 组成部分 / 分值
- 总分

## [商务/技术/综合]评分标准
- 核对各部分总分，原文没有明确分值时不自行填入。

- 序号 / 评分项 / 满分分值 / 评分标准（原文摘录）

## 价格评分标准
- 核对价格评分总分，保留原文分值。

- 序号 / 评分项 / 满分分值 / 评分标准（原文摘录）

- 根据原文结构组织评分细则；原文区分商务/技术时分别输出，合并时归入综合评分标准主题。
- 价格评分只保留一个总分入口，基准价、公式及所有得分情形均写入同一评分项，禁止拆分价格评分。
- 评分细则应尽量保留原文，不得删除有分值的评分要求。
- 评分标准必须直接呈现各档条件与得分、扣分规则或公式；“详见某文件/章节/附件”只作继续检索的线索，不能作为解析值。独立的评标方法、总分构成按其真实范围输出，不冒充评分细则。
- 若目标正文不在授权资料中或追踪后仍无法取得，仅在 gaps 和 coverage 记录目标与缺口；已有的实质规则可保留，不能用转引句填满清单。
- 同一评分项内的总体说明、各评分档次、条件分支和备注用完整句子或 JSON 字符串换行保留逻辑边界，不使用 HTML 分隔符。
- 评分档次是上级评分项的规则，不得误当成新的评分项；保留影响得分的扣分规则，否决投标的条款交由否决模块提取。
