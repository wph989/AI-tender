"""检索以具体待办收敛；缓存、换词或修改状态不能绕过已耗尽的工作额度。"""

import asyncio
import copy

import pytest
from synthesis_fixtures import accept, noop, submission, summary_record
from test_analysis_argument_failures import request
from test_analysis_research import block, session
from test_analysis_topic_flow import execute, prepared_flow, search, update
from test_deep_analysis import call

from tender.application.analysis.agent import ResearchMiddleware
from tender.application.analysis.research import AgentLimits
from tender.application.analysis.topic_flow import TopicFlow, TopicIncomplete, TopicUpdate


def test_completed_topic_cannot_be_searched_while_other_topics_continue():
    async def run():
        retrieved = []
        research = session([block()])
        retrieve = research.retrieve

        async def track(sources, query):
            retrieved.append(query)
            return await retrieve(sources, query)

        research.retrieve = track
        state, _, _, _ = await execute([
            search("a"),
            call("submit_analysis", submission([summary_record()], final=False) | {
                "topic_updates": [update("a", ["warranty"])]}, "a"),
            search("a", "重复核对质保", "redundant"),
            search("b", "数量", "b"),
            call("submit_analysis", submission([summary_record(key="count")]) | {
                "topic_updates": [update("b", ["count"])]}, "finish"),
        ], research=research)
        assert retrieved == ["质保", "数量"]
        assert "已完成" in state["tool_results"]["call_redundant"]["data"]["content"]
        assert len(state["draft"]["fields"]) == 2

    asyncio.run(run())


def test_last_search_results_can_still_be_submitted_after_idle_threshold():
    async def run():
        research = session([block()])
        retrieve = research.retrieve

        async def delayed(sources, query):
            if query != "找到正文":
                return [], {}
            return await retrieve(sources, query)

        research.retrieve = delayed
        state, _, _, audited = await execute([
            search("a", "第一次", "first"), search("a", "第二次", "second"),
            search("a", "找到正文", "third"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [update("a", ["warranty"])]}, "finish"),
        ], keys=("a",), research=research)
        assert state["draft"]["fields"] and audited
        assert "research_notice" in state["tool_results"]["call_third"]["data"]["content"]
        assert not any(w.get("exhausted") for w in state["topic_flow"]["search_work"].values())

    asyncio.run(run())


def test_verified_progress_reopens_pending_stop_without_resetting_total_attempts():
    from tender.application.analysis.search_control import TopicSearch

    flow, state, _ = prepared_flow()
    task = {"detail": "核对起算点", "record_keys": ["warranty"]}
    flow.apply([TopicUpdate.model_validate(update(
        "a", ["warranty"], status="researching", tasks=[task],
    ))], {"warranty"})
    control = TopicSearch(flow)
    for index in range(3):
        work = control.begin("search_document", {"topic_keys": ["a"], "query": str(index)})
        control.end(work, {"blocks": []}, {"s1r1c0"})
    # 最后一批证据修正并核实了事项，仍有具体待办时可以继续，累计请求不能归零。
    state["staged_items"][0]["business"]["content"]["内容"] = "自验收合格日起质保三年"
    work = control.begin("search_document", {"topic_keys": ["a"], "query": "例外条件"})
    control.end(work, {"blocks": []}, {"s1r1c0"})
    ledger = control.ledger[work[0]["id"]]
    assert ledger["attempts"] == 4 and ledger["idle"] == 1
    assert not ledger.get("exhausted") and not ledger.get("pending_stop")


@pytest.mark.parametrize("tool,args", [
    ("search_document", {"query": "质保", "topic_keys": ["a"]}),
    ("search_knowledge", {"query": "质保", "topic_keys": ["a"]}),
    ("read_document", {"block_id": "s1r1c0", "topic_keys": ["a"], "after": 1}),
])
def test_argument_budget_closes_new_research_even_without_first_successful_search(tool, args):
    async def run():
        research = session([block()], limits=AgentLimits(max_argument_failures=1))
        state = {"business_topics": [{"key": "a", "title": "a", "checks": ["质保期限"]}]}
        flow = TopicFlow(state, research)
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)
        state["argument_failures"] = 1
        state["finish_only"] = True
        invoked = []

        async def handler(req):
            invoked.append(req.tool_call)
            raise AssertionError("纠错耗尽后不能继续读取新原文")

        with pytest.raises(TopicIncomplete, match="参数纠错"):
            await middleware.awrap_tool_call(request(tool, args), handler)
        assert not invoked

    asyncio.run(run())


