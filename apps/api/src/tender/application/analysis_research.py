"""模块 Agent 的检索会话：权限在工具边界执行，证据在上下文之外保留。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from tender.application.knowledge import normalized

Retrieve = Callable[[list[dict], str], Awaitable[tuple[list[dict], dict]]]
Read = Callable[[dict], Awaitable[list[dict]]]


class SourceNotAllowed(PermissionError):
    """工具参数引用了清单外的来源；拒绝读取后允许模型按清单纠正。"""


@dataclass(frozen=True)
class AgentLimits:
    """持久快照使用同一预算；恢复执行不能重置计数来绕过限制。"""

    max_model_calls: int = 32
    max_tool_calls: int = 48
    max_evidence_blocks: int = 160
    timeout_seconds: int = 900
    context_tokens: int = 24000
    max_output_tokens: int = 4096


@dataclass
class ResearchSession:
    sources: Sequence[dict]
    project_id: int
    retrieve: Retrieve
    read: Read
    authorize: Callable[[], Awaitable[None]]
    limits: AgentLimits = field(default_factory=AgentLimits)
    seen: dict[str, dict] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    tool_calls: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def _begin(self, action: str, arguments: dict) -> None:
        # 每次工具操作都重新检查取消及关联权限；不能只在任务创建时检查一次。
        await self.authorize()
        async with self._lock:
            if self.tool_calls >= self.limits.max_tool_calls:
                raise ValueError("本模块已达到工具调用预算")
            self.tool_calls += 1
            self.events.append({"action": action, "arguments": arguments})

    def _sources(self, scope: str, source_id: int | None = None) -> list[dict]:
        if scope not in {"project", "reference"}:
            raise ValueError("检索范围只能是项目文档或关联知识库")
        rows = [
            s for s in self.sources if (s["project_id"] == self.project_id) == (scope == "project")
        ]
        if source_id is not None:
            rows = [s for s in rows if s["source_id"] == source_id]
            if not rows:
                raise SourceNotAllowed("资料不在本模块授权范围，请先 list_documents 核对 source_id")
        return rows

    def _remember(self, rows: list[dict], *, deduplicate: bool) -> dict:
        allowed = {(s["source_id"], s["parse_run_id"], s["version_id"]) for s in self.sources}
        blocks, duplicates = [], []
        remembered = dict(self.seen)
        for row in rows:
            if (row["source_id"], row["parse_run_id"], row["version_id"]) not in allowed:
                raise PermissionError("检索返回了范围外或错误版本的证据")
            key = str(row["block_id"])
            # 不跨文件按文字去重：同文异版、补充通知和历史资料必须保留各自证据身份。
            identical = next(
                (
                    old
                    for old in remembered.values()
                    if old["source_id"] == row["source_id"]
                    and old["parse_run_id"] == row["parse_run_id"]
                    and old["element_id"] == row["element_id"]
                    and normalized(old["content"]) == normalized(row["content"])
                ),
                None,
            )
            if deduplicate and identical:
                duplicates.append(identical["block_id"])
                continue
            if key not in remembered and len(remembered) >= self.limits.max_evidence_blocks:
                raise ValueError("本模块已达到证据块预算，请基于已有证据完成分析")
            remembered[key] = dict(row)
            blocks.append(
                {
                    k: row[k]
                    for k in (
                        "block_id",
                        "source_id",
                        "collection_id",
                        "project_id",
                        "purpose",
                        "file_name",
                        "offset",
                        "chapter",
                        "content",
                    )
                }
            )
        self.seen = remembered
        return {"blocks": blocks, "already_read": list(dict.fromkeys(duplicates))}

    async def documents(self) -> list[dict]:
        await self._begin("list_documents", {})
        return [
            {
                k: s[k]
                for k in (
                    "source_id",
                    "collection_id",
                    "project_id",
                    "file_name",
                    "purpose",
                )
            }
            for s in self.sources
        ]

    async def search(self, query: str, scope: str, source_id: int | None = None) -> dict:
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
            raise ValueError("检索问题须为1到500个字符")
        await self._begin("search_" + scope, {"query": query, "source_id": source_id})
        sources = self._sources(scope, source_id)
        if not sources:
            return {"blocks": [], "already_read": [], "warning": "当前没有关联参考资料"}
        rows, info = await self.retrieve(sources, query.strip())
        # 查询等待期间可能撤销关联，结果进入模型上下文前再次检查。
        await self.authorize()
        async with self._lock:
            result = self._remember(rows[:12], deduplicate=True)
        self.events.append(
            {
                "action": "search_result",
                "scope": scope,
                "block_ids": [b["block_id"] for b in result["blocks"]],
                **info,
            }
        )
        return result | {"retrieval": info}

    async def read_source(self, source_id: int, offset: int, limit: int = 6) -> dict:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 12:
            raise ValueError("阅读偏移须非负，每次只能读取1到12块")
        sources = [s for s in self.sources if s["source_id"] == source_id]
        if len(sources) != 1:
            raise SourceNotAllowed("资料不在本模块授权范围，请先 list_documents 核对 source_id")
        await self._begin(
            "read_document", {"source_id": source_id, "offset": offset, "limit": limit}
        )
        rows = await self.read(sources[0])
        await self.authorize()
        async with self._lock:
            # 显式补读允许重新返回旧证据；历史压缩后仍可从证据库恢复原文。
            result = self._remember(rows[offset : offset + limit], deduplicate=False)
        return result | {
            "total": len(rows),
            "next_offset": (offset + limit if offset + limit < len(rows) else None),
        }

    def checkpoint(self) -> dict[str, Any]:
        return {"seen": self.seen, "events": self.events, "tool_calls": self.tool_calls}
