"""工作级读取与请求级原文去重，覆盖范围、依赖及摘要恢复。"""

import asyncio
import copy
import json
import re

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import COMMON, noop, summary_record
from test_analysis_argument_failures import request
from test_analysis_combined_review import approve
from test_analysis_compact_protocol import ledger
from test_analysis_prompt_budget import FakeRequest
from test_analysis_research import block, session
from test_analysis_topic_flow import snapshot
from test_deep_analysis import KEY, ScriptedRouter, call

from tender.application.analysis.agent import (
    AnalysisSummarizationMiddleware,
    ResearchMiddleware,
    RoutedAgentModel,
    build_module_agent,
    invoke_module,
)
from tender.application.analysis.context import evidence_message, stamp_evidence, visible_evidence
from tender.application.analysis.policy import load_module_skill, select_skill_rules
from tender.application.analysis.protocol import ResearchDelta, ResearchLedger
from tender.application.analysis.skills import MODULES, skill_snapshot
from tender.application.analysis.topic_flow import TopicFlow, identity


def scoped_ledger():
    book, flow, state, research = ledger()
    entry = flow.entries[0]
    entry.update(scope=COMMON, checks=["金额", "日期"], unreviewed_evidence=[])
    flow.data["entries"] = {identity("a", COMMON): entry}
    for lot in ("A", "B"):
        scope = {"kind": "lots", "lot_refs": [lot]}
        flow.data["entries"][identity("a", scope)] = flow._entry(
            {"key": "a", "checks": ["金额", "日期"]}, scope
        )
    for i, content in enumerate(("公共条件", "A标段金额", "A标段日期", "B标段金额", "补遗待核对")):
        research.seen[f"s1r1c{i}"] = block() | {
            "block_id": f"s1r1c{i}", "content": content, "offset": i
        }
    works = book.works()
    cases = ((None, "金额"), ("A", "金额"), ("A", "日期"), ("B", "金额"))
    for index, (lot, check) in enumerate(cases):
        work = next(w for w in works if w["check"] == check
                    and w["scope"]["lot_refs"] == ([] if lot is None else [lot]))
        book.update([ResearchDelta(work_ids=[work["id"]], detail=f"事实{index}",
                                   evidence_ids=[f"s1r1c{index}"])])
    return book, flow, state, research


def selected_work(book, lot="A", check="金额"):
    return next(w["id"] for w in book.works()
                if w["scope"]["lot_refs"] == [lot] and w["check"] == check)


def test_work_context_excludes_other_checks_and_lots_but_keeps_common_and_unexamined():
    book, flow, _, _ = scoped_ledger()
    flow.data["entries"][identity("a", {"kind": "lots", "lot_refs": ["A"]})].update(
        unreviewed_evidence=["s1r1c4"]
    )
    text = json.dumps(book.context([selected_work(book)], limit=12000), ensure_ascii=False)
    assert "A标段金额" in text and "公共条件" in text and "补遗待核对" in text
    assert "A标段日期" not in text and "B标段金额" not in text


def test_common_work_does_not_expand_to_another_common_check_and_shared_evidence_is_once():
    book, _, _, _ = scoped_ledger()
    common = [w for w in book.works() if w["scope"]["kind"] == "common"]
    date = next(w for w in common if w["check"] == "日期")
    amount = next(w for w in common if w["check"] == "金额")
    book.update([ResearchDelta(work_ids=[date["id"]], detail="另一个公共日期",
                              evidence_ids=["s1r1c2"])])
    page = book.context([amount["id"]], limit=12000)
    assert "另一个公共日期" not in json.dumps(page, ensure_ascii=False)
    assert "A标段日期" not in json.dumps(page, ensure_ascii=False)
    page = book.context([selected_work(book), selected_work(book, check="日期")], limit=12000)
    assert sum(u.get("id") == "s1r1c0" for u in page["units"]) == 1


