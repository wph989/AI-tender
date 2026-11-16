"""Agent 工作区：只维护草稿版本、自查凭据和提交一致性，不安排业务阶段。"""

from __future__ import annotations

import copy
from typing import Literal

from pydantic import Field, ValidationError

from tender.application.analysis.context import evidence_version
from tender.application.analysis.contract import FLOW_VERSION
from tender.application.analysis.data import (
    DataInput,
    DataScope,
    SynthesisRecord,
    format_tree_issues,
    module_data,
    prepare_records,
    record_identity,
    scope_covers,
)
from tender.application.analysis.protocol import SubmissionRecord
from tender.application.knowledge.content import fingerprint, normalized
from tender.application.shared.validation import InputError, schema_feedback

AGENT_PROTOCOL = FLOW_VERSION


def resume_workspace(previous: dict) -> dict:
    """新attempt携带工作成果；同attempt恢复不经过这里，不能借此重置硬预算。"""
    state = copy.deepcopy(previous)
    if not state:
        return state
    if state.get("topic_flow") or not state.get("agent_workspace"):
        raise InputError.for_field("state", "旧阶段检查点不能补跑为新流程，请新建报告")
    if "research" in state:
        state["research"]["tool_calls"] = 0
    for key in (
        "draft", "tool_results", "tool_outcomes", "tool_call_keys", "stop_reason",
        "quality_status", "quality_issues", "model_unavailable_retries", "subagent_retries",
    ):
        state.pop(key, None)
    book = state["agent_workspace"]
    book.update(finalized=False, final_ids=[], draft_receipts={}, review_receipts={},
                attempt_serial=book.get("attempt_serial", 0) + 1)
    state["staged_items_verified"] = False
    return state


class DraftRecord(SubmissionRecord):
    # 范围属于结果数据；不再要求先改变研究工作的阶段才能修正范围。
    scope: DataScope
    work_ids: list[str] = Field(default_factory=list, max_length=50)
    version: int | None = Field(default=None, ge=1)


class ReviewRecord(DataInput):
    record_id: str
    version: int = Field(ge=1)
    status: Literal["passed", "needs_revision"]
    reason: str = Field(min_length=1, max_length=2000)
    block_ids: list[str] = Field(min_length=1, max_length=160)
    issue_ids: list[str] = Field(default_factory=list)


class MissingInput(DataInput):
    """缺件凭据的固定结构，避免错误形状在集合校验时抛出原始 TypeError。"""

    file_name: str = Field(min_length=1, max_length=300, pattern=r"\S")
    reference_ids: list[str] = Field(min_length=1, max_length=160)
    checked_source_ids: list[int] = Field(min_length=1, max_length=160)


class ReviewIssue(DataInput):
    id: str | None = None
    status: Literal["open", "resolved"] = "open"
    topic: str | None = None
    target: str | None = None
    detail: str = Field(min_length=1, max_length=2000)
    action: Literal["read", "repair", "provide_input"] | None = None
    record_ids: list[str] | None = None
    block_ids: list[str] | None = None
    missing_input: MissingInput | None = None


