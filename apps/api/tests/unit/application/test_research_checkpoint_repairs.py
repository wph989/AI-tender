"""检索门禁应提供可执行的修复信息，且不能把正常主题检索判为无进展。"""

import asyncio
import json

import pytest
from synthesis_fixtures import COMMON, research_done, submission, summary_record
from test_analysis_research import block, session
from test_analysis_synthesis import build, execute, topic
from test_deep_analysis import KEY, SKILL, ScriptedRouter, call

from tender.application.analysis_data import (
    BusinessRecord,
    assemble_dataset,
    prepare_records,
    resolve_scope,
)
from tender.application.analysis_output import ReferenceTrace, ResearchTopic, research_checkpoint
from tender.application.deep_analysis import invoke_module

TOPICS = [{"key": "warranty", "title": "质保期限"}]
SNAPSHOT = SKILL | {KEY + "/references/coverage.json": json.dumps(TOPICS, ensure_ascii=False)}
COVERAGE = [{
    "topic": "warranty", "scope": COMMON, "status": "extracted",
    "record_keys": ["warranty"], "detail": "已综合质保要求",
}]


def test_checkpoint_reports_all_errors_and_actual_queries_together():
    async def run():
        research = session([block()])
        await research.search("质保", "project")
        await research.search("参考词", "reference")
        research.sources.append(block(3, 10))
        with pytest.raises(ValueError) as caught:
            research_checkpoint(
                [ResearchTopic(**topic(queries=["虚构检索词"], evidence_ids=["fake"]))],
                [ReferenceTrace(topic="warranty", from_block_id="fake-origin", target="附件",
                                status="resolved", evidence_ids=["fake-target"], detail="已核对")],
                "已检索", expected_topics=TOPICS + [{"key": "price", "title": "报价"}],
                research=research,
            )
        details = caught.value.details
        assert {i["code"] for i in details["issues"]} == {
            "invalid_reference_origin", "invalid_reference_evidence", "invalid_evidence",
        }
        assert [q["query"] for q in details["project_searches"]] == ["质保"]
        assert details["expected_topics"][-1]["key"] == "price"

    asyncio.run(run())


def test_query_description_need_not_match_and_actual_searches_come_from_server():
    async def run():
        research = session([block()])
        await research.documents()
        await research.search("质保 要求", "project")
        result = research_checkpoint(
            [ResearchTopic(**topic(topic=" 质保期限 ", queries=["核对售后保障和质保期"]))],
            [], "已检索", expected_topics=TOPICS, research=research,
        )
        assert result["topics"][0]["topic"] == "warranty"
        assert result["topics"][0]["search_intents"] == ["核对售后保障和质保期"]
        assert "queries" not in result["topics"][0]
        assert result["project_searches"][0]["query"] == "质保 要求"

    asyncio.run(run())


def test_repeated_topic_descriptions_merge_and_missing_topics_become_gaps():
    async def run():
        research = session([block()])
        await research.documents()
        await research.search("质保", "project")
        result = research_checkpoint(
            [ResearchTopic(**topic()), ResearchTopic(**topic(topic="质保期限", queries=[]))],
            [], "已检索", expected_topics=TOPICS + [{"key": "price"}], research=research,
        )
        assert [t["topic"] for t in result["topics"]] == ["warranty", "price"]
        assert result["topics"][1]["status"] == "unresolved"
        assert result["topics"][0]["evidence_ids"] == ["s1r1c0"]

    asyncio.run(run())


@pytest.mark.parametrize("empty", [True, False])
def test_five_distinct_topic_searches_can_finish_without_new_evidence(empty):
    topics = [{"key": f"topic-{i}", "title": f"主题{i}"} for i in range(5)]
    checkpoints = [topic(
        "searched_not_found" if empty else "covered", topic=t["key"],
        queries=[t["title"]],
    ) for t in topics]
    coverage = [{
        "topic": t["key"], "scope": COMMON,
        "status": "pending" if empty else "extracted",
        "record_keys": [] if empty else ["warranty"], "detail": "已核对本主题",
    } for t in topics]
    state, _, router = asyncio.run(execute(
        [
            call("list_documents", {}, "documents"),
            *[call("search_document", {"query": t["title"]}, i) for i, t in enumerate(topics)],
            call("complete_research", research_done(checkpoints), "research"),
            call("submit_analysis", submission(
                [] if empty else [summary_record()], coverage=coverage,
            ), "final"),
        ],
        research=session([] if empty else [block()]),
        snapshot=SKILL | {KEY + "/references/coverage.json": json.dumps(topics)},
    ))
    assert not state.get("finish_only")
    assert len([e for e in state["research"]["events"] if e["action"] == "search_result"]) == 5
    assert len(state["draft"]["business_data"]["gaps"]) == (5 if empty else 0)
    assert "主题4" in str(router.requests[-1][0])


