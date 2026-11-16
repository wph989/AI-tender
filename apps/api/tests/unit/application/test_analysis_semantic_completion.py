"""Agent按内容充分性结束研究，登记笔记不是统一综合的前置条件。"""

import asyncio
import json

import pytest
from synthesis_fixtures import summary_record
from test_analysis_combined_review import approve, execute
from test_analysis_compact_protocol import ledger
from test_analysis_research import block, session
from test_deep_analysis import call

from tender.application.analysis.data import module_data
from tender.application.analysis.protocol import ResearchLedger
from tender.application.analysis.search_control import TopicSearch


def finish(key="ready"):
    return call("complete_research", {"research_summary": "已核对质保正文、条件和范围，依据充分"},
                key)


def test_sufficient_search_goes_straight_to_synthesis_without_per_check_registration():
    async def run():
        state, saved, router, reviewed = await execute(
            [summary_record()], research_steps=[finish()], synthesis_steps=[call(
                "submit_analysis", {"records": [summary_record(work_ids=["w1"])], "final": True},
                "only-batch",
            )],
        )
        assert len(router.requests) == 4 and len(reviewed) == 1
        first_tools = {t["function"]["name"] for t in router.requests[0][1]}
        assert "complete_research" in first_tools and "submit_analysis" not in first_tools
        assert len(module_data(state)["records"]) == 1
        assert all(not e.get("findings") for e in state["topic_flow"]["entries"].values())
        assert all(e["status"] == "ready" for e in state["topic_flow"]["entries"].values())
        assert all(not module_data(s)["records"] for s in saved if "draft" not in s)

    asyncio.run(run())


def test_shared_search_and_one_conclusion_can_cover_multiple_checklists():
    async def run():
        state, _, _, reviewed = await execute(
            [summary_record(work_ids=["w1", "w2"])], keys=("a", "b"),
            search_args={"query": "质保及例外", "work": ["w1", "w2"]},
            research_steps=[finish()],
        )
        assert {t for p in reviewed for t in p.get("topics", [p["topic"]])} == {"a", "b"}
        assert len(module_data(state)["records"]) == 1
        assert all(e["status"] == "ready" for e in state["topic_flow"]["entries"].values())

    asyncio.run(run())


def test_semantic_completion_does_not_bypass_independent_omission_review():
    async def run():
        calls = []

        async def missing(payload):
            calls.append(payload)
            return approve(payload) | {"issues": [{
                "topic": "a", "detail": "质保例外条款尚未展开", "target": "质保例外",
                "evidence_ids": ["s1r1c0"], "record_ids": [], "kind": "omission",
            }]}

        state, _, _, _ = await execute(
            [summary_record()], research_steps=[finish()], review=missing,
            tail=[finish("repair-ready"), call("submit_analysis", {
                "records": [], "final": True,
            }, "repair-final")],
        )
        assert state["quality_status"] == "needs_review"
        assert len(state["draft"]["fields"]) == 1
        assert len(state["business_gaps"]) == len(state["quality_issues"]) == 1
        assert state["business_gaps"][0]["issue_id"] == state["quality_issues"][0]["issue_id"]
        # 待补读请求完成一次定向复核后仍有具体遗漏，正常结束并保留缺口，不重复否决已审事实。
        assert len(calls) == 2

    asyncio.run(run())


def test_readiness_requires_real_project_retrieval_and_preserves_pending_semantic_work():
    book, flow, state, research = ledger()
    research.events.clear()
    with pytest.raises(ValueError, match="实际检索"):
        book.finish("认为依据充分")
    assert flow.researching and not state.get("research_completed")


def test_finish_preserves_checklist_and_unexamined_evidence_for_independent_review():
    book, flow, _, _ = ledger()
    unexamined = list(flow.entries[0]["unreviewed_evidence"])
    book.finish("已理解当前原文，开始统一综合")
    assert not flow.researching
    assert flow.entries[0]["unreviewed_evidence"] == unexamined
    assert not flow.entries[0]["checked"] and not flow.entries[0].get("findings")
    assert ResearchLedger(flow).works()[0]["id"] == "w1"


