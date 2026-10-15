"""真实 Agent 图的检索门禁、完整事项汇总、原文溯源和恢复回归。"""

import asyncio
import copy
import json

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import (
    COMMON,
    accept,
    noop,
    research_calls,
    research_done,
    submission,
    summary_record,
)
from test_analysis_research import block, session
from test_deep_analysis import KEY, SKILL, ScriptedRouter, call

from tender.application.analysis_output import (
    ReferenceTrace,
    ResearchTopic,
    output_schema,
    record_output,
    research_checkpoint,
)
from tender.application.analysis_research import AgentLimits
from tender.application.analysis_skills import MODULES, skill_snapshot
from tender.application.deep_analysis import RoutedAgentModel, build_module_agent, invoke_module
from tender.domain.errors import InvalidModelOutput, ModelOutputTruncated, ModelUnavailable


def build(
    router,
    research,
    state,
    save=noop,
    *,
    snapshot=SKILL,
    review=accept,
    key=KEY,
    checkpointer=None,
    reserve=noop,
):
    return build_module_agent(
        key=key,
        model=RoutedAgentModel(router=router),
        research=research,
        state=state,
        snapshot=snapshot,
        checkpointer=checkpointer or InMemorySaver(),
        reserve_tool=reserve,
        save=save,
        review_support=review,
    )


async def execute(script, *, research=None, snapshot=SKILL, review=accept, key=KEY):
    state, saved, router = {}, [], ScriptedRouter(script)

    async def save(value):
        saved.append(copy.deepcopy(value))

    graph, files = build(
        router,
        research or session([block()]),
        state,
        save,
        snapshot=snapshot,
        review=review,
        key=key,
    )
    await invoke_module(graph, files, thread_id="synthesis", task="分析项目要求")
    assert not router.calls
    return state, saved, router


@pytest.mark.parametrize("key", MODULES)
def test_every_frozen_module_has_usable_synthesis_format(key):
    snapshot = skill_snapshot()
    schema = output_schema(snapshot, key)
    assert schema["sections"]
    for section in schema["sections"]:
        assert section["columns"] and "序号" not in section["columns"]
    rules = snapshot[key + "/SKILL.md"]
    assert "complete_research" in rules and "content" in rules
    assert "field/group/sort_order/values/note" not in rules
    assert "每批最多3条" not in rules


def test_tool_schema_requires_content_and_has_no_legacy_submission_fields():
    async def run():
        _, _, router = await execute(
            [
                *research_calls(),
                call("submit_analysis", submission([summary_record()]), 1),
            ]
        )
        tools = {t["function"]["name"]: t["function"] for t in router.requests[0][1]}
        assert set(tools) == {
            "read_file",
            "list_documents",
            "search_document",
            "search_knowledge",
            "read_document",
            "complete_research",
            "submit_analysis",
        }
        params = tools["submit_analysis"]["parameters"]
        assert params["required"] == ["records"]
        assert "fields" not in params["properties"] and "outline_nodes" not in params["properties"]
        assert params["properties"]["records"]["maxItems"] == 24
        assert "content" in json.dumps(params)

    asyncio.run(run())


def test_early_submission_is_rejected_then_full_research_can_finish():
    state, saved, router = asyncio.run(
        execute(
            [
                call("submit_analysis", submission([summary_record()]), "early"),
                *research_calls(),
                call("submit_analysis", submission([summary_record()]), "final"),
            ]
        )
    )
    assert "complete_research" in state["tool_results"]["call_early"]["data"]["content"]
    assert all(not s.get("staged_items") for s in saved if not s.get("research_completed"))
    item = state["draft"]["fields"][0]
    assert item["output"]["content"] == {"字段": "质保期限", "内容": "质保期限为三年"}
    assert item["values"][0]["citations"][0]["quote"] == "质保三年"
    assert item["values"][0]["value"] != "质保三年"
    assert "综合输出" in str(router.requests[-1][0])


def topic(status="covered", **kwargs):
    return {
        "topic": "warranty",
        "status": status,
        "queries": ["质保"],
        "evidence_ids": ["s1r1c0"] if status == "covered" else [],
        "detail": "已核对质保主题",
        **kwargs,
    }