def test_different_checkpoint_errors_do_not_share_three_failure_limit():
    state, _, _ = asyncio.run(execute(
        [
            call("list_documents", {}, "documents"),
            call("complete_research", research_done([topic("unresolved")]), "no-search"),
            call("search_document", {"query": "质保"}, "search"),
            call("complete_research", research_done([topic(evidence_ids=["fake"])]), "evidence"),
            call("complete_research", research_done([topic()], [{
                "topic": "质保期限", "from_block_id": "fake", "target": "附件",
                "status": "missing", "detail": "等待附件",
            }]), "reference"),
            call("complete_research", research_done([topic()], [{
                "topic": "质保期限", "from_block_id": "s1r1c0", "target": "附件",
                "status": "resolved", "evidence_ids": ["fake"], "detail": "核对目标",
            }]), "target"),
            call("complete_research", research_done([topic()]), "correct"),
            call("submit_analysis", submission([summary_record()], coverage=COVERAGE), "final"),
        ], snapshot=SNAPSHOT,
    ))
    assert len(state["draft"]["fields"]) == 1
    for call_id in ("no-search", "evidence", "reference", "target"):
        feedback = json.loads(state["tool_results"]["call_" + call_id]["data"]["content"])
        assert feedback["remaining_attempts"] == 2
        assert [q["query"] for q in feedback["details"]["project_searches"]] == (
            [] if call_id == "no-search" else ["质保"]
        )


def test_changing_same_fabricated_evidence_still_exhausts_persisted_failure_limit():
    async def run():
        router = ScriptedRouter([
            call("list_documents", {}, "documents"),
            call("search_document", {"query": "质保"}, "search"),
            *[call("complete_research", research_done([topic(evidence_ids=[f"fake-{i}"])]), i)
              for i in range(3)],
        ])
        state = {}
        graph, files = build(router, session([block()]), state, snapshot=SNAPSHOT)
        with pytest.raises(ValueError, match="工具连续失败"):
            await invoke_module(graph, files, thread_id="same-research-error", task="分析")
        feedback = json.loads(state["tool_results"]["call_2"]["data"]["content"])
        assert feedback["remaining_attempts"] == 0
        assert "已耗尽" in feedback["next_action"]
        assert list(state["research_failure_patterns"].values()) == [3]
        assert "research_completed" not in state

    asyncio.run(run())


def test_unknown_topic_is_retained_as_description_and_cannot_claim_expected_coverage():
    async def run():
        research = session([block()])
        await research.documents()
        await research.search("质保", "project")
        result = research_checkpoint(
            [ResearchTopic(**topic(topic="售后相关事项", queries=[]))],
            [ReferenceTrace(topic="售后相关事项", from_block_id="s1r1c0", target="附件",
                            status="missing", detail="尚未取得附件")],
            "核对售后条款", expected_topics=TOPICS, research=research,
        )
        assert result["topics"][0]["status"] == "unresolved"
        assert result["additional_topics"][0]["topic"] == "售后相关事项"
        assert result["references"][0]["topic"] == "售后相关事项"

    asyncio.run(run())


def test_omitted_topics_can_finish_with_visible_gaps_and_no_invented_results():
    state, _, _ = asyncio.run(execute([
        call("list_documents", {}, "documents"),
        call("search_document", {"query": "售后条款"}, "search"),
        call("complete_research", research_done(), "research"),
        call("submit_analysis", submission(), "final"),
    ], snapshot=SNAPSHOT))
    assert not state["draft"]["fields"]
    data = state["draft"]["business_data"]
    assert data["gaps"][0]["topic"] == "warranty"
    assert data["coverage"][0]["status"] == "pending"


def test_topic_descriptions_cannot_replace_a_real_project_search():
    async def run():
        research = session([block()])
        await research.documents()
        await research.search("质保", "reference")
        with pytest.raises(ValueError) as caught:
            research_checkpoint(
                [ResearchTopic(**topic("unresolved"))], [], "已搜索",
                expected_topics=TOPICS, research=research,
            )
        assert "project_not_searched" in {i["code"] for i in caught.value.details["issues"]}

    asyncio.run(run())