def test_known_gaps_settle_without_spending_model_calls_on_full_audit():
    async def run():
        flow, state, research = prepared_flow()
        flow.apply([TopicUpdate.model_validate(update(
            "a", ["warranty"], status="blocked", detail="附件二未提供",
        ))], {"warranty"})
        audited = []

        async def audit(payload):
            audited.append(payload)
            return {"issues": []}

        middleware = ResearchMiddleware(research, state, noop, noop,
                                        topic_flow=flow, review_coverage=audit)
        with pytest.raises(TopicIncomplete, match="未完成|受阻"):
            await middleware.advance_topics()
        assert not audited
        assert state["staged_items"][0]["verification"] == "supported"

    asyncio.run(run())


def test_specific_task_new_evidence_requires_review_of_the_associated_topic():
    async def run():
        reviewed = []
        research = session([block()])
        retrieve = research.retrieve

        async def additional(sources, query):
            if query == "起算点":
                return [block() | {"block_id": "s1r1c1", "offset": 1,
                                   "content": "质保自验收合格日起算三年"}], {}
            return await retrieve(sources, query)

        async def review(items):
            reviewed.append([i["business"]["key"] for i in items])
            await accept(items)

        research.retrieve = additional
        task = {"detail": "核对质保起算点", "record_keys": ["warranty"]}
        state, saved, _, _ = await execute([
            search("a"),
            call("submit_analysis", submission([
                summary_record(), summary_record(key="other", title="独立事项"),
            ], final=False) | {"topic_updates": [update(
                "a", ["warranty", "other"], status="researching", tasks=[task],
            )]}, "initial"),
            call("search_document", {"query": "起算点", "topic_keys": ["a"],
                                      "work": task["detail"]}, "targeted"),
            call("submit_analysis", submission([summary_record(citations=[{
                "block_id": "s1r1c1", "quote": "质保自验收合格日起算三年",
            }]), summary_record(key="other", title="独立事项")]) | {"topic_updates": [update(
                "a", ["warranty", "other"], tasks=[task | {"status": "resolved",
                                                            "evidence_ids": ["s1r1c1"]}],
            )]}, "finish"),
        ], keys=("a",), research=research, review=review)
        assert reviewed == [["warranty", "other"], ["warranty", "other"]]
        changed = next(s for s in saved if "s1r1c1" in s["topic_flow"]["evidence_topics"])
        assert changed["staged_items"][0]["review_status"] == "needs_review"
        assert changed["staged_items"][1]["review_status"] == "needs_review"
        assert len(state["draft"]["fields"]) == 2

    asyncio.run(run())


def test_one_exhausted_task_does_not_block_other_tasks_in_same_topic():
    async def run():
        research = session([block()])
        retrieve = research.retrieve
        retrieved = []

        async def track(sources, query):
            retrieved.append(query)
            return await retrieve(sources, query)

        research.retrieve = track
        tasks = [{"detail": "核对起算点", "record_keys": ["warranty"]},
                 {"detail": "核对易损件", "record_keys": ["other"]}]
        script = [search("a"), call("submit_analysis", submission([
            summary_record(), summary_record(key="other", title="易损件"),
        ], final=False) | {"topic_updates": [update(
            "a", ["warranty", "other"], status="researching", tasks=tasks,
        )]}, "initial")]
        script.extend(call("search_document", {"query": f"起算点{index}", "topic_keys": ["a"],
                                              "work": tasks[0]["detail"]}, f"attempt{index}")
                      for index in range(4))
        script.extend([
            call("search_document", {"query": "易损件", "topic_keys": ["a"],
                                      "work": tasks[1]["detail"]}, "other"),
            call("submit_analysis", submission() | {"topic_updates": [update(
                "a", ["warranty", "other"], tasks=[tasks[0] | {"status": "blocked"},
                                                    tasks[1] | {"status": "resolved"}],
            )]}, "settle"),
        ])
        with pytest.raises(TopicIncomplete, match="受阻"):
            await execute(script, keys=("a",), research=research)
        assert retrieved == ["质保", "起算点0", "起算点1", "起算点2", "易损件"]

    asyncio.run(run())