@pytest.mark.parametrize(
    "problem",
    [
        "invented_evidence",
        "reference_evidence",
        "reference_origin",
    ],
)
def test_research_checkpoint_requires_real_project_search_and_complete_scope(problem):
    async def run():
        research = session([block(), block(2, 20)])
        await research.documents()
        await research.search("质保", "project")
        await research.search("参考", "reference")
        values, refs = [topic()], []
        if problem in {"invented_evidence", "reference_evidence"}:
            values = [topic(evidence_ids=["fake" if problem == "invented_evidence" else "s2r1c0"])]
        elif problem == "reference_origin":
            refs = [
                ReferenceTrace(
                    topic="warranty",
                    from_block_id="s2r1c0",
                    target="附件",
                    status="missing",
                    detail="参考库不能伪装成本项目转引起点",
                )
            ]
        with pytest.raises(ValueError):
            research_checkpoint(
                [ResearchTopic(**t) for t in values],
                refs,
                "检索完成",
                expected_topics=[{"key": "warranty"}],
                research=research,
            )

    asyncio.run(run())


def test_empty_search_can_record_an_honest_gap_without_inventing_evidence():
    async def run():
        research = session([])
        await research.documents()
        await research.search("质保", "project")
        result = research_checkpoint(
            [ResearchTopic(**topic("searched_not_found"))],
            [],
            "本次未找到质保条款",
            expected_topics=[{"key": "warranty"}],
            research=research,
        )
        assert result["evidence_ids"] == []

    asyncio.run(run())


@pytest.mark.parametrize("status", ["missing", "cycle", "budget_exhausted"])
def test_final_submission_cannot_silently_clear_reference_gaps(status):
    checkpoint = topic("unresolved", evidence_ids=["s1r1c0"], detail="质保附件待核对")
    trace = {
        "topic": "warranty",
        "from_block_id": "s1r1c0",
        "target": "附件A",
        "status": status,
        "detail": "尚未取得实质条款",
        "evidence_ids": [],
    }
    coverage = [
        {
            "topic": "warranty",
            "scope": COMMON,
            "status": "pending",
            "record_keys": [],
            "detail": "附件A待核对",
        }
    ]
    state, _, _ = asyncio.run(
        execute(
            [
                *research_calls(topics=[checkpoint], references=[trace]),
                call("submit_analysis", submission(coverage=coverage, gaps=[]), 1),
            ],
            snapshot=SKILL | {KEY + "/references/coverage.json": '[{"key":"warranty"}]'},
        )
    )
    gaps = state["draft"]["business_data"]["gaps"]
    assert {g["code"] for g in gaps} == {"search_exhausted", "unresolved_reference"}
    assert any("附件A" in g["detail"] for g in gaps)


@pytest.mark.parametrize(
    "bad_coverage",
    [
        [],
        [
            {
                "topic": "warranty",
                "scope": COMMON,
                "status": "extracted",
                "record_keys": ["invented"],
                "detail": "错误记录身份",
            }
        ],
    ],
)
def test_incomplete_final_coverage_preserves_results_and_shows_pending_gap(bad_coverage):
    state, saved, router = asyncio.run(
        execute(
            [
                *research_calls(topics=[topic()]),
                call("submit_analysis", submission([summary_record()], coverage=bad_coverage), 1),
            ],
            snapshot=SKILL | {KEY + "/references/coverage.json": '[{"key":"warranty"}]'},
        )
    )
    assert state["draft"]["fields"][0]["output"]["content"] == summary_record()["content"]
    data = state["draft"]["business_data"]
    assert data["coverage"][0]["status"] == "pending"
    assert any(g["topic"] == "warranty" for g in data["gaps"])


@pytest.mark.parametrize(
    "content", [{}, {"字段": "质保"}, {"原文": "质保三年"}, {"字段": "质保", "内容": []}]
)
def test_summary_requires_meaningful_content_using_the_skill_columns(content):
    with pytest.raises(ValueError):
        record_output(summary_record(content=content), output_schema(SKILL, KEY))


def test_technical_summary_preserves_task_title_and_key_requirement_list():
    key = "tech_requirement_parsing"
    entry = summary_record(
        title="平台迁移",
        group="技术方案要求",
        content={"要求摘要": "制定迁移及服务保障方案", "关键要求": ["质保三年"]},
    )
    state, _, _ = asyncio.run(
        execute(
            [
                *research_calls(),
                call("submit_analysis", submission([entry]), 1),
            ],
            key=key,
            snapshot={key + "/SKILL.md": "分析技术要求"},
        )
    )
    output = state["draft"]["fields"][0]["output"]
    assert output["layout"] == "list" and output["content"]["关键要求"] == ["质保三年"]


