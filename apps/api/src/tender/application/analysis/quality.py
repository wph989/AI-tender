"""执行是否结束与业务结论是否完备分别表达，问题身份不随描述改写变化。"""
from tender.application.knowledge.content import source_signature

QUALITY_STATUSES = {"self_check_passed", "needs_review", "needs_input", "unknown"}


def validate_project_claims(
    fields: list[dict], project_id: int,
) -> None:
    """发布前复核本项目来源边界，业务语义由 Agent 草稿自查负责。"""
    for field in fields:
        refs = [ref for value in field["values"] for ref in value["citations"]]
        own = {ref["source_id"] for ref in refs if ref["project_id"] == project_id}
        if not own:
            raise ValueError("项目结论及参考建议都须引用本项目相关要求；参考建议还须保留参考来源")


def quality_status(data: dict) -> str:
    explicit = data.get("quality_status")
    if explicit in QUALITY_STATUSES:
        return explicit
    # 执行结束不能证明质量通过；未结算时只依据已登记的问题表达状态。
    issues = data.get("quality_issues", [])
    if issues:
        return ("needs_input" if all(i.get("action") == "provide_input" for i in issues)
                else "needs_review")
    return "unknown"


def aggregate_quality(values: list[str]) -> str:
    for value in ("needs_review", "needs_input", "unknown"):
        if value in values:
            return value
    return "self_check_passed" if values else "unknown"


def input_changed(data: dict, sources: list[dict]) -> bool:
    """按专题实际消费的输入判断变化，未处理过的资料需要重新研究。"""
    return data.get("quality_input_signature") != source_signature(sources)


def refresh_input(state: dict, sources: list[dict]) -> None:
    """补入新资料后重新研究与审查，保留同版本成果，撤销旧版本证据。"""
    allowed = {(s["source_id"], s.get("version_id"), s.get("parse_run_id")) for s in sources}
    research = state.get("research", {})
    seen = {key: row for key, row in research.get("seen", {}).items()
            if (row["source_id"], row.get("version_id"), row.get("parse_run_id")) in allowed}
    research.update(seen=seen)
    items = [item for item in state.get("staged_items", [])
             if all(ref.get("block_id") in seen
                    for ref in item.get("business", {}).get("citations", []))]
    state["staged_items"] = items
    state["business_gaps"] = []
    workspace = state.get("agent_workspace")
    if not workspace:
        raise ValueError("补跑状态缺少当前Agent工作区")
    workspace.update(reviews={}, finalized=False, final_ids=[], draft_receipts={})
    for issue in workspace["issues"].values():
        if issue.get("action") == "provide_input":
            issue.update(action="read", status="open",
                         detail="资料已更新，重新核对：" + issue["detail"])
            issue.pop("missing_input", None)
