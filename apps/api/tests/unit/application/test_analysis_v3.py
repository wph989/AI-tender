"""新协议沿生产图验证草稿复用、身份、批次预算和整项定位。"""

import asyncio
import copy
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import noop
from test_analysis_combined_review import approve
from test_analysis_compact_protocol import ledger
from test_analysis_research import block, session
from test_analysis_topic_flow import snapshot
from test_deep_analysis import KEY, ScriptedRouter, call

from tender.application.analysis.agent import RoutedAgentModel, build_module_agent, invoke_module
from tender.application.analysis.data import module_data, record_identity
from tender.application.analysis.protocol import SubmissionRecord, submission_records


def build(
    script, research=None, *, reserve=None, review=None, state=None, budget=None, keys=("a",),
):
    state, saved, reviewed, reserved = state if state is not None else {}, [], [], []

    async def save(value):
        saved.append(copy.deepcopy(value))

    async def check(payload):
        reviewed.append(payload)
        return await review(payload) if review else approve(payload)

    async def begin(key):
        reserved.append(key)
        return await reserve(key) if reserve else key

    router = ScriptedRouter(script)
    frozen = snapshot(keys) | {"__analysis_flow_version__": "research-v3",
        KEY + "/references/output_schema.json": json.dumps(schema(), ensure_ascii=False)}
    graph, files = build_module_agent(
        key=KEY, model=RoutedAgentModel(router=router), research=research or session([block()]),
        state=state, snapshot=frozen, checkpointer=InMemorySaver(), reserve_tool=noop,
        begin_tool=begin, save=save, review_combined=check, budget_status=budget,
    )
    return graph, files, state, saved, reviewed, reserved


def batch(queries, name="batch"):
    return call("search_document_batch", {"queries": [
        {"query": query, "work_ids": ["w1"]} for query in queries]}, name)


def finish():
    return [call("submit_analysis", {"records": [raw()], "final": False}, "draft"),
            call("complete_research", {"research_summary": "已核对完整条款"}, "done")]


def raw(**overrides):
    return {"kind": "fact", "group": "项目基本信息", "content": {"字段": "质保", "内容": "三年"},
            "scope": {"kind": "common"}, "block_ids": ["s1r1c0"], "work_ids": ["w1"],
            **overrides}


def schema():
    return {"version": "1", "sections": [{"title": "项目基本信息", "layout": "table",
            "columns": ["字段", "内容"], "title_column": "字段"}]}


def test_identity_replay_update_and_failed_original_position_survive_checkpoint():
    book, _, state, _ = ledger()
    state["output_schema"] = schema()
    records = [SubmissionRecord.model_validate(raw(group="bad")),
               SubmissionRecord.model_validate(raw())]
    adapted, rejected = submission_records(records, state, book.works(), "call-1")
    assert [i for i, _ in adapted] == [1] and rejected[0]["index"] == 0
    key = adapted[0][1].key
    restored = json.loads(json.dumps(state))
    again, _ = submission_records(records, restored, book.works(), "call-1")
    assert again[0][1].key == key
    changed = SubmissionRecord.model_validate(raw(id=record_identity(state, key),
                                                 content={"字段": "新标题", "内容": "五年"}))
    updated, _ = submission_records([changed], restored, book.works(), "call-2")
    assert updated[0][1].key == key and updated[0][1].title == "新标题"


def test_scope_unknown_requires_explicit_declaration_and_title_keeps_full_body():
    book, _, state, _ = ledger()
    state["output_schema"] = schema()
    record = SubmissionRecord.model_validate(raw(scope=None))
    assert submission_records([record], state, book.works(), "scope")[1]
    record = SubmissionRecord.model_validate(raw(content={"字段": ["甲" * 200, "乙" * 200],
                                                         "内容": "完整内容"}))
    adapted, errors = submission_records([record], state, book.works(), "title")
    assert not errors and len(adapted[0][1].title) == 300
    assert len(adapted[0][1].content["字段"][1]) == 200


