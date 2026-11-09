"""资源收敛回归：真实阶段切换、重复动作和连续条款读取。"""

import asyncio
import json

import pytest
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import noop, summary_record
from test_analysis_argument_failures import request
from test_analysis_combined_review import approve
from test_analysis_compact_protocol import ledger
from test_analysis_research import block, session
from test_analysis_topic_flow import snapshot
from test_deep_analysis import KEY, ScriptedRouter, call

from tender.application.analysis.agent import (
    ResearchMiddleware,
    RoutedAgentModel,
    build_module_agent,
    invoke_module,
)
from tender.application.analysis.data import module_data


@pytest.mark.parametrize("status", [
    {"model_calls_remaining": 8}, {"tool_calls_remaining": 8},
    {"seconds_remaining": 100, "finish_reserve_seconds": 300},
])
def test_research_v2_reserves_synthesis_before_hard_budget(status):
    _, flow, state, research = ledger()
    middleware = ResearchMiddleware(research, state, noop, noop, lambda: status, topic_flow=flow)
    assert middleware.budget_needs_synthesis(status)
    asyncio.run(middleware.abefore_model({"messages": []}, None))
    assert not flow.researching
    assert state["research_completed"]
    assert not flow.entries[0]["checked"] and not flow.entries[0].get("findings")
    assert not module_data(state)["records"]


def test_low_budget_keeps_initial_real_search_required():
    _, flow, state, research = ledger()
    research.events.clear()
    middleware = ResearchMiddleware(research, state, noop, noop,
                                    lambda: {"model_calls_remaining": 1}, topic_flow=flow)
    asyncio.run(middleware.abefore_model({"messages": []}, None))
    assert flow.researching and not state.get("research_completed")


def test_budget_closed_search_does_not_spend_argument_corrections_and_quote_still_works():
    _, flow, state, research = ledger()

    async def run():
        middleware = ResearchMiddleware(research, state, noop, noop,
                                        lambda: {"tool_calls_remaining": 2}, topic_flow=flow)
        executed = []

        async def handler(req):
            executed.append(req.tool_call["name"])
            return ToolMessage(content='{"blocks":[]}', tool_call_id=req.tool_call["id"])

        result = await middleware.awrap_tool_call(
            request("search_document", {"query": "换词再找", "work": "w1"}), handler,
        )
        assert json.loads(result.content)["work_closed"] and not executed
        assert not state.get("argument_failures")
        await middleware.awrap_tool_call(request("read_document", {
            "block_id": "s1r1c0", "before": 0, "after": 0,
        }, call_id="quote"), handler)
        assert executed == ["read_document"]

    asyncio.run(run())


def test_batch_reads_merge_overlapping_windows_and_preserve_clause_order():
    async def run():
        rows = [block() | {"block_id": f"s1r1c{i}", "offset": i, "element_id": i,
                           "content": f"条款{i}"} for i in range(30)]
        research = session(rows)
        research.compact_results = True
        research.seen = {rows[i]["block_id"]: rows[i] for i in (2, 5, 20)}
        reads = []
        read = research.read

        async def tracked(source, offset, limit):
            reads.append((offset, limit))
            return await read(source, offset, limit)

        research.read = tracked
        result = await research.read_evidence(["s1r1c5", "s1r1c2", "s1r1c20"], 2, 3)
        assert reads == [(0, 9), (18, 6)]
        assert [r["id"] for r in result["blocks"]] == [
            f"s1r1c{i}" for i in [*range(9), *range(18, 24)]
        ]
        assert research.tool_calls == 1
        assert result["windows"] == [
            {"first_id": "s1r1c0", "last_id": "s1r1c8"},
            {"first_id": "s1r1c18", "last_id": "s1r1c23"},
        ]

    asyncio.run(run())


def test_batch_read_checks_all_anchors_before_reading_or_recording_evidence():
    async def run():
        research = session([block()])
        research.seen = {"s1r1c0": block()}
        with pytest.raises(ValueError, match="尚未读取"):
            await research.read_evidence(["s1r1c0", "invented"], 0, 2)
        assert research.tool_calls == 0 and set(research.seen) == {"s1r1c0"}

    asyncio.run(run())


