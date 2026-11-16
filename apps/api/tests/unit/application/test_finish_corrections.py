"""收尾纠正必须采用配置快照、恢复保留计数，并保全已通过校验的事项。"""

import asyncio
import copy
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from synthesis_fixtures import accept, noop, research_calls, submission, summary_record
from test_analysis_research import block, session
from test_analysis_synthesis import execute
from test_deep_analysis import call, submitted_field

from tender.application.analysis.agent import ResearchMiddleware
from tender.application.analysis.research import AgentLimits
from tender.application.analysis.runtime import limits_snapshot
from tender.application.knowledge.content import validate_items
from tender.config.schema import READONLY_REASONS, resolve_values, validate_value, write_denial


def test_finish_correction_config_defaults_overrides_and_bounds():
    assert AgentLimits().max_finish_corrections == 2
    for value in (1, 5, 1000000):
        assert validate_value("analysis.max_finish_corrections", value) is None
    for value in (True, 1.5, "5"):
        assert validate_value("analysis.max_finish_corrections", value) is not None
    assert "固定修复轮数" in READONLY_REASONS["analysis.max_finish_corrections"]
    assert write_denial("admin", ["analysis.max_finish_corrections"]) is not None
    frozen = limits_snapshot(SimpleNamespace(resolved_config=lambda: resolve_values({
        "analysis.max_finish_corrections": 5,
    })))
    assert AgentLimits(**frozen).max_finish_corrections == 5


@pytest.mark.parametrize("maximum", [1, 2, 5])
def test_finish_budget_exhausts_at_configured_round_and_preserves_verified_result(maximum):
    async def run():
        research = session([block()], limits=AgentLimits(max_finish_corrections=maximum))
        await research.search("质保", "project")
        fields = validate_items([submitted_field("质保期限", "质保三年")], research.seen)
        fields[0]["verification"] = "supported"
        state, saved = {"staged_items": fields, "staged_items_verified": True}, []

        async def save(value):
            saved.append(copy.deepcopy(value))

        middleware = ResearchMiddleware(research, state, noop, save, review_support=accept)
        await middleware.abefore_model({"messages": [AIMessage(content="", id="initial")]}, None)
        stop_round = research.limits.max_no_progress_rounds + maximum
        for number in range(1, stop_round):
            message = AIMessage(content="", id=str(number))
            await middleware.abefore_model({"messages": [message]}, None)
            assert state["no_progress_rounds"] == number and "draft" not in state
            # 同一模型消息在checkpoint恢复后再次执行，不能多扣一次机会。
            await middleware.abefore_model({"messages": [message]}, None)
            assert state["no_progress_rounds"] == number
        assert state["finish_only"]
        with pytest.raises(RuntimeError, match=f"已达{maximum}次上限"):
            await middleware.abefore_model({"messages": [
                AIMessage(content="", id=str(stop_round)),
            ]}, None)
        assert saved[-1]["staged_items"][0]["verification"] == "supported"
        assert saved[-1]["no_progress_rounds"] == stop_round and "draft" not in state

    asyncio.run(run())


@pytest.mark.parametrize("maximum", [2, 5])
def test_real_graph_can_finish_after_two_idle_corrections_only_when_budget_is_increased(maximum):
    scenario = execute([
        *research_calls(),
        call("submit_analysis", submission([summary_record()], final=False), "record"),
        *[call("read_document", {"block_id": "s1r1c0", "before": n, "after": 0}, n)
          for n in range(6)],
        call("submit_analysis", {"records": [], "final": True}, "final"),
    ], research=session([block()], limits=AgentLimits(max_finish_corrections=maximum)))
    if maximum == 2:
        with pytest.raises(RuntimeError, match="收尾纠正已达2次上限"):
            asyncio.run(scenario)
        return
    state, _, router = asyncio.run(scenario)
    assert state["finish_only"] and len(state["draft"]["business_data"]["records"]) == 1
    assert "收尾连续无进展纠正剩余2轮" in str(router.requests[-1][0])
    assert "上限5轮" in str(router.requests[-1][0])


def test_new_verified_fact_restarts_consecutive_idle_count_in_finish_mode():
    async def run():
        research = session([block()], limits=AgentLimits(max_finish_corrections=1))
        state = {}
        middleware = ResearchMiddleware(research, state, noop, noop, review_support=accept)
        for n in range(4):
            await middleware.abefore_model({"messages": [AIMessage(content="", id=str(n))]}, None)
        assert state["finish_only"] and state["no_progress_rounds"] == 3
        fields = validate_items([submitted_field("质保期限", "质保三年")], {"s1r1c0": block()})
        fields[0]["verification"] = "supported"
        state["staged_items"] = fields
        await middleware.abefore_model({"messages": [AIMessage(content="", id="new-fact")]}, None)
        assert state["no_progress_rounds"] == 0 and state["finish_only"]

    asyncio.run(run())
