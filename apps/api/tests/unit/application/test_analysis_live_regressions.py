"""13:49真实运行暴露的协议丢失与空召回回归，覆盖发给模型的最终请求。"""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
import test_analysis_v3 as fixture
from test_analysis_research import block, session
from test_deep_analysis import ScriptedRouter, call

from tender.application.analysis import execution
from tender.application.analysis.agent import invoke_module
from tender.application.analysis.research import AgentLimits
from tender.application.analysis.validation import ToolIssue, record_issues, resolve_issues
from tender.application.knowledge.content import rank_chunks


def test_supplier_receives_complete_batch_schemas_and_keeps_partial_validation(monkeypatch):
    async def run():
        router = ScriptedRouter([fixture.batch(["质保"]), *fixture.finish()])
        monkeypatch.setattr(fixture, "ScriptedRouter", lambda _: router)
        graph, files, *_ = fixture.build([])
        await invoke_module(graph, files, thread_id="supplier-schema", task="核对完整协议")
        schemas = {tool["function"]["name"]: tool["function"]["parameters"]
                   for tool in router.requests[0][1]}
        records = schemas["submit_analysis"]["properties"]["records"]["items"]
        assert records["properties"]["kind"]["enum"] == [
            "fact", "requirement", "lot", "format_node", "relation",
        ]
        assert set(records["required"]) >= {"kind", "content", "block_ids", "work_ids"}
        updates = schemas["update_research"]["properties"]["updates"]
        assert updates["maxItems"] == 50
        assert "found" in updates["items"]["properties"]["status"]["enum"]
        assert "scope" in updates["items"]["properties"]

    asyncio.run(run())


def test_bad_batch_feedback_does_not_repeat_accumulated_record_ids():
    # 同工作下24条失败共用额度，但每条回执只定位自身，不能重复前面所有ID。
    state = {}
    issues = [ToolIssue("invalid_kind", f"records.{i}.kind", "选择合法kind", ("w1",),
                        (f"record-{i}",)) for i in range(24)]
    first = record_issues(state, "submit_analysis", issues, "batch", 6)
    assert [row["record_ids"] for row in first] == [[f"record-{i}"] for i in range(24)]
    assert sum(len(row.get("pending_record_ids", [])) for row in first) <= 24
    restored = json.loads(json.dumps(state))
    assert record_issues(restored, "submit_analysis", issues, "batch", 6) == first
    entry, = restored["tool_issue_ledger"]["issues"].values()
    assert entry["attempts"] == 1 and len(entry["pending_record_ids"]) == 24
    resolve_issues(restored, "submit_analysis", ["w1"], paths=("records.*",),
                   record_ids=("record-0",))
    assert entry["active"] and len(entry["pending_record_ids"]) == 23


@pytest.mark.parametrize("field,value", [("topic", []), ("topic", {}), ("issue_id", ["bad"])])
def test_malformed_review_issue_returns_protocol_feedback(field, value):
    from test_analysis_check_receipts import packet
    from test_analysis_combined_review import approve

    from tender.application.analysis.review import validate
    from tender.domain.shared.errors import InvalidModelOutput

    payload = packet()
    result = approve(payload)
    result["issues"] = [{"topic": "a", "kind": "omission", "action": "read",
        "target": "替换部件", "detail": "补读部件条款", "record_ids": [],
        "evidence_ids": ["b1"], field: value}]
    with pytest.raises(InvalidModelOutput):
        validate(result, payload)


def test_review_issue_ids_resolve_to_known_business_reasons():
    from test_analysis_check_receipts import packet
    from test_analysis_combined_review import approve

    from tender.application.analysis.review import validate

    payload = packet()
    payload["repair_issues"] = [
        {"issue_id": "a" * 64, "detail": "未保留替换部件重新起算条件"},
        {"issue_id": "b" * 64, "detail": "付款期限与原文不符"},
    ]
    result = approve(payload)
    result["reviews"]["a"].update(supported=False, issues=["a" * 64 + "；" + "b" * 64 + "；"])
    validate(result, payload)
    assert result["reviews"]["a"]["issues"] == ["未保留替换部件重新起算条件；付款期限与原文不符；"]


def test_unknown_issue_id_alone_is_not_a_business_reason():
    from test_analysis_check_receipts import packet
    from test_analysis_combined_review import approve

    from tender.application.analysis.review import validate
    from tender.domain.shared.errors import InvalidModelOutput

    payload = packet()
    result = approve(payload)
    result["reviews"]["a"].update(supported=False, issues=["f" * 64])
    with pytest.raises(InvalidModelOutput, match="具体原因"):
        validate(result, payload)