def test_batch_deduplicates_and_drafts_go_directly_to_one_review():
    async def run():
        state, saved, reviewed, reserved = {}, [], [], []

        async def save(value):
            saved.append(copy.deepcopy(value))

        async def review(payload):
            reviewed.append(payload)
            return approve(payload)

        async def reserve(key):
            reserved.append(key)
            return key

        router = ScriptedRouter([
            call("list_documents", {}, "docs"),
            call("search_document_batch", {"queries": [
                {"query": "质保", "work_ids": ["w1"]},
                {"query": "质保", "work_ids": ["w1"]},
            ]}, "batch"),
            call("submit_analysis", {"records": [raw()], "final": False}, "draft"),
            call("complete_research", {"research_summary": "已核对质保三年"}, "done"),
        ])
        frozen = snapshot(("a",)) | {"__analysis_flow_version__": "research-v3",
            KEY + "/references/output_schema.json": json.dumps(schema(), ensure_ascii=False)}
        research = session([block()])
        graph, files = build_module_agent(
            key=KEY, model=RoutedAgentModel(router=router), research=research, state=state,
            snapshot=frozen, checkpointer=InMemorySaver(), reserve_tool=noop,
            begin_tool=reserve, save=save, review_combined=review,
        )
        await invoke_module(graph, files, thread_id="v3", task="研究并暂存")
        assert not router.calls and len(reviewed) == 1
        assert "call_batch" not in reserved and reserved.count("call_batch:query:0") == 1
        assert state["tool_outcomes"]["call_batch"] == "skipped"
        assert state["tool_outcomes"]["call_batch:query:0"] == "ok"
        payload = json.loads(state["tool_results"]["call_batch"]["data"]["content"])
        assert len(payload["queries"]) == 1 and payload["queries"][0]["indices"] == [0, 1]
        assert len(payload["blocks"]) == 1
        result = module_data(state)
        assert len(result["records"]) == 1 and result["records"][0]["title"] == "质保"
        assert "content_evidence" not in result["records"][0]
        assert result["evidence"] and all(not module_data(s)["records"]
                                          for s in saved if "draft" not in s)
        receipt = json.loads(state["tool_results"]["call_draft"]["data"]["content"])["records"][0]
        assert receipt["id"] == result["records"][0]["id"]
        assert "values" not in reviewed[0]["records"][0]

    asyncio.run(run())


@pytest.mark.parametrize("invalid", ["foreign", ""])
def test_review_requires_evidence_from_delivered_packet(invalid):
    from tender.application.analysis.review import validate
    from tender.domain.shared.errors import InvalidModelOutput

    packet = {"records": [{"record_id": "r1"}], "record_index": [{"record_id": "r1"}],
              "evidence": [{"id": "b1"}], "context_evidence": [], "topic": "a"}
    with pytest.raises(InvalidModelOutput, match="block_ids"):
        validate({"reviews": {"r1": {"supported": True, "block_ids": [invalid], "issues": []}},
                  "issues": []}, packet)


def test_partial_batch_failure_preserves_successes_and_settles_each_query():
    async def run():
        research = session([block()])
        retrieve = research.retrieve
        active, peak = 0, 0

        async def recall(sources, query):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(0)
                if query == "失败":
                    raise RuntimeError("检索服务故障")
                return await retrieve(sources, query)
            finally:
                active -= 1

        research.retrieve = recall
        graph, files, state, _, reviewed, _ = build([
            batch(["质保", "失败", "期限", "条件"]), *finish(),
        ], research)
        await invoke_module(graph, files, thread_id="partial", task="批量取证")
        response = json.loads(state["tool_results"]["call_batch"]["data"]["content"])
        assert [q["status"] for q in response["queries"]] == ["ok", "error", "ok", "ok"]
        assert peak == 2 and active == 0
        assert len(response["blocks"]) == 1 and len(reviewed) == 1
        assert state["tool_outcomes"]["call_batch:query:1"] == "error"
        assert state["topic_flow"]["search_work"]["w1"]["attempts"] == 1

    asyncio.run(run())


def test_batches_with_new_evidence_do_not_trigger_global_no_progress_stop():
    async def run():
        rows = [block() | {"block_id": f"s1r1c{i}", "offset": i, "element_id": i + 1,
                           "content": f"独立条款{i}"} for i in range(5)]
        research = session(rows)

        async def recall(sources, query):
            return [rows[int(query[1:])]], {"mode": "keyword"}

        research.retrieve = recall
        graph, files, state, _, reviewed, _ = build([
            *(batch([f"q{i}"], f"b{i}") for i in range(5)), *finish(),
        ], research)
        await invoke_module(graph, files, thread_id="batch-progress", task="继续获取新增条款")
        assert set(research.seen) == {row["block_id"] for row in rows}
        assert all(state["tool_outcomes"].get(f"call_b{i}:query:0") == "ok" for i in range(5))
        assert "research_stop_reason" not in state["topic_flow"] and len(reviewed) == 1
        assert "active_tool_round_id" not in state

    asyncio.run(run())


