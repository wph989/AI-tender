"""开发复盘档案；与执行检查点分开管理生命周期。"""

from typing import Any, Protocol


class AnalysisArchive(Protocol):
    def write(self, snapshot: dict[str, Any]) -> None:
        """仅归档已确认终态的执行快照，保留期从finished_at计算。"""
        ...