def test_amendment_expands_specific_task_review_to_all_related_topics():
    from tender.application.analysis.search_control import TopicSearch

    flow, state, research = prepared_flow(("a", "b"))
    duplicate = copy.deepcopy(state["staged_items"][0])
    duplicate.update(id="other")
    duplicate["business"]["key"] = "other"
    state["staged_items"].append(duplicate)
    task = {"detail": "核对起算点", "record_keys": ["warranty"]}
    flow.apply([TopicUpdate.model_validate(update(
        "a", ["warranty", "other"], status="researching", tasks=[task],
    ))], {"warranty", "other"})
    TopicSearch(flow).begin("search_document", {"topic_keys": ["a"], "work": task["detail"]})
    research.seen["new"] = block() | {"content": "本项目全部条款更正", "file_name": "补遗一.pdf"}
    flow.evidence({"s1r1c0"}, ["a"])
    assert all(item["review_status"] == "needs_review" for item in state["staged_items"])


def test_repeated_evidence_exhaustion_survives_query_renaming_and_restore():
    from tender.application.analysis.research import ToolArgumentError
    from tender.application.analysis.search_control import TopicSearch

    flow, state, research = prepared_flow()
    task = {"detail": "核对起算点", "record_keys": ["warranty"]}
    flow.apply([TopicUpdate.model_validate(update(
        "a", ["warranty"], status="researching", tasks=[task],
    ))], {"warranty"})
    control = TopicSearch(flow)
    for query in ("起算点", "质保何时开始", "质保起始日期"):
        work = control.begin("search_document", {"topic_keys": ["a"], "work": task["detail"],
                                                "query": query})
        control.end(work, {"already_read": ["s1r1c0"], "blocks": [], "page": {"has_more": False}},
                    {"s1r1c0"})
    restored = TopicFlow(copy.deepcopy(state), research)
    restored.apply([TopicUpdate.model_validate(update(
        "a", ["warranty"], status="researching", tasks=[task],
    ))], {"warranty"})
    with pytest.raises(ToolArgumentError, match="耗尽|受阻"):
        TopicSearch(restored).begin("search_document", {"topic_keys": ["a"],
                                                       "work": task["detail"], "query": "换词"})
    assert len(state["staged_items"]) == 1


def test_more_search_pages_and_real_continuations_do_not_exhaust_work():
    from tender.application.analysis.search_control import TopicSearch

    flow, state, research = prepared_flow()
    flow.entries[0]["checked"] = []
    flow.entries[0]["requested_status"] = "researching"
    flow.sync()
    control = TopicSearch(flow)
    for index in range(5):
        work = control.begin("search_document", {"topic_keys": ["a"], "query": "质保",
                                                 "offset": index * 6})
        control.end(work, {"already_read": ["s1r1c0"], "blocks": [],
                           "page": {"offset": index * 6, "has_more": index < 4,
                                    "next_offset": (index + 1) * 6 if index < 4 else None}},
                    {"s1r1c0"})
    assert work and not any(e["status"] == "blocked" for e in flow.entries)
    assert control.begin("read_document", {"block_id": "s1r1c0", "topic_keys": ["a"],
                                           "before": 0, "after": 1})


def test_quote_only_reads_remain_available_after_work_completion():
    from tender.application.analysis.search_control import TopicSearch

    flow, _, _ = prepared_flow()
    assert TopicSearch(flow).begin("read_document", {"block_id": "s1r1c0", "topic_keys": ["a"],
                                                     "before": 0, "after": 0}) == []