def test_compact_evidence_and_summary_restore_keep_source_chapter():
    from langchain_core.messages import ToolMessage

    from tender.application.analysis.context import evidence_message, evidence_version

    async def run():
        row = block() | {"chapter": "附件一：合同协议书 / 服务期限", "content": "服务期限为 天。"}
        research = session([row])
        research.compact_results = True
        result = await research.search("服务期限", "project")
        item, = result["blocks"]
        assert item["source_id"] == 1 and item["chapter"] == row["chapter"]
        message = ToolMessage(content=json.dumps({"already_read": [row["block_id"]]}),
                              tool_call_id="restore", name="search_document")
        restored = evidence_message(message, [], research.seen)
        item, = json.loads(restored.content)["blocks"]
        assert item["source_id"] == 1 and item["chapter"] == row["chapter"]
        assert evidence_version(row) != evidence_version(row | {"chapter": "专用合同条款"})

    asyncio.run(run())


def test_work_context_and_independent_review_keep_chapter_boundaries():
    from test_analysis_review_v2 import flow_fixture

    from tender.application.analysis.context import work_units
    from tender.application.analysis.protocol import ResearchLedger
    from tender.application.analysis.review import batches

    async def run():
        flow = await flow_fixture()
        flow.research.seen["s1r1c0"]["chapter"] = "第一节通用合同条款 / 9.2预付款"
        works = ResearchLedger(flow).works()
        units = work_units(flow, works, [w["id"] for w in works])
        evidence = [unit for unit in units if unit["kind"] == "evidence"]
        assert evidence and all(u["chapter"].startswith("第一节通用合同条款") for u in evidence)
        packets, _ = batches(flow, "a", [])
        spans = [span for p in packets for span in p["evidence"] + p["context_evidence"]]
        assert spans and all(span["chapter"].startswith("第一节通用合同条款") for span in spans)

    asyncio.run(run())


@pytest.mark.parametrize("long_record", [False, True])
def test_restored_work_context_exposes_update_id_with_complete_record(long_record):
    from test_analysis_review_v2 import flow_fixture

    from tender.application.analysis.context import work_units
    from tender.application.analysis.protocol import (
        ResearchLedger,
        SubmissionRecord,
        submission_records,
    )
    from tender.application.analysis.topic_flow import TopicFlow

    async def run():
        flow = await flow_fixture()
        item = flow.state["staged_items"][0]
        if long_record:
            item["business"]["content"] = {"字段": "质保", "内容": "完整条件；" * 600}
        # 恢复后应能仅凭按需读取的正文修改原事项，不能再拼接另一份索引或误用内部key。
        restored = json.loads(json.dumps(flow.state))
        flow = TopicFlow(restored, flow.research)
        works = ResearchLedger(flow).works()
        units = work_units(flow, works, [w["id"] for w in works])
        records = [u for u in units if u.get("record_id") == item["id"]]
        assert records
        if long_record:
            assert all(u["kind"] == "note_fragment" for u in records)
            record = json.loads("".join(
                u["text"] for u in sorted(records, key=lambda u: u["start"])))
        else:
            record, = records
        restored["output_schema"] = fixture.schema()
        changed = SubmissionRecord.model_validate(fixture.raw(
            id=record["record_id"], work_ids=[w["id"] for w in works],
            content={"字段": "质保", "内容": "五年"},
        ))
        updated, rejected = submission_records([changed], restored, works, "restored-update")
        assert not rejected
        assert updated[0][1].key == item["business"]["key"]

    asyncio.run(run())


@pytest.mark.parametrize("variation", ["identical", "content", "evidence", "scope"])
def test_repeated_new_record_requires_existing_id_only_when_business_and_evidence_match(variation):
    from test_analysis_review_v2 import flow_fixture

    from tender.application.analysis.protocol import (
        ResearchLedger,
        SubmissionRecord,
        submission_records,
    )

    async def run():
        flow = await flow_fixture()
        state = json.loads(json.dumps(flow.state))
        item = state["staged_items"][0]
        business = item["business"]
        state["output_schema"] = fixture.schema()
        works = ResearchLedger(flow).works()
        raw = fixture.raw(kind=business["kind"], content=business["content"],
                          scope=business["scope"], work_ids=[w["id"] for w in works])
        if variation == "content":
            raw["content"] = dict(raw["content"]) | {"内容": "五年"}
        elif variation == "evidence":
            raw["block_ids"] = ["s1r1c1"]
        elif variation == "scope":
            raw["scope"] = {"kind": "lots", "lot_refs": ["标段甲"]}
            works = [dict(w) | {"scope": {"kind": "unknown", "lot_refs": []}} for w in works]
        prepared, rejected = submission_records(
            [SubmissionRecord.model_validate(raw)], state, works, "repeat-without-id")
        if variation != "identical":
            assert not rejected and len(prepared) == 1
            return
        assert not prepared
        assert rejected[0]["id"] == item["id"]
        # 明确重复只要求模型使用原id；不自动合并或改写已保存正文。
        assert "id" in rejected[0]["error"]
        assert state["staged_items"] == flow.state["staged_items"]
        raw["id"] = rejected[0]["id"]
        prepared, rejected = submission_records(
            [SubmissionRecord.model_validate(raw)], state, works, "repeat-corrected-id")
        assert not rejected and prepared[0][1].key == business["key"]

    asyncio.run(run())


