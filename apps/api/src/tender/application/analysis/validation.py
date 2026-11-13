"""解析工具的可恢复校验与问题账；业务错误和程序故障必须走不同通路。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from tender.application.analysis.research import ToolArgumentError
from tender.application.knowledge.content import fingerprint
from tender.application.shared.validation import validation_message


@dataclass(frozen=True)
class ToolIssue:
    code: str
    path: str
    message: str
    work_ids: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()


class ToolValidationError(ToolArgumentError):
    """校验器明确声明的可修正问题；未声明的ValueError仍作为程序故障暴露。"""

    def __init__(self, issues: list[ToolIssue]):
        self.issues = issues
        super().__init__(validation_message((i.path, i.message) for i in issues))

    @classmethod
    def at(cls, code: str, path: str, message: str) -> ToolValidationError:
        return cls([ToolIssue(code, path, message)])


def record_issues(state: dict, tool: str, issues: list[ToolIssue], call_id: str,
                  limit: int) -> list[dict]:
    """按业务对象和错误位置扣账；改非法值、调整批次位置及同调用重放都不能刷新机会。"""
    ledger = state.setdefault("tool_issue_ledger", {"version": 1, "issues": {}})["issues"]
    result = []
    for issue in issues:
        path = re.sub(r"(?<=\.)\d+(?=\.|$)|\[\d+\]", "*", issue.path)
        known = {item["id"] for item in state.get("staged_items", [])}
        # 新增被拒事项已有回执身份，但模型换名或不带回执ID重交时仍共用工作纠错额度。
        # 正式接受后沿原问题身份继续记账，不能因身份从预分配转为已保存而重新获额。
        owners = sorted(issue.record_ids if known & set(issue.record_ids) else issue.work_ids
                        ) or ["$tool"]
        previous = next((key for key, value in ledger.items() if value.get("tool") == tool
            and value["code"] == issue.code
            and re.sub(r"(?<=\.)\d+(?=\.|$)|\[\d+\]", "*", value["path"]) == path
            and set(value["record_ids"]) & set(issue.record_ids)), None)
        key = previous or fingerprint([tool, owners, issue.code, path])
        entry = ledger.setdefault(key, {"attempts": 0, "call_ids": []})
        pending = set(entry.get("pending_record_ids", entry.get("record_ids", []))) if (
            entry.get("active")) else set()
        identifiers = set(entry.get("record_ids", [])) | set(issue.record_ids)
        if call_id not in entry["call_ids"]:
            entry["call_ids"].append(call_id)
            entry["attempts"] += 1
        entry.update(asdict(issue), tool=tool, active=True,
                     record_ids=sorted(identifiers),
                     pending_record_ids=sorted(pending | set(issue.record_ids)),
                     remaining_attempts=max(0, limit - entry["attempts"]))
        result.append({k: v for k, v in entry.items() if k != "call_ids"} | {"key": key})
    return result


def resolve_issues(state: dict, tool: str, work_ids: list[str], *, paths: tuple[str, ...],
                   record_ids: tuple[str, ...] = ()) -> None:
    """只解决本次已校验对象的问题，保留计数和其它工作的未决问题。"""
    for issue in state.get("tool_issue_ledger", {}).get("issues", {}).values():
        # 仅校验了另一个字段或省略了原问题字段，不能把旧问题标为已修复。
        field = re.sub(r"(?<=\.)\d+(?=\.|$)|\[\d+\]", "*", issue["path"])
        owner_matches = (set(issue["record_ids"]) & set(record_ids) if issue["record_ids"]
                         else set(issue["work_ids"]) & set(work_ids))
        if (issue["tool"] == tool and issue.get("active") and owner_matches
                and any(field == p or field.startswith(p + ".") for p in paths)):
            if issue["record_ids"]:
                # 同一工作下的几个被拒事项共用额度，各自必须按回执ID修正后才销掉缺口。
                pending = set(issue.get("pending_record_ids", issue["record_ids"]))
                issue["pending_record_ids"] = sorted(pending - set(record_ids))
                issue["active"] = bool(issue["pending_record_ids"])
            else:
                issue["active"] = False