def test_new_unrelated_evidence_and_task_renaming_do_not_refresh_idle_budget():
    from tender.application.analysis.research import ToolArgumentError
    from tender.application.analysis.search_control import TopicSearch

    flow, state, research = prepared_flow()
    task = {"detail": "核对起算点", "record_keys": ["warranty"]}
    flow.apply([TopicUpdate.model_validate(update(
        "a", ["warranty"], status="researching", tasks=[task],
    ))], {"warranty"})
    control = TopicSearch(flow)
    for index in range(3):
        before = set(research.seen)
        work = control.begin("search_document", {"topic_keys": ["a"], "work": task["detail"],
                                                 "query": f"换词-{index}"})
        key = f"unrelated-{index}"
        research.seen[key] = block() | {"content": f"无关说明{index}"}
        control.end(work, {"blocks": [{"id": key, "text": "无关说明"}]}, before)
    assert flow.entries[0]["status"] != "blocked"
    renamed = task | {"detail": "质保从哪天开始",
                      "task_id": next(iter(flow.entries[0]["tasks"]))}
    flow.apply([TopicUpdate.model_validate(update(
        "a", ["warranty"], status="researching", tasks=[renamed],
    ))], {"warranty"})
    with pytest.raises(ToolArgumentError, match="耗尽"):
        control.begin("search_document", {"topic_keys": ["a"], "work": renamed["detail"]})
    assert all(task["status"] == "blocked" for task in flow.entries[0]["tasks"].values())
    assert control.summary(state)["exhausted_work"] == 1
    assert control.summary(state)["research_calls"] == 3


def test_real_read_continuations_can_exceed_three_windows():
    from tender.application.analysis.search_control import TopicSearch

    flow, state, research = prepared_flow()
    flow.entries[0]["checked"] = []
    flow.entries[0]["requested_status"] = "researching"
    flow.sync()
    control = TopicSearch(flow)
    for index in range(5):
        before = set(research.seen)
        work = control.begin("read_document", {"topic_keys": ["a"], "block_id": "s1r1c0",
                                               "before": 0, "after": 1})
        key = f"continuation-{index}"
        research.seen[key] = block() | {"content": "清单续段"}
        control.end(work, {"blocks": [{"id": key, "text": "清单续段"}]}, before)
    assert flow.entries[0]["status"] != "blocked"
    assert not control.summary(state)["exhausted_work"]


@pytest.mark.parametrize("action", ["read_document", "search_document"])
def test_pending_stop_still_allows_concrete_continuation(action):
    from tender.application.analysis.search_control import TopicSearch

    flow, state, research = prepared_flow()
    flow.entries[0].update(checked=[], requested_status="researching")
    flow.sync()
    control = TopicSearch(flow)
    for index in range(3):
        work = control.begin("search_document", {"topic_keys": ["a"], "query": str(index)})
        control.end(work, {"blocks": [], "already_read": ["s1r1c0"],
                           "page": {"offset": 0, "has_more": True, "next_offset": 6}},
                    {"s1r1c0"})
    work = control.begin(action, {"topic_keys": ["a"], "block_id": "s1r1c0",
                                  "query": "2", "offset": "6", "before": 0, "after": 1})
    research.seen["next"] = block() | {"content": "但易损件仅保修一年"}
    control.end(work, {"blocks": [{"id": "next"}],
                       "page": {"offset": 6, "has_more": False, "next_offset": None}},
                {"s1r1c0"})
    assert flow.entries[0]["status"] != "blocked"
    assert not control.summary(state)["exhausted_work"]


def test_same_first_page_with_more_results_cannot_extend_research_by_rephrasing():
    from tender.application.analysis.search_control import TopicSearch

    flow, state, _ = prepared_flow()
    flow.entries[0]["checked"] = []
    flow.entries[0]["requested_status"] = "researching"
    flow.sync()
    control = TopicSearch(flow)
    for index in range(3):
        work = control.begin("search_document", {"topic_keys": ["a"], "query": f"同义词{index}"})
        control.end(work, {"blocks": [], "already_read": ["s1r1c0"],
                           "page": {"has_more": True}}, {"s1r1c0"})
    assert any(w.get("pending_stop") for w in control.ledger.values())


