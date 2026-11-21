"""报告读取、调度和快照发布共用的持久协议。"""

from __future__ import annotations

RUNTIME_VERSION = "deepagents-0.7.22-v6-records"
FLOW_VERSION = "skill-agent-v1"
FLOW_VERSION_KEY = "__analysis_flow_version__"


def is_current_report(report: dict) -> bool:
    """只有当前运行与Agent契约的报告才进入应用读写路径。"""
    snapshot = report.get("skill_snapshot") or {}
    return (
        report.get("runtime_version") == RUNTIME_VERSION
        and snapshot.get(FLOW_VERSION_KEY) == FLOW_VERSION
    )
