"""将 Skill 的展示格式固定为 JSON 结构，并在汇总前核对实际检索记录。"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tender.application.shared.validation import InputError, validation_message

OUTPUT_VERSION = "1"


class OutputSection(BaseModel):
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


class OutputSchema(BaseModel):
    """冻结Skill声明的统一结构；应用读取和HTTP响应复用同一约束。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal["1"]
    sections: list[OutputSection] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sections(self):
        if len({section.title for section in self.sections}) != len(self.sections):
            raise ValueError("输出分类不能重复")
        return self


def output_schema(snapshot: dict, module_key: str) -> dict:
    """从报告冻结的结构化声明读取格式。"""
    path = module_key + "/references/output_schema.json"
    if path not in snapshot:
        raise ValueError("模块缺少冻结的 JSON 输出声明：" + module_key)
    try:
        return OutputSchema.model_validate_json(snapshot[path]).model_dump(exclude_unset=True)
    except ValueError as exc:
        # 声明损坏时停止执行，避免格式规则与最终展示出现两套口径。
        raise ValueError("模块 Skill JSON 输出声明无效：" + module_key) from exc


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
        ))
        # 各分类列相同时可一起诊断内容键，避免模型修正分类后再碰到内容错误。
        if len({tuple(s["columns"]) for s in schema["sections"]}) == 1:
            section = schema["sections"][0]
    content = record.get("content") or {}
    if section is not None and (not content or set(content) - set(section["columns"])):
        issues.append(("content",
            "content 只能填写当前分类的内容键：" + "、".join(section["columns"])
            + "；具体事项名称和结论写在列对应的值中，不作为content键"
        ))
    if section is None:
        raise InputError(validation_message(issues), field_issues=issues)
    # 两列各自的数组没有可靠配对语义，声明为单值的列必须逐条提交。
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
