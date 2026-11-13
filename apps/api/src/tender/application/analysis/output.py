"""将 Skill 的展示格式固定为 JSON 结构，并在汇总前核对实际检索记录。"""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tender.application.knowledge.content import normalized
from tender.application.shared.validation import InputError, validation_message

OUTPUT_VERSION = "1"


class _OutputSection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: Annotated[str, Field(pattern=r"\S")]
    layout: Literal["table", "list", "tree"]
    columns: list[Annotated[str, Field(pattern=r"\S")]] = Field(min_length=1)
    scalar_columns: list[str] = Field(default_factory=list)
    title_column: str | None = None

    @model_validator(mode="after")
    def unique_columns(self):
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("输出列名不能重复")
        if (len(set(self.scalar_columns)) != len(self.scalar_columns)
                or set(self.scalar_columns) - set(self.columns)):
            raise ValueError("单值列必须来自输出列且不能重复")
        if self.title_column is not None and self.title_column not in self.columns:
            raise ValueError("标题来源必须是本分类的输出列")
        return self


class _OutputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal["1"]
    sections: list[_OutputSection] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sections(self):
        if len({section.title for section in self.sections}) != len(self.sections):
            raise ValueError("输出分类不能重复")
        return self


def output_schema(snapshot: dict, module_key: str) -> dict:
    """从冻结声明读取格式；仅无声明的历史快照沿用原 Markdown 解释方式。"""
    path = module_key + "/references/output_schema.json"
    if path in snapshot:
        try:
            return _OutputSchema.model_validate_json(snapshot[path]).model_dump(exclude_unset=True)
        except ValueError as exc:
            # 已声明却损坏是资源错误，回退会使模型规则与实际展示悄悄分叉。
            raise ValueError("模块 Skill JSON 输出声明无效：" + module_key) from exc
    return _legacy_output_schema(snapshot, module_key)


def _legacy_output_schema(snapshot: dict, module_key: str) -> dict:
    """旧报告继续解释自己的模板，不能从当前资源补入新规则。"""
    if module_key == "bid_format_outline_parsing":
        return {"version": OUTPUT_VERSION, "sections": [
            {"title": "*", "layout": "tree", "columns": ["编制要求"]},
        ]}
    if module_key == "tech_requirement_parsing":
        return {"version": OUTPUT_VERSION, "sections": [
            {"title": "项目背景", "layout": "list", "columns": ["背景"]},
            {"title": "技术方案要求", "layout": "list",
             "columns": ["章节来源", "要求摘要", "关键要求"]},
        ]}
    if module_key == "general_module_parsing":
        return {"version": OUTPUT_VERSION, "sections": [
            {"title": "补充发现", "layout": "table", "columns": ["事项", "分析结论"]},
            {"title": "跨文件关联", "layout": "table", "columns": ["事项", "分析结论"]},
        ]}
    content = snapshot.get(module_key + "/references/output_format.md", "")
    template = re.search(r"\x60{3}markdown\s*\n(.*?)\x60{3}", content, re.S)
    if template is None:
        raise ValueError("模块缺少可识别的 Skill 输出格式：" + module_key)
    sections, title = [], ""
    for line in template[1].splitlines():
        if line.startswith("## "):
            title = re.sub(r"<[^>]*>", "", line[3:]).strip()
        elif title and line.startswith("|"):
            columns = [c.strip() for c in line.strip("|").split("|")]
            # 序号属于显示顺序，不允许模型将它作为业务断言提交。
            columns = [c for c in columns if c != "序号"]
            names = (
                ["商务评分标准", "技术评分标准", "综合评分标准"]
                if title == "[商务/技术/综合]评分标准"
                else ["*"] if title == "[岗位职能名称]" else [title]
            )
            sections.extend(
                {"title": name, "layout": "table", "columns": columns} for name in names
            )
            title = ""
    if not sections:
        raise ValueError("模块输出格式没有分类或表格列：" + module_key)
    return {"version": OUTPUT_VERSION, "sections": sections}