def test_new_research_drafts_do_not_trigger_global_no_progress_stop():
    async def run():
        costs = ["安装", "调试", "培训", "运输", "保险"]
        research = session([block() | {"content": "费用包含" + "、".join(costs)}])
        graph, files, state, _, reviewed, _ = build([
            call("search_document", {"query": "费用", "work_ids": ["w1"]}, "search"),
            *(call("submit_analysis", {"records": [raw(content={
                "字段": "费用", "内容": "包含" + cost,
            })], "final": False}, f"draft{i}") for i, cost in enumerate(costs)),
            call("complete_research", {"research_summary": "费用条款已全部暂存"}, "done"),
        ], research)
        await invoke_module(graph, files, thread_id="draft-progress", task="逐条暂存完整事项")
        assert state["tool_outcomes"].get("call_done") == "ok"
        assert len(module_data(state)["records"]) == 5 and len(reviewed) == 1
        assert "research_stop_reason" not in state["topic_flow"]

    asyncio.run(run())


@pytest.mark.parametrize("protocol", ["research-v2", "research-v3"])
def test_research_draft_signature_counts_business_changes_without_renewing_duplicates(protocol):
    _, flow, state, _ = ledger()
    flow.data["protocol"] = protocol
    assert flow.researching
    before = flow.signature()
    item = {"id": "first", "verification": "pending", "review_status": "current",
            "business": raw() | {"key": "first", "title": "质保"}}
    state["staged_items"] = [item]
    signature = flow.signature()
    assert (signature != before) == (protocol == "research-v3")
    duplicate = copy.deepcopy(item)
    duplicate.update(id="second", review_status="needs_review")
    duplicate["business"].update(key="second", title="重命名")
    state["staged_items"].append(duplicate)
    assert flow.signature() == signature
    duplicate["business"]["content"]["内容"] = "五年"
    assert (flow.signature() != signature) == (protocol == "research-v3")


@pytest.mark.parametrize("source_id", [2, 999])
@pytest.mark.parametrize("prefetch_validates", [True, False])
def test_invalid_batch_source_does_not_discard_valid_subqueries(source_id, prefetch_validates):
    async def run():
        research = session([block()])
        if not prefetch_validates:
            prefetch = research.prefetch_search

            async def recall(query, selected_source=None):
                # 模拟预取未发现来源问题，仍须在串行校验阶段隔离该子查询。
                if selected_source != source_id:
                    await prefetch(query, selected_source)

            research.prefetch_search = recall
        graph, files, state, _, reviewed, _ = build([
            call("search_document_batch", {"queries": [
                {"query": "质保", "work_ids": ["w1"]},
                {"query": "错误来源", "source_id": source_id, "work_ids": ["w1"]},
                {"query": "期限", "work_ids": ["w1"]},
            ]}, "mixed"),
            # 旧逻辑整批失败后仍能完成图运行，使失败断言直接指向批次回执。
            call("search_document", {"query": "核对质保", "work_ids": ["w1"]}, "recover"),
            *finish(),
        ], research)
        await invoke_module(graph, files, thread_id="mixed-source", task="保留合法来源查询")
        payload = json.loads(state["tool_results"]["call_mixed"]["data"]["content"])
        assert "queries" in payload, payload
        assert [q["status"] for q in payload["queries"]] == ["ok", "error", "ok"]
        assert "授权范围" in payload["queries"][1]["error"]
        assert [state["tool_outcomes"][f"call_mixed:query:{i}"] for i in range(3)] == [
            "ok", "error", "ok",
        ]
        assert set(research.seen) == {"s1r1c0"}
        assert len(module_data(state)["records"]) == 1 and len(reviewed) == 1

    asyncio.run(run())


def test_batch_budget_shortage_keeps_successful_query_and_does_not_reserve_parent():
    async def run():
        from tender.domain.shared.errors import BudgetExhausted

        async def reserve(key):
            if key.endswith("query:1"):
                raise BudgetExhausted("工具额度不足")
            return key

        graph, files, state, _, _, reserved = build([
            batch(["质保", "期限"]), *finish(),
        ], reserve=reserve)
        await invoke_module(graph, files, thread_id="budget", task="保留预算内成果")
        response = json.loads(state["tool_results"]["call_batch"]["data"]["content"])
        assert [q["status"] for q in response["queries"]] == ["ok", "skipped"]
        assert "call_batch" not in reserved and len(module_data(state)["records"]) == 1

    asyncio.run(run())