def test_batch_read_capacity_exposes_unread_boundary_and_can_continue():
    async def run():
        from tender.application.analysis.research import AgentLimits

        rows = [block() | {"block_id": f"s1r1c{i}", "offset": i, "element_id": i,
                           "content": f"条款{i}" + "条件" * 200} for i in range(15)]
        research = session(rows, limits=AgentLimits(context_tokens=6000, max_output_tokens=3000))
        research.compact_results = True
        research.seen = {rows[i]["block_id"]: rows[i] for i in (0, 3)}
        result = await research.read_evidence(["s1r1c0", "s1r1c3"], 0, 8)
        assert result["read_limited"] and len(result["blocks"]) < 12
        last = result["blocks"][-1]["id"]
        assert result["windows"][0]["last_id"] == last
        assert "s1r1c11" not in research.seen
        from tender.application.analysis.review import batches
        from tender.application.analysis.topic_flow import TopicFlow

        flow = TopicFlow({"business_topics": [{"key": "a", "checks": ["完整清单"]}]}, research)
        flow.evidence(set(), ["a"], result)
        from tender.application.analysis.review import _reads
        from tender.application.analysis.topic_flow import TopicIncomplete

        with pytest.raises(TopicIncomplete, match="超过审查上下文"):
            batches(flow, "a", [])
        reads = _reads(flow, flow.entries)
        assert reads[0]["read_limited"]
        assert reads[0]["continue_from"] == result["continue_from"]
        continuation = await research.read_evidence(last, 0, 3)
        assert any(row["id"] not in {r["id"] for r in result["blocks"]}
                   for row in continuation["blocks"])

    asyncio.run(run())


@pytest.mark.parametrize("window", [0, 1])
def test_reused_read_updates_new_topic_ownership_without_another_storage_read(window):
    _, flow, state, research = ledger()
    flow.state["business_topics"].append({"key": "b", "checks": ["例外"]})
    flow.data["entries"]["b"] = flow._entry(flow.state["business_topics"][-1],
                                            {"kind": "unknown", "lot_refs": []})
    middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)

    async def run():
        calls = []

        async def handler(req):
            calls.append(True)
            args = req.tool_call["args"]
            keys = flow.topic_keys(None, block_id=args["block_id"], work=args["work"])
            flow.data["active_topics"] = keys
            flow.evidence(set(research.seen), keys, {"already_read": ["s1r1c0"]})
            return ToolMessage(
                content=json.dumps({"blocks": [{"id": "s1r1c0", "text": "质保三年"}]}),
                tool_call_id=req.tool_call["id"],
            )

        for index, work in enumerate(("w1", "w2")):
            await middleware.awrap_tool_call(request("read_document", {
                "block_id": "s1r1c0", "before": window, "after": window, "work": work,
            }, call_id=f"read-{index}", round_id=f"round-{index}"), handler)
        assert len(calls) == 1
        assert set(flow.data["evidence_topics"]["s1r1c0"]) == {"a", "b"}
        assert flow.data["entries"]["b"]["evidence_ids"] == ["s1r1c0"]
        assert not state.get("topic_research_round")

    asyncio.run(run())


@pytest.mark.parametrize("anchors,before,after,expected", [
    ([2, 7], 2, 8, [(0, 12), (12, 4)]),
    ([0, 12, 24, 36], 0, 11, [(0, 12), (12, 12), (24, 12), (36, 12)]),
])
def test_batch_read_splits_merged_window_at_repository_limit(anchors, before, after, expected):
    async def run():
        rows = [block() | {"block_id": f"s1r1c{i}", "offset": i, "element_id": i,
                           "content": f"条款{i}"} for i in range(50)]
        research = session(rows)
        research.compact_results = True
        research.seen = {rows[i]["block_id"]: rows[i] for i in anchors}
        read, calls = research.read, []

        async def bounded_read(source, offset, limit):
            # 仓储契约最多12块；不让无限制的内存替身掩盖真实装配失败。
            assert 1 <= limit <= 12
            calls.append((offset, limit))
            return await read(source, offset, limit)

        research.read = bounded_read
        result = await research.read_evidence([rows[i]["block_id"] for i in anchors], before, after)
        assert calls == expected
        last = anchors[-1] + after
        assert [r["id"] for r in result["blocks"]] == [f"s1r1c{i}" for i in range(last + 1)]
        assert research.tool_calls == 1
        assert result["windows"] == [{"first_id": "s1r1c0", "last_id": f"s1r1c{last}"}]

    asyncio.run(run())