def test_document_tool_sequence_and_unsearched_supplement_do_not_block_valid_results():
    research = session([block()])
    research.sources.append(block(3, 10))
    state, _, _ = asyncio.run(execute([
        call("search_document", {"query": "质保", "source_id": 1}, "search"),
        call("complete_research", {"topics": [topic(queries=[])]}, "research"),
        call("submit_analysis", {
            "records": [summary_record()], "coverage": [{**COVERAGE[0], "topic": "质保期限"}],
            "final": True,
        }, "final"),
    ], research=research, snapshot=SNAPSHOT))
    assert state["draft"]["fields"]
    data = state["draft"]["business_data"]
    assert data["coverage"][0]["topic"] == "warranty"
    assert any(g["code"] == "missing_source" and "3.pdf" in g["detail"] for g in data["gaps"])


@pytest.mark.parametrize("empty", [True, False])
def test_search_without_new_evidence_keeps_verified_results_and_updates_ledger(empty):
    async def run():
        research = session([block()])

        async def retrieve(sources, query):
            return ([] if empty and query == "补充核对" else [block()]), {}

        research.retrieve = retrieve
        state, _, _ = await execute([
            call("list_documents", {}, "documents"),
            call("search_document", {"query": "质保"}, "search"),
            call("complete_research", research_done([topic()]), "research"),
            call("submit_analysis", submission([summary_record()], final=False), "saved"),
            call("search_document", {"query": "补充核对"}, "extra"),
            call("submit_analysis", {"records": [], "final": True}, "final"),
        ], research=research, snapshot=SNAPSHOT)
        assert len(state["draft"]["fields"]) == 1
        assert [e["query"] for e in state["research_completed"]["project_searches"]] == [
            "质保", "补充核对",
        ]

    asyncio.run(run())


@pytest.mark.parametrize("content", [
    {"关键要求": "质保三年"}, {"要求摘要": "质保三年"}, {"关键要求": ["质保三年"]},
])
def test_single_technical_requirement_is_normalized_then_reviewed_and_locatable(content):
    async def run():
        reviewed = []

        async def review(items):
            for item in items:
                reviewed.append(item["business"]["content"])
                item["verification"] = "supported"

        key = "tech_requirement_parsing"
        state, _, _ = await execute([
            call("search_document", {"query": "质保"}, "search"),
            call("complete_research", {}, "research"),
            call("submit_analysis", {"records": [summary_record(
                group="技术方案要求", content=content,
            )], "final": True}, "final"),
        ], snapshot={key + "/SKILL.md": "综合技术要求"}, key=key, review=review)
        assert reviewed == [{"关键要求": ["质保三年"], "要求摘要": "质保三年"}]
        assert state["draft"]["fields"][0]["values"][0]["citations"][0]["block_id"] == "s1r1c0"

    asyncio.run(run())


def test_partial_columns_are_allowed_when_analysis_body_has_evidence():
    state, _, _ = asyncio.run(execute([
        call("search_document", {"query": "质保"}, "search"),
        call("complete_research", {}, "research"),
        call("submit_analysis", {"records": [summary_record(content={"内容": "质保三年"})],
                                 "final": True}, "final"),
    ]))
    assert state["draft"]["fields"][0]["output"]["content"] == {"内容": "质保三年"}


def test_nested_format_groups_are_saved_one_node_at_a_time():
    key = "bid_format_outline_parsing"
    records = [summary_record(
        key=node, title=node, kind="format_node", group="", node_type="group",
        parent_key=parent, content={"编制要求": ["质保三年"]},
    ) for node, parent in (("child", "parent"), ("parent", None))]
    state, _, _ = asyncio.run(execute([
        call("search_document", {"query": "质保"}, "search"),
        call("complete_research", {}, "research"),
        call("submit_analysis", {"records": [records[1]], "final": False}, "parent"),
        call("submit_analysis", {"records": [records[0]], "final": False}, "child"),
        call("submit_analysis", {"records": [], "final": True}, "final"),
    ], snapshot={key + "/SKILL.md": "核对格式树"}, key=key))
    child = next(r for r in state["draft"]["business_data"]["records"] if r["key"] == "child")
    assert child["parent_key"] == "parent" and child["parent_path"] == ["parent"]


def test_named_lot_without_original_code_can_be_analyzed_and_resolved_by_name():
    raw = BusinessRecord(
        key="maintenance", title="运维服务标段", text="运维服务标段",
        kind="lot", scope=COMMON, citations=[{"block_id": "s1r1c0", "quote": "运维服务标段"}],
    )
    prepared = prepare_records([raw], {}, {"s1r1c0": block() | {"content": "运维服务标段"}}, KEY)
    assert prepared[0]["business"]["code"] is None
    resolved = resolve_scope({"kind": "lots", "lot_refs": ["运维服务标段"]}, [{
        "lot_id": 1, "code": None, "title": "运维服务标段", "aliases": [],
    }])
    assert resolved["lot_ids"] == [1] and resolved["kind"] == "lots"


