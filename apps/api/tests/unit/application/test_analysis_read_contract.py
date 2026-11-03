"""补读窗口契约：运行时按 before 优先截断，参数超限不得终止模块。"""

import asyncio
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import research_calls, submission, summary_record
from test_analysis_research import block, session
from test_deep_analysis import KEY, SKILL, ScriptedRouter, call

from tender.application.analysis.agent import (
    RoutedAgentModel,
    build_module_agent,
    invoke_module,
)
from tender.application.analysis.research import AgentLimits, ToolArgumentError
from tender.ports.repository.knowledge.sources import ChunkWindow


async def noop(*args):
    pass


def build(router, research, state):
    return build_module_agent(
        key=KEY,
        model=RoutedAgentModel(router=router),
        research=research,
        state=state,
        snapshot=SKILL,
        checkpointer=InMemorySaver(),
        reserve_tool=noop,
        save=noop,
    )


def rows(count=15):
    return [
        block()
        | {"block_id": f"s1r1c{i}", "element_id": i + 1, "offset": i, "content": f"第{i}项条款"}
        for i in range(count)
    ]


def payload(state, call_id="call_2"):
    return json.loads(state["tool_results"][call_id]["data"]["content"])


def final_calls(number=9):
    return (
        *research_calls(query="条款"),
        call("submit_analysis", submission([summary_record(quote="第0项条款")]), number),
    )


def run_read(arguments, *, limits=None, count=15, read=None):
    async def run():
        research = session(rows(count), limits=limits)
        if read is not None:
            research.read = read
        router = ScriptedRouter(
            [
                call("search_document", {"query": "条款"}, 1),
                call("read_document", arguments, 2),
                *final_calls(),
            ]
        )
        state = {}
        graph, files = build(router, research, state)
        await invoke_module(graph, files, thread_id="read-contract", task="分析")
        return research, state

    return asyncio.run(run())


def test_read_document_clamps_sum_over_eleven_and_reports_applied_window():
    research, state = run_read({"block_id": "s1r1c5", "before": 11, "after": 11})
    result = payload(state)
    assert result["requested"] == {"before": 11, "after": 11}
    # before 优先：先取满向前窗口，after 不再扩张总量。
    assert result["applied"] == {"before": 11, "after": 0}
    assert result["truncated"] is True and "截断" in result["warning"]
    assert [b["id"] for b in result["blocks"]] == [f"s1r1c{i}" for i in range(6)]
    assert set(research.seen) >= {b["id"] for b in result["blocks"]}


def test_read_document_clamps_before_first_then_after():
    _, state = run_read({"block_id": "s1r1c5", "before": 8, "after": 8})
    result = payload(state)
    assert result["applied"] == {"before": 8, "after": 3}
    assert result["truncated"] is True


def test_read_document_full_budget_clamps_to_quote_only_without_tool_error():
    research, state = run_read(
        {"block_id": "s1r1c0", "before": 2, "after": 2},
        limits=AgentLimits(max_evidence_blocks=2),
    )
    result = payload(state)
    assert result["applied"] == {"before": 0, "after": 0}
    assert result["quote_only"] is True and "未补入邻域" in result["warning"]
    # 预算已满只回读已登记原块，不新增证据，也不计入终止性工具失败。
    assert set(research.seen) == {"s1r1c0", "s1r1c1"}
    assert not state.get("tool_failures", {}).get("read_document")
    # 唯一的参数错误来自收尾阶段被运行时拒绝的扩展检索，补读本身没有记账。
    assert state["argument_failure_rounds"]["tools"] == ["search_document"]


def test_lower_level_read_evidence_still_rejects_oversized_window():
    async def run():
        research = session(rows())
        await research.search("条款", "project")
        with pytest.raises(ToolArgumentError):
            await research.read_evidence("s1r1c0", 11, 11)
        # 单侧越界仍由底层拒绝，工具层的截断不能放宽证据窗口底线。
        with pytest.raises(ToolArgumentError):
            await research.read_evidence("s1r1c0", -1, 0)

    asyncio.run(run())


def test_read_document_result_never_claims_unread_neighbours():
    data = rows()

    async def read(selected_source, offset, limit):
        # 适配器可能返回大于请求的窗口；运行时必须按 offset 过滤，不能把邻块冒充已读。
        window = data[max(0, offset - 1):offset + limit + 1]
        return ChunkWindow(window, len(data), True)

    _, state = run_read({"block_id": "s1r1c3", "before": 2, "after": 2}, read=read)
    result = payload(state)
    assert [b["id"] for b in result["blocks"]] == [
        f"s1r1c{i}" for i in range(1, 6)
    ]
    assert result["applied"] == {"before": 2, "after": 2}
    assert result["truncated"] is False


def test_read_document_schema_failure_is_correctable_not_terminal():
    async def run():
        research = session(rows())
        router = ScriptedRouter(
            [
                call("search_document", {"query": "条款"}, 1),
                call("read_document", {"block_id": "s1r1c0", "before": -1}, 2),
                *final_calls(),
            ]
        )
        state = {}
        graph, files = build(router, research, state)
        await invoke_module(graph, files, thread_id="read-schema", task="分析")
        assert "draft" in state
        assert state["argument_failures"] == 1
        assert not state.get("tool_failures", {}).get("read_document")
        content = state["tool_results"]["call_2"]["data"]["content"]
        assert content.startswith("[tool_argument_invalid]")

    asyncio.run(run())