@pytest.mark.parametrize("tool", ["search_document", "read_document"])
def test_new_evidence_invalidates_old_batches_and_requires_a_new_synthesis(tool):
    async def run():
        original = block()
        extra = block() | {
            "block_id": "next",
            "element_id": 2,
            "offset": 1,
            "content": "质保自验收合格之日起算",
        }
        research = session([original, extra])

        async def retrieve(sources, query):
            return ([original] if query == "质保" else [extra]), {}

        research.retrieve = retrieve
        new_args = (
            {"query": "起算点"}
            if tool == "search_document"
            else {"block_id": "s1r1c0", "before": 0, "after": 1}
        )
        combined = summary_record(
            text="自验收合格起质保三年",
            citations=[
                {"block_id": "s1r1c0", "quote": original["content"]},
                {"block_id": "next", "quote": extra["content"]},
            ],
        )
        state, saved, _ = await execute(
            [
                *research_calls(),
                call("submit_analysis", submission([summary_record()], final=False), 1),
                call(tool, new_args, "new"),
                call("submit_analysis", submission([combined]), "early"),
                call("complete_research", research_done(), "again"),
                call("submit_analysis", submission([combined]), "finish"),
            ],
            research=research,
        )
        after = next(s for s in saved if "call_new" in s.get("tool_results", {}))
        assert not after.get("staged_items") and "research_completed" not in after
        assert "complete_research" in state["tool_results"]["call_early"]["data"]["content"]
        records = state["draft"]["business_data"]["records"]
        assert len(records) == 1 and records[0]["content"] == combined["content"]
        assert len(records[0]["citations"]) == 2

    asyncio.run(run())


def test_same_key_correction_replaces_summary_and_unchanged_final_does_not_review_twice():
    async def run():
        reviewed = []

        async def review(items):
            reviewed.extend(copy.deepcopy(items))
            await accept(items)

        corrected = summary_record(text="设备质保期限：三年")
        state, _, _ = await execute(
            [
                *research_calls(),
                call("submit_analysis", submission([summary_record()], final=False), 1),
                call("submit_analysis", submission([corrected], final=False), 2),
                call("submit_analysis", submission([corrected]), 3),
            ],
            review=review,
        )
        assert len(reviewed) == 2 and reviewed[0]["id"] == reviewed[1]["id"]
        records = state["draft"]["business_data"]["records"]
        assert len(records) == 1 and records[0]["content"] == corrected["content"]

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["unsupported", "truncated"])
def test_failed_final_review_requires_explicit_completion_after_correction(failure):
    async def run():
        attempts = []

        async def review(items):
            attempts.append(copy.deepcopy(items))
            if len(attempts) == 1:
                if failure == "truncated":
                    raise ModelOutputTruncated("模拟校验输出截断")
                for item in items:
                    item.update(verification="unsupported", verification_issues=["原文仅为三年"])
            else:
                await accept(items)

        state, saved, _ = await execute(
            [
                *research_calls(),
                call("submit_analysis", submission([summary_record(text="质保五年")]), 1),
                call("read_document", {"block_id": "s1r1c0", "before": 0, "after": 0}, 2),
                call("submit_analysis", submission([summary_record()], final=False), 3),
                call("submit_analysis", submission(), 4),
            ],
            review=review,
        )
        before_final = [
            s
            for s in saved
            if "call_3" in s.get("tool_results", {}) and "call_4" not in s.get("tool_results", {})
        ]
        assert before_final and "draft" not in before_final[0]
        assert "pending_final" not in before_final[0]
        assert len(attempts) == 2
        assert state["draft"]["fields"][0]["output"]["content"] == summary_record()["content"]

    asyncio.run(run())


@pytest.mark.parametrize("error", [ModelUnavailable, InvalidModelOutput])
def test_review_failure_preserves_previously_verified_summaries(error):
    async def run():
        state, count = {}, 0

        async def review(items):
            nonlocal count
            count += 1
            if count > 1:
                raise error("模拟供应商不可用")
            await accept(items)

        router = ScriptedRouter(
            [
                *research_calls(),
                call("submit_analysis", submission([summary_record()], final=False), 1),
                call("submit_analysis", submission([summary_record("second")]), 2),
            ]
        )
        graph, files = build(router, session([block()]), state, review=review)
        with pytest.raises(RuntimeError):
            await invoke_module(graph, files, thread_id="review-failure", task="分析")
        assert [i["business"]["key"] for i in state["staged_items"]] == ["warranty"]
        assert "draft" not in state and count == 2

    asyncio.run(run())