def test_permission_failure_cancels_remaining_retrievals_and_reclaims_reservations():
    async def run():
        research = session([block()])
        waiting, canceled = asyncio.Event(), asyncio.Event()

        async def recall(sources, query):
            if query == "撤权":
                await waiting.wait()
                raise PermissionError("资料已撤权")
            waiting.set()
            try:
                await asyncio.Event().wait()
            finally:
                canceled.set()

        research.retrieve = recall
        graph, files, state, _, reviewed, _ = build([batch(["撤权", "等待", "剩余"])], research)
        with pytest.raises(PermissionError, match="撤权"):
            await invoke_module(graph, files, thread_id="revoke", task="取证")
        assert canceled.is_set() and not reviewed and not research.seen
        assert all(state["tool_outcomes"][f"call_batch:query:{i}"] == "unknown" for i in range(3))

    asyncio.run(run())


def test_zero_project_evidence_skips_synthesis_and_review():
    async def run():
        from tender.application.analysis.topic_flow import TopicIncomplete

        graph, files, state, _, reviewed, _ = build([
            batch(["未命中"]),
            call("complete_research", {"research_summary": "未取得原文"}, "done"),
        ], session([]))
        with pytest.raises(TopicIncomplete, match="取证失败"):
            await invoke_module(graph, files, thread_id="empty", task="取证")
        assert not reviewed and state["stop_reason"]["code"] == "evidence_failed"

    asyncio.run(run())


def test_valid_relation_group_survives_unrelated_bad_record_in_same_batch():
    from tender.application.analysis.data import prepare_record_batch

    book, _, state, research = ledger()
    state["output_schema"] = schema()
    records = [raw(key="base"), raw(key="revised", content={"字段": "修订", "内容": "三年"}),
               raw(kind="relation", subject_key="revised", object_key="base",
                   predicate="supersedes"),
               raw(group="bad", title="错误项")]
    adapted, errors = submission_records([SubmissionRecord.model_validate(v) for v in records],
                                         state, book.works(), "mixed")
    assert not errors
    prepared, rejected = prepare_record_batch([v for _, v in adapted], state, research.seen, KEY)
    assert len(prepared) == 3 and rejected[0]["index"] == 3
    assert prepared[2]["business"]["subject_text"]


def test_work_draft_changes_advance_once_and_notes_do_not_extend_idle_budget():
    from tender.application.analysis.search_control import TopicSearch

    book, flow, state, research = ledger()
    flow.data["protocol"] = "research-v3"
    control = TopicSearch(flow)
    for index in range(3):
        selected = control.begin("search_document", {"query": str(index), "work": ["w1"]})
        if index == 1:
            state["staged_items"] = [{"id": "x", "work_ids": ["w1"], "verification": "pending",
                                      "business": {"key": "x", "content": {
                                          "字段": "质保", "内容": "三年",
                                      }}}]
        control.end(selected, {"blocks": []}, set(research.seen))
    assert control.ledger["w1"]["idle"] == 1
    selected = control.begin("search_document", {"query": "最后", "work": ["w1"]})
    control.end(selected, {"blocks": []}, set(research.seen))
    assert control.ledger["w1"]["exhausted"]


def test_single_search_accepts_v3_work_ids_and_encoded_container_arguments():
    async def run():
        graph, files, state, _, reviewed, _ = build([
            call("search_document", {"query": "质保", "work_ids": '["w1"]'}, "single"),
            call("submit_analysis", {"records": json.dumps([raw()], ensure_ascii=False),
                                     "final": False}, "draft"),
            call("complete_research", {"research_summary": "已核对"}, "done"),
        ])
        await invoke_module(graph, files, thread_id="encoded", task="研究并暂存")
        assert len(reviewed) == 1 and len(module_data(state)["records"]) == 1
        assert state["topic_flow"]["search_work"]["w1"]["attempts"] == 1

    asyncio.run(run())


def test_typed_bad_record_does_not_renumber_valid_identity_and_can_be_corrected():
    async def run():
        state = {}
        identity = record_identity(state, "r-" + record_identity(state, "submission:call_draft:0"))
        graph, files, state, _, reviewed, _ = build([
            batch(["质保"]),
            call("submit_analysis", {"records": [raw(id=[], content=7), raw()],
                                     "final": False}, "draft"),
            call("submit_analysis", {"records": [raw(id=identity)], "final": False}, "correct"),
            call("complete_research", {"research_summary": "已核对"}, "done"),
        ], state=state)
        await invoke_module(graph, files, thread_id="typed", task="保留有效事项")
        receipts = json.loads(state["tool_results"]["call_draft"]["data"]["content"])["records"]
        assert "progress" not in json.loads(state["tool_results"]["call_draft"]["data"]["content"])
        assert [r["status"] for r in receipts] == ["rejected", "accepted"]
        assert receipts[0]["id"] == identity
        assert receipts[1]["id"] == record_identity(state, state["submission_identities"][
            "call_draft:1"])
        assert len(reviewed) == 1 and len(module_data(state)["records"]) == 2

    asyncio.run(run())


