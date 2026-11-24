"""按调用者能力定义的仓储端口；SQL 与共享事务由同一实现提供。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ChunkWindow:
    """有界原文窗口；流式回退未扫描全文时，total 为 None。"""

    rows: list[dict[str, Any]]
    total: int | None
    has_more: bool


class SourceReader(Protocol):
    company_id: int

    def collection(self, collection_id: int) -> dict[str, Any]:
        """取知识库；不存在、已删除或项目已删除时抛 ``LookupError``。"""
        ...

    def collection_for_project(self, project_id: int) -> int | None:
        """项目的资料库 id；项目下没有资料库时返回 ``None``。"""
        ...

    def collections_for_project(self, project_id: int) -> list[int]:
        """项目可用的知识库：自己的资料库 + 显式关联的独立知识库。"""
        ...

    def sources(self, collection_ids: list[int]) -> list[dict[str, Any]]:
        """这批知识库里当前可用的资料及其解析/索引状态。

        每行同时带回解析批次、在途任务、最近一次失败与最新索引，调用方据此判断
        「能不能检索」而不是再查一遍库。
        """
        ...

    def blocks(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        """资料在该解析批次下的全部元素（按页、按序）。"""
        ...

    def readable_chunks(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        """资料的检索分块：在元素之上再按长度切分，并带定位信息。"""
        ...

    def read_chunk_window(
        self, source: dict[str, Any], offset: int, limit: int,
    ) -> ChunkWindow:
        """读取指定分块范围并重新核对权限，不加载整份资料。"""
        ...

    def resolve(self, ref: dict[str, Any], *, with_content: bool = False) -> dict[str, Any]:
        """校验一条引文的身份并补全定位；身份不符时抛 ``LookupError``。

        引文里的数字全部视作不可信输入，所以整条身份必须在**一次**带权限约束的查询里匹配。
        """
        ...

    def project_exists(self, project_id: int) -> bool: ...
