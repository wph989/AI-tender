"""后台任务队列端口：API 只提交任务名与稳定 ID，不依赖 Celery 实现。"""

from __future__ import annotations

from typing import Protocol


class TaskQueue(Protocol):
    def enqueue(
        self,
        task_name: str,
        args: tuple[object, ...],
        *,
        countdown: float = 0,
    ) -> str | None:
        """提交可由数据库状态恢复的消息；消息体不得包含文件或配置快照。

        返回 broker 的任务 id（拿不到就返回 None）：调用方只把它当关联号写进响应，
        任务进度仍以数据库里的状态为准，不依赖结果后端。
        """
        ...