@pytest.mark.parametrize("status", [
    {"model_calls_remaining": 8}, {"tool_calls_remaining": 8},
    {"seconds_remaining": 200, "finish_reserve_seconds": 300},
])
def test_review_repair_can_use_reserved_budget_and_still_reserves_final_review(status):
    book, flow, state, research = ledger()
    for key in ("b", "c", "d", "e", "f"):
        topic = {"key": key, "checks": ["其他已核对事项"]}
        state["business_topics"].append(topic)
        flow.data["entries"][key] = flow._entry(topic, {"kind": "unknown", "lot_refs": []})
        flow.associate("s1r1c0", [key])
    book.finish("已核对质保年限，等待完整性审查")

    async def run():
        from tender.application.analysis.review import audit_combined

        async def missing(payload):
            return approve(payload) | {"issues": [{
                "topic": "a", "kind": "omission", "detail": "补读质保起算点条款",
                "target": "起算点条款", "record_ids": [], "evidence_ids": ["s1r1c0"],
            }]}

        assert not await audit_combined(flow, missing, noop)
        remaining = dict(status)
        middleware = ResearchMiddleware(research, state, noop, noop, lambda: remaining,
                                        topic_flow=flow)
        await middleware.abefore_model({"messages": []}, None)
        assert flow.researching
        executed = []

        async def handler(req):
            executed.append(req.tool_call["name"])
            return ToolMessage(content='{"blocks":[]}', tool_call_id=req.tool_call["id"])

        await middleware.awrap_tool_call(request("search_document", {
            "query": "质保起算点", "work": next(w["id"] for w in book.works()
                                                  if w["kind"] == "task"),
        }), handler)
        assert executed == ["search_document"]
        # 修复额度仍须收敛，剩余两次只能用于综合和最后复核。
        remaining.update(model_calls_remaining=2)
        await middleware.abefore_model({"messages": []}, None)
        assert not flow.researching
        assert any(t["status"] == "pending" for e in flow.entries for t in e["tasks"].values())

    asyncio.run(run())


def test_split_batch_rejects_late_unauthorized_rows_before_saving_any_evidence():
    async def run():
        from tender.ports.repository.knowledge.sources import ChunkWindow

        rows = [block() | {"block_id": f"s1r1c{i}", "offset": i, "element_id": i,
                           "content": f"条款{i}"} for i in range(20)]
        research = session(rows)
        research.seen = {rows[i]["block_id"]: rows[i] for i in (2, 7)}
        original, read = dict(research.seen), research.read

        async def changed_version(source, offset, limit):
            window = await read(source, offset, limit)
            if offset == 12:
                return ChunkWindow([row | {"version_id": 999} for row in window.rows],
                                   window.total, window.has_more)
            return window

        research.read = changed_version
        with pytest.raises(PermissionError, match="错误版本"):
            await research.read_evidence(["s1r1c2", "s1r1c7"], 2, 8)
        assert research.seen == original
        assert not any(e["action"] == "read_result" for e in research.events)

    asyncio.run(run())


def test_budget_boundary_graph_can_research_review_issue_and_publish_repaired_record():
    async def run():
        state, reviewed = {}, []
        second = block() | {"block_id": "s1r1c1", "offset": 1, "element_id": 2,
                            "content": "质保自验收合格之日起计算"}
        research = session([block(), second])

        async def retrieve(sources, query):
            return ([second] if query == "起算点" else [block()]), {"mode": "keyword"}

        research.retrieve = retrieve
        record = summary_record(work_ids=["w1"])
        repaired = summary_record(text="质保三年，自验收合格之日起计算", work_ids=["w1"],
                                  citations=[*record["citations"], {
                                      "block_id": "s1r1c1", "quote": second["content"],
                                  }])
        router = ScriptedRouter([
            call("search_document", {"query": "质保", "work": "w1"}, "search"),
            call("submit_analysis", {"records": [record], "final": True}, "first-final"),
            call("search_document", {"query": "起算点", "work": "w2"}, "repair-search"),
            call("complete_research", {"research_summary": "已补齐起算点"}, "repair-done"),
            call("submit_analysis", {"records": [repaired], "final": True}, "repaired-final"),
        ])

        async def review(payload):
            reviewed.append(payload)
            if len(reviewed) == 1:
                return approve(payload) | {"issues": [{
                    "topic": "a", "detail": "缺少质保起算点", "target": "起算点",
                    "evidence_ids": ["s1r1c0"], "record_ids": [], "kind": "reference",
                }]}
            assert payload["repair_issues"]
            assert any(e["id"] == "s1r1c1" for e in payload["evidence"])
            return approve(payload)

        graph, files = build_module_agent(
            key=KEY, model=RoutedAgentModel(router=router), research=research, state=state,
            snapshot=snapshot(("a",)) | {"__analysis_flow_version__": "research-v2"},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop, review_combined=review,
            budget_status=lambda: {"model_calls_remaining": 10 - len(router.requests)
                                  - len(reviewed)},
        )
        await invoke_module(graph, files, thread_id="reserved-repair", task="解析完整质保条款")
        assert not router.calls and len(reviewed) == 2
        published = module_data(state)["records"]
        assert len(published) == 1
        assert "验收合格" in str(published[0])
        assert {r["block_id"] for r in state["staged_items"][0]["values"][0]["citations"]} == {
            "s1r1c0", "s1r1c1",
        }

    asyncio.run(run())