def test_argument_decoding_preserves_json_text_inside_content():
    from tender.application.analysis.protocol import tool_arguments

    body = '{"work_ids":"[1,2]"}'
    result = tool_arguments("submit_analysis", {"records": json.dumps([raw(
        content={"字段": "格式", "内容": body}, scope={"kind": "lots", "lot_refs": '["标段一"]'},
    )], ensure_ascii=False)})
    assert result["records"][0]["content"]["内容"] == body
    assert result["records"][0]["scope"]["lot_refs"] == ["标段一"]


def test_conflicting_confirmed_scope_rejects_only_its_own_record():
    book, _, state, _ = ledger()
    state["output_schema"] = schema()
    works = book.works()
    works[0]["scope"] = {"kind": "common", "lot_refs": []}
    records = [raw(scope={"kind": "unknown"}), raw()]
    adapted, errors = submission_records([SubmissionRecord.model_validate(r) for r in records],
                                         state, works, "scopes")
    assert [index for index, _ in adapted] == [1]
    assert errors[0]["index"] == 0 and "scope" in errors[0]["error"]


def test_retrieval_cache_ignores_work_ids_without_losing_work_association():
    from tender.application.analysis.policy import tool_key

    assert tool_key("search_document", {"query": "质保", "work_ids": ["w1"]}, retrieval=True) == (
        tool_key("search_document", {"query": "质保", "work_ids": ["w2"]}, retrieval=True))


def test_serial_expansion_failure_keeps_later_successful_subqueries():
    async def run():
        research = session([block()])
        count = 0

        async def expand(sources, rows):
            nonlocal count
            count += 1
            if count == 1:
                raise RuntimeError("邻段服务故障")
            return rows, []

        research.expand = expand
        graph, files, state, _, reviewed, _ = build([batch(["失败", "质保"]), *finish()], research)
        await invoke_module(graph, files, thread_id="expand", task="保留有效子查询")
        payload = json.loads(state["tool_results"]["call_batch"]["data"]["content"])
        assert [q["status"] for q in payload["queries"]] == ["error", "ok"]
        assert len(reviewed) == 1

    asyncio.run(run())


def test_partial_batch_resume_reuses_success_and_settles_work_once():
    async def run():
        from langgraph.errors import NodeCancelledError

        research = session([block()])
        count = 0

        async def expand(sources, rows):
            nonlocal count
            count += 1
            if count == 2:
                raise asyncio.CancelledError()
            return rows, []

        research.expand = expand
        graph, files, state, _, _, reserved = build([batch(["质保", "期限"])], research)
        with pytest.raises(NodeCancelledError):
            await invoke_module(graph, files, thread_id="interrupt", task="取证")
        assert state["tool_outcomes"]["call_batch:query:0"] == "ok"
        restored = json.loads(json.dumps(state))
        resumed = session([block()])
        resumed.seen = restored["research"]["seen"]
        resumed.events = restored["research"]["events"]
        requests = []
        retrieve = resumed.retrieve

        async def recall(sources, query):
            requests.append(query)
            return await retrieve(sources, query)

        resumed.retrieve = recall
        graph, files, state, _, _, new_reserved = build([
            batch(["质保", "期限"]), *finish(),
        ], resumed, state=restored)
        await invoke_module(graph, files, thread_id="resumed", task="恢复取证")
        assert requests == ["期限"]
        assert "call_batch:query:0" in reserved and "call_batch:query:0" not in new_reserved
        assert state["topic_flow"]["search_work"]["w1"]["attempts"] == 1
        assert state["topic_flow"]["search_work"]["w1"]["evidence_ids"] == ["s1r1c0"]

    asyncio.run(run())


def test_corrected_evidence_pass_cache_survives_another_record_repair():
    async def run():
        from test_analysis_review_v2 import flow_fixture

        from tender.application.analysis.review import audit_combined

        flow = await flow_fixture()
        first = flow.state["staged_items"][0]
        second = copy.deepcopy(first)
        second["id"] = "second-id"
        second["business"].update(key="second", title="另一事项")
        flow.state["staged_items"].append(second)
        flow.entries[0]["record_keys"].append("second")
        flow.research.seen["alternative"] = block() | {"block_id": "alternative"}
        flow.entries[0]["evidence_ids"].append("alternative")
        requests = []

        async def review(payload):
            requests.append(copy.deepcopy(payload))
            result = approve(payload)
            if len(requests) == 1:
                result["reviews"][first["id"]]["block_ids"] = ["alternative"]
                result["issues"] = [{"topic": "a", "kind": "unsupported", "detail": "补充条件",
                    "target": "第二事项", "record_ids": [second["id"]], "evidence_ids": []}]
            return result

        assert not await audit_combined(flow, review, noop)
        assert first["business"]["citations"][0]["block_id"] == "alternative"
        second["business"]["conditions"]["expression"] = "补充完整适用条件"
        assert await audit_combined(flow, review, noop)
        assert [r["record_id"] for r in requests[1]["records"]] == ["second-id"]

    asyncio.run(run())


