# project_basic_info_parsing 业务数据输出

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
- 解析结论只输出项目基本信息相关内容，禁止混入评分、废标、技术方案等其他模块。
- 无明确来源的字段省略，不得用其他主体信息互相填充。


## 甲方信息
- 字段 / 内容
- 公司名称
- 公司地址
- 公司联系人
- 公司联系电话
- 公司电子邮箱
- 公司开户银行
- 公司银行账号

## 代理信息
- 字段 / 内容
- 公司名称
- 公司地址
- 联系人
- 联系电话
- 公司电子邮箱
- 公司开户银行
- 公司银行账号

## 项目基本信息
- 字段 / 内容
- 项目名称
- 项目编号
- 项目地点
- 项目规模
- 投标截止日期
- 服务期限
- 招标范围
- 标段划分
- 中标份额
- 最高投标限价
- 资金来源
- 资金落实情况

## 分标信息
- 字段 / 内容
- 分标名称
- 分标编号
- 包名称
- 包号
- 分标资质要求
- 分标限额标准
- 分标拟定中标人数量
- 分标项目负责人资质

- 甲方信息、代理信息、项目基本信息之间禁止互相填充。
- 分标信息仅当原文明确出现标段/包明细时输出；没有分标时省略相关条目。
- 不同分标的字段分别输出解析值，在 text 中写明所属分标并独立引用，禁止写“同上”“详见分标信息”替代具体内容。
- 只保留有明确内容的字段；不得输出示例占位符或空的解析值。
