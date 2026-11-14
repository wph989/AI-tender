"""检索单次交付完整条款，审查沿用同一依赖，并核对实时身份与容量。"""

import asyncio
from dataclasses import replace

import pytest
from test_analysis_research import block, session


def fragmented():
    texts = ("5.1 开标", "与投标截止同一时刻。", "仅限标段一。", "除另行通知外。")
    return [block() | {"block_id": "s1r1g2c0", "offset": 0,
                       "content": "5.1 开标\n与投标截止同一时刻。\n仅限标段一。\n"
                                  "除另行通知外，迟到不受理。",
                       "locations": [{"element_id": 1, "page_no": 1, "anchor": "p1b1",
                                      "char_start": 0, "char_end": sum(map(len, texts)) + 3,
                                      "bbox": [0, 0, 1, 0.35]}]}]


def research(rows):
    result = session(rows)
    result.compact_results = True

    async def retrieve(*_):
        return rows, {"mode": "keyword"}

    result.retrieve = retrieve
    return result


def test_search_delivers_each_original_id_and_clause_condition_in_one_tool_call():
    async def run():
        rows = fragmented()
        agent = research(rows)
        result = await agent.search("开标时刻", "project")
        assert {b["id"] for b in result["blocks"]} == {r["block_id"] for r in rows}
        assert result["blocks"][0]["text"] == rows[0]["content"]
        assert set(result["blocks"][0]) == {"id", "text"}
        assert agent.tool_calls == 1
        assert result["page"]["limit"] == agent.limits.max_search_results
        assert all(agent.seen[r["block_id"]]["element_id"] == r["element_id"] for r in rows)
        reviewed = await agent.review_context({rows[0]["block_id"]})
        assert set(reviewed["dependencies"][rows[0]["block_id"]]) == set(agent.seen)

    asyncio.run(run())


def test_context_budget_preserves_anchor_and_reports_omitted_evidence():
    async def run():
        rows = fragmented()
        agent = research(rows)
        rows.extend([block() | {"block_id": f"s1r1g2c{i}", "offset": i, "element_id": i + 1}
                     for i in range(1, 4)])
        agent.limits = replace(agent.limits, max_evidence_blocks=2)
        result = await agent.search("开标", "project")
        assert result["blocks"][0]["id"] == rows[0]["block_id"]
        assert len(agent.seen) == 2
        assert result["budget_exhausted"] and result["omitted_blocks"] == 2

    asyncio.run(run())


@pytest.mark.parametrize("invalid", ["identity", "content", "missing"])
def test_context_identity_change_or_incomplete_window_cannot_enter_evidence(invalid):
    async def run():
        rows = fragmented()
        agent = research(rows)
        original = agent.read

        async def read(*args):
            window = await original(*args)
            if not window.rows:
                return window
            if invalid == "identity":
                window.rows[-1]["version_id"] = 999
            elif invalid == "content":
                window.rows[0] = window.rows[0] | {"content": "已改变正文"}
            else:
                window.rows.pop()
            return window

        agent.read = read
        agent.seen = {row["block_id"]: dict(row) for row in rows}
        with pytest.raises(PermissionError):
            await agent.review_context({rows[0]["block_id"]})

    asyncio.run(run())
