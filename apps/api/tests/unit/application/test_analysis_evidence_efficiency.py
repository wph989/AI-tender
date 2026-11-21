"""取证优化必须保留完整条款，并在失败时保持旧证据账。"""

import asyncio

import pytest
from test_analysis_research import block, session

from tender.application.shared.research import AgentLimits, EvidenceBudgetError


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
