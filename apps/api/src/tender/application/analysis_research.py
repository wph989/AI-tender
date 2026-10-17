"""模块 Agent 的检索会话：权限在工具边界执行，证据在上下文之外保留。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from tender.application.knowledge import normalized

Retrieve = Callable[[list[dict], str], Awaitable[tuple[list[dict], dict]]]
Read = Callable[[dict], Awaitable[list[dict]]]
Expand = Callable[[list[dict], list[dict]], Awaitable[tuple[list[dict], list[dict]]]]


class SourceNotAllowed(PermissionError):
    """工具参数引用了清单外的来源；拒绝读取后允许模型按清单纠正。"""


class ToolArgumentError(ValueError):
    """工具参数越界或类型不符；属于可自纠正错误，回传给模型修正而不是终止模块。"""


class EvidenceBudgetError(ValueError):
    """证据块预算已满；拒绝新增原文但允许模型基于已有证据完成分析，属于可自纠正错误。"""


@dataclass(frozen=True)
class AgentLimits:
    """持久快照使用同一预算；恢复执行不能重置计数来绕过限制。"""

    max_model_calls: int = 40
    max_tool_calls: int = 48
    max_evidence_blocks: int = 160
    similarity_threshold: float = 0.6
    max_search_results: int = 6
    timeout_seconds: int = 1800
    context_tokens: int = 24000
    max_output_tokens: int = 8192
    max_tool_failures: int = 3
    max_no_progress_rounds: int = 3
    max_finish_corrections: int = 2
    rate_limit_backoff_seconds: int = 30
    rate_limit_max_wait_seconds: int = 600
    max_identical_tool_calls: int = 3
    max_validation_failures: int = 3
    max_subagent_retries: int = 2


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
    expand: Expand | None = None
    # 问答保留原协议；专题解析在构图时开启，避免把位置和检索分数交给分析模型。
    compact_results: bool = False
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
        omitted = 0
        remembered = dict(self.seen)
        # 同元素才可能内容相同；按元素分桶后每批只需比较桶内已读块，避免每次检索全账扫描。
        by_element: dict[tuple, list[dict]] = {}
        for old in remembered.values():
            by_element.setdefault(
                (old["source_id"], old["parse_run_id"], old["element_id"]), []
            ).append(old)
        for row in rows:
            if (row["source_id"], row["parse_run_id"], row["version_id"]) not in allowed:
                raise PermissionError("检索返回了范围外或错误版本的证据")
            key = str(row["block_id"])
            element = (row["source_id"], row["parse_run_id"], row["element_id"])
            # 不跨文件按文字去重：同文异版、补充通知和历史资料必须保留各自证据身份。
            content = normalized(row["content"])
            identical = next(
                (
                    old for old in by_element.get(element, [])
                    # 预算丢弃或被覆盖的旧块不再代表已读内容。
                    if remembered.get(str(old["block_id"])) is old
                    and normalized(old["content"]) == content
                ),
                None,
            )
            if deduplicate and identical:
                duplicates.append(identical["block_id"])
                continue
            if key not in remembered and len(remembered) >= self.limits.max_evidence_blocks:
                # 预算只限制新增证据；混合批次仍须返回可容纳的新块和已读块，避免补读死路。
                # 继续检查后续行的权限，不能因预算已满而跳过越权结果。
                omitted += 1
                continue
            remembered[key] = dict(row)
            by_element.setdefault(element, []).append(remembered[key])
            blocks.append(
                {"id": key, "text": row["content"]}
                if self.compact_results
                else {
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
        if omitted and not blocks and not duplicates:
            raise EvidenceBudgetError("本模块已达到证据块预算，请基于已有证据完成分析")
        self.seen = remembered
        result = {"blocks": blocks, "already_read": list(dict.fromkeys(duplicates))}
        if omitted:
            result.update(
                budget_exhausted=True,
                omitted_blocks=omitted,
                warning="证据块预算已满，本批只返回预算内及已读原文；请据此提交并说明检索缺口",
            )
        return result

    async def documents(self) -> list[dict]:
        await self._begin("list_documents", {})
        if self.compact_results:
            return [
                {
                    "id": str(s["source_id"]),
                    "text": ("本项目资料" if s["project_id"] == self.project_id else "参考资料")
                    + "："
                    + s["file_name"]
                    + "；用途："
                    + s["purpose"],
                }
                for s in self.sources
            ]
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
            raise ToolArgumentError("检索问题须为1到500个字符")
        await self._begin("search_" + scope, {"query": query, "source_id": source_id})
        sources = self._sources(scope, source_id)
        if not sources:
            return {"blocks": [], "already_read": [], "warning": "当前没有关联参考资料"}
        rows, info = await self.retrieve(sources, query.strip())
        # 专题使用运行快照里的数量上限；问答沿用原协议，避免串改其它消费入口。
        result_limit = self.limits.max_search_results if self.compact_results else 12
        rows, relations = rows[:result_limit], []
        if self.expand:
            # 扩展必须处于同一次检索工具内，让 Agent 真正读到关联原文；范围仍是本次所选资料。
            rows, relations = await self.expand(sources, rows)
        selected_sources = {s["source_id"] for s in sources}
        if any(r["source_id"] not in selected_sources for r in rows):
            raise PermissionError("检索返回了所选范围以外的资料，不能将参考资料混入本项目")
        if self.compact_results:
            # 扩展也不能绕过专题单次输出上限；未返回的关系证据不会登记进证据账。
            rows = rows[:result_limit]
        # 查询等待期间可能撤销关联，结果进入模型上下文前再次检查。
        await self.authorize()
        async with self._lock:
            result = self._remember(rows, deduplicate=True)
            # 超预算未进入证据账的块不能通过关系引文旁路进入上下文。
            relations = [
                link
                for link in relations
                if link.get("citations")
                and all(str(ref.get("block_id")) in self.seen for ref in link["citations"])
            ]
        if self.expand and not self.compact_results:
            result["relations"] = relations
        self.events.append(
            {
                "action": "search_result",
                "scope": scope,
                "query": query.strip(),
                "source_ids": sorted(selected_sources),
                "block_ids": [
                    b["id" if self.compact_results else "block_id"] for b in result["blocks"]
                ],
                **info,
                "relations": relations,
            }
        )
        return result if self.compact_results else result | {"retrieval": info}

    async def read_evidence(self, block_id: str, before: int = 2, after: int = 2) -> dict:
        """只允许围绕已读 ID 补读，服务端解析位置，防止模型猜测偏移或跨版本读取。"""
        if any(type(n) is not int or n < 0 for n in (before, after)) or before + after > 11:
            raise ToolArgumentError("before/after 必须为非负整数，连同当前块每次最多12块")
        row = self.seen.get(block_id)
        if row is None:
            raise ToolArgumentError("证据ID尚未读取，请先检索；不得猜测其他资料的ID")
        sources = [s for s in self.sources if s["source_id"] == row["source_id"]]
        if len(sources) != 1:
            raise SourceNotAllowed("证据所属资料不在授权范围")
        await self._begin("read_evidence", {"block_id": block_id, "before": before, "after": after})
        rows = await self.read(sources[0])
        await self.authorize()
        if any(r["source_id"] != row["source_id"] for r in rows):
            raise PermissionError("补读返回了其它来源的资料")
        # 依赖原文 offset 而不是列表下标，过滤缺块窗口时也不会错读其它条款。
        selected = sorted(
            (r for r in rows if row["offset"] - before <= r["offset"] <= row["offset"] + after),
            key=lambda r: r["offset"],
        )
        if not any(str(r["block_id"]) == block_id for r in selected):
            raise PermissionError("证据已失效，请基于最新资料重新分析")
        async with self._lock:
            return self._remember(selected, deduplicate=False)

    async def read_source(self, source_id: int, offset: int, limit: int = 6) -> dict:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 12:
            raise ToolArgumentError("阅读偏移须非负，每次只能读取1到12块")
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