class DraftWorkspace:
    def __init__(self, state: dict, seen: dict, module_key: str):
        self.state, self.seen, self.module_key = state, seen, module_key
        self.book = state.setdefault(
            "agent_workspace",
            {
                "protocol": AGENT_PROTOCOL,
                "reviews": {},
                "issues": {},
                "notes": {},
                "history": [],
                "final_ids": [],
                "finalized": False,
            },
        )
        if self.book["protocol"] != AGENT_PROTOCOL:
            raise ValueError("草稿协议不兼容，请新建报告")
        state.setdefault("staged_items", [])

    def items(self) -> dict[str, dict]:
        return {item["id"]: item for item in self.state["staged_items"]}

    def _blocks(self, ids: list[str]) -> None:
        if not ids or set(ids) - self.seen.keys():
            raise InputError.for_field("block_ids", "必须选择已读取的非空原文ID")

    def _editable(self) -> None:
        if self.book["finalized"]:
            raise InputError.for_field("final", "本次结果已最终提交，不能继续修改同一提交")

    def dependencies(self, item: dict) -> set[str]:
        data = item["business"]
        keys = {data[k] for k in ("parent_key", "subject_key", "object_key") if data.get(k)}
        keys.update(data.get("requirement_keys", []))
        by_key = {i["business"]["key"]: i["id"] for i in self.items().values()}
        if keys - by_key.keys():
            raise InputError.for_field("dependencies", "草稿所依赖的记录已删除，需修正依赖")
        return {by_key[k] for k in keys}

    def signature(self, rid: str) -> str:
        items, visited, pending, versions = self.items(), set(), [rid], []
        while pending:
            key = pending.pop()
            if key in visited:
                continue
            if key not in items:
                raise InputError.for_field("record_id", "草稿不存在或已删除")
            visited.add(key)
            item = items[key]
            versions.append(
                [
                    key,
                    item["draft_version"],
                    sorted(
                        (ref["block_id"], evidence_version(self.seen[ref["block_id"]]))
                        for ref in item["business"]["citations"]
                    ),
                ]
            )
            pending.extend(self.dependencies(item))
        return fingerprint(sorted(versions))

    def review_current(self, rid: str) -> bool:
        receipt = self.book["reviews"].get(rid)
        if not receipt or receipt["status"] != "passed":
            return False
        try:
            return receipt["signature"] == self.signature(rid) and all(
                key in self.seen and evidence_version(self.seen[key]) == value
                for key, value in receipt["evidence_versions"].items()
            )
        except (InputError, KeyError):
            return False

    def save_records(
        self, records: list[dict], call_id: str, delete_ids: list[str] | None = None
    ) -> dict:
        replay = self.book.setdefault("draft_receipts", {}).get(call_id)
        if replay:
            if replay["input"] != fingerprint([records, delete_ids or []]):
                raise InputError.for_field("call_id", "同一工具调用不能修改参数")
            return copy.deepcopy(replay["result"])
        self._editable()
        accepted, rejected = [], []
        delete_ids = delete_ids or []
        items = self.items()
        if set(delete_ids) - items.keys():
            raise InputError.for_field("delete_ids", "只能删除已有草稿ID")
        # 删除也留痕；引用被删除项的草稿会在复核或最终提交时得到具体依赖错误。
        for rid in delete_ids:
            self.book["history"].append({"event": "delete", "record": copy.deepcopy(items[rid])})
        self.state["staged_items"] = [i for i in items.values() if i["id"] not in delete_ids]
        aliases: dict[str, str] = {}
        for index, raw in enumerate(records):
            try:
                row = DraftRecord.model_validate(raw)
                self._blocks(row.block_ids)
                items = self.items()
                old = items.get(row.id or "")
                if row.id and old is None:
                    raise InputError.for_field("id", "修改必须使用已有草稿ID")
                if old and row.version != old["draft_version"]:
                    raise InputError.for_field(
                        "version", f"草稿当前版本为{old['draft_version']}，请回读后修改"
                    )
                # 新attempt可能再次收到call1，新增身份必须与沿用的草稿区分。
                key = (old["business"]["key"] if old else
                       f"draft:{self.book.get('attempt_serial', 0)}:{call_id}:{index}")
                value = row.model_dump(exclude={"id", "key", "version", "work_ids", "block_ids"})
                if row.key and row.key in aliases:
                    raise InputError.for_field("key", "同批临时key不能重复")
                for field in ("parent_key", "subject_key", "object_key"):
                    if value.get(field):
                        value[field] = aliases.get(value[field], value[field])
                        if value[field] not in items:
                            raise InputError.for_field(field, "请先保存依赖记录，再使用其回执ID")
                        value[field] = items[value[field]]["business"]["key"]
                value["requirement_keys"] = [aliases.get(k, k) for k in value["requirement_keys"]]
                if set(value["requirement_keys"]) - items.keys():
                    raise InputError.for_field("requirement_keys", "请使用已有要求事项ID")
                value["requirement_keys"] = [
                    items[k]["business"]["key"] for k in value["requirement_keys"]
                ]
                section: dict = next(
                    (
                        s
                        for s in self.state["output_schema"]["sections"]
                        if s["title"] in {row.group, "*"}
                    ),
                    {},
                )
                if not value.get("title"):
                    title = row.content.get(section.get("title_column", ""))
                    value["title"] = ("；".join(title) if isinstance(title, list) else title or "")[
                        :300
                    ]
                value.update(
                    key=key,
                    structuring="complete",
                    citations=[{"block_id": b} for b in row.block_ids],
                    sort_order=old["business"]["sort_order"] if old else len(items),
                )
                prepared = prepare_records(
                    [SynthesisRecord.model_validate(value)], self.state, self.seen, self.module_key
                )[0]
                semantic = fingerprint(
                    {
                        k: v
                        for k, v in prepared["business"].items()
                        if k not in {"id", "key", "sort_order"}
                    }
                )
                # 幂等回执以实际内容为准；新的调用ID不能把同一事项再次新增。
                same = next(
                    (i for i in items.values() if i.get("draft_signature") == semantic), None
                )
                if old is None and same:
                    old, prepared = same, same
                version = (
                    old["draft_version"]
                    if old and old.get("draft_signature") == semantic
                    else old["draft_version"] + 1
                    if old
                    else 1
                )
                prepared.update(
                    draft_version=version,
                    draft_signature=semantic,
                    verification="pending",
                    review_status="needs_review",
                    work_ids=row.work_ids,
                )
                changed = not old or old["draft_version"] != version
                items[prepared["id"]] = prepared
                if row.key:
                    aliases[row.key] = prepared["id"]
                self.state["staged_items"] = list(items.values())
                if changed:
                    self.book["history"].append(
                        {"event": "draft", "record": copy.deepcopy(prepared)}
                    )
                accepted.append(
                    {
                        "index": index,
                        "id": prepared["id"],
                        "version": version,
                        "status": "saved" if changed else "unchanged",
                    }
                )
            except (InputError, ValidationError) as exc:
                rejected.append({
                    "index": index,
                    "error": schema_feedback(exc) if isinstance(exc, ValidationError) else str(exc),
                    "fields": exc.field_issues if isinstance(exc, InputError) else [],
                })
        result = {"accepted": accepted, "rejected": rejected, "deleted": delete_ids}
        self.book["draft_receipts"][call_id] = {
            "input": fingerprint([records, delete_ids]),
            "result": copy.deepcopy(result),
        }
        return result

    def record_review(self, records: list[dict], issues: list[dict], call_id: str) -> dict:
        receipts = self.book.setdefault("review_receipts", {})
        digest = fingerprint([records, issues])
        if call_id in receipts:
            if receipts[call_id]["input"] != digest:
                raise InputError.for_field("call_id", "同一工具调用不能修改参数")
            return copy.deepcopy(receipts[call_id]["result"])
        self._editable()
        next_issues = copy.deepcopy(self.book["issues"])
        issue_receipts, review_receipts = [], []
        for index, raw in enumerate(issues):
            issue = ReviewIssue.model_validate(raw)
            previous = next_issues.get(issue.id or "")
            if issue.id and previous is None:
                raise InputError.for_field("issues.id", "修改问题必须使用回执ID")
            value = (previous or {}) | issue.model_dump(exclude_none=True, exclude={"id"})
            if not all(value.get(k) for k in ("topic", "target", "action")):
                raise InputError.for_field("issues", "新增问题须填写topic、target和action")
            value.setdefault("record_ids", [])
            value.setdefault("block_ids", [])
            if value["status"] != "resolved" and set(value["record_ids"]) - self.items().keys():
                raise InputError.for_field("issues.record_ids", "问题只能关联已有草稿")
            if value["block_ids"]:
                self._blocks(value["block_ids"])
            if value["action"] == "provide_input":
                proof = value.get("missing_input")
                if not isinstance(proof, dict):
                    raise InputError.for_field(
                        "missing_input", "缺件须填写文件名、转引原文和已核对资料ID"
                    )
                # 更新问题可以沿用检查点中的凭据，也需校验其完整结构。
                proof = MissingInput.model_validate(proof).model_dump()
                self._blocks(proof["reference_ids"])
                sources = {s["source_id"] for s in self.state.get("authorized_sources", [])}
                if sources and set(proof["checked_source_ids"]) - sources:
                    raise InputError.for_field("checked_source_ids", "只能选择授权资料ID")
            iid = issue.id or record_identity(
                self.state, f"issue:{self.book.get('attempt_serial', 0)}:{call_id}:{index}"
            )
            value["id"] = iid
            next_issues[iid] = value
            issue_receipts.append({"id": iid, "status": value["status"]})
        next_reviews = copy.deepcopy(self.book["reviews"])
        for raw in records:
            review = ReviewRecord.model_validate(raw)
            item = self.items().get(review.record_id)
            if item is None or item["draft_version"] != review.version:
                raise InputError.for_field("version", "自查必须引用当前草稿ID与版本")
            self._blocks(review.block_ids)
            if set(review.issue_ids) - next_issues.keys():
                raise InputError.for_field("issue_ids", "请选择已登记的问题ID")
            value = review.model_dump() | {
                "signature": self.signature(review.record_id),
                "evidence_versions": {
                    key: evidence_version(self.seen[key]) for key in review.block_ids
                },
            }
            next_reviews[review.record_id] = value
            review_receipts.append(
                {"id": review.record_id, "version": review.version, "status": review.status}
            )
        self.book.update(issues=next_issues, reviews=next_reviews)
        self.book["history"].append(
            {
                "event": "review",
                "records": copy.deepcopy(records),
                "issues": [copy.deepcopy(next_issues[i["id"]]) for i in issue_receipts],
            }
        )
        result = {"reviews": review_receipts, "issues": issue_receipts}
        receipts[call_id] = {"input": digest, "result": copy.deepcopy(result)}
        return result

    def finalize(self, ids: list[str], summary: str) -> dict:
        if self.book["finalized"]:
            if ids == self.book["final_ids"]:
                return {"final": True, "record_ids": ids}
            raise InputError.for_field("final", "本次最终结果已提交")
        items = self.items()
        if len(set(ids)) != len(ids) or set(ids) - items.keys():
            raise InputError.for_field("record_ids", "最终结果必须选择不重复的现有草稿ID")
        if not summary.strip():
            raise InputError.for_field("summary", "请说明最终结论与未解决范围")
        structural_errors = format_tree_issues([items[rid]["business"] for rid in ids])
        if structural_errors:
            raise InputError.for_field("record_ids", next(iter(structural_errors.values()))[1])
        by_key = {i["business"]["key"]: i["business"] for i in items.values()}
        # 目录内编号、名称和别名共用身份；共享简称保留所有候选，不能随意选一个。
        aliases: dict[str, set[tuple]] = {}
        for index, lot in enumerate(self.state.get("topic_lots", [])):
            values = ([lot] if isinstance(lot, str) else [
                lot.get("code"), lot.get("title"), lot.get("name"),
                *(lot.get("aliases") or []),
            ])
            lot_id = None if isinstance(lot, str) else lot.get("lot_id", lot.get("id"))
            identity = ("lot", lot_id) if lot_id is not None else ("entry", index)
            for value in values:
                if value:
                    aliases.setdefault(normalized(value), set()).add(identity)

        def comparable_scope(row):
            scope = row["scope"]
            if scope["kind"] != "lots":
                return scope | {"lot_ids": []}
            lot_ids: list[tuple] = []
            for ref in scope["lot_refs"]:
                matches = aliases.get(normalized(ref), set())
                if len(matches) > 1:
                    return {"kind": "unknown", "lot_ids": [], "lot_refs": scope["lot_refs"]}
                # 专题可早于项目概况完成；目录尚缺的标段继续按取证原文比较。
                lot_ids.append(next(iter(matches)) if matches else ("ref", normalized(ref)))
            return scope | {"lot_ids": lot_ids}

        for rid in ids:
            if not self.review_current(rid):
                raise InputError.for_field(
                    "record_ids", f"{rid}缺少当前版本或依赖版本的通过自查记录"
                )
            row = items[rid]["business"]
            scope = comparable_scope(row)
            if scope["kind"] == "unknown":
                raise InputError.for_field("scope", "正式结果的适用范围尚未确认")
            if self.dependencies(items[rid]) - set(ids):
                raise InputError.for_field("record_ids", "最终结果缺少父节点或明确依赖的事项")
            # 父节点和两个端点都须覆盖本条适用范围，防止引用扩大成全项目结论。
            for field in ("parent_key", "subject_key", "object_key"):
                if row.get(field) and not scope_covers(
                    comparable_scope(by_key[row[field]]), scope
                ):
                    raise InputError.for_field(field, "父节点或关系端点未覆盖当前记录的适用范围")
            if row["kind"] == "relation":
                for side in ("subject", "object"):
                    if row[side + "_text"] != by_key[row[side + "_key"]]["text"]:
                        raise InputError.for_field(
                            "record_ids", "关系端点正文已变化，请重新保存关系"
                        )
        unresolved = [i for i in self.book["issues"].values() if i["status"] == "open"]
        linked_issues = {iid for rid in ids for iid in self.book["reviews"][rid]["issue_ids"]}
        if any(
            (set(i["record_ids"]) & set(ids) or i["id"] in linked_issues)
            for i in unresolved
        ):
            raise InputError.for_field("record_ids", "选中草稿仍有关联的未解决错误")
        # 校验全部完成后一次性形成投影；保存自查或退出Agent不能隐式发布草稿。
        self.book.update(finalized=True, final_ids=list(ids), summary=summary)
        self.state["quality_issues"] = [
            dict(
                i,
                issue_id=i["id"],
                evidence_ids=i["block_ids"],
                kind="reference" if i["action"] == "provide_input" else "unsupported",
            )
            for i in unresolved
        ]
        self.state["quality_status"] = (
            "needs_input"
            if unresolved and all(i["action"] == "provide_input" for i in unresolved)
            else "needs_review"
            if unresolved
            else "verified"
        )
        # 缺件和遗漏沿用既有缺口投影，正式页面和下游快照都能保留同一问题身份。
        self.state["business_gaps"] = [
            {"key": "issue:" + i["id"], "issue_id": i["id"], "topic": i["topic"],
             "target": i["target"], "detail": i["detail"], "action": i["action"],
             "code": "unresolved_reference" if i["action"] == "provide_input" else "omission",
             "scope": {"kind": "unknown", "lot_refs": []}, "evidence_ids": i["block_ids"],
             **({"missing_input": i["missing_input"]} if i.get("missing_input") else {})}
            for i in unresolved
        ]
        for rid in ids:
            items[rid].update(verification="supported", review_status="current")
        self.state["draft"] = {
            "fields": [copy.deepcopy(items[rid]) for rid in ids],
            "relations": [],
            "research_summary": summary,
        }
        self.state["draft"]["business_data"] = module_data(self.state)
        return {"final": True, "record_ids": ids, "quality_status": self.state["quality_status"]}

    def progress(self) -> dict:
        return {
            "protocol": AGENT_PROTOCOL,
            "activity": self.book.get("activity"),
            "topics": [],
            "audit_round": 0,
            "draft_count": len(self.items()),
            "reviewed_count": sum(self.review_current(rid) for rid in self.items()),
            "unresolved_issues": sum(i["status"] == "open" for i in self.book["issues"].values()),
        }