def test_candidate_version_change_invalidates_pass_even_when_final_selection_is_unchanged():
    async def run():
        from test_analysis_review_v2 import flow_fixture

        from tender.application.analysis.review import audit_combined, batches

        flow = await flow_fixture()
        item = flow.state["staged_items"][0]
        flow.research.seen["candidate"] = block() | {"block_id": "candidate"}
        flow.entries[0]["evidence_ids"].append("candidate")
        item["review_evidence_ids"] = ["candidate"]

        async def review(payload):
            return approve(payload)

        assert await audit_combined(flow, review, noop)
        assert not any(p["records"] for p in batches(flow, "a", [])[0])
        flow.research.seen["candidate"]["content"] = "修订新增例外"
        assert [r["record_id"] for p in batches(flow, "a", [])[0] for r in p["records"]] == [
            item["id"],
        ]

    asyncio.run(run())


def test_large_topic_packets_preserve_complete_items_without_repeating_all_bodies():
    async def run():
        from dataclasses import replace

        from test_analysis_review_v2 import flow_fixture

        from tender.application.analysis.review import batches, fits

        flow = await flow_fixture()
        flow.research.limits = replace(flow.research.limits, review_max_input_tokens=6000)
        template = flow.state["staged_items"][0]
        items = []
        for index in range(30):
            item = copy.deepcopy(template)
            item["id"] = str(index)
            item["business"].update(key=str(index), title=f"事项{index}", content={
                "字段": f"事项{index}", "内容": "完整条件与例外" * 30,
            })
            items.append(item)
        flow.state["staged_items"] = items
        flow.entries[0]["record_keys"] = [str(index) for index in range(30)]
        packets, _ = batches(flow, "a", [])
        assert len(packets) > 1 and all(fits(p, flow.research.limits) for p in packets)
        assert [row["record_id"] for p in packets for row in p["records"]] == [
            str(index) for index in range(30)]
        assert all(row["business"]["content"]["内容"] == "完整条件与例外" * 30
                   for packet in packets for row in packet["records"])
        assert all(len(p["context_records"]) == 0 for p in packets)

    asyncio.run(run())


def test_original_unknown_work_can_explicitly_split_after_checkpoint_scope_migration():
    book, _, state, _ = ledger()
    state["output_schema"] = schema()
    works = book.works()
    state["topic_flow"]["synthesis_work_origins"] = {"w1": copy.deepcopy(works[0])}
    works[0]["scope"] = {"kind": "common", "lot_refs": []}
    state = json.loads(json.dumps(state))
    adapted, errors = submission_records([SubmissionRecord.model_validate(raw(
        scope={"kind": "lots", "lot_refs": ["标段一"]},
    ))], state, works, "split")
    assert not errors and adapted[0][1].scope.kind == "lots"
    adapted, errors = submission_records([SubmissionRecord.model_validate(raw(scope=None))],
                                         state, works, "inherit")
    assert not errors and adapted[0][1].scope.kind == "common"


def test_duplicate_alias_group_does_not_reject_unrelated_valid_reference_group():
    book, _, state, _ = ledger()
    state["output_schema"] = schema()
    records = [raw(key="dup"), raw(key="dup"),
               raw(kind="relation", predicate="conflicts", subject_key="dup", object_key="dup"),
               raw(key="first"), raw(key="second"),
               raw(kind="relation", predicate="requires", subject_key="first", object_key="second")]
    adapted, errors = submission_records([SubmissionRecord.model_validate(r) for r in records],
                                         state, book.works(), "duplicate")
    assert [index for index, _ in adapted] == [3, 4, 5]
    assert [error["index"] for error in errors] == [0, 1, 2]
    assert len(state["submission_identities"]) == 6


def test_budget_research_exit_reuses_drafts_without_another_synthesis_call():
    async def run():
        state = {}
        graph, files, state, _, reviewed, _ = build([
            batch(["质保"]),
            call("submit_analysis", {"records": [raw()], "final": False}, "draft"),
        ], state=state, budget=lambda: {
            "model_calls_remaining": 4 if state.get("staged_items") else 40,
        })
        await invoke_module(graph, files, thread_id="draft-exit", task="研究并暂存")
        assert len(reviewed) == 1 and len(module_data(state)["records"]) == 1
        assert state["topic_flow"]["research_stop_reason"] == "budget_reserve"

    asyncio.run(run())


