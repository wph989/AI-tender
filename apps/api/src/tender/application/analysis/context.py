"""按显式工作关联组织上下文；去重资格只来自当前对话中的同版本完整原文。"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, ToolMessage, message_to_dict

from tender.application.analysis.data import semantic_payload
from tender.application.analysis.topic_flow import identity
from tender.application.analysis.validation import ToolIssue, ToolValidationError
from tender.application.knowledge.content import fingerprint
from tender.application.shared.validation import allowed_values


def evidence_version(row: dict) -> str:
    # 检索分数和排序会随查询改变，不能让它们撤销同一来源版本原文的去重资格。
    return fingerprint({key: row.get(key) for key in (
        "source_id", "collection_id", "project_id", "parse_run_id", "version_id",
        "block_id", "element_id", "offset", "content", "locations",
    )})


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def model_message(message) -> dict:
    # 版本证明属于程序账，不送给模型；预算计量与实际路由共用相同视图。
    value = message_to_dict(message)
    value["data"].get("additional_kwargs", {}).pop("analysis_evidence", None)
    return value


def _payload(message: ToolMessage) -> dict:
    if message.status == "error" or not isinstance(message.content, str):
        return {}
    try:
        value = json.loads(message.content)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _evidence_units(payload: dict) -> list[dict]:
    return [unit for field in ("blocks", "units")
            for unit in (payload[field] if isinstance(payload.get(field), list) else [])
            if isinstance(unit, dict) and ("kind" not in unit or unit["kind"] == "evidence")]


def rule_topics(flow, messages, works: list[dict]) -> set[str]:
    known = {w["id"]: w for w in works}
    topics: set[str] = set()
    for message in reversed(messages):
        if isinstance(message, ToolMessage) and message.name == "get_research_context":
            payload = _payload(message)
            if isinstance(payload.get("topics"), list):
                topics.update(key for key in payload["topics"] if isinstance(key, str))
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            args = call.get("args", {})
            ids = args.get("work_ids", args.get("work", []))
            ids = [ids] if isinstance(ids, str) else ids if isinstance(ids, list) else []
            topics.update(known[key]["topic"] for key in ids
                          if isinstance(key, str) and key in known)
            for update in args.get("updates", []) if isinstance(args.get("updates"), list) else []:
                if not isinstance(update, dict) or not isinstance(update.get("work_ids"), list):
                    continue
                topics.update(known[key]["topic"] for key in update["work_ids"]
                              if isinstance(key, str) and key in known)
            keys = args.get("topic_keys", [])
            keys = keys if isinstance(keys, list) else []
            topics.update(key for key in keys
                          if isinstance(key, str) and any(e["topic"] == key for e in flow.entries))
        if topics:
            break
    # 待分析的补遗或跨主题修订不能因当前关注一个工作而丢掉其它相关细则。
    topics.update(e["topic"] for e in flow.entries if e.get("unreviewed_evidence"))
    return topics or {e["topic"] for e in flow.entries}


def work_units(flow, works: list[dict], work_ids: list[str]) -> list[dict]:
    known = {w["id"]: w for w in works}
    if not work_ids or set(work_ids) - known.keys():
        raise ToolValidationError([ToolIssue("invalid_work", "work_ids",
            "work_ids：请选择有效的非空work_ids；可选ID：" + allowed_values(known),
            tuple(i for i in work_ids if i in known))])
    selected = {key: known[key] for key in work_ids}
    # 后续待办继承产生它的研究线索，不要求模型再抄一份父问题与证据。
    while True:
        previous = set(selected)
        for entry in flow.entries:
            for wid, note in entry.get("dispositions", {}).items():
                if set(note.get("followup_ids", [])) & selected.keys() and wid in known:
                    selected[wid] = known[wid]
        if previous == selected.keys():
            break
    primary = {identity(w["topic"], w["scope"]) for w in selected.values()}
    topics = {w["topic"] for w in selected.values()}
    units, evidence, record_keys = [], set(), set()
    assigned = {key for entry in flow.entries for note in entry.get("dispositions", {}).values()
                for key in note.get("evidence_ids", [])}
    for entry in flow.entries:
        common = (entry["topic"] in topics
                  and identity(entry["topic"], entry["scope"]) not in primary
                  and (entry["scope"]["kind"] == "common" or any(
                      set(entry["scope"]["lot_refs"]) & set(w["scope"]["lot_refs"])
                      for w in selected.values() if w["topic"] == entry["topic"])))
        if not common and identity(entry["topic"], entry["scope"]) not in primary:
            continue
        matching = [w for w in works
                    if w["topic"] == entry["topic"] and w["scope"] == entry["scope"]]
        chosen = matching if common else [w for w in matching if w["id"] in selected]
        all_notes = entry.get("dispositions", {})
        # 尚未分配的原文不能静默消失；补遗保守关联的待分析原文也始终带入。
        evidence.update(set(entry["evidence_ids"]) - assigned)
        evidence.update(entry.get("unreviewed_evidence", []))
        for work in chosen:
            note = all_notes.get(work["id"], {})
            task = entry["tasks"].get(work.get("task_id"), {})
            finding = entry.get("findings", {}).get(work["check"], {})
            ids = set(note.get("evidence_ids", [])) | set(task.get("evidence_ids", []))
            ids.update(finding.get("evidence_ids", []))
            evidence.update(ids)
            record_keys.update(task.get("record_keys", []))
            units.append({"kind": "work", "work_id": work["id"], "topic": work["topic"],
                          "scope": work["scope"], "check": work["check"],
                          "status": note.get("status", work["status"]),
                          "notes": note.get("notes") or [note.get("detail")
                                                        or finding.get("detail", "")],
                          "evidence_ids": sorted(ids), "target": work.get("target", ""),
                          **({"issue_id": task["issue_id"], "action": task.get("action", "read")}
                             if task.get("issue_id") else {})})
        if entry["references"]:
            units.append({"kind": "references", "topic": entry["topic"], "scope": entry["scope"],
                          "references": entry["references"]})
            for trace in entry["references"]:
                evidence.add(trace["from_block_id"])
                evidence.update(trace.get("evidence_ids", []))
        for item in flow.state.get("staged_items", []):
            key = item.get("business", {}).get("key")
            if key in entry["record_keys"] and (
                common or not item.get("work_ids") or set(item["work_ids"]) & selected.keys()
            ):
                record_keys.add(key)
    items = {i["business"]["key"]: i for i in flow.state.get("staged_items", [])
             if i.get("business")}
    record_keys.update(k for k, i in items.items() if set(i.get("work_ids", [])) & selected.keys())
    pending, visited = sorted(record_keys), set()
    while pending:
        key = pending.pop(0)
        if key in visited:
            continue
        visited.add(key)
        item = items.get(key)
        if item is None:
            units.append({"kind": "missing_dependency", "record_key": key})
            continue
        business = item["business"]
        units.append({"kind": "record", "record_key": key,
                      "business": {k: v for k, v in semantic_payload(business).items()
                                   if k != "text"},
                      "topics": sorted({known[wid]["topic"] for wid in item.get("work_ids", [])
                                        if wid in known}),
                      "review_status": item.get("review_status"),
                      "verification_issues": item.get("verification_issues", [])})
        evidence.update(r["block_id"] for r in business.get("citations", []))
        pending.extend(business[k] for k in ("parent_key", "subject_key", "object_key")
                       if business.get(k) and business[k] not in visited)
        pending.extend(key for key in business.get("requirement_keys", []) if key not in visited)
    # 长笔记也分成完整、有位置的片段；不能切开JSON后要求模型猜测剩余结构。
    fragmented = []
    for unit in units:
        text = _dump(unit)
        if len(text) <= 1400:
            fragmented.append(unit)
        else:
            fragmented.extend({"kind": "note_fragment", "id": fingerprint(unit)[:16],
                               "topics": unit.get("topics", [unit.get("topic")]),
                               "start": start, "total": len(text), "text": text[start:start + 1000]}
                              for start in range(0, len(text), 1000))
    for key in sorted(evidence):
        row = flow.research.seen.get(key)
        if row is None:
            raise ToolValidationError([ToolIssue("stale_evidence", "work_ids",
                "关联原文已变化或缺失，请重新核对工作依据", tuple(work_ids))])
        text = row["content"]
        fragmented.extend({"kind": "evidence", "id": key, "start": start, "total": len(text),
                           "version": evidence_version(row), "text": text[start:start + 1000]}
                          for start in range(0, max(1, len(text)), 1000))
    return fragmented


def context_page(units: list[dict], offset: int, limit: int, revision: str | None) -> dict:
    version = fingerprint(units)
    if (offset < 0 or offset > len(units) or offset > 0 and revision is None
            or revision is not None and revision != version):
        raise ToolValidationError([ToolIssue("stale_cursor", "offset",
                                            "上下文或游标发生变化，请从offset=0重新读取")])
    result: list[dict] = []
    size, end = 0, offset
    for unit in units[offset:]:
        length = len(_dump(unit))
        # 至少返回一个完整单元；极小limit也不能截断引文或笔记。
        if result and size + length > max(256, min(limit, 12000)):
            break
        result.append(unit)
        size += length
        end += 1
    topics = {topic for unit in units for topic in [unit.get("topic"), *unit.get("topics", [])]
              if isinstance(topic, str)}
    return {"units": result, "topics": sorted(topics),
            "revision": version, "offset": offset, "total": len(units),
            "has_more": end < len(units), "next_offset": end if end < len(units) else None}


def visible_evidence(messages, seen: dict) -> set[str]:
    ranges: dict[str, list[tuple[int, int]]] = {}
    current = {key: evidence_version(row) for key, row in seen.items()}
    for message in messages:
        if not isinstance(message, ToolMessage) or message.status == "error":
            continue
        versions = message.additional_kwargs.get("analysis_evidence", {})
        for unit in _evidence_units(_payload(message)):
            key = unit.get("id")
            row = seen.get(key)
            text = unit.get("text")
            if (not isinstance(key, str) or row is None or not isinstance(text, str)
                    or versions.get(key) != current[key]):
                continue
            if "kind" in unit and unit["kind"] != "evidence":
                continue
            start = unit.get("start", 0)
            total = unit.get("total", len(row["content"]))
            if (type(start) is int and total == len(row["content"]) and start >= 0
                    and text == row["content"][start:start + len(text)]):
                ranges.setdefault(key, []).append((start, start + len(text)))
    visible = set()
    for key, segments in ranges.items():
        end = 0
        for start, stop in sorted(segments):
            if start > end:
                break
            end = max(end, stop)
        if end == len(seen[key]["content"]):
            visible.add(key)
    return visible


def evidence_message(message: ToolMessage, messages, seen: dict) -> ToolMessage:
    """缓存始终保存完整响应；展示去重每次依据有效历史重新计算，包括同ID重放。"""
    payload = _payload(message)
    if not payload:
        return message
    visible = visible_evidence(messages, seen)
    versions = dict(message.additional_kwargs.get("analysis_evidence", {}))
    # 底层检索按历史已读去重，不代表原文还在模型上下文；摘要后须补回可信原文。
    returned = {unit.get("id") for unit in _evidence_units(payload)}
    for key in payload.get("already_read", []):
        if key in seen and key not in visible and key not in returned:
            payload.setdefault("blocks", []).append({"id": key, "text": seen[key]["content"]})
            versions[key] = evidence_version(seen[key])
    for unit in _evidence_units(payload):
        key = unit.get("id")
        if key in seen and versions.get(key) != evidence_version(seen[key]):
            if message.name == "get_research_context":
                return message.model_copy(update={
                    "status": "error", "content": "上下文版本已变化，请从offset=0重新读取",
                })
            unit["text"] = seen[key]["content"]
            unit.pop("in_context", None)
            versions[key] = evidence_version(seen[key])
        if key in visible and versions.get(key) == evidence_version(seen[key]):
            unit.pop("text", None)
            unit["in_context"] = True
        unit.pop("version", None)
    return message.model_copy(update={
        "content": json.dumps(payload, ensure_ascii=False),
        "additional_kwargs": message.additional_kwargs | {"analysis_evidence": versions},
    })


def stamp_evidence(message: ToolMessage, seen: dict) -> ToolMessage:
    """在首次取得工具响应时记录证据版本，不能在缓存重放时重新签发旧原文。"""
    payload = _payload(message)
    if not payload:
        return message
    versions = {unit["id"]: evidence_version(seen[unit["id"]])
                for unit in _evidence_units(payload)
                if unit.get("id") in seen and isinstance(unit.get("text"), str)
                and ("kind" not in unit or unit["kind"] == "evidence")}
    return message.model_copy(update={
        "additional_kwargs": message.additional_kwargs | {"analysis_evidence": versions},
    })
