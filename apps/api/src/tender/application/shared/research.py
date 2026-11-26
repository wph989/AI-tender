"""分析与问答共用的检索会话，统一核对来源、证据额度与补读版本。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from tender.application.knowledge.content import normalized
from tender.application.shared.validation import InputError, allowed_values
from tender.domain.shared.digest import fingerprint
from tender.ports.repository.knowledge.sources import ChunkWindow

Retrieve = Callable[[list[dict], str], Awaitable[tuple[list[dict], dict]]]
Read = Callable[[dict, int, int], Awaitable[ChunkWindow]]
Expand = Callable[[list[dict], list[dict]], Awaitable[tuple[list[dict], list[dict]]]]


class SourceNotAllowed(PermissionError):
    """工具参数引用了清单外的来源；拒绝读取后允许模型按清单纠正。"""


class ToolArgumentError(InputError):
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
    rate_limit_backoff_seconds: int = 30
    rate_limit_max_wait_seconds: int = 600
    # 该配置键沿用现有名称，实际限制当前专题图的检查点连接恢复，不启动递归子Agent。
    max_subagent_retries: int = 2
    # 供应商不可用时在同一 thread/attempt 内的有界恢复次数。
    max_model_recoveries: int = 2
    # 同一查询最多翻 5 页；候选窗口按页大小成倍缓存，避免改写同义词续命。
    max_search_pages: int = 5

    @property
    def search_window(self) -> int:
        """召回与分页共用一个候选窗口，避免调整单页数量后提前丢掉后续页。"""
        return self.max_search_results * self.max_search_pages


# 已检索候选按查询缓存，供 offset 翻页复用；进程内有效，不写入检查点。
SEARCH_CACHE_ENTRIES = 8


def _dependency_fingerprint(row: dict) -> str:
    # 检索分数和处理状态不属于原文身份，否则检索命中与仓储补读会被误判为不同版本。
    return fingerprint([row.get(k) for k in (
        "source_id", "version_id", "parse_run_id", "block_id", "offset", "element_id", "content",
        "locations",
    )])


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
    # 专题解析的候选缓存：同一查询按 offset 翻页时不再重复 embedding/重排/DB 查询。
    _search_cache: dict[tuple, tuple[list[dict], dict]] = field(default_factory=dict, repr=False)
    # 同一查询的并发分页只召回一次；不同查询仍可并行。锁的数量受本轮工具预算约束。
    _search_locks: dict[tuple, asyncio.Lock] = field(default_factory=dict, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def _begin(self, action: str, arguments: dict) -> None:
        # 每次工具操作都重新检查取消及关联权限；不能只在任务创建时检查一次。
        await self.authorize()
        async with self._lock:
            if not self.compact_results and self.tool_calls >= self.limits.max_tool_calls:
                raise ValueError("本模块已达到工具调用预算")
            self.tool_calls += 1
            self.events.append({"action": action, "arguments": arguments})

    async def _context_blocks(self, anchors: set[str], before: int, after: int,
                              *, extend: bool) -> tuple[list[dict], dict]:
        """合并普通邻域，再沿锚点元素读到边界；探边的其它条款不额外入账。"""
        ranges: dict[int, list[tuple[int, int]]] = {}
        for key in sorted(anchors):
            row = self.seen[key]
            offset = row["offset"]
            ranges.setdefault(row["source_id"], []).append((max(0, offset - before),
                                                          offset + after + 1))
        blocks = []
        for source_id, windows in ranges.items():
            source = next(s for s in self.sources if s["source_id"] == source_id)
            merged: list[list[int]] = []
            for start, end in sorted(windows):
                if merged and start <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])
            for start, end in merged:
                for offset in range(start, end, 12):
                    await self.authorize()
                    window = await self.read(source, offset, min(12, end - offset))
                    window = self._validate_window(source, window, offset, min(12, end - offset))
                    blocks.extend(window.rows)
        # 长表格/段落可能横跨很多块；沿已知元素读至边界，不能把固定邻域当作完整依赖。
        by_position = {(r["source_id"], r["offset"]): r for r in blocks}
        checked = set(by_position)
        pending = [(self.seen[key]["source_id"], self.seen[key]["offset"],
                    self.seen[key]["element_id"]) for key in anchors] if extend else []
        visited = set()
        included = set(by_position)
        while pending:
            sid, offset, element_id = pending.pop()
            if (sid, offset) in visited:
                continue
            visited.add((sid, offset))
            for neighbor in (offset - 1, offset + 1):
                if neighbor < 0:
                    continue
                position = sid, neighbor
                if position not in checked:
                    await self.authorize()
                    source = next(s for s in self.sources if s["source_id"] == sid)
                    window = await self.read(source, neighbor, 1)
                    window = self._validate_window(source, window, neighbor, 1)
                    checked.add(position)
                    for row in window.rows:
                        by_position[row["source_id"], row["offset"]] = row
                adjacent = by_position.get(position)
                if adjacent and adjacent["element_id"] == element_id:
                    included.add(position)
                    pending.append((sid, neighbor, element_id))
        blocks = [by_position[position] for position in sorted(included)]
        await self.authorize()
        if anchors - {r["block_id"] for r in blocks}:
            raise PermissionError("补读引文已失效，请基于最新资料重新分析")
        dependencies = {}
        for key in sorted(anchors):
            anchor = self.seen[key]
            actual = next(r for r in blocks if r["block_id"] == key)
            if _dependency_fingerprint(anchor) != _dependency_fingerprint(actual):
                raise PermissionError("补读引文内容或版本已变化，请基于最新资料重新分析")
            positions = {anchor["offset"]}
            if extend:
                for direction in (-1, 1):
                    offset = anchor["offset"] + direction
                    while (adjacent := by_position.get((anchor["source_id"], offset))):
                        if adjacent["element_id"] != anchor["element_id"]:
                            break
                        positions.add(offset)
                        offset += direction
            positions.update(range(max(0, anchor["offset"] - before),
                                   anchor["offset"] + after + 1))
            dependencies[key] = [r["block_id"] for r in blocks
                                 if r["source_id"] == anchor["source_id"]
                                 and r["offset"] in positions]
        return blocks, dependencies

    def _validate_window(self, source: dict, window: ChunkWindow, offset: int,
                         limit: int) -> ChunkWindow:
        identity = tuple(source[k] for k in ("source_id", "version_id", "parse_run_id"))
        if any(tuple(r[k] for k in ("source_id", "version_id", "parse_run_id")) != identity
               for r in window.rows):
            raise PermissionError("补读返回了其它来源或错误版本的资料")
        selected = [r for r in window.rows if offset <= r["offset"] < offset + limit]
        if window.total is not None and {r["offset"] for r in selected} != set(
                range(offset, min(offset + limit, window.total))):
            raise PermissionError("补读原文窗口不完整，请基于最新资料重新分析")
        return ChunkWindow(selected, window.total, window.has_more)

    def _check_evidence_capacity(self, block_ids: set[str]) -> None:
        additional = len(block_ids - self.seen.keys())
        required = len(self.seen) + additional
        if required > self.limits.max_evidence_blocks:
            raise EvidenceBudgetError(
                f"已保留{len(self.seen)}块，新增{additional}块，"
                f"共需{required}块，"
                f"上限{self.limits.max_evidence_blocks}块",
            )

    def _remember_complete(self, blocks: list[dict]) -> dict:
        # 必要依赖不能像检索候选一样逐块省略；完整批次验证成功后才替换证据账。
        self._check_evidence_capacity({r["block_id"] for r in blocks})
        return self._remember(blocks, deduplicate=False)

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
        # 只有检索需要去重；显式补读必须原样返回，避免为不用的比较建立索引和归一化文本。
        by_element: dict[tuple, list[dict]] = {}
        if deduplicate:
            for old in remembered.values():
                by_element.setdefault(
                    (old["source_id"], old["parse_run_id"], old["element_id"]), []
                ).append(old)
        for row in rows:
            if (row["source_id"], row["parse_run_id"], row["version_id"]) not in allowed:
                raise PermissionError("检索返回了范围外或错误版本的证据")
            key = str(row["block_id"])
            element = (row["source_id"], row["parse_run_id"], row["element_id"])
            if deduplicate:
                # 不跨文件按文字去重：同文异版、补充通知和历史资料保留各自证据身份。
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
                if identical:
                    duplicates.append(identical["block_id"])
                    continue
            if key not in remembered and len(remembered) >= self.limits.max_evidence_blocks:
                # 预算只限制新增证据；混合批次仍须返回可容纳的新块和已读块，避免补读死路。
                # 继续检查后续行的权限，不能因预算已满而跳过越权结果。
                omitted += 1
                continue
            remembered[key] = dict(row)
            if deduplicate:
                by_element.setdefault(element, []).append(remembered[key])
            blocks.append(
                # 章节区分已填写条款、通用条款和空白格式，精简输出也不能丢失这一语义。
                {"id": key, "text": row["content"],
                 **{k: row[k] for k in ("source_id", "chapter") if row.get(k) is not None}}
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
        result: dict[str, Any] = {"blocks": blocks, "already_read": list(dict.fromkeys(duplicates))}
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

    async def search(
        self, query: str, scope: str, source_id: int | None = None, offset: int = 0
    ) -> dict:
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 500:
            raise ToolArgumentError("检索问题须为1到500个字符")
        if type(offset) is not int or offset < 0:
            raise ToolArgumentError("检索分页偏移须为非负整数")
        # 专题使用运行快照里的数量上限；问答沿用原协议，避免串改其它消费入口。
        page_size = self.limits.max_search_results if self.compact_results else 12
        if self.compact_results and offset >= page_size * self.limits.max_search_pages:
            # 翻页上限属于可纠正的调用方式错误：不消耗工具或证据预算，也不终止模块。
            return {
                "blocks": [],
                "already_read": [],
                "page": {
                    "offset": offset,
                    "limit": page_size,
                    "next_offset": None,
                    "has_more": False,
                },
                "search_hint": (
                    f"同一查询最多翻{self.limits.max_search_pages}页；"
                    "请按未覆盖子主题拆分检索、限定 source_id 或登记缺口，"
                    "不要继续翻同一查询。"
                ),
            }
        arguments = {"query": query, "source_id": source_id}
        if self.compact_results:
            arguments["offset"] = offset
        await self._begin("search_" + scope, arguments)
        sources = self._sources(scope, source_id)
        if not sources:
            return {"blocks": [], "already_read": [], "warning": "当前没有关联参考资料"}
        relations: list[dict] = []
        has_more = False
        if self.compact_results:
            cache_key = (
                scope,
                # 空格、HTML 实体会改变关键词拆分与嵌入语义，不能沿用引文匹配的归一化。
                query.strip(),
                source_id,
                tuple(sorted(s["source_id"] for s in sources)),
            )
            async with self._search_locks.setdefault(cache_key, asyncio.Lock()):
                cached = self._search_cache.get(cache_key)
                if cached is None:
                    retrieved, info = await self.retrieve(sources, query.strip())
                    # 失败或取消时不写缓存，等待者仍可重试；不启动脱离模块生命周期的后台请求。
                    candidates = [dict(row) for row in retrieved[:self.limits.search_window]]
                    info = dict(info) | {
                        "candidate_limited": bool(info.get("search_limited"))
                        or len(retrieved) > len(candidates)
                    }
                    info.pop("search_limited", None)
                    cached = (candidates, info)
                    self._search_cache[cache_key] = cached
                    if len(self._search_cache) > SEARCH_CACHE_ENTRIES:
                        self._search_cache.pop(next(iter(self._search_cache)))
            candidates, info = cached
            rows = candidates[offset:offset + page_size]
            # 即使本页因去重变少也按原始页大小推进游标，避免翻页卡死。
            has_more = offset + page_size < len(candidates)
            search_limited = bool(info.get("candidate_limited"))
        else:
            retrieved, info = await self.retrieve(sources, query.strip())
            search_limited = bool(info.get("search_limited")) or len(retrieved) > page_size
            rows = retrieved[:page_size]
            if self.expand:
                # 问答扩展在同一次检索内返回关联原文；专题解析只使用紧凑分页。
                rows, relations = await self.expand(sources, rows)
        selected_sources = {s["source_id"] for s in sources}
        if any(r["source_id"] not in selected_sources for r in rows):
            raise PermissionError("检索返回了所选范围以外的资料，不能将参考资料混入本项目")
        # 查询等待期间可能撤销关联，结果进入模型上下文前再次检查。
        await self.authorize()
        seen_before = set(self.seen)
        async with self._lock:
            result = self._remember(rows, deduplicate=True)
            # 超预算未进入证据账的块不能通过关系引文旁路进入上下文。
            relations = [
                link
                for link in relations
                if link.get("citations")
                and all(str(ref.get("block_id")) in self.seen for ref in link["citations"])
            ]
        page = None
        next_offset = offset + page_size if has_more else None
        if self.compact_results:
            page = {
                "offset": offset,
                "limit": page_size,
                "next_offset": next_offset,
                "has_more": has_more,
            }
            result["page"] = page
            if search_limited:
                result["search_limited"] = True
            if has_more:
                # 窗口外还有匹配不代表缓存已读完；先翻页才能复用已有召回，避免反复付费改写查询。
                result["search_hint"] = (
                    "同一查询仍有下一页：具体缺口需要时用 offset=next_offset 继续读取；"
                    "依据充分即可综合，不必穷尽相关性候选；未读分页不能声称已核对。"
                )
            elif search_limited:
                result["search_hint"] = (
                    "本次检索的候选窗口已到末尾，仍可能有未返回内容；"
                    "仅对具体未决条件拆分查询或限定 source_id；有未读相关条款时登记缺口。"
                )
            elif not rows and offset:
                result["search_hint"] = (
                    "该查询已无更多候选，请拆分主题、限定 source_id 或改用其它查询。"
                )
            elif not rows and info.get("mode") == "keyword":
                # 关键词回退按组合词的命中比例过滤；长查询空命中不能证明单个主题没有条款。
                # 仅对真正空召回提示，已读证据去重后的空 blocks 仍是成功命中。
                result["search_hint"] = (
                    "本次使用关键词检索且未命中，组合查询中的多个词会共同参与匹配；"
                    "请改用单一核心概念或原文中的短语，按子主题分别检索。未命中不等于原文未约定。"
                )
        elif self.expand:
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
                **{k: v for k, v in info.items() if k != "candidate_limited"},
                "search_limited": search_limited,
                "relations": relations,
                **(
                    {
                        "offset": offset,
                        "next_offset": next_offset,
                        "has_more": has_more,
                        "new_evidence": len(set(self.seen) - seen_before),
                    }
                    if self.compact_results
                    else {}
                ),
            }
        )
        return result if self.compact_results else result | {"retrieval": info}

    async def read_evidence(
        self, block_id: str | list[str], before: int = 2, after: int = 2,
    ) -> dict:
        """只允许围绕已读 ID 补读，服务端解析位置，防止模型猜测偏移或跨版本读取。"""
        if (any(type(n) is not int or not 0 <= n <= 11 for n in (before, after))
                or before + after > 11):
            raise ToolArgumentError("before/after 必须为非负整数，连同当前块每次最多12块")
        anchors = [block_id] if isinstance(block_id, str) else list(dict.fromkeys(block_id))
        if not 1 <= len(anchors) <= 4 or set(anchors) - self.seen.keys():
            raise ToolArgumentError(
                "block_id：须提供1到4个已读ID；可选ID：" + allowed_values(self.seen),
            )
        await self._begin("read_evidence", {"block_id": block_id, "before": before, "after": after})
        # 新Agent自行选择阅读窗口；每侧强截到一块会把一次连续补读放大成多轮模型调用。
        # 仍由上层12块常规窗口、下方完整元素软容量和证据总预算约束实际交付。
        applied = {"before": before, "after": after}
        blocks, dependencies = await self._context_blocks(
            set(anchors), applied["before"], applied["after"], extend=bool(before or after),
        )
        # 上下文只在完整元素之间截断；长段/表格本身始终作为整体交付。
        remaining = max(1024, (self.limits.context_tokens - self.limits.max_output_tokens) // 2)
        groups: list[list[dict]] = []
        for row in blocks:
            if groups and all(row[k] == groups[-1][-1][k] for k in (
                    "source_id", "element_id")) and row["offset"] == groups[-1][-1]["offset"] + 1:
                groups[-1].append(row)
            else:
                groups.append([row])
        selected: list[dict] = []
        for group in groups:
            size = sum(len(r["content"]) + len(r["block_id"]) + 32 for r in group)
            # 邻块不能抢占首个锚点的完整元素；即使超过软交付目标，也要完整返回该条款。
            has_anchor = any(r["block_id"] in anchors for r in selected)
            if selected and size > remaining and (has_anchor or not any(
                    r["block_id"] in anchors for r in group)):
                break
            selected.extend(group)
            remaining -= size
        limited = len(selected) < len(blocks)
        blocks = selected
        await self.authorize()
        async with self._lock:
            result = self._remember_complete(blocks)
        windows = []
        previous = None
        for row in blocks:
            if previous and row["source_id"] == previous["source_id"] and (
                    row["offset"] == previous["offset"] + 1):
                windows[-1]["last_id"] = row["block_id"]
            else:
                windows.append({"first_id": row["block_id"], "last_id": row["block_id"]})
            previous = row
        continuation = list(dict.fromkeys(key for window in windows
                                         for key in (window["first_id"], window["last_id"])))
        if limited:
            # 多锚点批次未交付的锚点原本就已读，可直接续读，不能只给前一窗口的边界。
            continuation.extend(key for key in anchors
                                if key not in {r["block_id"] for r in blocks}
                                and key not in continuation)
        result.update(requested={"before": before, "after": after}, applied=applied,
                      truncated=limited, windows=windows, read_limited=limited,
                      dependencies=dependencies, continue_from=continuation
                      if limited else [])
        self.events.append({"action": "read_result", "anchor_ids": anchors,
                            "block_ids": [r["block_id"] for r in blocks],
                            "windows": windows, "truncated": limited, "applied": applied,
                            "read_limited": limited,
                            "continue_from": result["continue_from"]})
        if limited:
            result["warning"] = "批量原文达到上下文容量，仅返回已读区间；按边界ID继续读取。"
        return result

    async def read_source(self, source_id: int, offset: int, limit: int = 6) -> dict:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 12:
            raise ToolArgumentError("阅读偏移须非负，每次只能读取1到12块")
        sources = [s for s in self.sources if s["source_id"] == source_id]
        if len(sources) != 1:
            raise SourceNotAllowed("资料不在本模块授权范围，请先 list_documents 核对 source_id")
        await self._begin(
            "read_document", {"source_id": source_id, "offset": offset, "limit": limit}
        )
        window = await self.read(sources[0], offset, limit)
        await self.authorize()
        async with self._lock:
            # 显式补读允许重新返回旧证据；历史压缩后仍可从证据库恢复原文。
            result = self._remember(window.rows, deduplicate=False)
        return result | {
            "total": window.total,
            "next_offset": offset + limit if window.has_more else None,
        }

    def checkpoint(self) -> dict[str, Any]:
        return {"seen": self.seen, "events": self.events, "tool_calls": self.tool_calls}