def test_refined_queries_with_new_original_text_need_no_progress_registration():
    book, flow, _, research = ledger()

    control = TopicSearch(flow)
    for index in range(7):
        selected = control.begin("search_document", {"query": f"具体缺口{index}", "work": "w1"})
        before = set(research.seen)
        key = f"s1r1c{index + 1}"
        research.seen[key] = block() | {"block_id": key, "content": f"独立条件{index}"}
        result = {"blocks": [{"id": key, "text": f"独立条件{index}"}]}
        flow.evidence(before, ["a"], result)
        control.end(selected, result, before)
    assert not control.ledger["w1"].get("exhausted")
    book.finish("已读完整条件，开始统一综合")
    assert not flow.researching and not flow.entries[0].get("findings")


def test_repeated_collection_stops_without_claiming_that_content_is_missing():
    book, flow, _, research = ledger()
    from tender.application.analysis.research import WorkClosed

    control = TopicSearch(flow)
    for _ in range(research.limits.max_no_progress_rounds):
        selected = control.begin("read_document", {"block_id": "s1r1c0", "work": "w1"})
        control.end(selected, {"already_read": ["s1r1c0"]}, set(research.seen))
    with pytest.raises(WorkClosed):
        control.begin("read_document", {"block_id": "s1r1c0", "work": "w1"})
    assert not flow.entries[0]["blocked_checks"]
    book.finish("已有原文足够，无需重复采集")
    assert not flow.researching


def test_new_evidence_after_readiness_reopens_research_and_keeps_unreviewed_draft_internal():
    book, flow, state, research = ledger()

    book.finish("依据已充分")
    before = set(research.seen)
    research.seen["s1r1c1"] = block() | {"block_id": "s1r1c1", "content": "补遗：质保修改为五年"}
    flow.evidence(before, ["a"], {"blocks": [{"id": "s1r1c1"}]})
    assert flow.researching and not state.get("research_completed")
    assert "s1r1c1" in flow.entries[0]["unreviewed_evidence"]
    assert not module_data(state)["records"]


@pytest.mark.parametrize("batch_sizes", [(2,), (1, 1), (2, 1), (1, 1, 1)])
def test_first_synthesis_can_split_unknown_scope_and_bind_each_lots_current_work(batch_sizes):
    async def run():
        from tender.application.analysis.topic_flow import TopicFlow

        clauses = [("A标段", "A标段质保三年"), ("B标段", "B标段质保五年"),
                   ("C标段", "C标段质保六年")][:sum(batch_sizes)]
        raw = block() | {"content": "；".join(quote for _, quote in clauses)}
        records = [summary_record(
            key=lot, work_ids=["w1"], scope={"kind": "lots", "lot_refs": [lot]},
            content={"字段": "质保期限", "内容": quote},
            citations=[{"block_id": "s1r1c0", "quote": quote}],
        ) for lot, quote in clauses]
        steps, offset = [], 0
        for index, size in enumerate(batch_sizes):
            steps.append(call("submit_analysis", {
                "records": records[offset:offset + size], "final": index == len(batch_sizes) - 1,
            }, f"lots-{index}"))
            offset += size
        state, _, _, _ = await execute(
            records, evidence_rows=[raw], research_steps=[finish()], synthesis_steps=steps,
        )
        restored = session([raw])
        restored.seen = state["research"]["seen"]
        flow = TopicFlow(state, restored)
        known = {w["id"]: w for w in ResearchLedger(flow).works()}
        for item in state["staged_items"]:
            assert item["work_ids"]
            assert all(known[wid]["scope"] == item["business"]["scope"]
                       for wid in item["work_ids"])
        assert len(module_data(state)["records"]) == len(clauses)

    asyncio.run(run())


