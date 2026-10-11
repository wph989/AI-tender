---
name: tech-requirement-parsing
description: "技术要求解析专家。从招标文件及技术附件中提取项目背景、产品参数、功能性能、标准接口，以及技术方案的任务、架构、实施、服务保障、安全和风险控制要求。"
---

# 技术要求解析 Skill

## 适用场景
- 触发：项目控制器启动当前专题技术要求解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：submit_analysis 原生工具提交的字段（field/group/sort_order/values/note），每个值附已读取原文块的引用。

## 领域知识

本模块为技术响应核对和技术方案编写提供依据，按项目背景、技术要求组织内容。

技术方案要求优先提取招标方明确划分的研究课题、专项任务、子项目或工作包，其次提取总体架构、关键技术、功能模块、接口集成、实施交付、迁移切换、运维保障、安全技术措施和风险控制。独立任务单元必须逐一保留。

商务合同、资格业绩、评分废标、格式应答、人员组织和知识产权程序条款由其他模块处理。
明确的产品参数、功能、性能、标准、接口和检测试验要求均须保留；货物类参数表本身就是技术响应依据，不能因其不是方案叙述而排除。精确保留数值、单位、上下限、否定和星号标记，星号本身不代表否决。

## 识别规则

以下为关键词种子和重点章节名；应根据文档措辞继续扩展同义词：
- "技术方案"、"技术标"、"技术建议书"、"技术规范书"
- "研究课题"、"专项任务"、"工作内容"、"子项目"、"工作包"
- "总体架构"、"关键技术"、"实施方案"、"迁移"、"运维"、"安全方案"
- "技术参数"、"性能指标"、"规格"、"接口"、"检测"、"标准"、"★"、"▲"

## 执行流程

1. **识别项目类型**：判断软件建设、工程、服务、科研或综合项目的核心技术任务
2. **定位核心章节**：检索项目背景、技术方案、技术规范、工作内容和独立任务单元
3. **扩展上下文**：读取命中章节的完整层级及相邻条款
4. **核对技术响应**：保留参数表和方案要求，排除属于其他模块的条款；附表、脚注和参数条件一起阅读
5. **按主题归并**：独立任务逐项保留，一般要求按架构、实施、保障、安全等主题归并
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

## 参考文件
- `references/output_format.md`：本 Skill 专属输出模板和格式约束

## 工具与证据

- 运行时先调用 `load_skill` 加载本文件及 `references/output_format.md`，无需重复读取；其余细则按需读取。
- `list_documents()`：返回授权资料的 id 和说明文本；资料 id 可填入检索的 source_id。
- `search_document(query, source_id?)`：检索本项目；`search_knowledge(query, source_id?)`：检索关联参考库。
- 检索证据只含 `id`、`text`。把证据 id 填入引用的 `block_id`；quote 必须是该 text 的连续原文。
- `read_document(block_id, before=2, after=2)`：围绕已读证据补读；before/after 合计最多11，均为0时只补读本块。不得猜测ID或扫描全文。
- `read_file(file_path)`：只读 `/skills/tech-requirement-parsing/references/` 下当前任务需要的细则，或压缩历史；不能读取招标文件磁盘路径。
- `submit_analysis`：结构化提交，普通业务记录每批最多3条，格式每批最多6节点；`final=false` 暂存，明确核对完成后 `final=true`。

## 证据选择与纠错

1. 先按本专题的问题检索，再核对主体、标段、表头、脚注、条件和补充文件。上下文不足时按证据ID补读；不能用关键词命中代替事实判断。
2. 同一事实在相同适用范围内重复出现，选最直接、完整的一处。跨块条件、不同标段、修订前后和未决冲突所需的证据分别保留；检索相似度和自报置信分数不作为可信度。
3. 引用只提交ID和连续摘录，不生成页码、坐标、文件路径或来源元数据。服务端校验实际读取记录、资料权限和版本后，按保留的ID补齐定位。
4. 工具返回结构化错误时，按 `message` 和 `remaining_attempts` 修正；只补交未通过部分，不重交已保存事实。更换字段名或重复相同请求不会获得新额度。
5. 收到收尾提示就停止扩展检索，提交已有可靠结果并在 `research_summary` 记录缺口；不得声称缺口是文件未约定。不得再委派子Agent，服务故障与重试由运行时处理。

## 注意
- 项目背景有集中原文时优先引用；无集中表述时只能基于已知事实简要归纳
- 一般技术要求允许合并概括，但不得合并或遗漏明确编号、命名的独立任务单元
- 不新增原文未要求的技术路线、产品选型或实施承诺
