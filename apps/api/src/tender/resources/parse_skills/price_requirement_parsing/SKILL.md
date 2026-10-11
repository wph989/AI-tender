---
name: price-requirement-parsing
description: "价格要求解析专家。从招标文件中提取报价规则、价格条款、调价公式、最高限价。当需要解析报价相关信息时使用本 Skill。"
---

# 价格要求解析 Skill

## 适用场景
- 触发：项目控制器启动当前专题价格要求解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：submit_analysis 原生工具提交的字段（field/group/sort_order/values/note），每个值附已读取原文块的引用。

## 领域知识

价格要求只回答“招标方如何约束本次投标报价”，主要包括：

1. **报价方式**：固定总价、单价合同、费率报价等
2. **最高限价/预算金额**：投标报价不得超过的上限
3. **报价包含内容**：税费、运费、安装费等是否包含
4. **折扣/下浮**：下浮率、折扣率、P 值范围
5. **超限处理**：超过限价或低于成本价的处理规则

每个金额、比例或税率都必须先判断主语：只有招标方设定的投标限价/预算、报价内部构成、下浮范围和超限处理可以提取。企业注册资本、营收、纳税、历史业绩金额，代理服务费、保证金、履约金、法规罚款、模板占位金额、历史成交价、市场参考价及纯价格评分公式必须排除。

## 识别规则

关键词种子（可扩展，不限于）："报价"、"价格"、"最高限价"、"预算金额"、"投标报价"、"费率"、"单价"、"总价"

## 执行流程

1. **精确检索**：使用 `search_document` 搜索"报价""价格"等章节
2. **扩展上下文**：根据命中位置使用 `read_document` 读取报价表和相邻条款
3. **主语判定**：逐个判断候选数值是否约束本次投标报价
4. **逐列过滤**：混排表格只保留标段标识和限价、预算、报价构成、下浮相关列
5. **互斥归类**：金额限价、报价内部构成、折扣/下浮分别归表，不重复
6. **输出结果**：按本 Skill 的输出协议调用 submit_analysis；没有依据的条目省略。

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

## 参考文件（按标类型加载）
根据任务 category 及 lots 中的类别覆盖，加载对应子目录下的参考文件：
- `references/output_format.md`：本 Skill 专属输出模板和格式约束
- `references/<type_dir>/extraction_rules.md`：含税/不含税处理、报价方式分类、最高限价提取、严禁行为、自检清单
- `references/<type_dir>/examples.md`：完整报价要求提取样例
- category 取值：service（服务类）、engineering（工程类）、goods（货物类）；type_dir 使用相同值
- 类别由用户选择并由运行时提供；不能自行默认成服务类，标段有覆盖类别时同时参考对应规则

## 工具与证据

- 运行时先调用 `load_skill` 加载本文件及 `references/output_format.md`，无需重复读取；其余细则按需读取。
- `list_documents()`：返回授权资料的 id 和说明文本；资料 id 可填入检索的 source_id。
- `search_document(query, source_id?)`：检索本项目；`search_knowledge(query, source_id?)`：检索关联参考库。
- 检索证据只含 `id`、`text`。把证据 id 填入引用的 `block_id`；quote 必须是该 text 的连续原文。
- `read_document(block_id, before=2, after=2)`：围绕已读证据补读；before/after 合计最多11，均为0时只补读本块。不得猜测ID或扫描全文。
- `read_file(file_path)`：只读 `/skills/price-requirement-parsing/references/` 下当前任务需要的细则，或压缩历史；不能读取招标文件磁盘路径。
- `submit_analysis`：结构化提交，普通业务记录每批最多3条，格式每批最多6节点；`final=false` 暂存，明确核对完成后 `final=true`。

## 证据选择与纠错

1. 先按本专题的问题检索，再核对主体、标段、表头、脚注、条件和补充文件。上下文不足时按证据ID补读；不能用关键词命中代替事实判断。
2. 同一事实在相同适用范围内重复出现，选最直接、完整的一处。跨块条件、不同标段、修订前后和未决冲突所需的证据分别保留；检索相似度和自报置信分数不作为可信度。
3. 引用只提交ID和连续摘录，不生成页码、坐标、文件路径或来源元数据。服务端校验实际读取记录、资料权限和版本后，按保留的ID补齐定位。
4. 工具返回结构化错误时，按 `message` 和 `remaining_attempts` 修正；只补交未通过部分，不重交已保存事实。更换字段名或重复相同请求不会获得新额度。
5. 收到收尾提示就停止扩展检索，提交已有可靠结果并在 `research_summary` 记录缺口；不得声称缺口是文件未约定。不得再委派子Agent，服务故障与重试由运行时处理。

## 注意
- 金额数字必须**精确提取**
- 注意区分"含税价"和"不含税价"
- 多标段同类限价分别输出条目，写明适用标段并逐条引用；原文明确共同适用时可合并并写明范围
- 模板占位符、“详见附件”“待定”等无实质数值内容不得输出
