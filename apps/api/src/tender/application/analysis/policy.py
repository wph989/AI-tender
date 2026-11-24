"""从冻结资源组装现行单 Agent 的业务规则。"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from hashlib import sha256

from tender.application.knowledge.content import CATEGORIES


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
    redundant = {"## 参考文件", "## 本项目的检索与输出"}
    return "\n\n".join(section.strip() for section in sections
                       if section.strip() and not (
                           section.splitlines()[0].strip() == "## 参考文件"
                           or section.strip() in redundant
                       ))


def load_module_skill(snapshot: dict, key: str, *, categories: Sequence[str] = ()) -> dict:
    """从冻结快照组装领域规则，重跑时仍使用原来的资源版本。"""
    content = snapshot.get(key + "/SKILL.md")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("报告缺少模块 Skill 快照")
    resources = {p: v for p, v in snapshot.items() if p.startswith(key + "/")}
    digest = sha256(json.dumps(resources, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    ref_dir = key + "/references/"
    required = (
        ["locate_rules.md", "outline_extract_rules.md", "toc_filter_rules.md"]
        if key == "bid_format_outline_parsing" else ["extraction_rules.md"]
    )
    paths = [ref_dir + name for name in required]
    # 按本项目和标段选择品类细则，混合品类也只加载各自的一份。
    paths.extend(ref_dir + category + "/extraction_rules.md"
                 for category in dict.fromkeys(categories) if category in CATEGORIES)
    rules = [_model_domain_rules(content), *(resources[p] for p in paths if p in resources)]
    output = resources.get(ref_dir + "output_format.md", "")
    return {
        "sha256": digest.hexdigest(),
        "model_rules": "\n\n".join(rules),
        "output_rules": _skill_section(output, "## 事项组织") or output,
    }
