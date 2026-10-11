"""解析运行时的确定性护栏；模型改写字段名或重新发起工具调用不能重置失败账。"""

from __future__ import annotations

import json
from hashlib import sha256

from tender.application.knowledge import fingerprint, normalized


def load_module_skill(snapshot: dict, key: str) -> dict:
    """只加载报告冻结的当前模块，不从磁盘热读，保证重跑能解释使用了哪套规则。"""
    path = key + "/SKILL.md"
    content = snapshot.get(path)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("报告缺少模块 Skill 快照")
    resources = {p: v for p, v in snapshot.items() if p.startswith(key + "/")}
    digest = sha256(json.dumps(resources, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    # 输出清单是每个专题的必要规则；品类细则和示例仍通过 read_file 按需读取。
    output_path = key + "/references/output_format.md"
    instructions = content
    if output_path in resources:
        instructions += "\n\n" + resources[output_path]
    return {
        "path": "/skills/" + key.replace("_", "-") + "/SKILL.md",
        "sha256": digest.hexdigest(),
        "instructions": instructions,
    }


def correction_count(state: dict, entry: dict) -> int:
    """同时按字段和证据事实记账，避免只改展示名称就获得新的纠错额度。"""
    label = str(entry.get("group", "")) + ":" + str(entry.get("field", "未知字段"))
    keys = ["field:" + label]
    for value in entry.get("values", []):
        refs = sorted(
            (str(r.get("block_id")), normalized(str(r.get("quote", ""))))
            for r in value.get("citations", [])
        )
        if refs:
            # 同一段原文可承载不同事实，不能仅凭引文共享额度；保留值和适用条件，
            # 但不含展示字段名，使仅改名的同一断言仍沿用失败账。
            fact = [
                normalized(str(value.get("value", ""))),
                normalized(str(entry.get("group", ""))),
                normalized(str(entry.get("note", ""))),
                refs,
            ]
            keys.append("fact:" + fingerprint(fact))
    ledger = state.setdefault("correction_failures", {})
    count = max((ledger.get(k, 0) for k in keys), default=0) + 1
    for key in keys:
        ledger[key] = count
    # 保留旧状态键供历史日志与恢复逻辑使用。
    state.setdefault("field_failures", {})[label] = count
    return count


def progress_signature(seen: dict, state: dict, *, verified_only: bool = True) -> str:
    """只有新增原文或通过校验的新事实算进展；改名、工具成功、草稿暂存都不算。"""
    facts = sorted(
        {
            fingerprint([value.get("value"), value.get("citations")])
            for entry in state.get("staged_items", [])
            if not verified_only or entry.get("verification") == "supported"
            for value in entry.get("values", [])
        }
    )
    return fingerprint([sorted(seen), facts])


def tool_key(name: str, arguments: dict) -> str:
    # 空白变化不应触发昂贵的重复检索；其它工具保留原参数，避免改动引用原文。
    args = dict(arguments)
    if name in {"search_document", "search_knowledge"} and isinstance(args.get("query"), str):
        args["query"] = normalized(args["query"])
        args.setdefault("source_id", None)
    if name == "read_document":
        args.setdefault("before", 2)
        args.setdefault("after", 2)
    return fingerprint([name, args])


def error_feedback(code: str, message: str, *, remaining: int, tool: str = "") -> str:
    return json.dumps(
        {
            "ok": False,
            "error_code": code,
            "tool": tool,
            "message": message[:1800],
            "remaining_attempts": max(0, remaining),
            "next_action": (
                "按错误字段修正参数或补读依据；无依据的结论省略，缺口写入research_summary。"
            ),
        },
        ensure_ascii=False,
    )


def select_verified_repeats(entries: list[dict]) -> None:
    """多批次独立验证过的同一事实选一套充分证据，避免后续并集重新堆积重复定位。"""
    chosen: dict[tuple, list[dict]] = {}
    for entry in entries:
        if entry.get("verification") != "supported":
            continue
        for value in entry["values"]:
            refs = value["citations"]
            sources = tuple(sorted({str(r.get("source_id")) for r in refs}))
            # 备注中的主体、起算点等也经过支持性校验；条件不同不能互换证据，
            # 否则合并备注后会留下缺少引用的断言。
            key = (
                entry.get("group", ""), entry["field"], normalized(value["value"]),
                entry.get("note", ""), sources,
            )
            group = chosen.setdefault(key, [])
            group.append(value)
    for values in chosen.values():
        # 每套引用已经独立通过支持性校验，可选较少、较直接的一套；不能从中随意删单条。
        best = min(
            (v["citations"] for v in values),
            key=lambda refs: (len(refs), sum(len(r["quote"]) for r in refs), fingerprint(refs)),
        )
        for value in values:
            value["citations"] = list(best)