@pytest.mark.parametrize("first_batch_size", [1, 2])
def test_lot_batches_resume_with_original_work_after_serialized_state_restore(first_batch_size):
    from langgraph.checkpoint.memory import InMemorySaver
    from synthesis_fixtures import noop
    from test_analysis_topic_flow import snapshot
    from test_deep_analysis import KEY, ScriptedRouter

    from tender.application.analysis.agent import (
        RoutedAgentModel,
        build_module_agent,
        invoke_module,
    )
    from tender.application.analysis.topic_flow import TopicFlow

    class InterruptedRouter(ScriptedRouter):
        async def chat(self, messages, tools):
            if not self.calls:
                raise RuntimeError("模拟首批保存后进程中断")
            return await super().chat(messages, tools)

    async def run():
        clauses = [("A标段", "A标段质保三年"), ("B标段", "B标段质保五年"),
                   ("C标段", "C标段质保六年")]
        raw = block() | {"content": "；".join(quote for _, quote in clauses)}
        records = [summary_record(
            key=lot, work_ids=["w1"], scope={"kind": "lots", "lot_refs": [lot]},
            content={"字段": "质保期限", "内容": quote},
            citations=[{"block_id": "s1r1c0", "quote": quote}],
        ) for lot, quote in clauses]
        state, saver = {}, InMemorySaver()

        async def review(payload):
            return approve(payload)

        def build(router, research):
            return build_module_agent(
                key=KEY, model=RoutedAgentModel(router=router), research=research, state=state,
                snapshot=snapshot(("a",)) | {"__analysis_flow_version__": "research-v2"},
                checkpointer=saver, reserve_tool=noop, save=noop, review_combined=review,
            )

        router = InterruptedRouter([
            call("list_documents", {}, "docs"),
            call("search_document", {"query": "质保", "work": "w1"}, "search"), finish(),
            call("submit_analysis", {"records": records[:first_batch_size], "final": False},
                 "first-batch"),
        ])
        graph, files = build(router, session([raw]))
        with pytest.raises(RuntimeError, match="模拟首批保存"):
            await invoke_module(graph, files, thread_id="lot-resume", task="核对各标段质保")
        assert len(state["staged_items"]) == first_batch_size
        assert not module_data(state)["records"]
        # JSON往返与重建会话模拟数据库状态恢复，不能依赖上次进程中的可变对象。
        state = json.loads(json.dumps(state, ensure_ascii=False))
        restored = session([raw])
        restored.seen = state["research"]["seen"]
        restored.events = state["research"]["events"]
        restored.tool_calls = state["research"]["tool_calls"]
        previous_calls = restored.tool_calls
        resumed = ScriptedRouter([call("submit_analysis", {
            "records": records[first_batch_size:], "final": True,
        }, "remaining-lots")])
        graph, files = build(resumed, restored)
        await invoke_module(graph, files, thread_id="lot-resume", task="继续综合")
        assert len(resumed.requests) == 1 and restored.tool_calls == previous_calls
        assert len(module_data(state)["records"]) == len(clauses)
        book = ResearchLedger(TopicFlow(state, restored))
        known = {work["id"]: work for work in book.works()}
        for item in state["staged_items"]:
            assert item["work_ids"]
            assert all(known[wid]["scope"] == item["business"]["scope"]
                       for wid in item["work_ids"])
        # 审查完成后原始工作不能再为新范围背书，后续变化须重新确认。
        foreign = {"business": {"key": "foreign", "scope": {"kind": "lots", "lot_refs": ["D"]}}}
        with pytest.raises(ValueError):
            book.record_updates([foreign], ["w1"])

    asyncio.run(run())


