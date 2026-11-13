"""工具失败分类账本：可纠正错误只收窄工具，语义失败才保留三次终止线。"""

import asyncio
import json

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from test_analysis_research import block, session

from tender.application.analysis.agent import (
    FAILURE_POLICY_VERSION,
    TOOL_ARGUMENT_PREFIX,
    ResearchMiddleware,
)
from tender.application.analysis.research import (
    AgentLimits,
    EvidenceBudgetError,
    ToolArgumentError,
)


async def noop(*args):
    pass


def middleware(research, state=None):
    return ResearchMiddleware(research, state if state is not None else {}, noop, noop)


def request(name, args, *, call_id="c1", round_id="r1"):
    call = {"name": name, "args": args, "id": call_id, "type": "tool_call"}
    return ToolCallRequest(
        tool_call=call,
        tool=None,
        state={"messages": [AIMessage(content="", id=round_id, tool_calls=[call])]},
        runtime=None,
    )


def safe_json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {}


def test_invalid_read_document_arguments_do_not_enter_terminal_tool_failures():
    async def run():
        research = session([block()])
        state = {}
        wraps = middleware(research, state)

        async def handler(_request):
            await research.read_evidence("missing")

        for ordinal in range(4):
            result = await wraps.awrap_tool_call(
                request("read_document", {"block_id": f"missing-{ordinal}"},
                        call_id=f"c{ordinal}", round_id=f"r{ordinal}"),
                handler,
            )
            assert result.status == "error"
            assert safe_json(result.content)["error_code"] == "tool_argument_invalid"
        assert state["argument_failures"] == 4
        assert not state.get("tool_failures", {}).get("read_document")
        assert not state.get("finish_only")
        assert research.limits.max_argument_failures > 4

    asyncio.run(run())


def test_parallel_invalid_calls_in_one_model_round_count_once_per_tool():
    async def run():
        research = session([block()])
        state = {}
        wraps = middleware(research, state)

        async def handler(_request):
            raise ToolArgumentError("block_id尚未读取")

        results = await asyncio.gather(*[
            wraps.awrap_tool_call(
                request("read_document", {"block_id": f"missing-{n}"},
                        call_id=f"c{n}", round_id="same-round"),
                handler,
            )
            for n in range(3)
        ])
        assert all(result.status == "error" for result in results)
        assert state["argument_failures"] == 1
        assert state["argument_failure_rounds"]["tools"] == ["read_document"]

    asyncio.run(run())


def test_argument_failure_cap_enters_finish_only_and_keeps_verified_results():
    async def run():
        research = session([block()], limits=AgentLimits(max_argument_failures=2))
        state = {"staged_items": [{"id": "verified", "verification": "supported"}]}
        wraps = middleware(research, state)

        async def handler(_request):
            raise ToolArgumentError("参数不合法")

        for ordinal in range(2):
            await wraps.awrap_tool_call(
                request("search_document", {"query": ""},
                        call_id=f"c{ordinal}", round_id=f"r{ordinal}"),
                handler,
            )
        assert state["argument_failures"] == 2
        assert state["finish_only"] is True
        assert state["staged_items"] == [{"id": "verified", "verification": "supported"}]
        assert not state.get("tool_failures")

    asyncio.run(run())


def test_evidence_budget_rejection_is_non_terminal_and_bounded():
    async def run():
        research = session(
            [block(), block(2, 20)],
            limits=AgentLimits(max_evidence_blocks=1, max_evidence_budget_failures=2),
        )
        await research.read_source(1, 0)
        state = {}
        wraps = middleware(research, state)

        async def handler(_request):
            await research.read_source(2, 0)

        for ordinal in range(2):
            result = await wraps.awrap_tool_call(
                request("search_knowledge", {"query": "质保"},
                        call_id=f"c{ordinal}", round_id=f"r{ordinal}"),
                handler,
            )
            assert result.status == "error"
            assert safe_json(result.content)["error_code"] == "evidence_budget_exhausted"
        assert state["evidence_budget_failures"] == 2
        assert state["finish_only"] is True
        assert not state.get("tool_failures")
        assert research.seen.keys() == {"s1r1c0"}

    asyncio.run(run())


def test_unknown_source_id_is_correctable_but_revocation_is_terminal():
    async def run():
        research = session([block()])
        state = {}
        wraps = middleware(research, state)

        async def outside(_request):
            await research.read_source(99, 0)

        result = await wraps.awrap_tool_call(
            request("read_document", {"block_id": "s1r1c0"}), outside,
        )
        assert result.status == "error"
        assert safe_json(result.content)["error_code"] == "source_not_allowed"
        assert not state.get("tool_failures") and not state.get("argument_failures")

        async def revoked(_request):
            return ToolMessage("ok", tool_call_id="c2", name="list_documents")

        async def deny():
            raise PermissionError("知识库关联已撤销")

        research.authorize = deny
        with pytest.raises(PermissionError, match="撤销"):
            await wraps.awrap_tool_call(
                request("list_documents", {}, call_id="c2"), revoked,
            )

    asyncio.run(run())