def test_duplicate_new_receipt_updates_original_without_losing_other_valid_item():
    from tender.application.analysis.data import module_data, record_identity

    async def run():
        state = {}
        original_id = record_identity(state, "r-" + record_identity(
            state, "submission:call_draft:0"))
        other = fixture.raw(content={"字段": "替换部件质保", "内容": "五年"})
        graph, files, state, *_ = fixture.build([
            fixture.batch(["质保"]),
            call("submit_analysis", {"records": [fixture.raw()]}, "draft"),
            call("submit_analysis", {"records": [fixture.raw(), other]}, "repeat"),
            call("submit_analysis", {"records": [fixture.raw(id=original_id)]}, "correct"),
            call("complete_research", {"research_summary": "已核对两项独立要求"}, "done"),
        ], state=state, research=session([block() | {
            "content": "主设备质保三年，替换部件质保五年。"}]))
        await invoke_module(graph, files, thread_id="duplicate-correction", task="按原id纠正重复")
        result = json.loads(state["tool_results"]["call_repeat"]["data"]["content"])
        assert [r["status"] for r in result["records"]] == ["rejected", "accepted"]
        assert result["records"][0]["id"] == original_id
        assert len(state["staged_items"]) == 2
        assert len(module_data(state)["records"]) == 2

    asyncio.run(run())


@pytest.mark.parametrize("status", ["inapplicable", "unresolved"])
def test_applicability_denial_overrides_supported_and_covered_without_retry(status):
    from test_analysis_check_receipts import packet
    from test_analysis_combined_review import approve

    from tender.application.analysis.review import validate

    payload = packet() | {"require_applicability": True}
    result = approve(payload)
    result["reviews"]["a"]["applicability"] = {
        "status": status, "reason": "当前项目已选择网上开标，现场材料条款未核清适用性",
        "block_ids": ["b1"],
    }
    validate(result, payload)
    assert not result["reviews"]["a"]["supported"]
    assert result["reviews"]["a"]["issues"]
    assert all(r["status"] == "needs_action" for r in result["check_results"].values())
    before = json.loads(json.dumps(result))
    validate(result, payload)
    assert result == before


@pytest.mark.parametrize("failure", ["missing", "foreign_evidence", "empty_reason"])
def test_new_review_requires_authorized_applicability_proof(failure):
    from test_analysis_check_receipts import packet
    from test_analysis_combined_review import approve

    from tender.application.analysis.review import validate
    from tender.domain.shared.errors import InvalidModelOutput

    payload = packet() | {"require_applicability": True}
    result = approve(payload)
    if failure == "missing":
        result["reviews"]["a"].pop("applicability")
    elif failure == "foreign_evidence":
        result["reviews"]["a"]["applicability"]["block_ids"] = ["not-delivered"]
    else:
        result["reviews"]["a"]["applicability"]["reason"] = ""
    with pytest.raises(InvalidModelOutput, match="applicability"):
        validate(result, payload)


def test_applicability_control_evidence_is_kept_in_final_citations():
    from test_analysis_check_receipts import packet
    from test_analysis_combined_review import approve

    from tender.application.analysis.review import validate

    payload = packet() | {"require_applicability": True, "record_evidence_ids": {"a": ["b1"]}}
    payload["context_evidence"].append({"id": "control", "text": "本项目采用电子开标"})
    result = approve(payload)
    result["reviews"]["a"]["applicability"]["block_ids"] = ["control"]
    validate(result, payload)
    assert result["reviews"]["a"]["block_ids"] == ["b1", "control"]
    before = json.loads(json.dumps(result))
    validate(result, payload)
    assert result == before


@pytest.mark.parametrize("field,value", [("supported", "yes"), ("block_ids", ["b1", "b1"])])
def test_applicability_normalization_cannot_hide_malformed_review(field, value):
    from test_analysis_check_receipts import packet
    from test_analysis_combined_review import approve

    from tender.application.analysis.review import validate
    from tender.domain.shared.errors import InvalidModelOutput

    payload = packet() | {"require_applicability": True}
    result = approve(payload)
    result["reviews"]["a"][field] = value
    result["reviews"]["a"]["applicability"]["status"] = "unresolved"
    with pytest.raises(InvalidModelOutput):
        validate(result, payload)


