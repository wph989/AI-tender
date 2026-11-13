"""专题业务状态及状态转换；框架回调只触发转换，不各自维护阶段组合。"""

from typing import Any, Literal, TypedDict, cast


class AnalysisState(TypedDict, total=False):
    topic_flow: dict[str, Any]
    model_round_seconds: float
    research_completed: dict[str, Any]
    research: dict[str, Any]
    staged_items: list[dict[str, Any]]
    staged_relations: list[dict[str, Any]]
    staged_items_verified: bool
    staged_prompt_ids: list[str]
    pending_final: dict[str, Any]
    topic_final_requested: dict[str, Any]
    recovery_finish_requested: str
    progress_signature: str
    no_progress_rounds: int
    draft: dict[str, Any]
    business_previous: dict[str, Any]
    rejected_records: dict[str, Any]
    gap_notes: list[str]
    business_coverage: list[dict[str, Any]]
    business_gaps: list[dict[str, Any]]


Phase = Literal["research", "synthesis", "verification", "completed"]


def clear_record_gaps(state: dict, item_ids: set[str]) -> None:
    """事项重新核实或其证明范围被替代后，展示不能继续沿用旧拒绝原因。"""
    resolved = [g for g in state.get("business_gaps", [])
                if g["key"].removeprefix("record:") in item_ids and g["key"].startswith("record:")]
    state["business_gaps"] = [g for g in state.get("business_gaps", []) if g not in resolved]
    notes = tuple(g["topic"] + "：" + g["detail"] for g in resolved)
    state["gap_notes"] = [note for note in state.get("gap_notes", []) if not note.startswith(notes)]


def published_items(snapshot: dict, *, final: bool = False) -> list[dict]:
    """待修订版本校验期间仍显示旧核实内容；最终成果只消费当前有效版本。"""
    flow = snapshot.get("topic_flow", {})
    deferred = flow.get("output_mode") == "after-research"
    if deferred and not final and not flow.get("release_results"):
        return []
    items = {item["id"]: item for item in snapshot.get("staged_items", [])}
    if snapshot.get("topic_flow"):
        for key, old in snapshot.get("business_previous", {}).items():
            if items.get(key, {}).get("verification") != "supported":
                items[key] = old
    valid = [item for item in items.values() if item.get("verification") == "supported"
             and not ((final or deferred) and item.get("review_status") == "needs_review")]
    if flow.get("protocol") in {"research-v2", "research-v3"}:
        reviewed = flow.get("audit", {}).get("record_topics", {})
        valid = [item for item in valid if item.get("review_status") == "current" and {
            e["topic"] for e in flow["entries"].values()
            if item.get("business", {}).get("key") in e["record_keys"]
        } <= set(reviewed.get(item["id"], []))]
        # 父节点及关系端点未经审查时，下游记录不能借独立支持判定进入部分成果。
        while True:
            keys = {item["business"]["key"] for item in valid}
            filtered = [item for item in valid if {
                item["business"].get(k) for k in ("parent_key", "subject_key", "object_key")
                if item["business"].get(k)
            } | set(item["business"].get("requirement_keys", [])) <= keys]
            if len(filtered) == len(valid):
                break
            valid = filtered
    return valid