def test_semantic_checkpoint_failure_keeps_three_strike_limit():
    async def run():
        research = session([block()])
        state = {}
        wraps = middleware(research, state)

        async def handler(req):
            call_id = req.tool_call["id"]
            if req.tool_call["name"] == "list_documents":
                return ToolMessage("[]", tool_call_id=call_id, name="list_documents")
            details = {"issues": [{"key": "reference:0:origin", "code": "invalid"}]}
            return ToolMessage(
                json.dumps({
                    "error_code": "research_checkpoint_invalid",
                    "message": "转引起点必须是已读取的项目原文",
                    "details": details,
                }),
                tool_call_id=call_id, name="complete_research", status="error",
            )

        for ordinal in range(2):
            result = await wraps.awrap_tool_call(
                request("complete_research", {},
                        call_id=f"c{ordinal}", round_id=f"r{ordinal}"),
                handler,
            )
            assert result.status == "error"
            # 其它工具成功不重置同一语义问题的失败账。
            await wraps.awrap_tool_call(
                request("list_documents", {},
                        call_id=f"ok{ordinal}", round_id=f"ok-round{ordinal}"),
                handler,
            )
        assert state["tool_failures"]["complete_research"] == 2
        with pytest.raises(ValueError, match="工具连续失败"):
            await wraps.awrap_tool_call(
                request("complete_research", {}, call_id="c9", round_id="r9"), handler,
            )
        assert state["tool_failures"]["complete_research"] == 3

    asyncio.run(run())


def test_mixed_tool_failures_report_actual_remaining_attempts_before_termination():
    async def run():
        research = session([block()], limits=AgentLimits(max_tool_failures=3))
        state = {}
        wraps = middleware(research, state)

        async def handler(req):
            return ToolMessage("研究更新未通过校验", tool_call_id=req.tool_call["id"],
                               name=req.tool_call["name"], status="error")

        for index, name in enumerate(("update_research", "get_research_context")):
            result = await wraps.awrap_tool_call(
                request(name, {}, call_id=f"c{index}", round_id=f"r{index}"), handler,
            )
            assert safe_json(result.content)["remaining_attempts"] == 2 - index
        with pytest.raises(ValueError, match="工具连续失败"):
            await wraps.awrap_tool_call(
                request("update_research", {}, call_id="last", round_id="last"), handler,
            )
        feedback = safe_json(state["tool_results"]["last"]["data"]["content"])
        assert feedback["remaining_attempts"] == 0
        assert "耗尽" in feedback["next_action"]
        assert state["tool_failures"]["update_research"] == 2

    asyncio.run(run())


def test_legacy_failure_counters_reset_once_under_new_policy():
    async def run():
        research = session([block()])
        state = {"tool_failures": {"read_document": 3}, "consecutive_tool_failures": 3}
        wraps = middleware(research, state)

        async def handler(req):
            return ToolMessage("[]", tool_call_id=req.tool_call["id"], name="list_documents")

        result = await wraps.awrap_tool_call(
            request("list_documents", {}, call_id="c1", round_id="r1"), handler,
        )
        assert result.status != "error"
        assert state["failure_policy_version"] == FAILURE_POLICY_VERSION
        assert state["tool_failures"].get("read_document") is None
        assert state["consecutive_tool_failures"] == 0
        # 版本标记已写入，后续失败从零重新记账而不是再次复位。
        state["tool_failures"]["list_documents"] = 1
        await wraps.awrap_tool_call(
            request("list_documents", {}, call_id="c2", round_id="r2"), handler,
        )
        assert state["tool_failures"]["list_documents"] == 0

    asyncio.run(run())


def test_schema_validation_failure_is_correctable_and_prefixed():
    async def run():
        research = session([block()])
        state = {}
        wraps = middleware(research, state)

        async def handler(req):
            # StructuredTool 的 handle_validation_error 结果是普通字符串，
            # ToolNode 会把它包成 status=success 的 ToolMessage。
            return ToolMessage(
                TOOL_ARGUMENT_PREFIX + "字段缺失", tool_call_id=req.tool_call["id"],
                name="read_document",
            )

        result = await wraps.awrap_tool_call(
            request("read_document", {"block_id": "s1r1c0"}), handler,
        )
        assert result.content.startswith(TOOL_ARGUMENT_PREFIX)
        assert state["argument_failures"] == 1
        assert not state.get("tool_failures")

    asyncio.run(run())


def test_source_scope_error_does_not_consume_evidence_budget_counter():
    async def run():
        research = session([block()], limits=AgentLimits(max_evidence_blocks=1))
        state = {}
        wraps = middleware(research, state)

        async def handler(_request):
            raise EvidenceBudgetError("本模块已达到证据块预算")

        await wraps.awrap_tool_call(
            request("search_document", {"query": "质保"}), handler,
        )
        assert state["evidence_budget_failures"] == 1
        assert not state.get("finish_only")

    asyncio.run(run())
