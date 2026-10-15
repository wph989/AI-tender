---
name: personnel-requirement-parsing
description: "人员要求解析专家。从招标文件中提取项目人员配置要求、资格、数量、专业。当需要解析项目团队人员相关要求时使用本 Skill。"
---

# 人员要求解析 Skill

## 适用场景
- 触发：项目控制器启动当前专题人员要求解析任务时调用。
- 输入：授权资料清单与按需检索得到的原文块，不预先灌入全文。
- 输出：完成检索后按专题模板综合的 content JSON，逐条附独立的原文溯源引用。

## 领域知识

人员要求是对投标人拟投入本项目的具体岗位人员提出的可操作要求，主要包括：

1. **项目经理/负责人**：资质等级、从业年限、类似项目经验
2. **技术负责人**：职称、专业背景、资格证书
3. **其他关键岗位**：安全员、质量员、施工员等
4. **人员数量**：各岗位的最低人数要求
5. **社保证明**：是否需提供社保缴纳证明
6. **不得兼任**：哪些岗位不得由同一人兼任

候选条款必须满足：主语是具体人员或岗位，且至少包含人数、个人证书/职称/学历、明确年限或针对个人属性的量化评分之一。仅出现岗位名称、团队配置合理等模糊表述不得提取。

必须排除企业资质/认证、企业业绩、企业持有证书数量、报价与商务条款、投标文件格式、中标后抽测，以及人员行为规范、稳定性、管理制度、服务态度和责任承担等软性要求。要求提供社保、劳动合同等证明材料时可以提取，但一般性的依法缴纳社保不得提取。

## 识别规则

关键词种子（可扩展，不限于）："人员"、"项目经理"、"技术负责人"、"配备"、"团队"、"人员配置"

## 执行流程

1. **精确检索**：使用 `search_document` 搜索"人员""项目经理"等章节
2. **扩展上下文**：根据命中位置使用 `read_document` 读取相邻条款
3. **主语判定**：回答“投标人是否需要为此安排一个具体的人”，否则排除
4. **逐岗位归并**：提取数量、评分、个人证书、经验、专业、技能、证明和兼任限制
5. **输出结果**：按本 Skill 的输出协议调用 submit_analysis；没有依据的条目省略。

## 输出协议

先核对资料清单，按 `references/coverage.json` 的全部主题检索主文件、澄清、补遗与附件。
遇到转引继续检索实际条款并补读，记录起点、目标、处理状态和依据。未找到或预算不足如实登记。
完成后调用 `complete_research(topics, references, research_summary)`：主题可用 key 或中文名称，
说明已读证据、covered/searched_not_found/unresolved 状态与未决事项；真实检索词由服务端保存，不用复述。
queries 仅为可选检索意图说明；遗漏主题自动记为待核对，重复说明合并。转引登记 resolved/missing/cycle/budget_exhausted。
未进入综合阶段不能提交结果；不能每找到一块证据就保存为最终条目。

综合全部已读证据，按 `references/output_format.md` 的分类、表格列和层级生成 content JSON。
`group` 为具体分类，`title` 为事项或任务名称，`content` 的键使用运行时输出 schema 中的中文列名。
技术方案要求包含“要求摘要”和逐条“关键要求”数组；格式条目使用“编制要求”数组，保留父子关系。
同一事项先归并、核对适用范围与冲突，再形成完整条目。摘要允许概括，门槛、公式、档次和例外必须完整。
`text` 由服务端从 content 生成，无需另填。缺少依据的内容省略，不能用“未提及/无”冒充事实。

通过 `submit_analysis(records, coverage, gaps, research_summary, final=false)` 按完整事项分批提交，
每批最多24条，最后明确 `final=true`。记录 `key` 是模块内稳定标识，纠正同一记录时沿用。
`kind` 为 fact/requirement/lot/format_node/relation；`scope.kind` 为 common/lots/unknown，
lots 的 `lot_refs` 填原文标段编号或名称。公共范围同样需要依据，未知不能推断为公共。
每条 `citations` 提供实际已读 block_id 与连续原文 quote，支持全部 content 及业务属性。
`conditions` 保留表达式、且/或、数值、单位、起算点及例外；`materials` 保留证明材料要求；
`scoring` 保留满分、公式、全部档次和扣分。不能可靠结构化时声明 `structuring=partial`。
只有项目概况模块提交 lot；code 只填原文编号，无编号时省略，title 保留原文名称。
格式模块用 format_node 与 node_type=group/section，分组可嵌套；用 parent_key 保留原文层级，同批不限制父子顺序。
关系端点可在同批提供，再填 subject_key/object_key 与 predicate。
supersedes 表示 subject 替代 object；修订和冲突须引用双方并明确适用范围，不按上传时间裁定。

