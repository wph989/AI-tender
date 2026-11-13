"""解析业务契约与确定性投影；业务身份不依赖展示文字，语义仍由原文校验。"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Literal
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tender.application.analysis.output import canonical_topic, record_output
from tender.application.analysis.state import published_items
from tender.application.knowledge.content import (
    dedupe_citations,
    fingerprint,
    match_text,
    normalized,
    validate_items,
)
from tender.application.shared.validation import (
    InputError,
    allowed_values,
    validation_message,
)

DATA_VERSION = "1"


class DataInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DataCitation(DataInput):
    """模型只选择已读块，文件、页码、坐标和原文由服务端补齐。"""

    block_id: str = Field(min_length=1, description="检索或补读实际返回的原文块ID")

    @model_validator(mode="before")
    @classmethod
    def discard_legacy_quote(cls, value):
        # 冻结样例和旧检查点可能仍带quote；它不是定位输入，不能再因改写或缺失而拒绝总结。
        if isinstance(value, dict):
            return {key: item for key, item in value.items() if key != "quote"}
        return value


class DataScope(DataInput):
    kind: Literal["common", "lots", "unknown"]
    lot_refs: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def check_refs(self):
        if (self.kind == "lots") != bool(self.lot_refs):
            raise ValueError("lots 范围必须提供标段原文指向；common/unknown 不填 lot_refs")
        if any(not ref.strip() for ref in self.lot_refs):
            raise ValueError("标段指向不能为空")
        return self


class ConditionTerm(DataInput):
    subject: str = Field(min_length=1)
    operator: Literal["=", "!=", ">", ">=", "<", "<=", "in", "text"]
    value: str = Field(min_length=1)
    unit: str | None = None
    time_basis: str | None = None


class Conditions(DataInput):
    expression: str = ""
    logic: Literal["all", "any", "mixed", "text"] = "text"
    terms: list[ConditionTerm] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)


class Material(DataInput):
    name: str = Field(min_length=1)
    requirement: str = Field(min_length=1)


class ScoreTier(DataInput):
    condition: str = Field(min_length=1)
    points: str = Field(min_length=1)


class Scoring(DataInput):
    max_points: str | None = None
    formula: str = ""
    tiers: list[ScoreTier] = Field(default_factory=list)
    deductions: list[str] = Field(default_factory=list)


class RecordContent(DataInput):
    """模型表达的业务内容；生成字段留在内部记录契约，避免模型重复填写。"""

    key: str = Field(min_length=1, max_length=100)
    kind: Literal["fact", "requirement", "lot", "format_node", "relation"]
    title: str = Field(min_length=1, max_length=300)
    content: dict[str, str | list[str]] = Field(
        default_factory=dict,
        description="键使用当前group在输出格式声明中的列名，事项名称及结论写在对应的值中",
    )
    scope: DataScope
    citations: list[DataCitation] = Field(
        min_length=1, description="总结所依据的已读块定位，只填写block_id，无需摘抄原文",
    )
    group: str = Field(
        default="", description="展示分类，填写当前Skill输出格式的title；不能用category代替",
    )
    category: str = Field(default="other", description="可选业务标签；展示分类填写group")
    structuring: Literal["complete", "partial"] = "partial"
    conditions: Conditions = Field(default_factory=Conditions)
    materials: list[Material] = Field(default_factory=list)
    scoring: Scoring | None = None
    code: str | None = None
    aliases: list[str] = Field(default_factory=list)
    node_type: Literal["group", "section"] | None = None
    parent_key: str | None = None
    requirement_keys: list[str] = Field(default_factory=list)
    predicate: Literal["supersedes", "conflicts", "requires", "contains"] | None = None
    subject_key: str | None = None
    object_key: str | None = None

    @model_validator(mode="after")
    def check_kind(self):
        # 招标文件可能只给标段名称；code 只保存原文编号，不能为满足协议让模型编造。
        if self.kind == "format_node" and self.node_type is None:
            raise ValueError("格式节点必须声明 node_type")
        # 原文的分组可以嵌套；是否循环、父节点是否存在由完整结构检查判断。
        if self.kind == "relation" and not all(
            (self.predicate, self.subject_key, self.object_key)
        ):
            raise ValueError("关系必须声明 predicate/subject_key/object_key")
        if self.kind != "format_node" and (self.node_type or self.parent_key):
            raise ValueError("仅格式节点可声明父子结构")
        if self.kind != "relation" and (self.predicate or self.subject_key or self.object_key):
            raise ValueError("仅关系记录可声明关系端点")
        return self


class BusinessRecord(RecordContent):
    text: str = Field(min_length=1)
    sort_order: int = Field(default=0, ge=0)


class SynthesisRecord(BusinessRecord):
    """汇总工具只需填专题内容，通用业务文本由服务端从内容确定性生成。"""

    text: str = ""
    content: dict[str, str | list[str]] = Field(
        min_length=1, description=RecordContent.model_fields["content"].description,
    )


class CoverageInput(DataInput):
    topic: str = Field(min_length=1, max_length=100)
    scope: DataScope
    status: Literal["extracted", "searched_not_found", "pending", "not_applicable"]
    record_keys: list[str] = Field(default_factory=list)
    detail: str = Field(min_length=1, max_length=2000)
    citations: list[DataCitation] = Field(default_factory=list)


class GapInput(DataInput):
    key: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=100)
    scope: DataScope
    code: Literal[
        "unresolved_reference", "unknown_condition", "scope_unknown", "conflict",
        "missing_source", "incomplete_structure", "search_exhausted",
    ]
    detail: str = Field(min_length=1, max_length=2000)


def record_identity(state: dict, key: str) -> str:
    # 命名空间随检查点保存；改名、改值、换引用不会改变同一个 key 的身份。
    namespace = state.setdefault("business_namespace", str(uuid4()))
    return str(uuid5(UUID(namespace), key))


def semantic_payload(record: Mapping) -> dict:
    """校验全部业务属性；内部编号和展示排序没有业务含义，不浪费审查上下文。"""
    excluded = {"id", "key", "module_key", "citations", "verification", "sort_order"}
    return {k: v for k, v in record.items() if k not in excluded}


def missing_scope_refs(scope: dict, citations: list[dict]) -> list[str]:
    """提交与最终选证共用原文指向规则，避免错误范围到付费审查后才暴露。"""
    if scope.get("kind") != "lots":
        return []
    return [ref for ref in scope.get("lot_refs", [])
            if not any(match_text(ref) in match_text(c["quote"]) for c in citations)]


def prepare_records(
    raw: list[BusinessRecord], state: dict, seen: dict, module_key: str,
) -> list[dict]:
    records = [entry.model_dump() for entry in raw]
    if len({entry["key"] for entry in records}) != len(records):
        raise InputError.for_field("key", "同批业务记录 key 重复")
    existing = {
        item["business"]["key"]: item["business"]
        for item in state.get("staged_items", []) if item.get("business")
    }
    outputs = {}
    if state.get("output_schema"):
        # 同批关系可先于端点；必须先生成整批文本，避免关系复制尚未生成的空文本。
        for entry in records:
            output = record_output(entry, state["output_schema"])
            entry["content"] = output["content"]
            # 展示与业务上下文来自同一份已校验 JSON，避免另写 text 又退回原文摘录。
            entry["text"] = "\n".join(
                f"{name}：" + ("\n".join(value) if isinstance(value, list) else value)
                for name, value in entry["content"].items()
            )
            outputs[entry["key"]] = output
    combined = existing | {entry["key"]: entry for entry in records}
    result = []
    for entry in records:
        output = outputs.get(entry["key"])
        if entry["kind"] == "lot" and module_key != "project_basic_info_parsing":
            raise InputError.for_field("kind",
                                       "标段目录由项目概况模块提交；其它模块填写 scope.lot_refs")
        if entry["kind"] == "format_node" and module_key != "bid_format_outline_parsing":
            raise InputError.for_field("kind", "格式节点由投标文件格式模块提交")
        refs = list(entry["citations"])
        if any(ref == entry["key"] or ref not in combined
               or combined[ref]["kind"] != "requirement" for ref in entry["requirement_keys"]):
            raise InputError.for_field("requirement_keys",
                                "requirement_keys：须引用同批或已提交的要求事项，不能引用自身")
        if entry["kind"] == "format_node":
            path, visited, current = [], {entry["key"]}, entry
            while current.get("parent_key"):
                parent = current["parent_key"]
                if parent not in combined or parent in visited:
                    raise InputError.for_field("parent_key",
                        "parent_key：格式层级存在缺失父节点或循环，请先提交父节点；"
                        "可选父节点key：" + allowed_values(
                            k for k, value in combined.items()
                            if value["kind"] == "format_node" and k not in visited
                        )
                    )
                current = combined[parent]
                if current["kind"] != "format_node":
                    raise InputError.for_field("parent_key",
                        "parent_key：格式父节点必须是格式节点；先提交kind=format_node的父节点"
                    )
                visited.add(parent)
                path.insert(0, current["title"])
                refs.extend(current["citations"])
            entry["parent_path"] = path
        if entry["kind"] == "relation":
            errors = []
            for endpoint in ("subject", "object"):
                target = combined.get(entry[endpoint + "_key"])
                if not target or target["kind"] in {"lot", "relation"}:
                    errors.append((
                        endpoint + "_key",
                        "关系端点必须是同批或已提交的本模块事实、要求或格式节点；"
                        "可选key：" + allowed_values(
                            k for k, value in combined.items()
                            if value["kind"] not in {"lot", "relation"}
                        ),
                    ))
            if errors:
                raise InputError(validation_message(errors), field_issues=errors)
            for endpoint in ("subject", "object"):
                target = combined[entry[endpoint + "_key"]]
                entry[endpoint + "_text"] = target["text"]
                refs.extend(target["citations"])
        # 所有属性与本条文本共用一套证据送审；禁止先审展示文字再补入未经验证的属性。
        item = validate_items([{
            "field": entry["title"], "group": entry["group"],
            "sort_order": entry["sort_order"],
            "values": [{"value": entry["text"], "citations": refs}],
        }], seen, align=False, citation_path="citations", source_locations=True)[0]
        entry.update(id=record_identity(state, entry["key"]), module_key=module_key)
        entry["citations"] = item["values"][0]["citations"]
        missing = missing_scope_refs(entry["scope"], entry["citations"])
        if missing:
            errors = [
                (f"scope.lot_refs[{entry['scope']['lot_refs'].index(ref)}]",
                 "必须填写引文中的标段原文编号或名称；当前指向未出现在引文中："
                 + ref + "。不要填写内部事项key；请按已引用原文修正，并同步关联工作的范围")
                for ref in missing
            ]
            raise InputError(validation_message(errors), field_issues=errors)
        item.update(id=entry["id"], business=entry)
        if output is not None:
            item["output"] = output
        result.append(item)
    return result


def prepare_record_batch(raw: list[SynthesisRecord], state: dict, seen: dict,
                         module_key: str) -> tuple[list[dict], list[dict]]:
    """共享同批有效引用图；仅移除坏记录及依赖它的事项，保留无关的有效依赖组。"""
    candidates, rejected = {}, {}
    details: dict[int, list[tuple[str, str]]] = {}
    for index, record in enumerate(raw):
        try:
            value = record.model_dump()
            if state.get("output_schema"):
                output = record_output(value, state["output_schema"])
                value["content"] = output["content"]
                value["text"] = "\n".join(
                    name + "：" + ("\n".join(v) if isinstance(v, list) else v)
                    for name, v in value["content"].items()
                )
            candidates[index] = value
        except InputError as exc:
            rejected[index] = str(exc)
            details[index] = exc.field_issues
    while candidates:
        context = dict(state) | {"staged_items": [
            *state.get("staged_items", []),
            *({"business": value} for value in candidates.values()),
        ]}
        accepted, failures = {}, {}
        for index in candidates:
            try:
                accepted[index] = prepare_records([raw[index]], context, seen, module_key)[0]
            except InputError as exc:
                failures[index] = str(exc)
                details[index] = exc.field_issues
        if not failures:
            return list(accepted.values()), [
                {"index": i, "key": raw[i].key, "title": raw[i].title, "error": error,
                 "field_issues": details.get(i, [])}
                for i, error in sorted(rejected.items())
            ]
        rejected.update(failures)
        candidates = {i: value for i, value in candidates.items() if i not in failures}
    return [], [{"index": i, "key": raw[i].key, "title": raw[i].title, "error": error,
                 "field_issues": details.get(i, [])}
                for i, error in sorted(rejected.items())]


def prepare_coverage(
    raw: list[CoverageInput], state: dict, seen: dict, topics: list[dict], module_key: str,
) -> tuple[list[dict], list[dict]]:
    entries, reviews = [], []
    for value in raw:
        entry = value.model_dump()
        entry["topic"] = canonical_topic(entry["topic"], topics)
        if entry["status"] == "extracted" and not entry["record_keys"]:
            entry.update(status="pending", detail="已保留分析结果，主题与具体条目的关联待核对")
        if entry["status"] == "not_applicable":
            if not entry["citations"]:
                # 无证明不能发布“不适用”结论，但也不应阻断其它有原文支持的分析条目。
                entry.update(status="pending", detail="不适用说明缺少原文依据，待核对")
                entries.append(entry)
                continue
            item = validate_items([{
                "field": "主题不适用：" + entry["topic"],
                "values": [{"value": entry["detail"], "citations": entry["citations"]}],
            }], seen, align=False, source_locations=True)[0]
            entry["citations"] = item["values"][0]["citations"]
            proof_key = "coverage:" + fingerprint([entry["topic"], entry["scope"]])
            previous = next((v for v in state.get("business_coverage", [])
                             if v["topic"] == entry["topic"] and v["scope"] == entry["scope"]
                             and v.get("review_id")), None)
            # 同一主题与范围的证明改写不能重置纠错次数；恢复旧检查点时沿用旧证明ID，
            # 不同标段仍独立计数。文字与引用变化会重新校验，不参与身份计算。
            item["id"] = previous["review_id"] if previous else record_identity(state, proof_key)
            item["business"] = {
                "id": item["id"],
                "key": proof_key,
                "kind": "coverage", "scope": entry["scope"], "module_key": module_key,
                "topic": entry["topic"], "text": entry["detail"],
            }
            entry["review_id"] = item["id"]
            reviews.append(item)
        entries.append(entry)
    return entries, reviews


def module_records(data: dict) -> list[dict]:
    """内部消费时回填引用；持久化业务 JSON 与证据分开，兼容历史内嵌引用。"""
    result = copy.deepcopy(data.get("records", []))
    evidence = data.get("evidence", {})
    for record in result:
        if "evidence_ids" in record:
            # 证据表写入后只读消费，回填引用不需要再次深拷贝。
            record["citations"] = [dict(evidence[key])
                                   for key in record["evidence_ids"] if key in evidence]
            if not record["evidence_ids"] or any(key not in evidence
                                                 for key in record["evidence_ids"]):
                # 少一处证据就可能丢失修订或条件，不能拿剩余引用冒充完整依据。
                record.update(citations=[], verification="unavailable")
    return result


def module_data(state: dict) -> dict:
    records = []
    evidence = {}
    for item in published_items(state):
        if item.get("verification") != "supported" or not item.get("business"):
            continue
        record = copy.deepcopy(item["business"])
        record["verification"] = "supported"
        if state.get("topic_flow"):
            record["review_status"] = item.get("review_status", "current")
        refs = dedupe_citations([
            ref for value in item["values"] for ref in value["citations"]
        ])
        refs_by_id = {fingerprint(ref): ref for ref in refs}
        if bindings := (item.get("output") or {}).get("citations"):
            # 整项与正文单元可能选中不同的等价出处；逐条绑定必须保留自己实际校验过的引用。
            record["content_evidence"] = {
                column: [[fingerprint(ref) for ref in group] for group in groups]
                for column, groups in bindings.items()
            }
            for groups in bindings.values():
                for group in groups:
                    for ref in group:
                        refs_by_id[fingerprint(ref)] = ref
        # 分析内容可以独立用于下游；位置和原文只保存在证据表，通过稳定 ID 关联。
        record.pop("citations", None)
        record["evidence_ids"] = list(refs_by_id)
        for evidence_id, ref in refs_by_id.items():
            evidence[evidence_id] = copy.deepcopy(ref)
        records.append(record)
    return {
        "schema_version": DATA_VERSION, "records": records, "evidence": evidence,
        "coverage": copy.deepcopy(state.get("business_coverage", [])),
        "gaps": copy.deepcopy(state.get("business_gaps", [])),
        "topics": copy.deepcopy(state.get("business_topics", [])),
        "research_summary": state.get("draft", {}).get(
            "research_summary", state.get("research_completed", {}).get("research_summary", "")
        ),
        "research": copy.deepcopy(state.get("research_completed", {})),
        **({"progress": {"topics": [{**{k: v for k, v in e.items()
                                         if k not in {"placeholder", "requested_status"}},
                                      "tasks": list(e["tasks"].values())}
                                     for e in state["topic_flow"]["entries"].values()],
                         "audit_round": state["topic_flow"]["audit"]["round"],
                         **({"phase": state["topic_flow"].get("phase", "research")}
                            if state["topic_flow"].get("output_mode") == "after-research" else {})}}
           if state.get("topic_flow") else {}),
    }


def display_items(items: list[dict]) -> list[dict]:
    """校验单元包含内部业务属性，页面只接收展示投影和可回查的记录身份。"""
    result = []
    for item in items:
        business = item.get("business")
        if business and business["kind"] == "coverage":
            continue
        rendered = {k: v for k, v in item.items() if k != "business"}
        if bindings := (item.get("output") or {}).get("citations"):
            # 逐条选中的额外出处也要经过既有可见性检查，避免整体出处可读时漏检局部引用。
            values = list(rendered["values"])
            refs = [*values[0]["citations"], *(
                ref for groups in bindings.values() for group in groups for ref in group
            )]
            values[0] = {
                **values[0], "citations": list({fingerprint(ref): ref for ref in refs}.values()),
            }
            rendered["values"] = values
        if business:
            scope = business["scope"]
            label = {"common": "公共要求", "unknown": "归属待确认"}.get(scope["kind"])
            label = label or "、".join(scope["lot_refs"])
            # 同名事项仍需让人看出适用差异，避免展示层再次抹去已核实的标段范围。
            note = "适用范围：" + label
            if business.get("structuring") == "partial":
                note += "；部分条件待核对"
            rendered.update(record_id=item["id"], note="；".join(
                part for part in (rendered.get("note", ""), note) if part
            ))
        result.append(rendered)
    return result


def resolve_scope(scope: dict, lots: list[dict]) -> dict:
    if scope["kind"] != "lots":
        return {"kind": scope["kind"], "lot_ids": [], "lot_refs": []}
    ids = []
    for ref in scope["lot_refs"]:
        matched = [lot["lot_id"] for lot in lots if normalized(ref) in {
            normalized(s) for s in [lot["code"], lot["title"], *lot.get("aliases", [])]
            if s
        }]
        if len(set(matched)) != 1:
            return {"kind": "unknown", "lot_ids": [], "lot_refs": scope["lot_refs"]}
        ids.extend(matched)
    return {"kind": "lots", "lot_ids": sorted(set(ids)), "lot_refs": scope["lot_refs"]}


def matches_scope(scope: dict, lot_id: int | None, *, unknown: bool = False) -> bool:
    return scope["kind"] == "common" or (
        scope["kind"] == "lots" and lot_id in scope.get("lot_ids", [])
    ) or (unknown and scope["kind"] == "unknown")


def scope_covers(container: dict, member: dict) -> bool:
    """关系只能在两个端点都适用的范围内生效，未知范围不能扩大为公共。"""
    if member["kind"] == "unknown":
        return False
    if container["kind"] == "common":
        return True
    return (
        container["kind"] == member["kind"] == "lots"
        and bool(member["lot_ids"])
        and set(member["lot_ids"]).issubset(container["lot_ids"])
    )


def data_gap(code: str, detail: str, scope: dict | None = None, **extra) -> dict:
    return {
        "code": code, "detail": detail,
        "scope": scope or {"kind": "unknown", "lot_ids": [], "lot_refs": []}, **extra,
    }


def format_tree_issues(records: list[dict]) -> dict[str, tuple[str, str]]:
    """逐条回退会改变整棵树，必须按最终保留的节点检查路径和所有祖先。"""
    nodes = {r["key"]: r for r in records if r["kind"] == "format_node"}
    issues, ancestors = {}, {}
    for key, node in nodes.items():
        path, visited, current = [], {key}, node
        while parent_key := current.get("parent_key"):
            if parent_key in visited:
                issues[key] = ("format_cycle", "格式父子关系存在循环，请修正关联节点")
                break
            parent = nodes.get(parent_key)
            if parent is None:
                issues[key] = ("missing_parent", "格式父节点未通过校验")
                break
            visited.add(parent_key)
            path.insert(0, parent["title"])
            current = parent
        if key not in issues and path != node.get("parent_path", []):
            issues[key] = ("parent_path_changed", "格式祖先路径已变化，请重新提交节点核对归属")
        ancestors[key] = visited - {key}
    for key in nodes:
        if key not in issues and ancestors[key] & issues.keys():
            issues[key] = ("missing_parent", "格式祖先归属待确认，请先修正父节点")
    return issues


def assemble_dataset(
    modules: list[dict], lots: list[dict], hydrated: dict[str, list[dict]] | None = None,
) -> dict:
    """仅编译通过校验的业务记录；模块执行完成不替代主题覆盖和适用范围。

    `hydrated` 供同一调用方已完成投影的模块复用，避免同一次发布重复解析业务 JSON。
    """
    result = {
        "schema_version": DATA_VERSION,
        "lots": [{**lot, "scope": resolve_scope(lot["scope"], lots)}
                 if "scope" in lot else copy.deepcopy(lot) for lot in lots],
        "facts": [], "requirements": [],
        "format_nodes": [], "relations": [], "coverage": [], "gaps": [],
    }
    records, by_key = [], {}
    for module in modules:
        data = module.get("business_data") or {}
        key = module["module_key"]
        available = []
        for record in (hydrated or {}).get(key) or module_records(data):
            if record.get("review_status") == "needs_review":
                result["gaps"].append(data_gap(
                    "record_needs_review", "新增证据影响该事项，尚待复核", record_id=record["id"],
                    module_key=key,
                ))
                continue
            # 必要证据缺失的记录整条不可用，只登记缺口，不能让剩余引用冒充完整依据。
            if record.get("verification") == "unavailable":
                result["gaps"].append(data_gap(
                    "source_unavailable", "记录的必要证据缺失", record_id=record["id"],
                    module_key=key,
                ))
                continue
            available.append(record)
        accepted = {r["key"]: r for r in available if r["kind"] != "coverage"}
        # 旧检查点的证明 key 可能相同；覆盖条目固定 review_id，不按业务 key 合并证明。
        proofs = {r["id"]: r for r in available if r["kind"] == "coverage"}
        structure_issues = format_tree_issues(list(accepted.values()))
        for raw in accepted.values():
            if raw.get("kind") in {"lot", "coverage"}:
                continue
            record = copy.deepcopy(raw)
            record["scope"] = resolve_scope(record["scope"], lots)
            record["effective_status"] = "active"
            if issue := structure_issues.get(record["key"]):
                record["effective_status"] = "unknown"
                result["gaps"].append(data_gap(
                    issue[0], issue[1], record["scope"], record_id=record["id"], module_key=key,
                ))
            by_key[(key, record["key"])] = record
            records.append(record)
            if record["scope"]["kind"] == "unknown":
                result["gaps"].append(data_gap(
                    "scope_unknown", "要求的标段归属尚未确认", record["scope"],
                    record_id=record["id"], module_key=key,
                ))
            if record.get("structuring") != "complete":
                result["gaps"].append(data_gap(
                    "incomplete_structure", "已保留原文，部分业务条件尚未结构化", record["scope"],
                    record_id=record["id"], module_key=key,
                ))
        coverage = data.get("coverage", [])
        for topic in data.get("topics", []):
            entries = [c for c in coverage if c["topic"] == topic["key"]]
            if not entries:
                entries = [{"topic": topic["key"], "status": "unchecked",
                            "scope": {"kind": "unknown", "lot_refs": []},
                            "detail": "此主题尚未完成核对", "record_keys": []}]
            elif lots:
                # A 标段已提取不能替 B 标段完成覆盖；公共条目才可覆盖所有标段。
                covered_scopes = [resolve_scope(c["scope"], lots) for c in entries]
                entries = [*entries, *[{
                    "topic": topic["key"], "status": "unchecked",
                    "scope": {"kind": "lots", "lot_refs": [lot["code"] or lot["title"]]},
                    "detail": "此标段的主题尚未完成核对", "record_keys": [],
                } for lot in lots if not any(
                    matches_scope(scope, lot["lot_id"]) for scope in covered_scopes
                )]]
            for entry in entries:
                item = copy.deepcopy(entry)
                item.update(module_key=key, title=topic["title"])
                item["scope"] = resolve_scope(item["scope"], lots)
                linked = [accepted[k] for k in item["record_keys"] if k in accepted]
                item["record_ids"] = [r["id"] for r in linked]
                if item["status"] == "extracted" and (
                    not item["record_ids"] or len(item["record_ids"]) != len(item["record_keys"])
                ):
                    item["status"] = "pending"
                    item["detail"] = "关联要求尚未全部通过校验"
                if item["status"] == "extracted":
                    scopes = [resolve_scope(r["scope"], lots) for r in linked]
                    covered = (
                        all(s["kind"] == "common" for s in scopes)
                        if item["scope"]["kind"] == "common" else
                        item["scope"]["kind"] == "lots" and all(
                            any(matches_scope(s, lot_id) for s in scopes)
                            for lot_id in item["scope"]["lot_ids"]
                        )
                    )
                    if not covered:
                        item.update(status="pending", detail="关联要求未覆盖所声明的适用范围")
                # 过程说明可以保存，但它不能成为无证据的缺席性业务结论。
                item.pop("citations", None)
                if item["status"] == "not_applicable":
                    proof = proofs.get(item.get("review_id"))
                    if proof:
                        # 保存校验器最终选中的证据，读取时仍要检查此结论的资料权限。
                        item["citations"] = copy.deepcopy(proof["citations"])
                    else:
                        item.update(status="pending", detail="不适用结论尚未通过原文校验")
                result["coverage"].append(item)
                if item["status"] not in {"extracted", "not_applicable"}:
                    result["gaps"].append(data_gap(
                        "coverage_" + item["status"], item["detail"], item["scope"],
                        topic=item["topic"], module_key=key,
                    ))
        for gap in data.get("gaps", []):
            result["gaps"].append({**gap, "module_key": key,
                                   "scope": resolve_scope(gap["scope"], lots)})
        if module["status"] != "completed":
            result["gaps"].append(data_gap(
                "module_incomplete", "专题尚未完整完成：" + module["title"], module_key=key,
            ))
    for record in records:
        kind, key = record["kind"], record["module_key"]
        if kind == "format_node":
            parent = by_key.get((key, record.get("parent_key")))
            record["parent_id"] = parent["id"] if parent else None
            record["requirement_ids"] = [
                by_key[(key, k)]["id"] for k in record["requirement_keys"] if (key, k) in by_key
            ]
        if kind == "relation":
            subject = by_key.get((key, record["subject_key"]))
            target = by_key.get((key, record["object_key"]))
            if (
                not subject or not target
                or not scope_covers(subject["scope"], record["scope"])
                or not scope_covers(target["scope"], record["scope"])
                or subject["text"] != record["subject_text"]
                or target["text"] != record["object_text"]
            ):
                result["gaps"].append(data_gap(
                    "unresolved_relation", "关系端点或适用范围未确认", record["scope"],
                    record_id=record["id"],
                ))
                continue
            record.update(subject_id=subject["id"], object_id=target["id"])
            if record["predicate"] == "supersedes":
                target.setdefault("superseded_in", []).append(record["scope"])
            if record["predicate"] == "conflicts":
                for side in (subject, target):
                    side.setdefault("conflicts_in", []).append(record["scope"])
                result["gaps"].append(data_gap(
                    "conflict", record["text"], record["scope"], record_id=record["id"],
                ))
        bucket = {"fact": "facts", "requirement": "requirements",
                  "format_node": "format_nodes", "relation": "relations"}[kind]
        result[bucket].append(record)
    # 不把同义改写自动当成同一要求；所有已核实身份保留，避免后续引用悄然失效。
    result["gaps"] = list({fingerprint(g): g for g in result["gaps"]}.values())
    result["readiness"] = "partial" if result["gaps"] else "usable"
    if not any(result[k] for k in ("facts", "requirements", "format_nodes")):
        result["readiness"] = "unavailable"
    return result


class ContextInput(DataInput):
    snapshot_id: int = Field(gt=0)
    purpose: Literal["outline", "content", "check"]
    lot_id: int | None = Field(default=None, gt=0)
    requirement_ids: list[str] = Field(default_factory=list, max_length=500)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=200)


class ContextError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def build_context(data: dict, request: ContextInput) -> dict:
    lots = data["lots"]
    lot_id = request.lot_id
    if len(lots) > 1 and lot_id is None:
        raise ContextError("lot_selection_required", "请先选择一个编制标段")
    if lot_id is None and any(
        g["code"] == "lot_catalog_unknown"
        or (g["code"] == "scope_unknown" and g["scope"].get("lot_refs"))
        for g in data["gaps"]
    ):
        raise ContextError("lot_scope_unresolved", "存在未解决的分标线索，请确认标段后再获取依据")
    if lot_id is None and len(lots) == 1:
        lot_id = lots[0]["lot_id"]
    if lot_id is not None and lot_id not in {lot["lot_id"] for lot in lots}:
        raise ContextError("invalid_lot", "标段不属于此解析快照")
    def eligible(record: dict) -> bool:
        return (
            matches_scope(record["scope"], lot_id)
            and record.get("effective_status", "active") == "active"
            and not any(matches_scope(s, lot_id) for s in record.get("superseded_in", []))
            and not any(matches_scope(s, lot_id) for s in record.get("conflicts_in", []))
        )

    requirements = [r for r in data["requirements"] if eligible(r)]
    if request.purpose == "content":
        if not request.requirement_ids:
            raise ContextError("requirements_required", "正文上下文必须指定章节关联的要求")
        allowed = {r["id"] for r in requirements}
        if set(request.requirement_ids) - allowed:
            raise ContextError("invalid_requirements", "包含其它标段、失效或未确认适用的要求")
        requirements = [r for r in requirements if r["id"] in request.requirement_ids]
    gaps = [g for g in data["gaps"] if matches_scope(g["scope"], lot_id, unknown=True)]
    unresolved = [r for k in ("facts", "requirements", "format_nodes") for r in data[k]
                  if matches_scope(r["scope"], lot_id, unknown=True) and not eligible(r)
                  and not any(matches_scope(s, lot_id) for s in r.get("superseded_in", []))]
    facts = [r for r in data["facts"] if eligible(r)]
    nodes = [r for r in data["format_nodes"] if eligible(r)]
    # 树的父节点不适用时不把子节点冒充成根；下游同时收到明确的结构缺口。
    node_ids = {n["id"] for n in nodes}
    for node in nodes:
        if node.get("parent_id") and node["parent_id"] not in node_ids:
            gaps.append(data_gap("missing_parent", "所选范围的格式树父节点待确认", node["scope"],
                                 record_id=node["id"]))
    manifest = [r["id"] for r in requirements]
    page = requirements[request.offset:request.offset + request.limit]
    next_offset = request.offset + len(page)
    readiness = "partial" if gaps or unresolved else "usable"
    if not (requirements or facts or nodes):
        readiness = "unavailable"
    return {
        "schema_version": DATA_VERSION, "snapshot_id": request.snapshot_id,
        "purpose": request.purpose, "lot_id": lot_id, "facts": facts,
        "requirements": page, "format_nodes": nodes, "unresolved": unresolved,
        "relations": [r for r in data["relations"] if eligible(r)],
        "coverage": [c for c in data["coverage"]
                     if matches_scope(c["scope"], lot_id, unknown=True)],
        "gaps": gaps, "readiness": readiness, "references": [],
        "requirement_manifest": manifest, "total_requirements": len(manifest),
        "next_offset": next_offset if next_offset < len(manifest) else None,
    }
