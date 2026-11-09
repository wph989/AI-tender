"""解析运行时的确定性护栏；模型改写字段名或重新发起工具调用不能重置失败账。"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from hashlib import sha256

from tender.application.analysis.data import semantic_payload
from tender.application.analysis.output import output_schema
from tender.application.knowledge.content import CATEGORIES, fingerprint, normalized


# 小节提取供通用契约复用；生产解析另按冻结资源中的显式主题关联选择细则。
def _skill_section(content: str, heading: str) -> str:
    match = re.search(rf"^{re.escape(heading)}\s*$(.*?)(?=^## |\Z)", content, re.M | re.S)
    if match is None:
        return ""
    body = match.group(1).strip()
    return heading + "\n" + body if body else ""


def _model_domain_rules(content: str) -> str:
    # 只剔除已由运行时提供的导航和通用协议；未知小节完整保留，不能按长度删业务规则。
    body = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", content, count=1, flags=re.S)
    sections = re.split(r"(?=^## )", body, flags=re.M)
    generic = ("按 coverage.json 核对业务内容，保留范围、条件、例外及完整清单。"
               "研究与提交协议以运行时工具为准；本文件只定义本专题的业务判断。")
    sections = [section.replace(generic, "") for section in sections]
    redundant = {"## 参考文件", "## 本项目的检索与输出"}
    return "\n\n".join(section.strip() for section in sections
                       if section.strip() and not (
                           section.splitlines()[0].strip() == "## 参考文件"
                           or section.strip() in redundant
                       ))


def _rule_parts(path: str, content: str, topics: set[str], *, complete: bool) -> dict:
    parts = []
    for line in content.splitlines():
        match = re.fullmatch(r"(.*?)\s*<!-- topics: (.*?) -->\s*", line)
        selected = []
        if match:
            line = match[1].rstrip()
            selected = [key.strip() for key in match[2].split(",")]
            if not selected or set(selected) - topics:
                # 自定义冻结清单可能更换主题；无法识别的关联只能扩大供给，不能误删业务约束。
                selected = []
        elif "<!-- topics:" in line:
            raise ValueError(path + "的规则关联格式错误")
        parts.append({"text": line, "topics": selected})
    return {"path": path, "parts": parts, "complete": complete}


def select_skill_rules(
    skill: dict, topics: set[str], *, full: bool = False,
) -> tuple[str, set[str]]:
    """只用冻结资源的明确关联筛选；未归类业务规则常驻，审查及综合使用全集。"""
    blocks, paths = [], set()
    for group in skill["rule_parts"]:
        included = [part for part in group["parts"]
                    if full or not part["topics"] or set(part["topics"]) & topics]
        blocks.append("\n".join(part["text"] for part in included))
        if group["complete"] and len(included) == len(group["parts"]):
            paths.add(group["path"])
    return "\n\n".join(blocks), paths


def skill_digest(content: str, *, schema: dict | None, topics: list[dict]) -> str:
    """从 Skill 正文提取执行流程与检索输出规则，附带输出键和主题清单。

    提取不到足够小节时返回空串，由调用方回退完整 instructions；宁可多注入，
    也不能让摘要轮次丢掉引用、校验或收尾要求。
    """
    flow = _skill_section(content, "## 执行流程") or _skill_section(content, "## 工作方法")
    retrieval = _skill_section(content, "## 本项目的检索与输出")
    if not flow or not retrieval:
        return ""
    parts = [flow, retrieval,
             "正文归纳总结，citations只填已读block_id，无需quote；程序补齐定位，通过支持性校验后保存。"]
    if schema:
        keys = "；".join(
            str(section.get("title", "")) + "（"
            + "、".join(str(column) for column in section.get("columns", [])) + "）"
            for section in schema.get("sections", [])
            if section.get("title")
        )
        if keys:
            parts.append("输出分类与内容键（完整schema见提交工具）：" + keys)
    if topics:
        parts.append(
            "必须登记的主题："
            + "、".join(str(topic.get("title") or topic.get("key")) for topic in topics)
        )
    digest = "\n\n".join(parts)
    return digest if len(digest) >= 200 else ""


def load_module_skill(snapshot: dict, key: str, *, categories: Sequence[str] = ()) -> dict:
    """只加载报告冻结的当前模块，不从磁盘热读，保证重跑能解释使用了哪套规则。"""
    path = key + "/SKILL.md"
    content = snapshot.get(path)
    if not isinstance(content, str) or not content.strip():
        raise ValueError("报告缺少模块 Skill 快照")
    resources = {p: v for p, v in snapshot.items() if p.startswith(key + "/")}
    digest = sha256(json.dumps(resources, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    # 核心细则在首次推理前加载，避免模型仅凭通用协议分析；示例仍按需读取。
    ref_dir = key + "/references/"
    native_format = ref_dir + "output_schema.json" in resources
    if native_format:
        # 原生声明也标识已适配的资源包；先校验，不能带着损坏格式进入模型推理。
        output_schema(snapshot, key)
    output_path = ref_dir + "output_format.md"
    instructions = content
    references = [output_path] if output_path in resources else []
    required = (
        ["locate_rules.md", "outline_extract_rules.md", "toc_filter_rules.md"]
        if key == "bid_format_outline_parsing" else ["extraction_rules.md"]
    )
    references.extend(ref_dir + name for name in required if ref_dir + name in resources)
    # 品类细则按项目/标段实际品类加载，覆盖混合品类；品类清单与知识库口径共用一份。
    references.extend(
        ref_dir + category + "/extraction_rules.md"
        for category in dict.fromkeys(categories)
        # 新包的技术细则已围绕方案重写；旧快照仍跳过冲突参数细则，保留历史语义。
        if category in CATEGORIES
        and (key != "tech_requirement_parsing" or native_format)
        and ref_dir + category + "/extraction_rules.md" in resources
    )
    for reference in references:
        instructions += "\n\n" + resources[reference]
    # 请求级系统提示不会进入下一轮历史；领域判别规则必须每轮存在，示例仍按需读取。
    domain_rules = "\n\n".join([
        *(_skill_section(content, heading) for heading in ("## 领域知识", "## 识别规则")),
        *(resources[p] for p in references if p != output_path),
    ])
    coverage_path = key + "/references/coverage.json"
    topics: list[dict] = []
    if coverage_path in resources:
        instructions += "\n\n必须登记状态的主题（coverage.json）：\n" + resources[coverage_path]
        try:
            parsed = json.loads(resources[coverage_path])
        except ValueError:
            parsed = None
        topics = parsed if isinstance(parsed, list) else []
    try:
        schema = output_schema(snapshot, key)
    except ValueError:
        # 输出声明的完整性由构建入口统一校验；摘要不能因此提前改变错误路径。
        schema = None
    prompt_digest = skill_digest(content, schema=schema, topics=topics)
    topic_keys = {topic["key"] for topic in topics}
    parts = [_rule_parts("/skills/" + key.replace("_", "-") + "/SKILL.md",
                         _model_domain_rules(content), topic_keys, complete=False)]
    parts.extend(_rule_parts("/skills/" + p.replace(key, key.replace("_", "-"), 1),
                             resources[p], topic_keys, complete=True)
                 for p in references if p != output_path)
    model_rules, _ = select_skill_rules({"rule_parts": parts}, set(), full=True)
    return {
        "path": "/skills/" + key.replace("_", "-") + "/SKILL.md",
        "sha256": digest.hexdigest(),
        "instructions": instructions,
        # 提取失败时回退完整正文，保证摘要轮次不会缺少关键规则。
        "digest": prompt_digest or instructions,
        "domain_rules": domain_rules,
        "model_rules": model_rules,
        "rule_parts": parts,
        "output_rules": (_skill_section(resources.get(output_path, ""), "## 事项组织")
                         or resources.get(output_path, "")),
        "domain_paths": ["/skills/" + p.replace(key, key.replace("_", "-"), 1)
                         for p in references if p != output_path],
        "references": references,
        "loaded_paths": ["/skills/" + p.replace(key, key.replace("_", "-"), 1)
                         for p in [*references, coverage_path, ref_dir + "output_schema.json"]
                         if p in resources],
        "line_counts": {"/skills/" + p.replace(key, key.replace("_", "-"), 1):
                        len(text.splitlines()) for p, text in resources.items()},
    }


def business_claim(entry: dict) -> dict | None:
    """纠错和进展关注业务语义，改展示名称或重新分配 key 不算新事实。"""
    if not entry.get("business"):
        return None
    return {k: v for k, v in semantic_payload(entry["business"]).items() if k != "title"}


def correction_count(state: dict, entry: dict) -> int:
    """同时按字段和证据事实记账，避免只改展示名称就获得新的纠错额度。"""
    label = str(entry.get("group", "")) + ":" + str(entry.get("field", "未知字段"))
    claim = business_claim(entry)
    # 业务记录同名很常见；使用服务端身份，避免不同标段或起算点的要求串账。
    keys = ["record:" + entry["id"]] if claim is not None else ["field:" + label]
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
            if claim is not None:
                fact.append(claim)
            keys.append("fact:" + fingerprint(fact))
    ledger = state.setdefault("correction_failures", {})
    count = max((ledger.get(k, 0) for k in keys), default=0) + 1
    for key in keys:
        ledger[key] = count
    # 保留旧状态键供历史日志与恢复逻辑使用。
    state.setdefault("field_failures", {})[label] = count
    return count


def progress_signature(
    seen: dict, state: dict, *, verified_only: bool = True, research_events: Sequence[dict] = (),
) -> str:
    """只有新增证据块、新增核实成果或阶段推进才算进展。

    换检索词、修好上一项校验问题都不产生可发布成果，不能用来续命；
    同一检索的重放和草稿改名同样不改变签名。``research_events`` 仅为兼容既有调用保留，
    不再参与指纹；签名格式已由旧版升级，旧检查点首次恢复会自然把无进展计数归零一次。
    """
    facts = sorted(
        {
            fingerprint([value.get("value"), value.get("citations"), business_claim(entry)])
            for entry in state.get("staged_items", [])
            if not verified_only or entry.get("verification") == "supported"
            for value in entry.get("values", [])
        }
    )
    return fingerprint([sorted(seen), facts, bool(state.get("research_completed"))])


def tool_key(name: str, arguments: dict, *, retrieval: bool = False) -> str:
    # 查询内部空格和HTML实体会改变召回语义；不能复用逐字引用的归一化。
    args = dict(arguments)
    if retrieval:
        # 业务归属不改变原文；缓存只复用读取，命中后仍须关联本次选择的工作和主题。
        args.pop("work", None)
        args.pop("topic_keys", None)
        if (isinstance(args.get("block_id"), list)
                and all(isinstance(key, str) for key in args["block_id"])):
            args["block_id"] = sorted(set(args["block_id"]))
    if name in {"search_document", "search_knowledge"} and isinstance(args.get("query"), str):
        args["query"] = args["query"].strip()
        args.setdefault("source_id", None)
        if retrieval:
            args.setdefault("offset", 0)
    if name == "read_document":
        args.setdefault("before", 2)
        args.setdefault("after", 2)
    return fingerprint([name, args])


def error_feedback(
    code: str, message: str, *, remaining: int, tool: str = "", details: dict | None = None,
) -> str:
    action = "按错误字段修正参数或补读依据；无依据的结论省略，缺口写入research_summary。"
    if details is not None:
        action = "逐项修正 issues；真实检索记录由服务端保存，无需复述检索词。未决主题登记缺口。"
    if remaining <= 0:
        action = "本次同类问题的纠错额度已耗尽，运行时保留已核实成果及诊断。"
    return json.dumps(
        {
            "ok": False,
            "error_code": code,
            "tool": tool,
            "message": message[:1800],
            "remaining_attempts": max(0, remaining),
            "next_action": action,
            **({"details": details} if details is not None else {}),
        },
        ensure_ascii=False,
    )


def select_verified_repeats(entries: list[dict]) -> None:
    """多批次独立验证过的同一事实选一套充分证据，避免后续并集重新堆积重复定位。"""
    chosen: dict[tuple, list[dict]] = {}
    for entry in entries:
        if entry.get("verification") != "supported":
            continue
        if entry.get("business"):
            # 相同文字可能具有不同条件与标段，业务记录不能套用展示字段的证据替换键。
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
