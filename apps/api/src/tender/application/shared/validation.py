"""供解析与知识引用共用的校验反馈：定位字段、保留修法、限制重复正文。"""

from collections.abc import Iterable

from pydantic import ValidationError


def allowed_values(values: Iterable[str]) -> str:
    """只展示服务端已知的候选，不能把模型提交的非法正文当作候选回显。"""
    choices = sorted(set(values))
    return "、".join(value[:80] for value in choices[:8]) + (
        f"（另有{len(choices) - 8}项，见当前索引）" if len(choices) > 8 else ""
    ) or "无可用项"


def validation_message(issues: Iterable[tuple[str, str]]) -> str:
    """同一字段只写一次，相同修法合并列出字段，避免重复提示挤占纠错上下文。"""
    by_path: dict[str, list[str]] = {}
    for path, reason in issues:
        reasons = by_path.setdefault(path, [])
        if reason not in reasons:
            reasons.append(reason)
    grouped: dict[str, list[str]] = {}
    for path, reasons in list(by_path.items())[:6]:
        grouped.setdefault("；".join(reasons), []).append(path)
    message = "；".join(f"{'、'.join(paths)}：{reason}" for reason, paths in grouped.items())
    if len(by_path) > 6:
        message += f"；另有{len(by_path) - 6}个字段待修正"
    return message[:1800]


def schema_feedback(error: ValidationError) -> str:
    """Pydantic 默认字符串包含input_value；仅回传字段路径和规则，避免重发坏草稿。"""
    messages = {"missing": "必填", "string_type": "应为文字", "list_type": "应为数组",
                "dict_type": "应为对象", "bool_type": "应为布尔值", "int_type": "应为整数",
                "extra_forbidden": "请删除此字段"}
    issues = []
    for issue in error.errors(include_input=False, include_url=False):
        reason = messages.get(issue["type"], issue["msg"].removeprefix("Value error, "))
        if issue["type"] in {"too_long", "too_short"}:
            # 只读取服务端约束的长度，不序列化ctx中的异常或模型输入。
            context = issue["ctx"]
            unit = "个字符" if context.get("field_type") == "String" else "项"
            reason = (f"最多{context['max_length']}{unit}" if issue["type"] == "too_long"
                      else f"至少{context['min_length']}{unit}")
        issues.append((".".join(map(str, issue["loc"])) or "$", reason))
    return validation_message(issues)