def test_examined_notes_accumulate_and_followup_keeps_parent_context_after_restore():
    book, flow, state, _ = scoped_ledger()
    work_id = selected_work(book)
    book.update([ResearchDelta(work_ids=[work_id], detail="附件有金额例外", status="examined",
                              examined_ids=["s1r1c4"], followups=[{
                                  "detail": "核对例外附件", "from_block_id": "s1r1c4"
                              }])])
    book.update([ResearchDelta(work_ids=[work_id], detail="还需核对起算条件", status="examined")])
    restored = ResearchLedger(TopicFlow(copy.deepcopy(state), flow.research))
    followup = next(w["id"] for w in restored.works() if w["kind"] == "task")
    text = json.dumps(restored.context([followup], limit=12000), ensure_ascii=False)
    assert all(value in text for value in ("附件有金额例外", "还需核对起算条件", "A标段金额"))


def test_context_paging_returns_complete_units_and_rejects_changed_revision():
    book, _, _, research = scoped_ledger()
    work_id = selected_work(book)
    research.seen["s1r1c1"]["content"] = "长原文" * 2000
    page = book.context([work_id], limit=1000)
    parts = []
    while True:
        parts.extend(page["units"])
        if not page["has_more"]:
            break
        page = book.context([work_id], page["next_offset"], 1800, revision=page["revision"])
    original = "".join(p["text"] for p in parts if p.get("id") == "s1r1c1")
    assert original == research.seen["s1r1c1"]["content"]
    research.seen["s1r1c1"]["content"] += "修订"
    with pytest.raises(ValueError, match="变化"):
        book.context([work_id], 1, 1000, revision=page["revision"])


def test_record_context_keeps_explicit_cross_topic_parent_and_citations():
    book, _, state, research = scoped_ledger()
    work_id = selected_work(book)
    state["staged_items"] = [
        {"business": {"key": "child", "parent_key": "parent", "citations": [],
                      "scope": {"kind": "lots", "lot_refs": ["A"]}}, "work_ids": [work_id]},
        {"business": {"key": "parent", "title": "跨主题父条件", "citations": [
            {"block_id": "s1r1c3", "quote": research.seen["s1r1c3"]["content"]}]}}
    ]
    text = json.dumps(book.context([work_id], limit=12000), ensure_ascii=False)
    assert "跨主题父条件" in text and "B标段金额" in text


def test_repeated_tool_result_uses_current_messages_and_restores_original_after_summary():
    _, flow, state, research = scoped_ledger()

    async def run():
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)

        async def original(req):
            payload = {"blocks": [{"id": "s1r1c1", "text": "A标段金额"}]}
            return ToolMessage(content=json.dumps(payload),
                               tool_call_id=req.tool_call["id"], name="read_document")

        args = {"block_id": "s1r1c1", "before": 0, "after": 0, "topic_keys": ["a"]}
        first = await middleware.awrap_tool_call(request("read_document", args), original)
        second_request = request("read_document", args, call_id="c2", round_id="r2")
        second_request.state["messages"] = [
            AIMessage(content="", tool_calls=[{"name": "read_document", "args": args, "id": "c1"}]),
            first, *second_request.state["messages"]
        ]
        second = await middleware.awrap_tool_call(second_request, original)
        assert "A标段金额" not in second.content
        assert json.loads(second.content)["blocks"][0]["in_context"]
        # 恢复只有摘要时，缓存仍须提供原文，同一call_id重放也一样。
        third = await middleware.awrap_tool_call(request("read_document", args), original)
        assert "A标段金额" in third.content
        replay = request("read_document", args)
        replay.state["messages"].append(first)
        # 同ID重放会替换旧消息，不能把即将被替换的唯一原文当作去重依据。
        assert "A标段金额" in (await middleware.awrap_tool_call(replay, original)).content
        research.seen["s1r1c1"]["version_id"] = 99
        changed = await middleware.awrap_tool_call(
            request("read_document", args, call_id="c3", round_id="r3"), original
        )
        assert "A标段金额" in changed.content

    asyncio.run(run())


