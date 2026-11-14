"""补跑旧草稿须提供可修改身份，长审查原因通过按需上下文保留。"""

import asyncio
import copy
import json

from synthesis_fixtures import noop
from test_analysis_compact_protocol import ledger
from test_analysis_review_v2 import flow_fixture
from test_deep_analysis import call

from tender.application.analysis.agent import ResearchMiddleware
from tender.application.analysis.context import work_units
from tender.application.analysis.protocol import ResearchLedger


def test_scope_feedback_uses_public_id_and_provides_work_and_evidence():
    async def run():
        flow = await flow_fixture()
        item = flow.state["staged_items"][0]
        item["id"] = "public-record-id"
        item["business"]["scope"] = {"kind": "unknown", "lot_refs": []}
        item["work_ids"] = ["w1"]
        flow.data.update(protocol="research-v3", phase="synthesis", synthesis_finished=True)
        middleware = ResearchMiddleware(flow.research, flow.state, noop, noop,
                                         topic_flow=flow, review_combined=noop)
        feedback = await middleware.advance_research()
        text = json.loads(feedback["messages"][0].content)["message"]
        assert '"id":"public-record-id"' in text
        assert '"work_ids":["w1"]' in text
        assert '"block_ids":' in text
        assert "修改用id" in text
        assert flow.state["staged_items"][0] is item

    asyncio.run(run())


def test_scope_prevalidation_resets_streak_when_invalid_items_decrease():
    async def run():
        flow = await flow_fixture()
        first = flow.state["staged_items"][0]
        first["business"]["scope"] = {"kind": "unknown", "lot_refs": []}
        second = copy.deepcopy(first)
        second["id"] = "second"
        second["business"]["key"] = "second"
        flow.state["staged_items"].append(second)
        flow.entries[0]["record_keys"].append("second")
        middleware = ResearchMiddleware(flow.research, flow.state, noop, noop,
                                         topic_flow=flow, review_combined=noop)
        for _ in range(2):
            flow.data.update(phase="synthesis", synthesis_finished=True)
            await middleware.advance_research()
        first["business"]["scope"] = {"kind": "common", "lot_refs": []}
        flow.data.update(phase="synthesis", synthesis_finished=True)
        assert await middleware.advance_research() is not None
        assert flow.state["prevalidation_failures"] == 1

    asyncio.run(run())


def test_long_verification_issues_are_paged_in_context_instead_of_repeated_in_prompt():
    book, flow, state, _ = ledger()
    item = {"id": "public-id", "business": {"key": "internal-key", "title": "质保",
            "kind": "fact", "scope": {"kind": "unknown", "lot_refs": []},
            "citations": [], "content": {"内容": "三年"}}, "work_ids": ["w1"],
            "verification_issues": ["很长的审查原因" * 400]}
    state["staged_items"] = [item]
    flow.entries[0]["record_keys"] = ["internal-key"]
    prompt = json.loads(book.prompt())
    assert prompt["records"][0]["issue_count"] == 1
    assert "很长的审查原因" not in json.dumps(prompt, ensure_ascii=False)
    units = work_units(flow, ResearchLedger(flow).works(), ["w1"])
    # 完整原因可跨片段恢复，压缩提示不能让修正所需信息消失。
    assert "很长的审查原因" in json.dumps(units, ensure_ascii=False)


def test_reparse_modifies_existing_public_id_without_duplicating_old_draft():
    from test_analysis_research import block, session
    from test_analysis_v3 import build, finish, raw

    from tender.application.analysis.agent import invoke_module

    async def run():
        research = session([block()])
        graph, files, state, _, _, _ = build([
            call("search_document", {"query": "质保", "work_ids": ["w1"]}, "search"),
            *finish(),
        ], research)
        await invoke_module(graph, files, thread_id="original", task="解析")
        item = state["staged_items"][0]
        identifier = item["id"]
        item["business"]["scope"] = {"kind": "unknown", "lot_refs": []}
        state.pop("draft", None)
        state["topic_flow"].update(phase="synthesis", synthesis_finished=False)
        state["topic_flow"]["audit"] = {"round": 0, "results": {}}
        graph, files, state, _, reviewed, _ = build([
            call("submit_analysis", {"records": [], "final": True}, "invalid-final"),
            call("submit_analysis", {"records": [raw(id=identifier)], "final": True}, "fix"),
        ], research, state=state)
        await invoke_module(graph, files, thread_id="reparse", task="按反馈修正旧草稿")
        assert len(state["staged_items"]) == 1
        assert state["staged_items"][0]["id"] == identifier
        assert state["staged_items"][0]["business"]["scope"]["kind"] == "common"
        assert len(reviewed) == 1 and "draft" in state

    asyncio.run(run())


def test_changed_topic_is_reviewed_without_inventing_business_issue():
    from test_analysis_review_efficiency import shared_flow

    from tender.application.analysis.review import review_scope

    async def run():
        flow = await shared_flow()
        _, signatures, _ = review_scope(flow)
        issue = {"topic": "a", "detail": "补读具体附件", "target": "附件甲",
                 "record_keys": [], "evidence_ids": []}
        flow.data["audit"].update(round=1, issues=[issue], signatures=signatures)
        flow.state["staged_items"][1]["business"]["content"] = {"内容": "已更新条款"}
        topics, _, repairs = review_scope(flow)
        assert "b" in topics
        assert repairs == [issue]

    asyncio.run(run())


def test_long_review_task_keeps_full_target_in_on_demand_context():
    book, flow, _, _ = ledger()
    detail, target = "具体原文遗漏" * 100, "招标公告具体章节" * 80
    flow.entries[0]["tasks"]["long"] = {"detail": detail, "target": target,
        "status": "pending", "evidence_ids": [], "record_keys": []}
    index = json.loads(book.prompt())["works"]
    task = next(item for group in index for item in group["items"] if item["kind"] == "task")
    assert task["context_required"] and len(task["check"]) == 81
    assert "target" not in task
    units = work_units(flow, book.works(), [task["id"]])
    work = next(unit for unit in units if unit["kind"] == "work")
    assert work["check"] == detail and work["target"] == target


def test_identical_errors_on_different_records_are_counted_separately():
    from synthesis_fixtures import summary_record
    from test_analysis_combined_review import approve, execute

    from tender.application.analysis.research import AgentLimits

    async def run():
        state = {}

        async def review(payload):
            result = approve(payload)
            for verdict in result["reviews"].values():
                verdict.update(supported=False, issues=["日期缺少明确依据"])
            return result

        await execute([summary_record(key="first"), summary_record(key="second")],
                      state=state, review=review, limits=AgentLimits(max_review_repairs=0))
        assert state["quality_status"] == "needs_review"
        assert state["draft"]["fields"] == []
        assert "审查仍有2项待核对" in state["stop_reason"]["message"]

    asyncio.run(run())