def test_rotating_queries_without_new_evidence_yields_to_synthesis():
    async def run():
        from test_analysis_combined_review import execute

        state, _, router, _ = await execute(
            [summary_record(work_ids=["w1"])],
            research_steps=[call("search_document", {"query": query, "work": "w1"}, str(i))
                            for i, query in enumerate(("质保期限", "保修年限", "三年"))],
            synthesis_steps=[call("submit_analysis", {
                "records": [summary_record(work_ids=["w1"])], "final": True,
            }, "final")],
        )
        assert state["topic_flow"]["research_stop_reason"] == "no_progress"
        assert len(router.requests) == 6
        assert len(module_data(state)["records"]) == 1
        assert not state.get("argument_failures")

    asyncio.run(run())


def test_batched_tool_infers_all_anchor_topics_and_keeps_single_read_contract():
    async def run():
        research = session([block(), block() | {
            "block_id": "s1r1c1", "offset": 1, "element_id": 2, "content": "不含人为损坏",
        }])
        await research.search("质保", "project")
        state = {}
        graph, _ = build_module_agent(
            key=KEY, model=RoutedAgentModel(router=ScriptedRouter([])), research=research,
            state=state,
            snapshot=snapshot(("a", "b")) | {"__analysis_flow_version__": "research-v2"},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop,
        )
        state["topic_flow"]["evidence_topics"] = {"s1r1c0": ["a"], "s1r1c1": ["b"]}
        tool = graph.nodes["tools"].bound.tools_by_name["read_document"]
        result = await tool.ainvoke(call("read_document", {
            "block_id": ["s1r1c0", "s1r1c1"], "before": 0, "after": 1,
        }, "batch"))
        assert result.status == "success"
        assert len(json.loads(result.content)["blocks"]) == 2
        assert all(set(keys) == {"a", "b"}
                   for keys in state["topic_flow"]["evidence_topics"].values())

    asyncio.run(run())


def test_small_topics_share_one_review_request_and_one_copy_of_evidence():
    async def run():
        from test_analysis_combined_review import execute
        from test_analysis_semantic_completion import finish

        state, _, _, reviewed = await execute(
            [summary_record(work_ids=["w1", "w2"])], keys=("a", "b"),
            search_args={"query": "质保", "work": ["w1", "w2"]}, research_steps=[finish()],
        )
        assert len(reviewed) == 1
        assert reviewed[0]["topics"] == ["a", "b"]
        assert len(reviewed[0]["records"]) == len(reviewed[0]["evidence"]) == 1
        assert {c["topic"] for c in reviewed[0]["checks"]} == {"a", "b"}
        assert len(module_data(state)["records"]) == 1
        assert all(e["status"] == "ready" for e in state["topic_flow"]["entries"].values())

    asyncio.run(run())


def test_review_keeps_distinct_evidence_contexts_separate():
    _, flow, _, research = ledger()

    async def run():
        from tender.application.analysis.review import audit_combined

        flow.state["business_topics"].append({"key": "b", "checks": ["例外"]})
        flow.data["entries"]["b"] = flow._entry(flow.state["business_topics"][-1],
                                                {"kind": "unknown", "lot_refs": []})
        research.seen["s1r1c1"] = block() | {
            "block_id": "s1r1c1", "offset": 1, "element_id": 2, "content": "三年质保不含耗材",
        }
        flow.data["entries"]["b"]["evidence_ids"] = ["s1r1c1"]
        reviewed = []

        async def review(payload):
            reviewed.append(payload)
            return approve(payload)

        assert await audit_combined(flow, review, noop)
        # 各主题的缓存必须只依赖自身提供的原文，避免拆回后漏掉跨主题证据依赖。
        assert len(reviewed) == 2
        assert [{span["id"] for span in p["evidence"]} for p in reviewed] == [
            {"s1r1c0"}, {"s1r1c1"},
        ]
        assert set(flow.data["audit"]["completed_topics"]) == {"0:a", "0:b"}

    asyncio.run(run())