def test_scoped_rules_keep_unknown_constraints_and_only_include_selected_details():
    snapshot = skill_snapshot()
    key = "project_basic_info_parsing"
    snapshot[key + "/SKILL.md"] += "\n## 自定义要求\n所有日期必须核对最新公告。\n"
    skill = load_module_skill(snapshot, key)
    rules, _ = select_skill_rules(skill, {"identity"})
    assert "所有日期必须核对最新公告" in rules
    assert "预算与限价区分" not in rules
    budget, _ = select_skill_rules(skill, {"budget"})
    assert "预算与限价区分" in budget
    assert skill["model_rules"] == select_skill_rules(skill, set(), full=True)[0]


def test_dedup_requires_contiguous_complete_original_and_matching_version():
    _, _, _, research = scoped_ledger()
    row = research.seen["s1r1c1"]
    row["content"] = "前半内容后半内容"

    def fragment(start, text):
        return stamp_evidence(ToolMessage(content=json.dumps({"units": [{
            "kind": "evidence", "id": "s1r1c1", "start": start,
            "total": len(row["content"]), "text": text,
        }]}), tool_call_id=str(start), name="get_research_context"), research.seen)

    head, tail = fragment(0, "前半内容"), fragment(4, "后半内容")
    assert not visible_evidence([head], research.seen)
    assert visible_evidence([head, tail], research.seen) == {"s1r1c1"}
    assert not visible_evidence([head, fragment(5, "半内容")], research.seen)
    row["score"] = 0.9
    assert visible_evidence([head, tail], research.seen) == {"s1r1c1"}
    row["version_id"] = 99
    assert not visible_evidence([head, tail], research.seen)


def test_historical_already_read_is_rehydrated_after_summary_and_cache_is_unchanged():
    _, _, _, research = scoped_ledger()
    cached = ToolMessage(content=json.dumps({"blocks": [], "already_read": ["s1r1c1"]}),
                         tool_call_id="repeat", name="search_document")
    rendered = evidence_message(cached, [], research.seen)
    assert json.loads(rendered.content)["blocks"][0]["text"] == "A标段金额"
    assert json.loads(cached.content)["blocks"] == []


def test_cache_version_change_refreshes_original_and_context_revision_requires_restart():
    _, _, _, research = scoped_ledger()
    cached = stamp_evidence(ToolMessage(content=json.dumps({"blocks": [{
        "id": "s1r1c1", "text": "A标段金额",
    }]}), tool_call_id="old", name="read_document"), research.seen)
    research.seen["s1r1c1"]["content"] = "补遗调整后的金额"
    assert "补遗调整后的金额" in evidence_message(cached, [cached], research.seen).content
    page = cached.model_copy(update={"name": "get_research_context"})
    assert evidence_message(page, [], research.seen).status == "error"


def test_partial_rules_cannot_claim_full_file_loaded_and_unmapped_rules_stay_visible():
    key = "project_basic_info_parsing"
    snapshot = skill_snapshot()
    skill = load_module_skill(snapshot, key)
    _, partial = select_skill_rules(skill, {"identity"})
    _, complete = select_skill_rules(skill, set(), full=True)
    path = "/skills/project-basic-info-parsing/references/extraction_rules.md"
    assert path not in partial and path in complete
    snapshot[key + "/references/coverage.json"] = '[{"key":"custom","checks":["核对"]}]'
    custom = load_module_skill(snapshot, key)
    assert "预算与限价区分" in select_skill_rules(custom, {"custom"})[0]


def test_actual_rule_selection_follows_work_ids_and_synthesis_keeps_all_rules():
    book, flow, state, research = ledger()

    async def run():
        key = "project_basic_info_parsing"
        skill = load_module_skill(skill_snapshot(), key)
        state["business_topics"] = [{"key": key, "checks": ["核对"]}
                                    for key in ("identity", "budget")]
        flow.data["entries"] = {}
        current = TopicFlow(state, research)
        book = ResearchLedger(current)
        work_id = next(w["id"] for w in book.works() if w["topic"] == "identity")
        middleware = ResearchMiddleware(
            research, state, noop, noop, skill=skill, topic_flow=current,
        )
        messages = [AIMessage(content="", tool_calls=[{
            "name": "search_document", "id": "search",
            "args": {"query": "项目名称", "work": work_id},
        }])]

        async def capture(req):
            return req

        result = await middleware.topic_model_call(FakeRequest(messages=messages), capture)
        assert "预算与限价区分" not in result.system_message.content
        current.data["phase"] = "synthesis"
        state["output_schema"] = {}
        result = await middleware.topic_model_call(FakeRequest(messages=messages), capture)
        assert "预算与限价区分" in result.system_message.content

    asyncio.run(run())