def test_new_evidence_revokes_completed_absence_even_without_business_records():
    book, flow, _, research = ledger()

    async def run():
        from synthesis_fixtures import noop

        from tender.application.analysis.protocol import ResearchDelta
        from tender.application.analysis.review import audit_combined

        flow.data["research_searches"] = {"a": {"q": {
            "query": "质保", "source_ids": [1], "has_more": False, "limited": False,
        }}}
        book.update([ResearchDelta(work_ids=["w1"], status="not_found", detail="未找到相关约定",
                                   scope={"kind": "common", "lot_refs": []})])

        async def review(payload):
            return approve(payload)

        await audit_combined(flow, review, noop)
        flow.sync()
        assert flow.entries[0]["status"] == "ready"
        before = set(research.seen)
        research.seen["s1r1c1"] = block() | {"block_id": "s1r1c1", "content": "质保五年"}
        flow.evidence(before, ["a"], {"blocks": [{"id": "s1r1c1"}]})
        assert flow.researching and flow.entries[0]["status"] != "ready"

    asyncio.run(run())


def test_review_resolution_closes_old_blocked_work_without_creating_omissions():
    async def run():
        from tender.application.analysis.quality import issue_identity

        state = {}
        issue = {"topic": "a", "kind": "omission", "action": "read",
                 "target": "可选签到步骤", "scope": {"kind": "common", "lot_refs": []},
                 "detail": "未见签到步骤", "evidence_ids": ["s1r1c0"], "record_keys": []}
        issue_id = issue_identity(issue)
        calls = []

        async def review(payload):
            calls.append(payload)
            result = approve(payload)
            if len(calls) == 1:
                result["issues"] = [{k: issue[k] for k in (
                    "topic", "kind", "action", "target", "detail", "evidence_ids", "scope"
                )} | {"record_ids": []}]
            return result

        state, _, _, _ = await execute(
            [summary_record(work_ids=["w1"])], state=state, keys=("a", "b"),
            search_args={"query": "质保及可选材料", "work": ["w1", "w2"]},
            research_steps=[call("update_research", {"updates": [{
                "work_ids": ["w2"], "status": "blocked", "detail": "原文未规定备用材料",
                "evidence_ids": ["s1r1c0"],
            }]}, "unrequired-materials"), finish()], review=review,
            tail=[call("update_research", {"updates": [{
                "work_ids": ["w3"], "status": "blocked",
                "detail": "核对原文后确认未规定签到步骤，无具体遗漏",
                "evidence_ids": ["s1r1c0"],
            }]}, "check-optional-step"), finish("repair-ready"),
                  call("submit_analysis", {"records": [summary_record(
                      key="additional", work_ids=["w1"], title="已核对的质保条件"
                  )], "final": True}, "repair-final")],
        )
        audit = state["topic_flow"]["audit"]
        assert audit["done"] and not audit["remaining"]
        assert state["quality_status"] == "verified" and not state["quality_issues"]
        assert len(module_data(state)["records"]) == 2
        assert not state["business_gaps"]
        entries = list(state["topic_flow"]["entries"].values())
        assert all(e["status"] == "ready" for e in entries)
        task = next(e["tasks"][issue_id] for e in entries if issue_id in e["tasks"])
        assert task["status"] == "resolved" and task["resolved_by"] == "independent_review"
        # 空主题只结束核对流程；不能为它伪造公共适用范围或不适用证明。
        empty = next(e for e in entries if e["topic"] == "b")
        assert not empty["record_keys"] and empty["scope"]["kind"] == "unknown"
        assert not empty.get("findings")

    asyncio.run(run())


def test_review_closes_old_reference_and_replays_after_serialized_restore():
    book, flow, state, research = ledger()

    async def run():
        from synthesis_fixtures import noop

        from tender.application.analysis.data import DataScope
        from tender.application.analysis.output import ReferenceTrace
        from tender.application.analysis.review import audit_combined
        from tender.application.analysis.topic_flow import TopicFlow, TopicUpdate

        flow.apply([TopicUpdate(topic="a", scope=DataScope(kind="common"),
            evidence_ids=["s1r1c0"], references=[ReferenceTrace(
                topic="a", from_block_id="s1r1c0", target="可选说明", status="missing",
            )])], set())
        book.finish("原文未规定可选要求，交由独立审查核对")

        async def review(payload):
            assert any(ref["target"] == "可选说明" for check in payload["checks"]
                       for ref in check["references"])
            return approve(payload)

        assert await audit_combined(flow, review, noop)
        restored = TopicFlow(json.loads(json.dumps(state, ensure_ascii=False)), research)
        assert restored.entries[0]["references"][0]["status"] == "resolved"
        assert restored.entries[0]["status"] == "ready"
        # 审查后改变原文必须使缓存失效，旧任务的关闭不能替新证据背书。
        research.seen["s1r1c0"]["content"] += "；另有例外"
        restored.sync()
        assert restored.entries[0]["status"] != "ready"

    asyncio.run(run())


