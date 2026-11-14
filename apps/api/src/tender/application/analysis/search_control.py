"""按具体核对项限制研究范围；无进展与关闭状态随专题检查点保存。"""

import re

from tender.application.analysis.policy import business_claim
from tender.application.analysis.research import ToolArgumentError, WorkClosed
from tender.application.knowledge.content import fingerprint


class TopicSearch:
    def __init__(self, flow) -> None:
        self.flow, self.state = flow, flow.state
        self.ledger = flow.data.setdefault("search_work", {})

    def reject(self, message: str, *, closed: bool = False) -> None:
        stats = self.flow.data.setdefault("efficiency", {})
        stats["blocked_research"] = stats.get("blocked_research", 0) + 1
        raise (WorkClosed if closed else ToolArgumentError)(message)

    def signature(self, target: dict) -> str:
        entries = [e for e in self.flow.entries if e["topic"] == target["topic"]
                   and e["scope"] == target["scope"]]
        # 核对项只认自身完成；具体待办只认所关联成果，不能被同主题其他事项续期。
        records = set(target["record_keys"])
        if target["kind"] == "exploration":
            records.update(k for e in entries for k in e["record_keys"])
        notes = []
        if self.flow.research_first:
            for entry in entries:
                if target["kind"] == "task":
                    task = entry["tasks"].get(target["task_id"], {})
                    # 已解决待办的笔记可继续修订，但只有解决状态变化能给研究续期。
                    notes.append(bool(task.get("status") == "resolved")
                                 if self.flow.data.get("protocol") == "research-v3"
                                 else task if task.get("status") == "resolved" else {})
                elif self.flow.data.get("protocol") != "research-v3":
                    notes.extend((check, sorted(value["evidence_ids"]), value["status"])
                                 for check, value in entry.get("findings", {}).items()
                                 if target["kind"] == "exploration" or check == target["work"])

        return fingerprint([
            ([] if self.flow.data.get("protocol") == "research-v3" else
             [e["checked"] for e in entries] if target["kind"] == "exploration" else
             [target["work"] in e["checked"] for e in entries]
             if target["kind"] == "check" else []),
            [business_claim(i) for i in self.state.get("staged_items", [])
             if (i.get("business", {}).get("key") in records
                 or target["id"] in i.get("work_ids", []))
             and (self.flow.data.get("protocol") == "research-v3"
                  or i.get("verification") == "supported")],
        ] + ([notes] if self.flow.research_first else []))

    def exhaust(self, target: dict) -> None:
        self.ledger[target["id"]]["exhausted"] = True
        if self.flow.simplified:
            # 停止重复采集不等于语义受阻；Agent仍可基于已有原文综合，由独立审查判定完整性。
            return
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
            elif target["kind"] != "exploration":
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
            work = [("task", t["detail"], t["record_keys"],
                     {"task_id": task_id, "target": t.get("target", "")})
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
            if (not work and entry["scope"]["kind"] == "unknown"
                    and (entry["record_keys"]
                         or self.flow.research_first and entry.get("findings"))):
                work = [("scope", "确认适用范围", entry["record_keys"], {})]
            for kind, detail, records, anchor in work:
                # 待办按服务端稳定ID区分；空关联记录及同事项上的不同问题也拥有独立进展。
                key = fingerprint([entry["topic"], entry["scope"], kind,
                                   {"task_id": anchor["task_id"]}
                                   if kind == "task" else [detail, anchor]])
                result.append({"id": key, "topic": entry["topic"], "scope": entry["scope"],
                               "kind": kind, "work": detail, "record_keys": records, **anchor})
        if self.flow.simplified:
            from tender.application.analysis.protocol import ResearchLedger

            known = ResearchLedger(self.flow).works()
            for choice in result:
                matched = next((w for w in known if w["topic"] == choice["topic"]
                                and w["scope"] == choice["scope"] and w["kind"] == choice["kind"]
                                and (w.get("task_id") == choice.get("task_id")
                                     if w["kind"] == "task"
                                     else w["check"] == choice["work"])), None)
                if matched:
                    choice["id"] = matched["id"]
        audit = self.flow.data.get("audit", {})
        issues = audit.get("remaining", audit.get("issues", []))
        if self.flow.data.get("protocol") == "research-v3" and audit.get("round") and issues:
            affected = {key for issue in issues for key in issue.get("record_keys", [])}
            work_ids = {wid for key in affected for wid in items.get(key, {}).get("work_ids", [])}
            issue_tasks = set(audit.get("issue_task_ids", []))
            # 修复只为未决问题取证；新的附件、续段及冲突须与问题的实际目标或锚点相连。
            result = [choice for choice in result if choice["id"] in work_ids
                      or set(choice["record_keys"]) & affected
                      or choice.get("task_id") in issue_tasks
                      or choice["kind"] == "reference" and any(
                          issue["topic"] == choice["topic"] and (
                              choice.get("from_block_id") in issue.get("evidence_ids", [])
                              or choice["work"] == issue.get("target")
                          ) for issue in issues)]
        return result

    def begin(self, name: str, args: dict) -> list[dict]:
        self.flow.data.pop("active_work", None)
        quote_only = name == "read_document" and args.get("before", 1) == args.get("after", 1) == 0
        if self.flow.simplified and not self.flow.researching and not quote_only:
            raise ToolArgumentError("综合阶段须用update_research的reopen明确重开具体工作后再检索")
        raw_keys, block_id = args.get("topic_keys"), args.get("block_id")
        # 门禁先于工具schema执行，坏类型须走同一纠错账，不能在set/dict操作时终止专题。
        if raw_keys is not None and (not isinstance(raw_keys, list)
                                    or any(not isinstance(key, str) for key in raw_keys)):
            raise ToolArgumentError("topic_keys须为主题key的字符串数组")
        if block_id is not None and not (isinstance(block_id, str) or (
                isinstance(block_id, list) and 1 <= len(block_id) <= 4
                and all(isinstance(key, str) for key in block_id))):
            raise ToolArgumentError("block_id须为已读原文ID，或最多4个ID的数组")
        keys = self.flow.topic_keys(args.get("topic_keys"), block_id=args.get("block_id"),
                                    work=args.get("work"))
        if name == "read_document":
            # 门禁先于工具schema，先收敛窗口类型，避免坏参数在range中击穿整批执行。
            args = dict(args)
            for field in ("before", "after"):
                value = args.get(field, 1)
                if isinstance(value, str) and value.isdecimal():
                    value = int(value)
                if type(value) is not int or not 0 <= value <= 11:
                    raise ToolArgumentError(field + "须为0～11的整数")
                args[field] = value
        if name == "read_document" and args.get("before", 1) == args.get("after", 1) == 0:
            return []
        try:
            # 工具schema允许数字字符串；门禁发生在schema之前，也须兼容其整数归一化。
            offset = int(args.get("offset", 0))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ToolArgumentError("offset须为非负整数") from exc
        choices = self.choices(keys)
        action = ("依据充分时complete_research，否则记录具体缺口或处理其他工作"
                  if self.flow.simplified and self.flow.researching else
                  "用update_research登记研究发现" if self.flow.researching else "提交已有事项")
        if not choices:
            self.reject("所选主题已完成或受阻；请" + action + "，新增线索用update_research登记",
                        closed=True)
        requested = args.get("work")
        if requested:
            if isinstance(requested, str):
                # 兼容模型把多个检查项用分号合并；不要求重复调用或精确复制长中文。
                requested = ([requested] if any(requested in {c["id"], c["work"]} for c in choices)
                             else [v.strip() for v in re.split(r"[；;\n]", requested) if v.strip()])
            if not isinstance(requested, list) or any(not isinstance(v, str) for v in requested):
                self.reject("work可省略，或填写当前search_work的id、文字及其数组")
            known = {v for c in choices for v in (c["id"], c["work"])}
            if set(requested) - known:
                if self.flow.simplified:
                    from tender.application.analysis.protocol import ResearchLedger

                    registered = {v for w in ResearchLedger(self.flow).works()
                                  if w["topic"] in keys for v in (w["id"], w["check"])}
                    if set(requested) <= registered and not set(requested) & known:
                        self.reject("所选工作已完成或受阻：" + "、".join(requested)
                                    + "；选择其他工作，有新线索时用update_research明确reopen",
                                    closed=True)
                    if set(requested) - registered:
                        self.reject("work须选择当前工作索引中的有效ID：" + "、".join(
                            c["id"] for c in choices[:8]
                        ))
                else:
                    self.reject("work未对应当前待办；请省略work按主题检索，或使用search_work返回的id")
            choices = [c for c in choices if set(requested) & {c["id"], c["work"]}]
            # 一个查询可关联多个主题，但显式work只扣它自己的账，不要求属于每个主题。
            selection_keys = sorted({c["topic"] for c in choices})
        else:
            # 未指明问题的检索只扣主题探索账，不将所有尚未尝试的核对项记为失败。
            scopes = {(c["topic"], fingerprint(c["scope"])): c for c in choices}
            choices = [{"id": fingerprint([c["topic"], c["scope"], "exploration"]),
                        "topic": c["topic"], "scope": c["scope"], "kind": "exploration",
                        "work": "主题探索", "record_keys": []} for c in scopes.values()]
            selection_keys = sorted({c["topic"] for c in choices})
        if not choices:
            self.reject("所选主题已完成或受阻；请" + action + "，新增线索用update_research登记",
                        closed=True)
        selected: list[dict] = []
        for topic in selection_keys:
            candidates = [c for c in choices if c["topic"] == topic]
            if not candidates:
                self.reject(
                    topic + "已完成或受阻，或work未对应具体未解决项；"
                    "请" + action + "，新增具体线索随topic_updates.tasks登记后再定向处理"
                )
            selected_before = len(selected)
            for candidate in candidates:
                ledger = self.ledger.get(candidate["id"], {})
                page_key = fingerprint([name, args.get("query", ""), args.get("source_id")])
                previous = ledger.get("pages", {}).get(page_key, {})
                paging = (previous.get("has_more") and previous.get("next_offset") == offset
                          and offset > previous.get("offset", 0)
                          and offset < self.flow.research.limits.search_window)
                # 轻量流程不要求靠写笔记续期；下一次不同查询先执行，再检查是否真有新原文。
                anchors = args.get("block_id", [])
                anchors = [anchors] if isinstance(anchors, str) else anchors
                unread = name == "read_document" and any(
                    not any(row["source_id"] == self.flow.research.seen[key]["source_id"]
                            and row["offset"] == self.flow.research.seen[key]["offset"] + step
                            for row in self.flow.research.seen.values())
                    for key in anchors if key in self.flow.research.seen
                    for step in range(-min(args.get("before", 1), 1),
                                      min(args.get("after", 1), 1) + 1)
                    if self.flow.research.seen[key]["offset"] + step >= 0)
                continuation = (unread or paging if self.flow.data.get("protocol") == "research-v3"
                                else self.flow.simplified or name == "read_document" or paging)
                if (self.flow.data.get("protocol") == "research-v3" and ledger.get("exhausted")
                        and (continuation or ledger.get("signature") != self.signature(candidate))):
                    ledger.update(exhausted=False, pending_stop=False, idle=0)
                if ledger.get("pending_stop"):
                    if ledger["signature"] == self.signature(candidate):
                        # 已有命中的后续页和清单邻段仍可补齐；不能在看到正文后截断条件。
                        if not continuation:
                            self.exhaust(candidate)
                    else:
                        ledger.update(pending_stop=False, idle=0)
                if ledger.get("exhausted"):
                    continue
                if name != "read_document" and offset > 0 and not paging:
                    self.reject("分页须使用同查询上一页实际返回的next_offset；末页或空结果不能继续翻页")
                selected.append(candidate | {"action": name, "query": args.get("query", ""),
                                              "source_id": args.get("source_id"),
                                              "offset": offset})
            if len(selected) == selected_before:
                self.reject("该工作研究额度已耗尽；请先" + action + "，或指定尚未处理的具体work",
                            closed=True)
        self.flow.data["active_work"] = selected
        self.flow.data["active_topics"] = keys
        return selected

    def end(self, work: list[dict], result: dict, before: set[str],
            *, batch_id: str | None = None) -> bool:
        if self.flow.data.get("protocol") != "research-v3":
            return self._end_legacy(work, result, before)
        self.flow.data.pop("active_work", None)
        if not work:
            return False
        settled = (self.flow.data.setdefault("settled_search_batches", {}).setdefault(batch_id, [])
                   if batch_id else [])
        work = [target for target in work if target["id"] not in settled]
        if not work:
            return False
        stats = self.flow.data.setdefault("efficiency", {})
        stats["research_calls"] = stats.get("research_calls", 0) + 1
        grouped: dict[str, list[dict]] = {}
        for target in work:
            grouped.setdefault(target["id"], []).append(target)
        progressed = False
        for wid, targets in grouped.items():
            target = targets[0]
            ledger = self.ledger.setdefault(wid, {"attempts": 0, "idle": 0})
            signature = self.signature(target)
            changed = "signature" in ledger and signature != ledger["signature"]
            associated, paging = set(), False
            pages = ledger.setdefault("pages", {})
            for item in targets:
                page = item.get("page", result.get("page", {}))
                ids = set(item.get("associated_ids", []))
                if "associated_ids" not in item:
                    ids = set(result.get("already_read", [])) | {
                        b.get("id", b.get("block_id")) for b in result.get("blocks", [])}
                associated.update(ids)
                page_key = fingerprint([item["action"], item.get("query"), item.get("source_id")])
                previous = pages.get(page_key, {})
                paging |= bool(previous.get("has_more") and ids
                               and previous.get("next_offset") == item.get("offset", 0)
                               and item.get("offset", 0) > previous.get("offset", 0))
                if page:
                    pages[page_key] = {
                        k: page.get(k) for k in ("offset", "has_more", "next_offset")
                    }
                if item.get("action") == "search_document":
                    searches = self.flow.data.setdefault("research_searches", {}).setdefault(
                        item["topic"], {})
                    sources = [s["source_id"] for s in self.flow.research.sources
                               if s["project_id"] == self.flow.research.project_id
                               and (item.get("source_id") is None
                                    or s["source_id"] == item["source_id"])]
                    searches[fingerprint([item.get("query"), sources])] = {
                        "query": item.get("query", "").strip(), "source_ids": sources,
                        "has_more": bool(page.get("has_more")),
                        "limited": bool(result.get("search_limited")
                                        or result.get("budget_exhausted")),
                    }
            # 证据必须新增到本工作；别的查询拿到的块、笔记和重复提交不能续期。
            previous_ids = set(ledger.get("evidence_ids", []))
            advance = changed or bool(associated - previous_ids) or paging
            ledger.update(attempts=ledger["attempts"] + 1, signature=signature,
                          evidence_ids=sorted(previous_ids | associated),
                          idle=0 if advance else ledger["idle"] + 1)
            if batch_id:
                settled.append(wid)
            progressed |= advance
            if advance:
                ledger.update(exhausted=False, pending_stop=False)
            elif ledger["idle"] >= min(2, self.flow.research.limits.max_no_progress_rounds):
                ledger["pending_stop"] = True
                self.exhaust(target)
                result["research_notice"] = (
                    "本工作连续两批没有实质推进，已停止补查；请分析已有原文并保留具体缺口"
                )
        if not progressed:
            stats["repeated_evidence_calls"] = stats.get("repeated_evidence_calls", 0) + 1
        result["next_action"] = (
            "先理解本批原文并暂存有据草稿；仅针对具体未决条件、续段或转引补查"
        )
        self.flow.sync()
        return progressed

    def _end_legacy(self, work: list[dict], result: dict, before: set[str]) -> bool:
        self.flow.data.pop("active_work", None)
        if not work:
            return False
        added = set(self.flow.research.seen) - before
        progressed = bool(added)
        stats = self.flow.data.setdefault("efficiency", {})
        stats["research_calls"] = stats.get("research_calls", 0) + 1
        if not added:
            stats["repeated_evidence_calls"] = stats.get("repeated_evidence_calls", 0) + 1
        for target in work:
            if self.flow.research_first and target.get("action") == "search_document":
                # 真实检索范围和未读分页供未找到结论核对；命中也保留，不能挑空结果作证明。
                searches = self.flow.data.setdefault("research_searches", {}).setdefault(
                    target["topic"], {})
                page = result.get("page", {})
                source_ids = [s["source_id"] for s in self.flow.research.sources
                              if s["project_id"] == self.flow.research.project_id
                              and (target.get("source_id") is None
                                   or s["source_id"] == target["source_id"])]
                searches[fingerprint([target.get("query"), source_ids])] = {
                    "query": target.get("query", "").strip(), "source_ids": source_ids,
                    "has_more": bool(page.get("has_more")),
                    "limited": bool(result.get("search_limited") or result.get("budget_exhausted")),
                }
            ledger = self.ledger.setdefault(target["id"], {"attempts": 0, "idle": 0})
            if ledger.get("exhausted"):
                continue
            ledger["attempts"] += 1
            signature = self.signature(target)
            # 只认本待办的变化；其它主题推进或笔记改写不能给它续期。
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
            progressed = progressed or bool(paging)
            if page:
                pages[page_key] = {k: page.get(k) for k in ("offset", "has_more", "next_offset")}
            continuation = bool(added) and (self.flow.simplified
                                           or target.get("action") == "read_document")
            if self.flow.simplified and added:
                # 只约束重复采集，不用缺少行政登记推断语义停滞；新增原文不等于内容完整。
                ledger.update(idle=0, pending_stop=False)
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
                "本待办连续检索尚无内容推进；请先分析本次原文并登记研究发现，"
                "没有实质推进将停止该待办的扩展研究并保留缺口"
            )
            if self.flow.simplified:
                # 最后一批仍交Agent理解；重复无新增达到上限才关闭，不强制通过examined解锁。
                self.exhaust(target)
                result["research_notice"] = (
                    "本工作连续采集没有新增原文，已停止重复采集；理解已有原文后，"
                    "依据充分则complete_research，否则保留具体缺口并处理其他工作"
                )
        if self.flow.simplified:
            # 每批回执提供语义决策出口，避免工具只不断诱导补查或机械登记笔记。
            result["next_action"] = (
                "先理解本次原文；若核对内容已充分，complete_research后统一综合。"
                "否则只针对缺失条件、例外、续段或转引继续检索，笔记按需保存。"
            )
        self.flow.sync()
        return progressed

    @staticmethod
    def summary(state: dict) -> dict:
        data = state.get("topic_flow", {})
        return {
            "exhausted_work": sum(bool(w.get("exhausted"))
                                  for w in data.get("search_work", {}).values()),
            **data.get("efficiency", {}),
        }
