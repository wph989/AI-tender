"""检索式 Agent 的权限和去重不能依赖提示词或模型自觉。"""

import asyncio

import pytest

from tender.application.shared.research import (
    AgentLimits,
    EvidenceBudgetError,
    ResearchSession,
    ToolArgumentError,
)
from tender.ports.repository.knowledge.sources import ChunkWindow


def source(sid=1, project=10):
    return {
        "source_id": sid,
        "collection_id": sid,
        "project_id": project,
        "file_name": f"{sid}.pdf",
        "purpose": "tender" if project == 10 else "reference",
        "parse_run_id": 1,
        "version_id": sid,
    }


def block(sid=1, project=10):
    return source(sid, project) | {
        "block_id": f"s{sid}r1c0",
        "element_id": sid,
        "content": "质保三年",
        "offset": 0,
        "chapter": "质保",
    }


async def allow():
    return None


def session(rows, *, auth=allow, limits=None):
    async def retrieve(sources, query):
        selected = {s["source_id"] for s in sources}
        return [row for row in rows if row["source_id"] in selected], {"mode": "keyword"}

    async def read(selected_source, offset, limit):
        selected = [row for row in rows if row["source_id"] == selected_source["source_id"]]
        return ChunkWindow(
            selected[offset:offset + limit], len(selected), offset + limit < len(selected),
        )

    return ResearchSession(
        [source(), source(2, 20)], 10, retrieve, read, auth, limits or AgentLimits()
    )


def test_retrieval_is_autonomous_without_mandatory_fulltext_scan():
    async def run():
        research = session([block(), block(2, 20)])
        assert research.seen == {}
        result = await research.search("质保要求", "project")
        assert [b["source_id"] for b in result["blocks"]] == [1]
        assert set(research.seen) == {"s1r1c0"}
        assert research.tool_calls == 1

    asyncio.run(run())


def test_source_and_evidence_reads_request_bounded_windows():
    async def run():
        rows = [block() | {"offset": index, "element_id": index + 1,
                           "block_id": f"s1r1c{index}"} for index in range(20)]
        research = session(rows)
        requests = []
        original = research.read

        async def read_window(selected_source, offset, limit):
            requests.append((offset, limit))
            return await original(selected_source, offset, limit)

        research.read = read_window
        result = await research.read_source(1, 10, 1)
        assert requests == [(10, 1)]
        assert result["total"] == 20 and result["next_offset"] == 11
        research.compact_results = True
        result = await research.read_evidence("s1r1c10", before=2, after=1)
        assert requests[-1] == (8, 4)
        assert [row["id"] for row in result["blocks"]] == [f"s1r1c{i}" for i in (8, 9, 10, 11)]

    asyncio.run(run())


def test_out_of_range_tool_arguments_are_correctable_not_terminal():
    async def run():
        research = session([block()])
        # 参数越界是可自纠正错误：运行时把提示回传模型，而不是击穿整个模块。
        with pytest.raises(ToolArgumentError):
            await research.read_source(1, -1)
        with pytest.raises(ToolArgumentError):
            await research.read_source(1, 0, 13)
        with pytest.raises(ToolArgumentError):
            await research.search("", "project")
        assert research.seen == {} and research.tool_calls == 0
        # 预算耗尽属于终态错误，不能被纠正提示绕过。
        exhausted = session([block()], limits=AgentLimits(max_tool_calls=0))
        with pytest.raises(ValueError) as excinfo:
            await exhausted.search("质保", "project")
        assert not isinstance(excinfo.value, ToolArgumentError)

    asyncio.run(run())


def test_evidence_budget_denies_new_blocks_but_allows_rereading_known_ones():
    async def run():
        research = session([block(), block(2, 20)], limits=AgentLimits(max_evidence_blocks=1))
        await research.read_source(1, 0)
        # 预算已满：新增证据被拒绝，但这是可自纠正提示，不是终止性错误。
        with pytest.raises(EvidenceBudgetError):
            await research.read_source(2, 0)
        # 已在证据账中的块仍可重复读取，保证压缩后可恢复原文。
        again = await research.read_source(1, 0)
        assert again["blocks"][0]["content"] == "质保三年"

    asyncio.run(run())


