"""取证优化必须保留完整条款，并在失败时保持旧证据账。"""

import asyncio
import copy
from dataclasses import replace

import pytest
from test_analysis_research import block, session

from tender.application.analysis.research import AgentLimits, EvidenceBudgetError


def rows(count, *, element=None):
    return [block() | {"block_id": f"s1r1c{i}", "offset": i,
                       "element_id": i if element is None else element,
                       "content": f"条件{i}"} for i in range(count)]


def test_compact_read_honors_requested_window_without_repeated_model_roundtrips():
    async def run():
        source_rows = rows(20)
        research = session(source_rows)
        research.compact_results = True
        research.seen = {"s1r1c10": source_rows[10]}
        result = await research.read_evidence("s1r1c10", 5, 6)
        assert [b["id"] for b in result["blocks"]] == [f"s1r1c{i}" for i in range(5, 17)]
        assert result["applied"] == {"before": 5, "after": 6}
        assert not result["truncated"] and not result["read_limited"]
        assert result["continue_from"] == []
        assert research.tool_calls == 1

    asyncio.run(run())


def test_compact_forward_read_keeps_evidence_budget_atomic():
    async def run():
        source_rows = rows(20)
        research = session(source_rows, limits=AgentLimits(max_evidence_blocks=10))
        research.compact_results = True
        research.seen = {"s1r1c0": source_rows[0]}
        with pytest.raises(EvidenceBudgetError):
            await research.read_evidence("s1r1c0", 0, 10)
        # 不把被总额度拒绝的窗口冒充已读；Agent可据反馈缩小同一窗口。
        assert set(research.seen) == {"s1r1c0"}
        result = await research.read_evidence("s1r1c0", 0, 9)
        assert [b["id"] for b in result["blocks"]] == [f"s1r1c{i}" for i in range(10)]
        assert len(research.seen) == 10

    asyncio.run(run())


def test_compact_long_element_is_complete_but_zero_window_only_rereads_anchor():
    async def run():
        source_rows = rows(8, element=1)
        research = session(source_rows)
        research.compact_results = True
        research.seen = {"s1r1c3": source_rows[3]}
        quote = await research.read_evidence("s1r1c3", 0, 0)
        assert [b["id"] for b in quote["blocks"]] == ["s1r1c3"]
        research.seen["s1r1c4"] = source_rows[4]
        result = await research.read_evidence(["s1r1c3", "s1r1c4"], 1, 1)
        assert [b["id"] for b in result["blocks"]] == [b["block_id"] for b in source_rows]
        assert result["windows"] == [{"first_id": "s1r1c0", "last_id": "s1r1c7"}]

    asyncio.run(run())


def test_long_anchor_element_is_returned_before_optional_neighbor_uses_capacity():
    async def run():
        source_rows = rows(5)
        for row in source_rows[1:4]:
            row.update(element_id=100, content="完整表格条件" * 1000)
        research = session(source_rows)
        research.compact_results = True
        research.seen = {"s1r1c1": source_rows[1]}
        result = await research.read_evidence("s1r1c1", 1, 1)
        assert [b["id"] for b in result["blocks"]] == [
            "s1r1c0", "s1r1c1", "s1r1c2", "s1r1c3",
        ]
        assert not result["read_limited"]

    asyncio.run(run())


def test_dependency_capacity_failure_is_atomic_and_reports_confirmed_union():
    async def run():
        source_rows = rows(168)
        research = session(source_rows, limits=AgentLimits(max_evidence_blocks=160))
        research.seen = {r["block_id"]: r for r in source_rows[:160]}
        # 八个连续续段缺失，已保留的其他材料不能被删除腾额度。
        for row in source_rows[159:]:
            row["element_id"] = 999
        before = copy.deepcopy(research.checkpoint())
        with pytest.raises(EvidenceBudgetError) as caught:
            await research.review_context({"s1r1c159"})
        assert research.checkpoint() == before
        assert caught.value.capacity == {"used": 160, "additional": 1, "required": 161,
                                         "limit": 160, "lower_bound": True}
        research.limits = replace(research.limits, max_evidence_blocks=200)
        result = await research.review_context({"s1r1c159"})
        assert len(research.seen) == 168
        assert result["dependencies"]["s1r1c159"] == [r["block_id"] for r in source_rows[158:]]

    asyncio.run(run())