@pytest.mark.parametrize("record", [raw(kind="lot"), raw(kind="format_node", node_type="group")])
def test_named_special_structures_still_require_title(record):
    book, _, state, _ = ledger()
    state["output_schema"] = schema()
    adapted, errors = submission_records([SubmissionRecord.model_validate(record)],
                                         state, book.works(), "named")
    assert not adapted and "title" in errors[0]["error"]


def test_resolved_task_note_rewrite_does_not_advance_work_signature():
    from tender.application.analysis.search_control import TopicSearch

    _, flow, _, _ = ledger()
    flow.data["protocol"] = "research-v3"
    flow.entries[0]["tasks"] = {"task": {"status": "resolved", "detail": "原笔记"}}
    target = {"id": "task-work", "kind": "task", "task_id": "task", "record_keys": [],
              "topic": flow.entries[0]["topic"], "scope": flow.entries[0]["scope"]}
    control = TopicSearch(flow)
    signature = control.signature(target)
    flow.entries[0]["tasks"]["task"]["detail"] = "笔记改写"
    assert control.signature(target) == signature
    flow.entries[0]["tasks"]["task"]["status"] = "pending"
    assert control.signature(target) != signature


def test_review_read_ranges_merge_only_contiguous_blocks_of_the_same_version():
    async def run():
        from test_analysis_review_v2 import flow_fixture

        from tender.application.analysis.review import _reads

        flow = await flow_fixture()
        rows = [block() | {"block_id": f"b{i}", "offset": offset, "version_id": version}
                for i, (offset, version) in enumerate(((0, 1), (1, 1), (3, 1), (2, 2)))]
        flow.research.seen.update({row["block_id"]: row for row in rows})
        flow.entries[0]["evidence_ids"] = ["b0"]
        flow.research.events = [{"action": "read_result", "anchor_ids": ["b0"],
            "block_ids": [row["block_id"] for row in rows], "read_limited": True,
            "continue_from": ["b2"]}] * 3
        ranges = _reads(flow, flow.entries)
        assert len(ranges) == 2
        assert ranges[0]["windows"] == [{"first_id": "b0", "last_id": "b1"},
                                         {"first_id": "b2", "last_id": "b2"}]
        assert ranges[1]["windows"] == [{"first_id": "b3", "last_id": "b3"}]
        assert all(r["read_limited"] and r["continue_from"] == ["b2"] for r in ranges)

    asyncio.run(run())


def test_mixed_confirmed_work_scopes_cannot_be_inherited():
    book, _, state, _ = ledger()
    state["output_schema"] = schema()
    first = book.works()[0] | {"scope": {"kind": "common", "lot_refs": []}}
    second = first | {"id": "w2", "scope": {"kind": "lots", "lot_refs": ["标段一"]}}
    record = SubmissionRecord.model_validate(raw(scope=None, work_ids=[first["id"], "w2"]))
    adapted, errors = submission_records([record], state, [first, second], "mixed-scopes")
    assert not adapted and "混合工作范围必须显式声明" in errors[0]["error"]


def test_batch_cancellation_stops_all_retrievals_and_releases_pending_children():
    async def run():
        research = session([block()])
        started, active = asyncio.Event(), set()

        async def recall(sources, query):
            active.add(query)
            if len(active) == 2:
                started.set()
            try:
                await asyncio.Event().wait()
            finally:
                active.remove(query)

        research.retrieve = recall
        graph, files, state, _, reviewed, _ = build([batch(["甲", "乙", "丙"])], research)
        task = asyncio.create_task(invoke_module(graph, files, thread_id="cancel", task="取证"))
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not active and not reviewed and not research.seen
        assert all(state["tool_outcomes"][f"call_batch:query:{i}"] == "unknown" for i in range(3))

    asyncio.run(run())