def test_multiple_checks_require_explicit_work_and_show_only_unfinished_checks():
    from tender.application.analysis.research import ToolArgumentError
    from tender.application.analysis.search_control import TopicSearch

    flow, _, _ = prepared_flow()
    flow.entries[0].update(checks=["期限", "条件", "例外"], checked=["期限"],
                           requested_status="researching")
    flow.sync()
    control = TopicSearch(flow)
    with pytest.raises(ToolArgumentError, match="条件.*例外"):
        control.begin("search_document", {"topic_keys": ["a"]})
    assert [w["work"] for w in control.begin("search_document", {
        "topic_keys": ["a"], "work": "条件",
    })] == ["条件"]


def test_quote_only_read_survives_argument_exhaustion_but_still_checks_access():
    import json

    from langchain_core.messages import ToolMessage

    async def run():
        flow, state, research = prepared_flow()
        state["argument_failures"] = research.limits.max_argument_failures
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)
        args = {"block_id": "s1r1c0", "topic_keys": ["a"], "before": 0, "after": 0}

        async def handler(req):
            return ToolMessage(
                content=json.dumps({"blocks": [{"id": "s1r1c0", "text": "质保三年"}]}),
                tool_call_id=req.tool_call["id"],
            )

        result = await middleware.awrap_tool_call(request("read_document", args), handler)
        assert result.status == "success"

        async def revoked():
            raise PermissionError("权限撤销")

        research.authorize = revoked
        with pytest.raises(PermissionError, match="权限撤销"):
            await middleware.awrap_tool_call(request("read_document", args, call_id="new"), handler)

    asyncio.run(run())


def test_cached_read_still_obeys_completed_work_gate():
    import json

    from langchain_core.messages import ToolMessage

    async def run():
        flow, state, research = prepared_flow()
        task = {"detail": "核对起算点", "record_keys": ["warranty"]}
        flow.apply([TopicUpdate.model_validate(update(
            "a", ["warranty"], status="researching", tasks=[task],
        ))], {"warranty"})
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)
        args = {"block_id": "s1r1c0", "topic_keys": ["a"], "work": task["detail"],
                "before": 0, "after": 1}
        invoked = []

        async def handler(req):
            invoked.append(req.tool_call)
            return ToolMessage(content=json.dumps({"blocks": []}),
                               tool_call_id=req.tool_call["id"])

        await middleware.awrap_tool_call(request("read_document", args), handler)
        flow.apply([TopicUpdate.model_validate(update(
            "a", ["warranty"], tasks=[task | {"status": "resolved"}],
        ))], {"warranty"})
        result = await middleware.awrap_tool_call(
            request("read_document", args, call_id="new"), handler,
        )
        assert result.status == "error" and "已完成" in result.content
        assert len(invoked) == 1

    asyncio.run(run())


def test_schema_argument_error_is_correctable_before_research_exhaustion():
    from langchain_core.messages import ToolMessage

    from tender.application.analysis.agent import TOOL_ARGUMENT_PREFIX

    async def run():
        research = session([block()])
        state = {"business_topics": [{"key": "a", "title": "a", "checks": ["质保期限"]}]}
        flow = TopicFlow(state, research)
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)

        async def invalid(req):
            return ToolMessage(content=TOOL_ARGUMENT_PREFIX + "offset必须是非负整数",
                               tool_call_id=req.tool_call["id"])

        result = await middleware.awrap_tool_call(request("search_document", {
            "topic_keys": ["a"], "query": "质保", "offset": -1,
        }), invalid)
        assert result.content.startswith(TOOL_ARGUMENT_PREFIX) and state["argument_failures"] == 1
        assert not flow.data["search_work"]
        assert "active_work" not in flow.data
        assert flow.entries[0]["status"] != "blocked"

    asyncio.run(run())


@pytest.mark.parametrize("args", [
    {"topic_keys": [{"topic": "a"}]}, {"topic_keys": "a"},
    {"block_id": {"id": "s1r1c0"}}, {"topic_keys": ["a"], "offset": "尾页"},
])
def test_work_gate_keeps_malformed_tool_arguments_correctable(args):
    async def run():
        flow, state, research = prepared_flow()
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)

        async def handler(req):
            raise AssertionError("无效参数不能读取原文")

        result = await middleware.awrap_tool_call(request("search_document", args), handler)
        assert result.status == "error" and state["argument_failures"] == 1
        assert not flow.data["search_work"]

    asyncio.run(run())
