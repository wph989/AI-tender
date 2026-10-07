"""检索式 Agent 的权限和去重不能依赖提示词或模型自觉。"""

import asyncio

import pytest

from tender.application.analysis_research import AgentLimits, ResearchSession


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

    async def read(s):
        return [row for row in rows if row["source_id"] == s["source_id"]]

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

    asyncio.run(run())