def test_mixed_supported_fact_and_independent_gap_reaches_review_without_being_dropped():
    async def run():
        raw = block() | {"content": "质保三年；起算日期详见第一章公告"}
        record = summary_record(content={"字段": "质保期限",
            "内容": "质保期限为三年，起算日期未载明，需核对转引公告"})
        calls = []

        async def review(payload):
            calls.append(payload)
            assert len(payload["records"] if len(calls) == 1 else payload["context_records"]) == 1
            return approve(payload) | {"issues": [{
                "topic": "a", "detail": "起算日期需定向补读转引公告", "target": "公告/起算日期",
                "evidence_ids": ["s1r1c0"], "record_ids": [], "kind": "omission", "action": "read",
            }]}

        state, _, _, _ = await execute([record], evidence_rows=[raw], review=review,
            tail=[finish("repair-ready"), call("submit_analysis", {
                "records": [], "final": True,
            }, "repair-final")])
        assert len(calls) == 2 and len(state["staged_items"]) == 1
        assert len(module_data(state)["records"]) == 1
        assert len(state["quality_issues"]) == len(state["business_gaps"]) == 1
        assert state["quality_issues"][0]["target"] == "公告/起算日期"

    asyncio.run(run())


def test_unproven_absence_is_rejected_by_independent_review():
    async def run():
        from tender.application.analysis.research import AgentLimits

        async def review(payload):
            assert len(payload["records"]) == 1
            result = approve(payload)
            verdict = next(iter(result["reviews"].values()))
            verdict.update(supported=False, issues=["单块原文不能证明整个项目没有质保要求"])
            return result

        state, _, _, _ = await execute([summary_record(content={
            "字段": "质保要求", "内容": "项目未规定质保要求",
        })], review=review, limits=AgentLimits(max_review_repairs=0))
        assert not module_data(state)["records"]
        assert len(state["staged_items"]) == 1
        assert state["quality_status"] == "needs_review"

    asyncio.run(run())


def test_submission_removes_discarded_draft_indexes_but_keeps_research_tasks():
    from tender.application.analysis.protocol import ResearchDelta

    book, flow, state, _ = ledger()
    book.update([ResearchDelta(work_ids=["w1"], detail="已核对质保条款",
                              evidence_ids=["s1r1c0"], scope={"kind": "common", "lot_refs": []})])
    entry = flow.entries[0]
    entry["record_keys"] = ["discarded"]
    entry["tasks"]["trace"] = {"detail": "重新核对旧草稿的条款", "target": "质保条款",
                                "status": "pending", "record_keys": ["discarded"],
                                "evidence_ids": []}
    entry.update(evidence_ids=[], unreviewed_evidence=[], findings={})
    flow.data["phase"] = "research"
    state["business_gaps"] = [{"key": "record:discarded", "topic": "a",
                              "scope": entry["scope"], "code": "unknown_condition",
                              "detail": "旧关键词过滤的缺口"}]

    async def run():
        result, _, _, packets = await execute([summary_record()], state=state,
                                              research_steps=[finish()])
        entries = list(result["topic_flow"]["entries"].values())
        assert all("discarded" not in e["record_keys"] for e in entries)
        assert any(task["detail"] == "重新核对旧草稿的条款" for packet in packets
                   for check in packet["checks"] for task in check["tasks"])
        assert len(module_data(result)["records"]) == 1
        assert result["quality_status"] == "verified"
        assert not result["business_gaps"]

    asyncio.run(run())