def test_missing_process_proofs_and_long_summary_do_not_block_cited_analysis():
    state, _, _ = asyncio.run(execute([
        call("search_document", {"query": "质保"}, "search"),
        call("complete_research", {"topics": [{
            "topic": "warranty", "status": "covered",
        }], "references": [{
            "topic": "warranty", "from_block_id": "s1r1c0", "target": "附件",
            "status": "resolved",
        }], "research_summary": "检索说明" * 2000}, "research"),
        call("submit_analysis", {"records": [summary_record()], "final": True,
                                 "research_summary": "过程总结" * 2000}, "final"),
    ], snapshot=SNAPSHOT))
    assert len(state["draft"]["fields"]) == 1
    assert len(state["draft"]["research_summary"]) == 4000
    assert len(state["research_completed"]["research_summary"]) == 4000
    assert {g["code"] for g in state["draft"]["business_data"]["gaps"]} == {
        "search_exhausted", "unresolved_reference",
    }


@pytest.mark.parametrize("order", [("old", "new"), ("new", "old")])
def test_revision_is_published_after_individually_saved_endpoints(order):
    records = {
        "old": summary_record(key="old", text="质保三年", title="原质保要求"),
        "new": summary_record(key="new", text="质保四年", quote="质保四年", title="新质保要求"),
        "revision": summary_record(
            key="revision",
            text="四年替代三年",
            quote="四年替代三年",
            title="质保修订关系",
            kind="relation",
            predicate="supersedes",
            subject_key="new",
            object_key="old",
        ),
    }
    state, _, _ = asyncio.run(
        execute(
            [
                call("search_document", {"query": "质保"}, "search"),
                call("complete_research", research_done([topic()]), "research"),
                *[call("submit_analysis", {"records": [records[key]], "final": False}, key)
                  for key in order],
                call(
                    "submit_analysis",
                    {
                        "records": [records["revision"]],
                        "final": True,
                        "coverage": [COVERAGE[0] | {"record_keys": ["old", "new"]}],
                    },
                    "final",
                ),
            ],
            research=session([block() | {"content": "质保三年；质保四年；四年替代三年"}]),
            snapshot=SNAPSHOT,
        )
    )
    data = assemble_dataset(
        [
            {
                "module_key": KEY,
                "title": "质保要求",
                "status": "completed",
                "business_data": state["draft"]["business_data"],
            }
        ],
        [],
    )
    # 验证发布后的关系和替代状态，避免只校验工具接受了请求却漏掉编制依据里的旧要求。
    assert not any(g["code"] == "unresolved_relation" for g in data["gaps"])
    assert len(data["relations"]) == 1
    by_key = {record["key"]: record for record in data["requirements"]}
    relation = data["relations"][0]
    assert (relation["subject_id"], relation["object_id"]) == (
        by_key["new"]["id"],
        by_key["old"]["id"],
    )
    assert by_key["old"]["superseded_in"] == [relation["scope"]]


@pytest.mark.parametrize("gap_mode", ["omitted", "null", "empty", "remaining"])
def test_final_gap_omission_preserves_staged_gaps_and_explicit_list_replaces_them(gap_mode):
    gaps = [
        {
            "key": key,
            "topic": "warranty",
            "scope": COMMON,
            "code": "unknown_condition",
            "detail": detail,
        }
        for key, detail in (
            ("start-date", "质保起算日期待核对"),
            ("exception", "质保例外条件待核对"),
        )
    ]
    final = {"records": [], "final": True}
    if gap_mode != "omitted":
        final["gaps"] = {
            "null": None,
            "empty": [],
            "remaining": gaps[1:],
        }[gap_mode]
    state, saved, _ = asyncio.run(
        execute(
            [
                call("search_document", {"query": "质保"}, "search"),
                call("complete_research", research_done([topic()]), "research"),
                call(
                    "submit_analysis",
                    {
                        "records": [summary_record()],
                        "coverage": COVERAGE,
                        "gaps": gaps,
                        "final": False,
                    },
                    "partial",
                ),
                call("submit_analysis", final, "final"),
            ],
            snapshot=SNAPSHOT,
        )
    )
    assert any(
        {g["key"] for g in s.get("business_gaps", [])}
        == {
            "start-date",
            "exception",
        }
        for s in saved
    )
    expected = (
        {"start-date", "exception"}
        if gap_mode in {"omitted", "null"}
        else ({"exception"} if gap_mode == "remaining" else set())
    )
    assert {g["key"] for g in state["draft"]["business_data"]["gaps"]} == expected
    assert len(state["draft"]["fields"]) == 1
