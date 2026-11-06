"""专题业务状态及状态转换；框架回调只触发转换，不各自维护阶段组合。"""

from typing import Any, Literal, TypedDict, cast


class AnalysisState(TypedDict, total=False):
    model_round_seconds: float
    research_completed: dict[str, Any]
    research: dict[str, Any]
    staged_items: list[dict[str, Any]]
    staged_relations: list[dict[str, Any]]
    staged_items_verified: bool
    staged_prompt_ids: list[str]
    pending_final: dict[str, Any]
    draft: dict[str, Any]
    business_previous: dict[str, Any]
    rejected_records: dict[str, Any]
    gap_notes: list[str]
    business_coverage: list[dict[str, Any]]
    business_gaps: list[dict[str, Any]]


Phase = Literal["research", "synthesis", "verification", "completed"]


class AnalysisTransitions:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        # 保留原字典身份与未知的历史字段，检查点、工具重放和预算继续共享同一份状态。
        self.state = cast(AnalysisState, snapshot)

    @property
    def phase(self) -> Phase:
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
