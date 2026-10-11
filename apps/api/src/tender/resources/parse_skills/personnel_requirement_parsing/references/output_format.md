# personnel_requirement_parsing 业务数据输出

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
- 解析结论按具体岗位/职能分类输出，禁止用“持证人员”“相关人员”等模糊属性作为分类名。
- 只输出针对具体人员个体或岗位的数量、证书、学历、职称、年限、评分/加分和证明材料要求。


## [岗位职能名称]
- 字段 / 内容
- 人员数量
- 评分/加分规则
- 证书/材料要求
- 工作经验
- 专业背景
- 技能要求
- 备注
- 包含岗位

- 每个岗位使用明确的岗位职能标题；多个条款涉及同一岗位时合并到同一章节。
- 每个岗位至少包含人员数量、个人证书/资格要求、评分/加分规则三者之一，否则不输出该岗位。
- 企业资质、企业业绩、团队整体方案评价不属于人员要求，直接排除。
- 备注只放总人数、兼任限制等与该岗位直接相关的限制；兼任限制优先保留完整原句，禁止改写数量上限和包含边界；包含岗位列出归入该职能分类的原文岗位名称。
- 例如原文“最多只能同时担任3项工程（含本项目）的总监理工程师”必须保留“最多3项”和“含本项目”的边界，不得改写为“不得同时兼任3个工程（含）以上”。