@pytest.mark.parametrize("key", MODULES)
def test_all_native_rule_mappings_are_valid_and_full_rules_preserve_every_untagged_line(key):
    snapshot = skill_snapshot()
    coverage = json.loads(snapshot[key + "/references/coverage.json"])
    topics = {v["key"] for v in coverage}
    for path, content in snapshot.items():
        if path.startswith(key + "/"):
            for annotation in re.findall(r"<!-- topics: (.*?) -->", content):
                assert {value.strip() for value in annotation.split(",")} <= topics
    skill = load_module_skill(snapshot, key, categories=["engineering", "goods", "service"])
    full, _ = select_skill_rules(skill, topics)
    assert full == skill["model_rules"]
    for group in skill["rule_parts"]:
        for part in group["parts"]:
            if part["text"].strip():
                assert part["text"] in full


def test_actual_graph_combines_registration_and_context_read_without_repeating_original():
    async def run():
        state = {}
        router = ScriptedRouter([
            call("list_documents", {}, "docs"),
            call("search_document", {"query": "质保", "work": "w1"}, "search"),
            AIMessage(content="", tool_calls=[
                call("update_research", {"updates": [{"work_ids": ["w1"], "detail": "质保三年",
                     "scope": COMMON, "evidence_ids": ["s1r1c0"]}]}, "notes"),
                call("get_research_context", {"work_ids": ["w1"]}, "context"),
            ]),
            call("submit_analysis", {"records": [summary_record() | {"work_ids": ["w1"]}],
                                     "final": True}, "submit"),
        ])

        async def review(payload):
            return approve(payload)

        graph, files = build_module_agent(
            key=KEY, model=RoutedAgentModel(router=router), research=session([block()]),
            state=state,
            snapshot=snapshot(("a",)) | {"__analysis_flow_version__": "research-v2"},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop, review_combined=review,
        )
        await invoke_module(graph, files, thread_id="work-context", task="核对质保")
        assert len(router.requests) == 4
        context = next(m["data"] for m in router.requests[-1][0]
                       if m["type"] == "tool" and m["data"].get("name") == "get_research_context")
        units = json.loads(context["content"])["units"]
        assert any(u.get("in_context") for u in units if u.get("id") == "s1r1c0")
        assert all("text" not in u for u in units if u.get("kind") == "evidence")
        assert all("analysis_evidence" not in m["data"].get("additional_kwargs", {})
                   for messages, _ in router.requests for m in messages)
        assert state["draft"]["fields"][0]["work_ids"] == ["w1"]

    asyncio.run(run())


def test_effective_summary_history_restores_full_source_even_when_archive_still_has_it():
    _, flow, state, research = scoped_ledger()

    async def run():
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)
        middleware.summarizer = AnalysisSummarizationMiddleware(
            RoutedAgentModel(router=None), backend=None, context_tokens=24000, output_tokens=8192,
        )
        source = stamp_evidence(ToolMessage(content=json.dumps({"blocks": [{
            "id": "s1r1c1", "text": "A标段金额",
        }]}), tool_call_id="old", name="read_document"), research.seen)
        req = request("read_document", {}, call_id="after-summary")
        from langchain_core.messages import HumanMessage

        req.state.update(messages=[source, *req.state["messages"]], _summarization_event={
            "cutoff_index": 1, "summary_message": HumanMessage(content="仅有摘要"),
            "file_path": None,
        })
        assert "A标段金额" in middleware.evidence_response(req, source).content

    asyncio.run(run())
