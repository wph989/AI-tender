"""执行是否结束与业务结论是否完备分别表达，问题身份不随描述改写变化。"""

import copy

from tender.application.knowledge.content import fingerprint, normalized, source_signature

QUALITY_STATUSES = {"verified", "needs_review", "needs_input", "unknown"}
ISSUE_ACTIONS = {"read", "repair", "provide_input"}


def issue_identity(issue: dict) -> str:
    # 主题只是责任归属；同一事项、范围及目标的缺口跨主题只修一次。
    scope = issue.get("scope", {"kind": "unknown", "lot_refs": []})
    scope = {**scope, "lot_refs": sorted(set(scope.get("lot_refs", [])))}
    return fingerprint([
        issue.get("kind", "unsupported"), scope,
        sorted(issue.get("record_keys", [])), normalized(str(issue.get("target", ""))),
    ])


def merge_issues(issues: list[dict]) -> list[dict]:
    result: dict[str, dict] = {}
    for raw in issues:
        issue = copy.deepcopy(raw)
        issue.setdefault("kind", "unsupported")
        issue.setdefault("action", "repair")
        key = issue.get("issue_id") or issue_identity(issue)
        issue["issue_id"] = key
        issue["topics"] = sorted(set(issue.get("topics", [])) | {issue["topic"]})
        if key in result:
            previous = result[key]
            previous["topics"] = sorted(set(previous["topics"]) | set(issue["topics"]))
            previous["evidence_ids"] = sorted(set(previous.get("evidence_ids", []))
                                               | set(issue.get("evidence_ids", [])))
            # 新证据确认缺件后需要用户输入；历史“补读”指令不能继续驱动空转。
            if issue["action"] == "provide_input":
                previous["action"] = "provide_input"
        else:
            result[key] = issue
    return list(result.values())


def quality_status(data: dict) -> str:
    explicit = data.get("quality_status")
    if explicit in QUALITY_STATUSES:
        return explicit
    # 历史结果无独立质量结算记录，不能根据 completed 猜测所有问题均已核清。
    issues = data.get("quality_issues", [])
    if issues:
        return ("needs_input" if all(i.get("action") == "provide_input" for i in issues)
                else "needs_review")
    return "unknown"


def aggregate_quality(values: list[str]) -> str:
    for value in ("needs_review", "needs_input", "unknown"):
        if value in values:
            return value
    return "verified" if values else "unknown"


def input_changed(data: dict, sources: list[dict], previous_sources: list[dict]) -> bool:
    """按专题上次处理的资料判断变化，历史无签名时沿用报告的输入快照。"""
    # 局部重新解析会推进报告快照，但不能替其他专题消费尚未处理的新附件。
    previous = data.get("quality_input_signature") or source_signature(previous_sources)
    return previous != source_signature(sources)


def refresh_input(state: dict, sources: list[dict]) -> None:
    """补入新资料后重新研究与审查，保留同版本成果，撤销旧版本证据。"""
    allowed = {(s["source_id"], s.get("version_id"), s.get("parse_run_id")) for s in sources}
    research = state.get("research", {})
    seen = {key: row for key, row in research.get("seen", {}).items()
            if (row["source_id"], row.get("version_id"), row.get("parse_run_id")) in allowed}
    research.update(seen=seen, dependencies={})
    items = [item for item in state.get("staged_items", [])
             if all(ref.get("block_id") in seen
                    for ref in item.get("business", {}).get("citations", []))]
    for item in items:
        item["review_status"] = "needs_review"
    state["staged_items"] = items
    # 输入已变化时旧版回退也必须重新核对，不能从旁路恢复已撤销的依据。
    state["business_previous"] = {}
    state.pop("rejected_records", None)
    state.pop("review_context_key", None)
    state["business_gaps"] = []
    state.pop("research_completed", None)
    flow = state.get("topic_flow", {})
    flow.update(phase="research", audit={"round": 0, "results": {}})
    flow.pop("synthesis_finished", None)
    flow["evidence_topics"] = {key: value for key, value in flow.get("evidence_topics", {}).items()
                               if key in seen}
    keys = {item["business"]["key"] for item in items}
    for entry in flow.get("entries", {}).values():
        entry.update(status="researching", requested_status="researching",
                     detail="资料已更新，重新核对")
        entry["evidence_ids"] = [key for key in entry["evidence_ids"] if key in seen]
        entry["record_keys"] = [key for key in entry["record_keys"] if key in keys]
        # 旧“缺件已确认”及查漏缓存不再成立，新的资料必须参与核对。
        for field in ("findings", "dispositions", "tasks"):
            entry[field] = {}
        entry["references"] = []
        entry["unreviewed_evidence"] = list(entry["evidence_ids"])
    flow.pop("research_searches", None)


def settle_quality(
    state: dict, issues: list[dict], *, audited_topics: set[str] | None = None,
) -> list[dict]:
    issues = merge_issues(issues)
    state["quality_issues"] = issues
    state["quality_status"] = (
        "needs_input" if issues and all(i["action"] == "provide_input" for i in issues)
        else "needs_review" if issues else "verified"
    )
    # 同一身份供前端缺口、进度及停止说明共用，避免一处合并而另一处重复统计。
    # 已审主题的历史程序缺口由本轮真实问题取代；未审主题的原有缺口继续保留。
    audited = audited_topics or set()
    gaps = [g for g in state.get("business_gaps", []) if not g.get("issue_id")
            and not (g.get("topic") in audited and g["key"].startswith(
                ("topic:", "finding:", "coverage:", "record:", "research:")))]
    for issue in issues:
        gaps.append({"key": "issue:" + issue["issue_id"], "issue_id": issue["issue_id"],
                     "topic": issue["topic"], "topics": issue["topics"],
                     "scope": issue.get("scope", {"kind": "unknown", "lot_refs": []}),
                     "code": issue["kind"], "kind": issue["kind"], "action": issue["action"],
                     "detail": issue["detail"], "target": issue.get("target", ""),
                     "record_keys": issue.get("record_keys", []),
                     "record_id": next((item["id"] for item in state.get("staged_items", [])
                                        if item.get("business", {}).get("key")
                                        in issue.get("record_keys", [])), None),
                     "evidence_ids": issue.get("evidence_ids", [])})
    state["business_gaps"] = gaps
    return issues