def test_applicability_denial_blocks_publication_after_full_audit():
    from test_analysis_combined_review import approve
    from test_analysis_review_v2 import flow_fixture

    from tender.application.analysis.review import audit_combined
    from tender.application.analysis.state import published_items

    async def run():
        flow = await flow_fixture(repairs=0)

        async def review(payload):
            result = approve(payload)
            for verdict in result["reviews"].values():
                verdict["applicability"].update(
                    status="inapplicable", reason="该要求是未选用的现场开标分支")
            return result

        async def save(_):
            pass

        assert await audit_combined(flow, review, save)
        assert not published_items(flow.state, final=True)
        assert flow.data["audit"]["remaining"]

    asyncio.run(run())


@pytest.mark.parametrize("query,text", [
    ("付款 比例 金额 前提 发票", "付款比例为合同价的30%。"),
    ("合同 工期 交付 服务期限 延期", "服务期限为两年。"),
    ("验收 主体 步骤 标准", "由委托人组织验收。"),
    ("质保 期限 响应 除外 缺陷责任", "缺陷责任期为24个月。"),
])
def test_parallel_keywords_recall_real_clause_at_original_semantic_threshold(query, text):
    # 四个查询来自商务模块首次全空召回；关键词不应要求在同一块同时出现。
    rows = [{"content": text, "embedding": [-1.0, 0.0]},
            {"content": "完全无关的正文", "embedding": [0.7, 0.714]}]
    result = rank_chunks(rows, query, [1.0, 0.0], min_similarity=0.8)
    assert [row["content"] for row in result] == [text]


def test_first_rule_reads_after_empty_search_leave_a_real_retrieval_opportunity(monkeypatch):
    async def run():
        research = session([block()], limits=AgentLimits(max_no_progress_rounds=2))
        recall = research.retrieve

        async def retrieve(sources, query):
            return ([], {"mode": "keyword"}) if query == "空查询" else await recall(sources, query)

        research.retrieve = retrieve
        original = fixture.snapshot
        monkeypatch.setattr(fixture, "snapshot", lambda keys: original(keys) | {
            fixture.KEY + "/references/example.md": "付款比例应保留明确的分期条件。",
            fixture.KEY + "/references/other.md": "服务期限应保留起算条件。",
        })
        graph, files, state, *_ = fixture.build([
            fixture.batch(["空查询"]),
            call("read_file", {"file_path": "/skills/project-basic-info-parsing/"
                               "references/example.md"}, "rule"),
            call("read_file", {"file_path": "/skills/project-basic-info-parsing/"
                               "references/other.md"}, "other-rule"),
            fixture.batch(["质保"], name="actual"), *fixture.finish(),
        ], research)
        await invoke_module(graph, files, thread_id="rules-after-empty", task="读取必要细则后取证")
        assert state["draft"]["fields"]
        assert len(state["read_skill_paths"]) == 2

    asyncio.run(run())


@pytest.mark.parametrize("project_id,expected", [(10, "completed"), (20, "failed")])
def test_executor_keeps_reviewed_fact_with_missing_note_and_checks_project_access(
    monkeypatch, project_id, expected,
):
    async def run():
        runtime = Mock()
        runtime.claim.return_value = True
        runtime.run = {"state": {}, "limits": asdict(AgentLimits()), "thread_id": "final",
                       "deadline_at": datetime.now(UTC) + timedelta(seconds=60),
                       "model_calls": 0, "tool_calls": 0}
        monkeypatch.setattr(execution, "AgentRuntime", lambda *_: runtime)

        async def invoke(*_args, state, **_kwargs):
            state["topic_flow"] = {"protocol": "research-v3"}
            state["draft"] = {"fields": [{"field": "开标要求", "business": {"kind": "fact"},
                "values": [{"value": "网上开标；文件未约定具体时间", "citations": [
                    {"project_id": project_id, "source_id": 1}]}]}]}

        @asynccontextmanager
        async def saver():
            yield None

        monkeypatch.setattr(execution, "build_module_agent", lambda **_: (object(), {}))
        monkeypatch.setattr(execution, "invoke_module", invoke)
        executor = execution.AnalysisExecutor(
            Mock(), model_factory=Mock(return_value=AsyncMock()), embedding_gateway=Mock(),
            rerank_gateway=Mock(), checkpoints=saver,
        )
        await executor.execute_module({"id": 1, "project_id": 10, "source_snapshot": [],
            "reference_snapshot": [],
            "skill_snapshot": {"__analysis_flow_version__": "skill-agent-v1"},
            "category": "goods", "topics": [], "lot_settings": []},
            {"id": 1, "module_key": "opening_requirement_parsing", "attempt": 1}, [])
        if expected == "completed":
            runtime.abandon.assert_not_called()
            assert runtime.finish.call_args.args[0] == expected
        else:
            runtime.finish.assert_not_called()
            assert runtime.abandon.call_args.args[0] == expected

    asyncio.run(run())