class AnalysisTransitions:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        # 保留原字典身份与未知的历史字段，检查点、工具重放和预算继续共享同一份状态。
        self.state = cast(AnalysisState, snapshot)

    @property
    def phase(self) -> Phase:
        if self.state.get("topic_flow", {}).get("phase") == "research":
            return "research"
        if not self.state.get("research_completed"):
            return "research"
        if any(
            item.get("verification") == "pending" for item in self.state.get("staged_items", [])
        ):
            return "verification"
        if self.state.get("draft"):
            return "completed"
        return "synthesis"

    def evidence_changed(self) -> None:
        if not self.state.pop("research_completed", None):
            return
        # 新证据改变综合依据；预算、已读原文和工具幂等账必须保留，旧完成意图必须撤销。
        self.state.pop("draft", None)
        self.state.pop("pending_final", None)
        self.state.pop("business_previous", None)
        self.state.pop("rejected_records", None)
        self.state.pop("gap_notes", None)
        self.state.update(
            {
                "staged_items": [],
                "staged_relations": [],
                "business_coverage": [],
                "business_gaps": [],
                "staged_items_verified": True,
                # 新证据重建成果后必须重新展示，不能因 ID 相同漏掉改写过的条目。
                "staged_prompt_ids": [],
            }
        )

    def research_completed(self, checkpoint: dict[str, Any]) -> None:
        self.state["research_completed"] = checkpoint

    def enter_research(self) -> None:
        """研究增量撤销旧完成意图，但保留正文和与新证据无关的审查结果。"""
        flow = self.state.get("topic_flow", {})
        if flow.get("phase") != "research":
            self.state.pop("progress_signature", None)
            self.state["no_progress_rounds"] = 0
        flow["phase"] = "research"
        flow.pop("synthesis_finished", None)
        self.state.pop("pending_final", None)
        self.state.pop("topic_final_requested", None)

    def finish_research(self, checkpoint: dict[str, Any], *, reason: str = "") -> None:
        """所有研究出口共用同一阶段转换，已有草稿直接进入审查。"""
        flow = self.state.get("topic_flow", {})
        if flow.get("phase") == "research":
            # 研究的空转次数不能转嫁给第一次综合，否则模型还没提交机会就会被结束。
            self.state.pop("progress_signature", None)
            self.state["no_progress_rounds"] = 0
        flow["phase"] = "synthesis"
        self.research_completed(checkpoint)
        if reason:
            flow["research_stop_reason"] = reason
        if flow.get("protocol") == "research-v3" and self.state.get("staged_items"):
            flow["synthesis_finished"] = True
        self.state.pop("recovery_finish_requested", None)

    def cancel_completion(self) -> None:
        """新提交必须重新表达完成意图，不能借用前一批的final发布错误改写。"""
        self.take_final()
        self.state.pop("topic_final_requested", None)
        self.state.get("topic_flow", {}).pop("synthesis_finished", None)

    def start_review(self) -> None:
        flow = self.state.get("topic_flow", {})
        flow["phase"] = "review"
        flow.pop("synthesis_work_origins", None)

    def end_review(self) -> None:
        self.state.get("topic_flow", {})["phase"] = "synthesis"

    def replace_items(self, items: list[dict[str, Any]]) -> None:
        self.state["staged_items"] = items

    def mark_verified(self, research: dict[str, Any] | None = None) -> None:
        self.state["staged_items_verified"] = True
        if research is not None:
            self.state["research"] = research

    def take_final(self) -> dict[str, Any] | None:
        # 完成意图只消费一次；校验失败后的纠正不能沿用上一次 final。
        return self.state.pop("pending_final", None)

    def request_final(self, summary: str, gaps: list[dict] | None) -> None:
        request: dict[str, Any] = {"research_summary": summary.strip()}
        # 省略清单沿用研究缺口；只有显式提交才授权校验通过后替换。
        if gaps is not None:
            request["business_gaps"] = gaps
        self.state["pending_final"] = request

    def publish_draft(self, draft: dict[str, Any]) -> None:
        flow = self.state.get("topic_flow", {})
        if flow.get("output_mode") == "after-research":
            flow.update(phase="completed", release_results=True)
        self.state["draft"] = draft
        self.take_final()

    def drop_pending(self, pending_ids: set[str]) -> None:
        """中止模块时丢弃未获支持的版本；上一版已核实内容仍保留在暂存结果中。"""
        for entry in self.state.get("staged_items", []):
            if (
                entry["id"] in pending_ids
                and entry.get("verification") != "supported"
                and entry.get("business", {}).get("kind") == "coverage"
            ):
                # 旧证明ID沿用后，恢复旧核实版本不能替新改写的不适用说明背书。
                for coverage in self.state.get("business_coverage", []):
                    if coverage.get("review_id") == entry["id"]:
                        coverage.update(status="pending", detail="本次不适用证明尚未通过原文校验")
        self.state["staged_items"] = [
            entry
            for entry in self.state.get("staged_items", [])
            if entry["id"] not in pending_ids or entry.get("verification") == "supported"
        ]
        for item_id in pending_ids:
            previous = self.state.get("business_previous", {}).get(item_id)
            if previous and not any(i["id"] == item_id for i in self.state["staged_items"]):
                self.state["staged_items"].append(previous)