def output_contract(schema: dict) -> str:
    """用冻结列名生成一个局部格式样例，避免精简提示后模型猜测分类和内容键的对应关系。"""
    section = schema["sections"][0]
    example = {
        "group": section["title"] if section["title"] != "*" else "原文具体岗位或格式层级",
        "content": {
            column: "具体事项名称" if index == 0 and len(section["columns"]) > 1
            else ["原文支持的具体要求"] if column in {"关键要求", "编制要求"}
            else "原文支持的具体结论"
            for index, column in enumerate(section["columns"])
        },
    }
    return (
        "group填写输出格式sections中的title（*使用原文具体岗位或格式层级）；"
        "content的键使用该分类的columns列名，"
        "具体事项名称和结论写在列对应的值中。局部格式示例（值为占位说明）："
        + json.dumps(example, ensure_ascii=False, separators=(",", ":"))
    )


def record_output(record: dict, schema: dict) -> dict:
    """仅接纳当前专题允许的分类和内容键，模型不能新增通用字段/原文表格。"""
    section = next((
        s for s in schema["sections"] if s["title"] in {record["group"], "*"}
    ), None)
    issues: list[tuple[str, str]] = []
    if section is None or (section["layout"] != "tree" and not record["group"].strip()):
        issues.append(("group",
            "结果分类不符合当前 Skill 输出格式：group须填写分类："
            + "、".join(s["title"] for s in schema["sections"])
            + "；category不能代替group"
        ))
        # 只用可确定的候选分类诊断内容键，不能把category悄悄转换成有效group。
        section = next((s for s in schema["sections"]
                        if s["title"] == record.get("category")), None)
        if section is None and len({tuple(s["columns"]) for s in schema["sections"]}) == 1:
            section = schema["sections"][0]
    content = record.get("content") or {}
    if section is not None and (not content or set(content) - set(section["columns"])):
        issues.append(("content",
            "content 只能填写当前分类的内容键：" + "、".join(section["columns"])
            + "；具体事项名称和结论写在列对应的值中，不作为content键"
        ))
    if section is None:
        raise InputError(validation_message(issues), field_issues=issues)
    # 两列各自的数组没有可靠配对语义；仅新快照声明单值列，旧报告保留原协议。
    for column in section.get("scalar_columns", []):
        if column in content and not isinstance(content[column], str):
            issues.append(("content." + column,
                           f"{column}必须是单个事项名称；请将多个独立字段分别逐条提交"))
    for column, value in content.items():
        values = value if isinstance(value, list) else [value]
        if not values or any(not isinstance(v, str) or not v.strip() for v in values):
            issues.append(("content." + column, "结果内容不能为空；缺少原文依据的内容键应省略"))
    if record["group"] == "技术方案要求" and not {"要求摘要", "关键要求"} & content.keys():
        issues.append(("content", "技术方案条目缺少有依据的要求内容；填写要求摘要或关键要求"))
    elif (len(section["columns"]) > 1 and content
          and not set(content) - {section["columns"][0]} and record["group"] != "总分构成"):
        issues.append(("content", "结果只有事项名称，缺少有依据的分析内容；请补充："
                       + "、".join(section["columns"][1:])))
    if issues:
        # 先汇总所有可独立判断的问题，再进行内容规范化；不能让模型逐个碰错。
        raise InputError(validation_message(issues), field_issues=issues)
    content = dict(content)
    if record["group"] == "技术方案要求":
        # 单条要求的字符串可直接包成数组；摘要与条目相互补齐不增加新断言，随后仍整体送审。
        if "关键要求" not in content:
            summary = content["要求摘要"]
            content["关键要求"] = list(summary) if isinstance(summary, list) else [summary]
        elif isinstance(content["关键要求"], str):
            content["关键要求"] = [content["关键要求"]]
        content.setdefault("要求摘要", "；".join(content["关键要求"]))
    # 原文可能只提供部分列，不能要求模型为了凑齐首末列而编造信息。
    return {
        "version": OUTPUT_VERSION, "layout": section["layout"],
        "columns": section["columns"], "content": content,
        "parent_key": record.get("parent_key"), "key": record["key"],
        "node_type": record.get("node_type"),
    }