def test_parallel_search_rejections_cannot_consume_reserved_synthesis_tools():
    _, flow, state, research = ledger()
    remaining = 12

    async def reserve():
        nonlocal remaining
        remaining -= 1

    async def forbidden(_):
        raise AssertionError("预算关闭后不能执行检索")

    async def run():
        middleware = ResearchMiddleware(research, state, reserve, noop,
                                        lambda: {"tool_calls_remaining": remaining},
                                        topic_flow=flow)
        for index in range(20):
            result = await middleware.awrap_tool_call(request("search_document", {
                "query": "重复搜索", "work": "w1",
            }, call_id=f"pending-{index}", round_id="same-response"), forbidden)
            assert json.loads(result.content)["work_closed"]
        assert remaining == 12 and not state.get("argument_failures")
        await middleware.abefore_model({"messages": []}, None)
        assert not flow.researching and not module_data(state)["records"]

    asyncio.run(run())


def test_evidence_limit_still_allows_synthesis_of_last_delivered_batch():
    _, flow, state, research = ledger()
    from dataclasses import replace

    research.limits = replace(research.limits, max_evidence_blocks=1)
    flow.evidence(set(), ["a"], {"already_read": ["s1r1c0"], "budget_exhausted": True})
    state["topic_budget_exhausted"] = "模拟旧检查点中的证据额度耗尽标记"
    middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)
    asyncio.run(middleware.abefore_model({"messages": []}, None))
    assert not state.get("topic_budget_exhausted") and not flow.researching
    assert set(research.seen) == {"s1r1c0"}


def test_merged_review_restores_persisted_response_without_another_model_call():
    async def run():
        import copy

        from test_analysis_combined_review import execute
        from test_analysis_semantic_completion import finish

        from tender.application.analysis.review import audit_combined
        from tender.application.analysis.topic_flow import TopicFlow

        state, _, _, _ = await execute(
            [summary_record(work_ids=["w1", "w2"])], keys=("a", "b"),
            search_args={"query": "质保", "work": ["w1", "w2"]}, research_steps=[finish()],
        )
        state.pop("draft", None)
        state["topic_flow"]["audit"] = {"round": 0, "results": {}}
        for item in state["staged_items"]:
            item.update(verification="pending", review_status="needs_review")
        research = session([block()])
        research.seen = state["research"]["seen"]
        flow = TopicFlow(state, research)
        saved = None
        calls = []

        async def save(value):
            nonlocal saved
            if value["topic_flow"]["audit"]["results"]:
                saved = copy.deepcopy(value)
                raise RuntimeError("模拟收到合包判定后进程退出")

        async def review(payload):
            calls.append(payload)
            return approve(payload)

        with pytest.raises(RuntimeError, match="进程退出"):
            await audit_combined(flow, review, save)
        assert len(calls) == 1 and saved is not None
        restored = TopicFlow(json.loads(json.dumps(saved)), research)
        assert await audit_combined(restored, review, noop)
        assert len(calls) == 1
        assert all(e["status"] == "ready" for e in restored.entries)

    asyncio.run(run())


def test_budget_boundary_graph_synthesizes_and_independently_reviews_existing_evidence():
    async def run():
        state, reviewed = {}, []
        research = session([block()])
        router = ScriptedRouter([
            call("search_document", {"query": "质保", "work": "w1"}, "search"),
            call("submit_analysis", {
                "records": [summary_record(work_ids=["w1"])], "final": True,
            }, "final"),
        ])

        async def review(payload):
            reviewed.append(payload)
            return approve(payload)

        graph, files = build_module_agent(
            key=KEY, model=RoutedAgentModel(router=router), research=research, state=state,
            snapshot=snapshot(("a",)) | {"__analysis_flow_version__": "research-v2"},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop, review_combined=review,
            budget_status=lambda: {"model_calls_remaining": 8 if research.seen else 40},
        )
        await invoke_module(graph, files, thread_id="reserved-synthesis", task="解析质保")
        assert len(router.requests) == 2 and len(reviewed) == 1
        assert len(module_data(state)["records"]) == 1
        assert "search_document" not in {t["function"]["name"] for t in router.requests[-1][1]}

    asyncio.run(run())