def test_budget_boundary_returns_available_and_known_blocks_without_losing_entire_batch():
    async def run():
        rows = [
            block()
            | {"block_id": f"s1r1c{i}", "element_id": i + 1, "offset": i, "content": f"第{i}项要求"}
            for i in range(4)
        ]
        research = session(rows, limits=AgentLimits(max_evidence_blocks=2))
        await research.read_source(1, 3, 1)
        # 新块排在已读块之前时，超限只能省略新块，不能把后面的已读原文也拒绝。
        result = await research.read_source(1, 0, 4)
        assert [b["block_id"] for b in result["blocks"]] == ["s1r1c0", "s1r1c3"]
        assert set(research.seen) == {"s1r1c0", "s1r1c3"}
        assert result["omitted_blocks"] == 2 and result["budget_exhausted"]
        assert result["warning"]
        # 达到预算也不能忽略随后出现的越权证据；仍须整批拒绝。
        before = dict(research.seen)
        with pytest.raises(PermissionError):
            research._remember([rows[1], block(99, 99)], deduplicate=False)
        assert research.seen == before

    asyncio.run(run())


def test_duplicate_hits_reuse_evidence_but_same_text_in_other_file_is_preserved():
    async def run():
        research = session([block(), block(2, 20)])
        await research.search("质保", "project")
        repeated = await research.search("售后质保", "project")
        assert repeated["blocks"] == [] and repeated["already_read"] == ["s1r1c0"]
        reference = await research.search("质保", "reference")
        assert reference["blocks"][0]["source_id"] == 2
        assert len(research.seen) == 2
        # 压缩模型历史后仍允许精确补读；去重不能让原文永久消失。
        reread = await research.read_source(1, 0)
        assert reread["blocks"][0]["content"] == "质保三年"

    asyncio.run(run())


def test_unknown_source_and_out_of_scope_retrieval_are_rejected_atomically():
    async def run():
        research = session([block()])
        with pytest.raises(PermissionError):
            await research.search("质保", "project", 99)
        with pytest.raises(PermissionError):
            await research.read_source(99, 0)
        with pytest.raises(PermissionError):
            research._remember([block(), block(99, 99)], deduplicate=True)
        assert research.seen == {}
        with pytest.raises(PermissionError):
            research._remember([block() | {"parse_run_id": 2}], deduplicate=True)

    asyncio.run(run())


def test_revocation_during_retrieval_prevents_results_entering_context():
    async def run():
        checks = 0

        async def authorize():
            nonlocal checks
            checks += 1
            if checks == 2:
                raise PermissionError("知识库关联已撤销")

        research = session([block()], auth=authorize)
        with pytest.raises(PermissionError, match="撤销"):
            await research.search("质保", "project")
        assert research.seen == {}

    asyncio.run(run())


def test_tool_budget_counts_concurrent_requests_and_survives_checkpoint():
    async def run():
        research = session([block()], limits=AgentLimits(max_tool_calls=1))
        results = await asyncio.gather(
            research.documents(), research.documents(), return_exceptions=True
        )
        assert sum(isinstance(result, ValueError) for result in results) == 1
        assert research.checkpoint()["tool_calls"] == 1
        checkpoint = research.checkpoint()
        restored = ResearchSession(
            research.sources, research.project_id, research.retrieve, research.read,
            research.authorize, research.limits, **checkpoint,
        )
        # 同一 attempt 的检查点恢复仍沿用计数，不能借进程重启获得新预算。
        with pytest.raises(ValueError, match="工具调用预算"):
            await restored.documents()
        assert restored.tool_calls == 1

    asyncio.run(run())