def test_oversized_dependency_stops_reading_as_soon_as_capacity_is_exceeded():
    async def run():
        source_rows = rows(1000, element=1)
        research = session(source_rows, limits=AgentLimits(max_evidence_blocks=4))
        research.seen = {source_rows[0]["block_id"]: source_rows[0]}
        before = copy.deepcopy(research.checkpoint())
        original, calls = research.read, []

        async def read(source, offset, limit):
            calls.append((offset, limit))
            return await original(source, offset, limit)

        research.read = read
        with pytest.raises(EvidenceBudgetError) as caught:
            await research.review_context({"s1r1c0"})
        # 容量已明确不足后不再扫描剩余续段，拒绝时旧证据与缓存也必须完整保留。
        assert len(calls) <= research.limits.max_evidence_blocks
        assert research.checkpoint() == before
        assert caught.value.capacity == {"used": 1, "additional": 4, "required": 5,
                                         "limit": 4, "lower_bound": True}
        assert "至少" in str(caught.value)

    asyncio.run(run())


def test_dependency_capacity_counts_unique_required_rows_and_excludes_boundary_probes():
    async def run():
        source_rows = rows(7)
        for row in source_rows[1:6]:
            row["element_id"] = 100
        research = session(source_rows, limits=AgentLimits(max_evidence_blocks=5))
        research.seen = {source_rows[3]["block_id"]: source_rows[3]}
        # 重叠锚点和元素两端探边不能重复计入必要依赖，恰好五块仍可完整接纳。
        research.seen[source_rows[4]["block_id"]] = source_rows[4]
        result = await research.review_context({"s1r1c3", "s1r1c4"})
        assert {row["block_id"] for row in result["blocks"]} == {
            row["block_id"] for row in source_rows[1:6]
        }
        assert len(research.seen) == 5

    asyncio.run(run())


@pytest.mark.parametrize("evidence_limit", [5, 160])
def test_limited_multi_anchor_read_can_continue_directly_from_undelivered_anchor(evidence_limit):
    async def run():
        source_rows = rows(8)
        for row in source_rows[1:4]:
            row.update(element_id=100, content="完整表格条件" * 1000)
        # 工具只交付软容量内的完整元素，未交付组不能提前占用证据额度。
        research = session(source_rows, limits=AgentLimits(max_evidence_blocks=evidence_limit))
        research.compact_results = True
        research.seen = {key: source_rows[index] for key, index in (
            ("s1r1c1", 1), ("s1r1c6", 6),
        )}
        result = await research.read_evidence(["s1r1c1", "s1r1c6"], 1, 1)
        assert result["read_limited"]
        assert "s1r1c6" in result["continue_from"]
        reread = await research.read_evidence("s1r1c6", 0, 0)
        assert [b["id"] for b in reread["blocks"]] == ["s1r1c6"]

    asyncio.run(run())


def test_dependency_cache_reuses_reads_but_revalidates_authorization():
    async def run():
        source_rows = rows(10)
        research = session(source_rows)
        research.seen = {"s1r1c5": source_rows[5]}
        original, calls, authorized = research.read, [], []

        async def read(source, offset, limit):
            calls.append((offset, limit))
            return await original(source, offset, limit)

        async def authorize():
            authorized.append(True)

        research.read, research.authorize = read, authorize
        await research.review_context({"s1r1c5"})
        count = len(calls)
        await research.review_context({"s1r1c5"})
        assert len(calls) == count and len(authorized) > 1
        # 内容指纹变化不能沿用旧依赖缓存。
        research.seen["s1r1c5"] = source_rows[5] | {"content": "新条件"}
        with pytest.raises(PermissionError):
            await research.review_context({"s1r1c5"})

    asyncio.run(run())


