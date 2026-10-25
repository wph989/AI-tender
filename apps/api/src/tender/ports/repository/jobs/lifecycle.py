"""按调用者能力定义的仓储端口；SQL 与共享事务由同一实现提供。"""

from __future__ import annotations

from typing import Protocol


class TaskLifecycle(Protocol):
    def renew_lease(self, kind: str, record_id: int) -> None:
        """给长任务续租。``kind`` 取 ``index`` / ``report`` / ``answer``。"""
        ...

    def finish_task(self, kind: str, record_id: int, status: str, error: str | None = None) -> None:
        """任务收口；已取消的记录不再改写。``kind`` 同上。"""
        ...