def test_invalid_submissions_stop_at_three_and_keep_saved_content():
    async def run():
        state = {}
        router = ScriptedRouter(
            [
                *research_calls(),
                call("submit_analysis", submission([summary_record()], final=False), 0),
                *[
                    call(
                        "submit_analysis",
                        submission([summary_record("bad", content={"未知列": "错误"})]),
                        n,
                    )
                    for n in range(1, 4)
                ],
            ]
        )
        graph, files = build(router, session([block()]), state)
        with pytest.raises(ValueError, match="连续三次提交无效"):
            await invoke_module(graph, files, thread_id="invalid", task="分析")
        assert len(state["staged_items"]) == 1 and "draft" not in state

    asyncio.run(run())


def test_narrative_completion_is_corrected_and_repeated_narrative_is_bounded():
    async def run():
        state, _, router = await execute(
            [
                *research_calls(),
                AIMessage(content="已经整理完成"),
                call("submit_analysis", submission([summary_record()]), 1),
            ]
        )
        assert "submit_analysis" in str(router.requests[-1][0]) and state["draft"]
        with pytest.raises(ValueError, match="连续三次未调用"):
            await execute([AIMessage(content="已经整理完成") for _ in range(3)])

    asyncio.run(run())


def test_skill_path_permissions_and_read_argument_errors_remain_correctable():
    state, _, _ = asyncio.run(
        execute(
            [
                call("read_file", {"file_path": "/skills/other/SKILL.md"}, "denied"),
                *research_calls(),
                call("read_document", {"block_id": "s1r1c0", "before": 12}, "range"),
                call("submit_analysis", submission([summary_record()]), 1),
            ]
        )
    )
    assert "denied" in state["tool_results"]["call_denied"]["data"]["content"].lower()
    assert state["tool_results"]["call_range"]["data"]["status"] == "error"
    assert state["draft"]


def test_checkpoint_replay_keeps_research_phase_and_does_not_repeat_retrieval():
    async def run():
        state, persisted, checkpointer = {}, {}, InMemorySaver()
        research = session([block()])
        router = ScriptedRouter(
            [
                *research_calls(),
                call("submit_analysis", submission([summary_record()]), 1),
            ]
        )

        async def crash_save(value):
            persisted.update(copy.deepcopy(value))
            if "call_research" in value.get("tool_results", {}):
                raise ConnectionError("模拟工具保存后图节点提交前断开")

        graph, files = build(router, research, state, crash_save, checkpointer=checkpointer)
        with pytest.raises(ConnectionError):
            await invoke_module(graph, files, thread_id="recover", task="分析")
        restored = session([block()])
        restored.seen = copy.deepcopy(persisted["research"]["seen"])
        restored.events = copy.deepcopy(persisted["research"]["events"])
        restored.tool_calls = persisted["research"]["tool_calls"]
        graph, files = build(router, restored, persisted, checkpointer=checkpointer)
        await invoke_module(graph, files, thread_id="recover", task="恢复")
        assert len(router.requests) == 4 and persisted["research_completed"]
        assert restored.tool_calls == research.tool_calls
        await invoke_module(graph, files, thread_id="recover", task="重复完成调用")
        assert len(router.requests) == 4

    asyncio.run(run())


def test_compaction_keeps_original_evidence_and_synthesis_phase():
    class CompactRouter(ScriptedRouter):
        async def chat(self, messages, tools):
            if not tools:
                from langchain_core.messages import message_to_dict

                from tender.ports.llm import Completion

                return Completion(
                    content="摘要",
                    model="fixture",
                    agent_message=message_to_dict(
                        AIMessage(content="已检索质保，等待综合输出"),
                    ),
                )
            return await super().chat(messages, tools)

    async def run():
        research = session(
            [block() | {"content": "质保三年" + "其他条款。" * 500}],
            limits=AgentLimits(context_tokens=5000),
        )
        router = CompactRouter(
            [
                *research_calls(),
                call("submit_analysis", submission([summary_record()]), 1),
            ]
        )
        state = {}
        graph, files = build(router, research, state)
        await invoke_module(graph, files, thread_id="compact", task="分析" + "历史说明。" * 1000)
        assert research.seen["s1r1c0"]["content"].endswith("其他条款。" * 500)
        assert state["research_completed"] and state["draft"]

    asyncio.run(run())
