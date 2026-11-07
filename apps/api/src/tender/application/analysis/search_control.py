"""按具体核对项限制研究范围；无进展与关闭状态随专题检查点保存。"""

from tender.application.analysis.policy import business_claim
from tender.application.analysis.research import ToolArgumentError
from tender.application.knowledge.content import fingerprint


class TopicSearch:
    def __init__(self, flow) -> None:
        self.flow, self.state = flow, flow.state
        self.ledger = flow.data.setdefault("search_work", {})

    def reject(self, message: str) -> None:
        stats = self.flow.data.setdefault("efficiency", {})
        stats["blocked_research"] = stats.get("blocked_research", 0) + 1
        raise ToolArgumentError(message)

    def signature(self, target: dict) -> str:
        entries = [e for e in self.flow.entries if e["topic"] == target["topic"]
                   and e["scope"] == target["scope"]]
        records = set(target["record_keys"]) or {k for e in entries for k in e["record_keys"]}
        return fingerprint([
            [e["checked"] for e in entries],
            [business_claim(i) for i in self.state.get("staged_items", [])
             if i.get("business", {}).get("key") in records
             and i.get("verification") == "supported"],
        ])

    def exhaust(self, target: dict) -> None:
        self.ledger[target["id"]]["exhausted"] = True
        for entry in self.flow.entries:
            if entry["topic"] != target["topic"] or entry["scope"] != target["scope"]:
                continue
            if target["kind"] == "task":
                entry["tasks"][target["task_id"]]["status"] = "blocked"
            elif target["kind"] == "check":
                entry["blocked_checks"] = sorted(set(entry.get("blocked_checks", []))
                                                  | {target["work"]})
            elif target["kind"] == "reference":
                for trace in entry["references"]:
                    if (trace["from_block_id"] == target["from_block_id"]
                            and trace["target"] == target["work"]):
                        trace["status"] = "budget_exhausted"
            else:
                entry["requested_status"] = "blocked"
            entry["detail"] = "待办连续检索无进展：" + target["work"]
        self.flow.sync()

    def choices(self, keys: list[str]) -> list[dict]:
        items = {i["business"]["key"]: i for i in self.state.get("staged_items", [])
                 if i.get("business")}
        result = []
        for entry in self.flow.entries:
            if entry["topic"] not in keys or entry["status"] in {"ready", "blocked"}:
                continue
            work = [("task", t["detail"], t["record_keys"], {"task_id": task_id})
                    for task_id, t in entry["tasks"].items() if t["status"] == "pending"]
            work += [("reference", r["target"], [], {"from_block_id": r["from_block_id"]})
                     for r in entry["references"]
                     if r["status"] not in {"resolved", "budget_exhausted"}]
            work += [("check", check, [], {}) for check in entry["checks"]
                     if check not in entry["checked"]
                     and check not in entry.get("blocked_checks", [])]
            if not work:
                work = [("review", "核实事项：" + key, [key], {}) for key in entry["record_keys"]
                        if items.get(key, {}).get("verification") != "supported"
                        or items.get(key, {}).get("review_status") == "needs_review"]
            for kind, detail, records, anchor in work:
                # 待办按服务端稳定ID区分；空关联记录及同事项上的不同问题也拥有独立进展。
                key = fingerprint([entry["topic"], entry["scope"], kind,
                                   anchor if kind == "task" else [detail, anchor]])
                result.append({"id": key, "topic": entry["topic"], "scope": entry["scope"],
                               "kind": kind, "work": detail, "record_keys": records, **anchor})
        return result

    def begin(self, name: str, args: dict) -> list[dict]:
        self.flow.data.pop("active_work", None)
        raw_keys, block_id = args.get("topic_keys"), args.get("block_id")
        # 门禁先于工具schema执行，坏类型须走同一纠错账，不能在set/dict操作时终止专题。
        if raw_keys is not None and (not isinstance(raw_keys, list)
                                    or any(not isinstance(key, str) for key in raw_keys)):
            raise ToolArgumentError("topic_keys须为主题key的字符串数组")
        if block_id is not None and not isinstance(block_id, str):
            raise ToolArgumentError("block_id须为已读原文的字符串ID")
        keys = self.flow.topic_keys(args.get("topic_keys"), block_id=args.get("block_id"))
        if name == "read_document" and args.get("before", 2) == args.get("after", 2) == 0:
            return []
        try:
            # 工具schema允许数字字符串；门禁发生在schema之前，也须兼容其整数归一化。
            offset = int(args.get("offset", 0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ToolArgumentError("offset须为非负整数") from exc
        choices = self.choices(keys)
        if args.get("work"):
            choices = [choice for choice in choices if choice["work"] == args["work"]]
        selected = []
        for topic in keys:
            candidates = [c for c in choices if c["topic"] == topic]
            if not candidates:
                self.reject(
                    topic + "已完成或受阻，或work未对应具体未解决项；"
                    "请提交已有事项，新增具体线索随topic_updates.tasks登记后再定向处理"
                )
            if len(candidates) > 1 and not args.get("work"):
                self.reject("请用work选择具体核对项或待办：" + "；".join(
                    dict.fromkeys(c["work"] for c in candidates)
                ))
            for candidate in candidates:
                ledger = self.ledger.get(candidate["id"], {})
                page_key = fingerprint([name, args.get("query", ""), args.get("source_id")])
                previous = ledger.get("pages", {}).get(page_key, {})
                paging = (previous.get("has_more") and previous.get("next_offset") == offset
                          and offset > previous.get("offset", 0)
                          and offset < self.flow.research.limits.search_window)
                continuation = name == "read_document" or paging
                if ledger.get("pending_stop"):
                    if ledger["signature"] == self.signature(candidate):
                        # 已有命中的后续页和清单邻段仍可补齐；不能在看到正文后截断条件。
                        if not continuation:
                            self.exhaust(candidate)
                    else:
                        ledger.update(pending_stop=False, idle=0)
                if ledger.get("exhausted"):
                    self.reject(
                        "该待办研究额度已耗尽，保留受阻缺口：" + candidate["work"]
                    )
                if name != "read_document" and offset > 0 and not paging:
                    self.reject("分页须使用同查询上一页实际返回的next_offset；末页或空结果不能继续翻页")
                selected.append(candidate | {"action": name, "query": args.get("query", ""),
                                              "source_id": args.get("source_id"),
                                              "offset": offset})
        self.flow.data["active_work"] = selected
        self.flow.data["active_topics"] = keys
        return selected

    def end(self, work: list[dict], result: dict, before: set[str]) -> None:
        self.flow.data.pop("active_work", None)
        if not work:
            return
        added = set(self.flow.research.seen) - before
        stats = self.flow.data.setdefault("efficiency", {})
        stats["research_calls"] = stats.get("research_calls", 0) + 1
        if not added:
            stats["repeated_evidence_calls"] = stats.get("repeated_evidence_calls", 0) + 1
        for target in work:
            ledger = self.ledger.setdefault(target["id"], {"attempts": 0, "idle": 0})
            ledger["attempts"] += 1
            signature = self.signature(target)
            # 只认本待办的核对及核实成果；新增无关原文、别的主题推进都不能重置计数。
            if signature != ledger.get("signature"):
                ledger["idle"] = 0
            pages = ledger.setdefault("pages", {})
            page_key = fingerprint([target["action"], target.get("query"), target.get("source_id")])
            offset = target.get("offset", 0)
            previous = pages.get(page_key, {})
            page = result.get("page", {})
            # 只有合法游标且本页确实命中原文才豁免；递增偏移量本身不代表有效分页。
            paging = (previous.get("has_more") and previous.get("next_offset") == offset
                      and offset > previous.get("offset", 0) and page.get("offset") == offset
                      and bool(result.get("blocks") or result.get("already_read")))
            if page:
                pages[page_key] = {k: page.get(k) for k in ("offset", "has_more", "next_offset")}
            continuation = target.get("action") == "read_document" and bool(added)
            if ledger.get("pending_stop") and not paging and not continuation:
                self.exhaust(target)
            if not paging and not continuation:
                ledger["idle"] += 1
            ledger["signature"] = signature
            if ledger["idle"] < self.flow.research.limits.max_no_progress_rounds:
                continue
            # 最后一批原文仍须交给Agent分析及提交；仅在未产生新成果却继续检索时关闭。
            ledger["pending_stop"] = True
            result["research_notice"] = (
                "本待办连续检索尚无核实成果；请先分析并提交本次原文支持的事项，"
                "没有实质推进将停止该待办的扩展研究并保留缺口"
            )
        self.flow.sync()

    @staticmethod
    def summary(state: dict) -> dict:
        data = state.get("topic_flow", {})
        return {
            "exhausted_work": sum(bool(w.get("exhausted"))
                                  for w in data.get("search_work", {}).values()),
            **data.get("efficiency", {}),
        }