def test_dependency_wrong_version_at_tail_does_not_save_any_rows():
    async def run():
        source_rows = rows(8, element=1)
        research = session(source_rows)
        research.seen = {"s1r1c3": source_rows[3]}
        before = copy.deepcopy(research.checkpoint())
        source_rows[-1]["version_id"] = 99
        with pytest.raises(PermissionError):
            await research.review_context({"s1r1c3"})
        assert research.checkpoint() == before

    asyncio.run(run())


def test_dependency_cache_ignores_search_score_and_rechecks_after_process_restart():
    async def run():
        source_rows = rows(7)
        research = session(source_rows)
        research.seen = {"s1r1c3": source_rows[3] | {"score": 0.95}}
        await research.review_context({"s1r1c3"})
        checkpoint = copy.deepcopy(research.checkpoint())
        restored = session(source_rows)
        restored.seen, restored.dependencies = checkpoint["seen"], checkpoint["dependencies"]
        source_rows[4]["version_id"] = 99
        with pytest.raises(PermissionError):
            await restored.review_context({"s1r1c3"})
        assert restored.seen == checkpoint["seen"]

    asyncio.run(run())


def test_submission_prepares_dependencies_before_staging_and_keeps_independent_record():
    from synthesis_fixtures import summary_record
    from test_analysis_combined_review import execute
    from test_deep_analysis import call

    async def run():
        source_rows = rows(8)
        records = [summary_record(key="too-wide", text="条件3", quote="条件3",
                                  citations=[{"block_id": "s1r1c3", "quote": "条件3"}]),
                   summary_record(key="fits", text="条件0", quote="条件0")]
        state, saved, _, _ = await execute(records, evidence_rows=source_rows,
            limits=AgentLimits(max_evidence_blocks=4), synthesis_steps=[
                call("submit_analysis", {"records": [r | {"work_ids": ["w1"]} for r in records],
                                         "final": False}, "batch"),
                call("submit_analysis", {"records": [], "final": True}, "final"),
            ])
        assert {item["business"]["key"] for item in state["staged_items"]} == {"fits"}
        assert "s1r1c4" not in state["research"]["seen"]
        staged = next(s for s in saved if s.get("staged_items"))
        assert staged["research"]["dependencies"]
        assert not any(item["business"]["key"] == "too-wide" for s in saved
                       for item in s.get("staged_items", []))

    asyncio.run(run())


def test_native_capacity_receipts_keep_original_positions_and_used_required_numbers():
    import json

    from test_analysis_v3 import build, raw
    from test_deep_analysis import call

    from tender.application.analysis.agent import invoke_module

    async def run():
        research = session(rows(8), limits=AgentLimits(max_evidence_blocks=4))
        script = [call("search_document", {"query": "条件", "work_ids": ["w1"]}, "search"),
                  call("submit_analysis", {"records": [
                      raw(block_ids=["s1r1c3"], content={"字段": "超限", "内容": "条件3"}),
                      raw(content={"字段": "有效", "内容": "条件0"}),
                  ], "final": False}, "capacity"),
                  call("complete_research", {"research_summary": "保留已核对结果与缺口"}, "done")]
        graph, files, state, _, _, _ = build(script, research)
        await invoke_module(graph, files, thread_id="capacity", task="分析")
        receipt = json.loads(state["tool_results"]["call_capacity"]["data"]["content"])
        assert [r["status"] for r in receipt["records"]] == ["rejected", "accepted"]
        assert receipt["records"][0]["capacity"] == {
            "used": 4, "additional": 1, "required": 5, "limit": 4, "lower_bound": True,
        }
        assert len(state["staged_items"]) == 1

    asyncio.run(run())