coverage、gaps 和 research_summary 可省略，由服务端沿用检索账并补齐待核对清单。
coverage 的主题可用 key 或中文名称；extracted 关联已核实 record_keys，searched_not_found 仅表示本次未找到，
pending 表示尚未解决，not_applicable 必须有原文引用并校验。可按标段分别登记。
最终 gaps 提供剩余内容缺口清单；complete_research 已登记的未决检索和转引由服务端保留，不能静默清空。
新检索或补读引入新依据后须重新 complete_research 并重新综合，旧批次不会与新证据混发。
来源、页码和坐标由服务端补齐；原文只作溯源，正文展示归纳后的业务内容。

## 参考文件（按标类型加载）
根据任务 category 及 lots 中的类别覆盖，加载对应子目录下的参考文件：
- `references/output_format.md`：本 Skill 专属输出模板和格式约束
- `references/<type_dir>/extraction_rules.md`：逐岗位提取规则、社保要求、兼任限制、严禁行为、自检清单
- `references/<type_dir>/examples.md`：完整人员配置要求提取样例
- category 取值：service（服务类）、engineering（工程类）、goods（货物类）；type_dir 使用相同值
- 类别由用户选择并由运行时提供；不能自行默认成服务类，标段有覆盖类别时同时参考对应规则

## 工具与证据

- 运行时先调用 `load_skill` 加载本文件及 `references/output_format.md`，无需重复读取；其余细则按需读取。
- `list_documents()`：返回授权资料的 id 和说明文本；资料 id 可填入检索的 source_id。
- `search_document(query, source_id?)`：检索本项目；`search_knowledge(query, source_id?)`：检索关联参考库。
- 检索证据只含 `id`、`text`。把证据 id 填入引用的 `block_id`；quote 必须是该 text 的连续原文。
- `read_document(block_id, before=2, after=2)`：围绕已读证据补读；before/after 合计最多11，均为0时只补读本块。不得猜测ID或扫描全文。
- `read_file(file_path)`：只读 `/skills/personnel-requirement-parsing/references/` 下当前任务需要的细则，或压缩历史；不能读取招标文件磁盘路径。
- `complete_research`：登记全部主题检索与转引，进入综合阶段。
- `submit_analysis`：综合全部证据后按完整事项提交，每批最多24条；`final=false` 暂存，核对完成后 `final=true`。

## 证据选择与纠错

1. 先按本专题的问题检索，再核对主体、标段、表头、脚注、条件和补充文件。上下文不足时按证据ID补读；不能用关键词命中代替事实判断。
2. 同一事实在相同适用范围内重复出现，选最直接、完整的一处。跨块条件、不同标段、修订前后和未决冲突所需的证据分别保留；检索相似度和自报置信分数不作为可信度。
3. 引用只提交ID和连续摘录，不生成页码、坐标、文件路径或来源元数据。服务端校验实际读取记录、资料权限和版本后，按保留的ID补齐定位。
4. 工具返回结构化错误时，按 `message` 和 `remaining_attempts` 修正；未补入新证据时只修正未通过事项；补入新依据后重新综合。更换名称或重复请求不会获得新额度。
5. 收到收尾提示就停止扩展检索，提交已有可靠结果并在 `research_summary` 记录缺口；不得声称缺口是文件未约定。不得再委派子Agent，服务故障与重试由运行时处理。

## 注意
- 人员资质要求需区分"强制性"和"加分项"
- 注意证书的有效期和等级要求
- 注意社保证明的时间要求
- 同时存在总人数和细分岗位时，以细分岗位为主，并将总人数写入相关岗位备注
