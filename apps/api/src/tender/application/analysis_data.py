"""解析业务契约与确定性投影；业务身份不依赖展示文字，语义仍由原文校验。"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Literal
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tender.application.knowledge import dedupe_citations, fingerprint, normalized, validate_items

DATA_VERSION = "1"


class DataInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DataCitation(DataInput):
    block_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)


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


class BusinessRecord(DataInput):
    key: str = Field(min_length=1, max_length=100)
    kind: Literal["fact", "requirement", "lot", "format_node", "relation"]
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)
    scope: DataScope
    citations: list[DataCitation] = Field(min_length=1)
    group: str = ""
    sort_order: int = Field(default=0, ge=0)
    category: str = "other"
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
        if self.kind == "lot" and not (self.code and self.code.strip()):
            raise ValueError("标段必须保留原文编号 code")
        if self.kind == "format_node" and self.node_type is None:
            raise ValueError("格式节点必须声明 node_type")
        if self.node_type == "group" and self.parent_key:
            raise ValueError("逻辑标容器必须是根节点")
        if self.kind == "relation" and not all(
            (self.predicate, self.subject_key, self.object_key)
        ):
            raise ValueError("关系必须声明 predicate/subject_key/object_key")
        if self.kind != "format_node" and (self.node_type or self.parent_key):
            raise ValueError("仅格式节点可声明父子结构")
        if self.kind != "relation" and (self.predicate or self.subject_key or self.object_key):
            raise ValueError("仅关系记录可声明关系端点")
        return self


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


def prepare_records(
    raw: list[BusinessRecord], state: dict, seen: dict, module_key: str,
) -> list[dict]:
    records = [entry.model_dump() for entry in raw]
    if len({entry["key"] for entry in records}) != len(records):
        raise ValueError("同批业务记录 key 重复")
    existing = {
        item["business"]["key"]: item["business"]
        for item in state.get("staged_items", []) if item.get("business")
    }
    combined = existing | {entry["key"]: entry for entry in records}
    result = []
    for entry in records:
        if entry["kind"] == "lot" and module_key != "project_basic_info_parsing":
            raise ValueError("标段目录由项目概况模块提交；其它模块填写 scope.lot_refs")
        if entry["kind"] == "format_node" and module_key != "bid_format_outline_parsing":
            raise ValueError("格式节点由投标文件格式模块提交")
        refs = list(entry["citations"])
        if entry["kind"] == "format_node":
            path, visited, current = [], {entry["key"]}, entry
            while current.get("parent_key"):
                parent = current["parent_key"]
                if parent not in combined or parent in visited:
                    raise ValueError("格式层级存在缺失父节点或循环，请先提交父节点")
                current = combined[parent]
                if current["kind"] != "format_node":
                    raise ValueError("格式父节点必须是格式节点")
                visited.add(parent)
                path.insert(0, current["title"])
                refs.extend(current["citations"])
            entry["parent_path"] = path
        if entry["kind"] == "relation":
            for endpoint in ("subject", "object"):
                target = combined.get(entry[endpoint + "_key"])
                if not target or target["kind"] in {"lot", "relation"}:
                    raise ValueError("关系端点必须先提交为本模块的事实、要求或格式节点")
                entry[endpoint + "_text"] = target["text"]
                refs.extend(target["citations"])
        # 所有属性与本条文本共用一套证据送审；禁止先审展示文字再补入未经验证的属性。
        item = validate_items([{
            "field": entry["title"], "group": entry["group"],
            "sort_order": entry["sort_order"],
            "values": [{"value": entry["text"], "citations": refs}],
        }], seen, align=False)[0]
        entry.update(id=record_identity(state, entry["key"]), module_key=module_key)
        entry["citations"] = item["values"][0]["citations"]
        item.update(id=entry["id"], business=entry)
        result.append(item)
    return result


def prepare_coverage(
    raw: list[CoverageInput], state: dict, seen: dict, topics: list[dict], module_key: str,
) -> tuple[list[dict], list[dict]]:
    allowed = {t["key"] for t in topics}
    entries, reviews = [], []
    for value in raw:
        entry = value.model_dump()
        if entry["topic"] not in allowed:
            raise ValueError("覆盖主题必须来自当前 Skill 的 coverage.json")
        if entry["status"] == "extracted" and not entry["record_keys"]:
            raise ValueError("已提取的主题必须关联 record_keys")
        if entry["status"] == "not_applicable":
            if not entry["citations"]:
                raise ValueError("确认不适用必须提供原文依据")
            item = validate_items([{
                "field": "主题不适用：" + entry["topic"],
                "values": [{"value": entry["detail"], "citations": entry["citations"]}],
            }], seen, align=False)[0]
            item["id"] = record_identity(state, "coverage:" + fingerprint(entry))
            item["business"] = {
                "id": item["id"],
                "key": "coverage:" + fingerprint([entry["topic"], entry["scope"]]),
                "kind": "coverage", "scope": entry["scope"], "module_key": module_key,
                "topic": entry["topic"], "text": entry["detail"],
            }
            entry["review_id"] = item["id"]
            reviews.append(item)
        entries.append(entry)
    return entries, reviews


def module_data(state: dict) -> dict:
    records = []
    for item in state.get("staged_items", []):
        if item.get("verification") != "supported" or not item.get("business"):
            continue
        record = copy.deepcopy(item["business"])
        record["verification"] = "supported"
        record["citations"] = dedupe_citations([
            ref for value in item["values"] for ref in value["citations"]
        ])
        records.append(record)
    return {
        "schema_version": DATA_VERSION, "records": records,
        "coverage": copy.deepcopy(state.get("business_coverage", [])),
        "gaps": copy.deepcopy(state.get("business_gaps", [])),
        "topics": copy.deepcopy(state.get("business_topics", [])),
        "research_summary": state.get("draft", {}).get("research_summary", ""),
    }


def display_items(items: list[dict]) -> list[dict]:
    """校验单元包含内部业务属性，页面只接收展示投影和可回查的记录身份。"""
    result = []
    for item in items:
        business = item.get("business")
        if business and business["kind"] == "coverage":
            continue
        rendered = {k: v for k, v in item.items() if k != "business"}
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


def assemble_dataset(modules: list[dict], lots: list[dict]) -> dict:
    """仅编译通过校验的业务记录；模块执行完成不替代主题覆盖和适用范围。"""
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
        accepted = {r["key"]: r for r in data.get("records", []) if r["kind"] != "coverage"}
        # 旧检查点的证明 key 可能相同；覆盖条目固定 review_id，不按业务 key 合并证明。
        proofs = {r["id"]: r for r in data.get("records", []) if r["kind"] == "coverage"}
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
                    "scope": {"kind": "lots", "lot_refs": [lot["code"]]},
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
