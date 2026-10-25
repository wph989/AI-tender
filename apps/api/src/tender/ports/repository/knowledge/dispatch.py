"""按调用者能力定义的仓储端口；SQL 与共享事务由同一实现提供。"""

from __future__ import annotations

from typing import Any, Protocol


class KnowledgeDispatchRepository(Protocol):
    def sources(self, collection_ids: list[int]) -> list[dict[str, Any]]:
        """这批知识库里当前可用的资料及其解析/索引状态。

        每行同时带回解析批次、在途任务、最近一次失败与最新索引，调用方据此判断
        「能不能检索」而不是再查一遍库。
        """
        ...

    def create_index(self, source: dict[str, Any]) -> None:
        """为一份资料登记一次索引任务。"""
        ...

    def collections_pending_index(self) -> list[int]:
        """资料仍可用的知识库 id；派发索引前先按它缩小范围。"""
        ...

    def claim_dispatchable(self, kind: str, limit: int) -> list[int]:
        """取出本公司在期应执行的任务并顺带续租，防止同一任务被重复投递。``kind`` 同上。"""
        ...