def test_batch_pagination_reuses_recall_and_returns_each_complete_original_block():
    async def run():
        from tender.application.analysis.research import AgentLimits

        limits = AgentLimits(max_search_results=2)
        rows = [block() | {"block_id": f"s1r1c{i}", "offset": i, "element_id": i,
                          "content": f"质保三年；条件{i}及例外均保留"} for i in range(3)]
        research = session(rows, limits=limits)
        retrieve, requests = research.retrieve, []

        async def recall(sources, query):
            requests.append(query)
            return await retrieve(sources, query)

        research.retrieve = recall
        graph, files, state, _, _, _ = build([
            batch(["质保"]),
            call("search_document_batch", {"queries": [
                {"query": "质保", "work_ids": ["w1"], "offset": 2}]}, "page-2"),
            *finish(),
        ], research)
        await invoke_module(graph, files, thread_id="batch-pages", task="补齐明确续页")
        first = json.loads(state["tool_results"]["call_batch"]["data"]["content"])
        second = json.loads(state["tool_results"]["call_page-2"]["data"]["content"])
        assert requests == ["质保"]
        assert first["queries"][0]["page"]["next_offset"] == 2
        assert second["queries"][0]["page"]["has_more"] is False
        assert {row["id"]: row["text"] for row in first["blocks"] + second["blocks"]} == {
            row["block_id"]: row["content"] for row in rows}

    asyncio.run(run())


def test_native_adapter_decodes_encoded_batch_before_per_record_validation(monkeypatch):
    from langchain_core.messages import messages_from_dict

    from tender.adapters.llm.agent_chat import AgentChat

    original = ScriptedRouter.chat

    async def checked_chat(self, messages, tools):
        completion = await original(self, messages, tools)
        submit_schema = next(tool["function"]["parameters"] for tool in tools
                             if tool["function"]["name"] == "submit_analysis")
        assert "block_ids" in submit_schema["properties"]["records"]["description"]

        class SDK:
            kwargs = {}

            def bind_tools(self, _tools):
                return self

            def _get_request_payload(self, _messages, **_options):
                return {}

        async def aggregate(_payload, _progress):
            message = messages_from_dict([completion.agent_message])[0]
            message.response_metadata["finish_reason"] = (
                "tool_calls" if message.tool_calls else "stop"
            )
            return message

        # 保留真实适配器的原生参数门禁，避免可控路由跳过它而掩盖整批拒绝。
        gateway = object.__new__(AgentChat)
        gateway.model, gateway._stream_chat, gateway._max_tokens = SDK(), True, 4096
        gateway._api_mode, gateway._api_key = "chat_completions", None
        gateway._timeout, gateway._total_timeout = 5, None
        gateway._aggregate_chat_stream = aggregate
        return await gateway.chat(messages, tools)

    monkeypatch.setattr(ScriptedRouter, "chat", checked_chat)

    async def run():
        body = '["原文中的JSON文本必须保留"]'
        graph, files, state, _, _, _ = build([
            batch(["质保"]),
            call("submit_analysis", {"records": json.dumps([
                None, raw(content=7), raw(content={"字段": "说明", "内容": body}),
            ], ensure_ascii=False), "final": False}, "draft"),
            call("complete_research", {"research_summary": "已核对"}, "done"),
        ])
        await invoke_module(graph, files, thread_id="native-batch", task="保留同批有效事项")
        receipts = json.loads(state["tool_results"]["call_draft"]["data"]["content"])["records"]
        assert [receipt["status"] for receipt in receipts] == ["rejected", "rejected", "accepted"]
        assert [receipt["index"] for receipt in receipts] == [0, 1, 2]
        assert len({receipt["id"] for receipt in receipts}) == 3
        assert module_data(state)["records"][0]["content"]["内容"] == body

    asyncio.run(run())


def test_premature_final_preserves_valid_draft_and_requires_research_completion():
    async def run():
        graph, files, state, _, reviewed, _ = build([
            batch(["质保"]),
            call("submit_analysis", {"records": [raw()], "final": True}, "early-final"),
            call("complete_research", {"research_summary": "已核对完整条款"}, "done"),
        ])
        await invoke_module(graph, files, thread_id="early-final", task="保存已有正文")
        receipt = json.loads(state["tool_results"]["call_early-final"]["data"]["content"])
        assert receipt["records"][0]["status"] == "accepted"
        assert receipt["final"] is False and "complete_research" in receipt["next_action"]
        assert len(reviewed) == len(module_data(state)["records"]) == 1

    asyncio.run(run())


def test_review_rejection_requires_specific_issue_and_empty_packet_uses_object():
    from tender.application.analysis.review import prompt, validate
    from tender.domain.shared.errors import InvalidModelOutput

    packet = {"records": [{"record_id": "r1"}], "record_index": [{"record_id": "r1"}],
              "evidence": [{"id": "b1"}], "context_evidence": [], "topic": "a"}
    with pytest.raises(InvalidModelOutput, match="具体正文、范围或依据问题及修法"):
        validate({"reviews": {"r1": {"supported": False, "block_ids": [], "issues": []}},
                  "issues": []}, packet)
    empty = packet | {"records": [], "record_index": []}
    validate({"reviews": {}, "issues": []}, empty)
    assert '"reviews":{}' in prompt(empty)
