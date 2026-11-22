"""执行是否结束与业务结论是否完备分别表达，问题身份不随描述改写变化。"""

import re

from tender.application.knowledge.content import source_signature

QUALITY_STATUSES = {"self_check_passed", "needs_review", "needs_input", "unknown"}
ABSENCE_TERMS = (
    "未载明", "未约定", "未见", "未检索到", "未找到", "无法认定", "条款缺失",
    "未明示", "未列示", "未单独列示", "未给出", "未规定", "未明确", "未划分", "缺失细节",
)


def is_absence_claim(field: dict) -> bool:
    """单段引文不能证明整份文件未约定；缺口应单独登记。"""
    body = field["field"] + "".join(value["value"] for value in field["values"])
    quotes = "\n".join(ref["quote"] for value in field["values"] for ref in value["citations"])
    return any(term in body and term not in quotes for term in ABSENCE_TERMS)


def validate_project_claims(
    fields: list[dict], project_id: int, *, defer_semantics: bool = False,
) -> None:
    """检查项目结论的来源边界和可确定的缺口、修订约束。"""
    for field in fields:
        refs = [ref for value in field["values"] for ref in value["citations"]]
        own = {ref["source_id"] for ref in refs if ref["project_id"] == project_id}
        if not own:
            raise ValueError("项目结论及参考建议都须引用本项目相关要求；参考建议还须保留参考来源")
        if defer_semantics and field.get("business"):
            continue
        body = field["field"] + field.get("note", "") + "".join(
            value["value"] for value in field["values"]
        )
        if is_absence_claim(field):
            raise ValueError("检索缺口只能写入 research_summary，单段引文不能证明整份文件未约定")
        if "补充" in body and re.search("调整|更正|修订|修改", body) and len(own) < 2:
            raise ValueError("跨文件修订结论须在同一字段同时引用原条款与补充文件")


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
    research.update(seen=seen, dependencies={})
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