class ResearchTopic(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    topic: str = Field(min_length=1)
    status: Literal["covered", "searched_not_found", "unresolved"] = Field(
        description="covered表示本主题已核对；仍有未读条件或缺失转引目标时用unresolved",
    )
    queries: list[str] = Field(
        default_factory=list,
        description="可选的检索意图说明；真实检索词由服务端记录，无需逐字复述",
    )
    evidence_ids: list[str] = Field(default_factory=list)
    detail: str = ""


class ReferenceTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    topic: str = Field(min_length=1)
    from_block_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    status: Literal["resolved", "missing", "cycle", "budget_exhausted"] = Field(
        description="resolved表示已读到目标实质条款；只找到索引或目标仍缺失不能标记resolved",
    )
    evidence_ids: list[str] = Field(
        default_factory=list, description="目标实质条款的已读ID，不用转引起点或另一处索引替代",
    )
    detail: str = ""


class ResearchCheckpointError(ValueError):
    """一次给出全部可修复问题，避免修好一项才发现下一项并耗尽工具额度。"""

    def __init__(self, issues: list[dict], context: dict):
        super().__init__("；".join(i["message"] for i in issues))
        self.details = {"issues": issues, **context}


def research_context(expected_topics: list[dict], research) -> dict:
    """真实检索账直接取工具事件，历史压缩后也无需模型记住和复述请求字符串。"""
    return {
        "expected_topics": expected_topics,
        "project_documents": [
            {"source_id": s["source_id"], "file_name": s["file_name"]}
            for s in research.sources if s["project_id"] == research.project_id
        ],
        "project_searches": [
            {"query": e["query"], "source_ids": e.get("source_ids", []),
             "evidence_ids": e.get("block_ids", [])}
            for e in research.events
            if e["action"] == "search_result" and e.get("scope") == "project"
        ],
    }


def canonical_topic(name: str, expected_topics: list[dict]) -> str:
    """key 和中文名称均可归档；不能确定归属的描述保留原名并登记覆盖缺口。"""
    key_match = next((t["key"] for t in expected_topics
                      if normalized(t["key"]) == normalized(name)), None)
    if key_match:
        return key_match
    matches = {t["key"] for t in expected_topics
               if t.get("title") and normalized(t["title"]) == normalized(name)}
    return next(iter(matches)) if len(matches) == 1 else name.strip()


def research_checkpoint(
    topics: list[ResearchTopic],
    references: list[ReferenceTrace],
    summary: str,
    *,
    expected_topics: list[dict],
    research,
) -> dict:
    """检索真实性由服务端账核对；模型的主题遗漏记缺口，不因复述形式阻断综合。"""
    context = research_context(expected_topics, research)
    issues = []

    def issue(code: str, message: str, *, key: str = "", **details) -> None:
        issues.append({"key": key or code, "code": code, "message": message, **details})

    searches = context["project_searches"]
    if not searches:
        issue("project_not_searched", "尚未实际检索项目资料，请先 search_document")
    searched_sources = {source for e in searches for source in e.get("source_ids", [])}
    required_sources = {s["source_id"] for s in research.sources
                        if s["project_id"] == research.project_id}
    # 未纳入检索的资料是实际范围缺口；允许发布已有依据的成果，并明确显示遗漏资料。
    document_gaps = [
        {"source_id": s["source_id"], "detail": "资料尚未纳入本次检索：" + s["file_name"]}
        for s in research.sources
        if s["source_id"] in required_sources - searched_sources
    ]
    expected = {t["key"] for t in expected_topics}
    grouped: dict[str, list[ResearchTopic]] = {}
    additional = []
    for topic in topics:
        canonical = canonical_topic(topic.topic, expected_topics)
        identity = canonical if canonical in expected else "additional"
        if topic.status == "covered" and not topic.evidence_ids:
            # 覆盖证明缺项只能说明待核对，不能因此阻止提交其它有明确引用的正文。
            topic = topic.model_copy(update={
                "status": "unresolved",
                "detail": (topic.detail + "；本主题缺少关联证据，覆盖情况待核对").strip("；"),
            })
        invalid = [block_id for block_id in topic.evidence_ids
                   if block_id not in research.seen
                   or research.seen[block_id]["project_id"] != research.project_id]
        if invalid:
            issue("invalid_evidence", f"主题{canonical}的依据必须是本次已读取的项目原文",
                  key=identity + ":invalid_evidence", topic=canonical, evidence_ids=invalid)
        if canonical in expected:
            grouped.setdefault(canonical, []).append(topic)
        else:
            additional.append(topic)
    traces = []
    for index, trace in enumerate(references):
        origin = research.seen.get(trace.from_block_id)
        if not origin or origin["project_id"] != research.project_id:
            issue("invalid_reference_origin", "转引起点必须是已读取的项目原文",
                  key=f"reference:{index}:origin", from_block_id=trace.from_block_id)
        if trace.status == "resolved" and not trace.evidence_ids:
            trace = trace.model_copy(update={
                "status": "missing",
                "detail": (trace.detail + "；转引目标缺少可追溯证据，尚待核对").strip("；"),
            })
        invalid = [block_id for block_id in trace.evidence_ids
                   if block_id not in research.seen
                   or research.seen[block_id]["project_id"] != research.project_id]
        if invalid:
            issue("invalid_reference_evidence", "转引目标必须是本次已读取的项目原文",
                  key=f"reference:{index}:evidence", evidence_ids=invalid)
        traces.append(trace.model_copy(update={
            "topic": canonical_topic(trace.topic, expected_topics),
        }))
    if issues:
        raise ResearchCheckpointError(issues, context)

    checked = []
    for item in expected_topics:
        entries = grouped.get(item["key"], [])
        if not entries:
            checked.append({
                "topic": item["key"], "status": "unresolved", "evidence_ids": [],
                "search_intents": [],
                "detail": "本次未单独交代“" + item.get("title", item["key"])
                + "”的核对情况，不能确认本主题已覆盖。",
            })
            continue
        statuses = {t.status for t in entries}
        # 同一主题的多个说明合并为一项；互相矛盾的覆盖状态保守登记为未决。
        checked.append({
            "topic": item["key"],
            "status": next(iter(statuses)) if len(statuses) == 1 else "unresolved",
            "search_intents": list(dict.fromkeys(q for t in entries for q in t.queries)),
            "evidence_ids": list(dict.fromkeys(b for t in entries for b in t.evidence_ids)),
            "detail": "；".join(dict.fromkeys(t.detail for t in entries if t.detail))[:2000]
            or "已登记本主题核对情况，覆盖状态与关联依据见检索记录。",
        })
    return {
        "topics": checked,
        "additional_topics": [
            t.model_dump(exclude={"queries"}) | {"search_intents": t.queries} for t in additional
        ],
        "references": [t.model_dump() for t in traces],
        "project_searches": searches,
        "document_gaps": document_gaps,
        "research_summary": summary.strip()[:4000]
        or "已执行本轮项目资料检索，未决主题和转引保留为待核对缺口。",
        "evidence_ids": sorted(research.seen),
    }


def research_gaps(checkpoint: dict) -> list[dict]:
    """未解决的检索范围随结果发布，最终提交不能将已登记的缺口静默清空。"""
    gaps = []
    for source in checkpoint.get("document_gaps", []):
        gaps.append({
            "key": "source:" + str(source["source_id"]), "topic": "资料范围",
            "scope": {"kind": "unknown", "lot_refs": []},
            "code": "missing_source", "detail": source["detail"],
        })
    for topic in checkpoint["topics"]:
        if topic["status"] != "covered":
            gaps.append({
                "key": "research:" + topic["topic"], "topic": topic["topic"],
                "scope": {"kind": "unknown", "lot_refs": []},
                "code": "search_exhausted", "detail": topic["detail"],
            })
    for index, trace in enumerate(checkpoint["references"]):
        if trace["status"] != "resolved":
            gaps.append({
                "key": "reference:" + str(index), "topic": trace["topic"],
                "scope": {"kind": "unknown", "lot_refs": []},
                "code": "unresolved_reference",
                "detail": trace["target"] + "：" + trace["detail"],
            })
    return gaps
