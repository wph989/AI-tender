"""解析协议的行为回归：数据最小化、真实Skill加载、有界恢复和必要证据保留。"""

import asyncio
import copy
import json
import re
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import research_calls, research_done, submission, summary_record
from test_analysis_research import block, session
from test_deep_analysis import KEY, SKILL, ScriptedRouter, call, submitted_field

from tender.application.analysis.agent import (
    ResearchMiddleware,
    RoutedAgentModel,
    build_module_agent,
    invoke_module,
)
from tender.application.analysis.policy import (
    correction_count,
    load_module_skill,
    select_verified_repeats,
)
from tender.application.analysis.research import ToolArgumentError
from tender.application.analysis.skills import MODULES, skill_snapshot, verify_items
from tender.application.knowledge.content import validate_items
from tender.domain.shared.errors import InvalidModelOutput, ModelOutputTruncated, ModelUnavailable
from tender.ports.llm.chat import Completion


async def noop(*args):
    pass


def build(router, research, state, **kwargs):
    return build_module_agent(
        key=KEY,
        model=RoutedAgentModel(router=router),
        research=research,
        state=state,
        snapshot=SKILL,
        checkpointer=InMemorySaver(),
        reserve_tool=noop,
        save=noop,
        **kwargs,
    )


def test_compact_evidence_hides_metadata_and_rereads_by_registered_id():
    async def run():
        rows = [
            block() | {"score": 0.99, "bbox": [1, 2, 3, 4], "page_no": 8},
            block()
            | {"block_id": "next", "element_id": 2, "offset": 1, "content": "但易损件仅保修一年"},
        ]
        research = session(rows)
        research.compact_results = True
        with pytest.raises(ToolArgumentError):
            await research.read_evidence("s1r1c0")
        result = await research.search("质保", "project")
        assert result["blocks"] == [{"id": r["block_id"], "text": r["content"]} for r in rows]
        assert "retrieval" not in result and "relations" not in result
        assert research.seen["s1r1c0"]["page_no"] == 8
        reread = await research.read_evidence("s1r1c0", 0, 1)
        assert reread["blocks"] == result["blocks"]
        assert research.events[-1]["action"] == "read_evidence"
        assert all(set(d) == {"id", "text"} for d in await research.documents())

    asyncio.run(run())


def test_retriever_cannot_mix_authorized_reference_into_project_scope():
    async def run():
        research = session([block(), block(2, 20)])

        async def mixed(*args):
            return [block(2, 20)], {}

        research.retrieve = mixed
        with pytest.raises(PermissionError, match="所选范围"):
            await research.search("质保", "project")
        assert not research.seen

    asyncio.run(run())


def test_skill_is_loaded_before_first_model_and_survives_checkpoint():
    async def run():
        router = ScriptedRouter(
            [
                *research_calls(),
                call(
                    "submit_analysis",
                    submission(summary="已检索，本专题无新增"),
                    2,
                ),
            ]
        )
        state, reservations = {}, []

        async def reserve():
            reservations.append(True)

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=session([block()]),
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=reserve,
            save=noop,
        )
        await invoke_module(graph, files, thread_id="forced-skill", task="分析")
        assert state["loaded_skill"]["sha256"] == load_module_skill(SKILL, KEY)["sha256"]
        first_prompt = str(router.requests[0][0])
        assert "检索项目概况" in first_prompt
        assert len(reservations) == 5
        await invoke_module(graph, files, thread_id="forced-skill", task="恢复")
        assert len(reservations) == 5 and len(router.requests) == 4

    asyncio.run(run())


def test_project_skills_have_loadable_references_and_distinct_domain_rules():
    snapshot = skill_snapshot()
    for key in MODULES:
        loaded = load_module_skill(snapshot, key)
        assert loaded["path"] == "/skills/" + key.replace("_", "-") + "/SKILL.md"
        assert f"name: {key.replace('_', '-')}" in loaded["instructions"]
        assert "read_document(source_id" not in loaded["instructions"]
        text = snapshot[key + "/SKILL.md"]
        for reference in re.findall(r"`(references/[^`]+\.md)`", text):
            for category in ("engineering", "goods", "service"):
                assert key + "/" + reference.replace("<type_dir>", category) in snapshot
        modified = snapshot | {key + "/SKILL.md": text + "\n新的业务规则"}
        assert load_module_skill(modified, key)["sha256"] != loaded["sha256"]
    assert "纯参数清单" in snapshot["tech_requirement_parsing/SKILL.md"]
    # 模型引用稳定 key，最终 parent_id 由服务端生成，避免模型编造记录身份。
    assert "parent_key" in snapshot["bid_format_outline_parsing/SKILL.md"]
    with pytest.raises(ValueError, match="Skill"):
        load_module_skill({}, KEY)


def test_identical_queries_reuse_results_and_stop_at_limit():
    async def run():
        research = session([block()])
        router = ScriptedRouter(
            [
                call("search_document", {"query": q}, n)
                for n, q in enumerate(["质保", " 质保 ", "质保", "质保"])
            ]
        )
        state = {}
        graph, files = build(router, research, state)
        with pytest.raises(RuntimeError, match="相同工具"):
            await invoke_module(graph, files, thread_id="repeat", task="分析")
        assert research.tool_calls == 1
        assert len(state["tool_results"]) == 3
        assert len(router.requests) == 4

    asyncio.run(run())


def test_success_in_other_tool_does_not_reset_failing_tool_counter():
    async def run():
        router = ScriptedRouter(
            [
                call("read_document", {"block_id": "missing-1"}, 1),
                call("list_documents", {}, 2),
                call("read_document", {"block_id": "missing-2"}, 3),
                call("list_documents", {}, 4),
                call("read_document", {"block_id": "missing-3"}, 5),
            ]
        )
        state = {}
        graph, files = build(router, session([block()]), state)
        with pytest.raises(ValueError, match="工具连续失败"):
            await invoke_module(graph, files, thread_id="tool-failures", task="分析")
        feedback = json.loads(state["tool_results"]["call_5"]["data"]["content"])
        assert feedback["remaining_attempts"] == 0
        assert feedback["tool"] == "read_document"
        assert state["tool_failures"]["read_document"] == 3

    asyncio.run(run())


def test_no_progress_enters_finish_mode_and_preserves_verified_results():
    async def run():
        router = ScriptedRouter(
            [call("list_documents", {}, "documents")]
            + [call("search_document", {"query": "质保"}, "search")]
            + [call("read_document", {"block_id": "s1r1c0", "before": n, "after": 0}, n)
               for n in range(3)]
            + [call("search_document", {"query": "收尾时的新检索"}, 4)]
            + [
                call("complete_research", research_done(), "research"),
                call(
                    "submit_analysis",
                    submission(summary="未找到新增，停止检索"),
                    6,
                )
            ]
        )
        research, state = session([block()]), {}
        graph, files = build(router, research, state)
        await invoke_module(graph, files, thread_id="no-progress", task="分析")
        assert state["finish_only"]
        assert research.tool_calls == 5
        assert state["tool_results"]["call_4"]["data"]["status"] == "error"
        assert "draft" in state

    asyncio.run(run())


def test_renaming_rejected_fact_does_not_reset_corrections():
    state = {}
    for index in range(3):
        assert correction_count(state, submitted_field(f"更名{index}", "质保五年")) == index + 1


@pytest.mark.parametrize("scope", ["group", "note"])
def test_shared_quote_does_not_share_corrections_across_scopes(scope):
    state = {}
    for index, subject in enumerate(("设备A", "设备B", "设备C")):
        entry = submitted_field(f"质保{index}", "质保五年")
        entry[scope] = subject
        assert correction_count(state, entry) == 1


def test_changing_value_does_not_reset_same_field_corrections():
    state = {}
    for index, value in enumerate(("质保五年", "质保六年", "质保七年"), start=1):
        assert correction_count(state, submitted_field("质保期", value)) == index


def test_shared_quote_gives_distinct_facts_their_own_review_attempts():
    async def run():
        quote = "时间安排以最新补充通知为准。"
        research = session([block() | {"content": quote}])
        await research.search("时间安排", "project")
        fields = [
            submitted_field(name, value, quote=quote)
            for name, value in (
                ("投标截止时间", "10月11日"),
                ("开标时间", "10月12日"),
                ("答疑截止时间", "10月10日"),
            )
        ]
        state = {}

        async def reject(items):
            for entry in items:
                entry["verification"] = "unsupported"
                entry["verification_issues"] = ["引用未给出该时间"]

        for attempt in range(1, 4):
            # 从已持久化状态重建，验证恢复不会重置额度，也不会在字段之间串账。
            state = json.loads(json.dumps(state))
            entries = validate_items(fields, research.seen)
            for entry in entries:
                entry["verification"] = "pending"
            state["staged_items"] = entries
            middleware = ResearchMiddleware(research, state, noop, noop, review_support=reject)
            if attempt < 3:
                feedback = await middleware.run_review_step()
                remaining = json.loads(feedback["messages"][0].content)["remaining_attempts"]
                assert remaining == 3 - attempt
            else:
                with pytest.raises(RuntimeError, match="纠正已达3次上限"):
                    await middleware.run_review_step()
            assert len(state["field_failures"]) == 3
            assert set(state["field_failures"].values()) == {attempt}

    asyncio.run(run())


@pytest.mark.parametrize(
    "error", [ConnectionError("本地连接中断"), ModelUnavailable("路由已耗尽")]
)
def test_subagent_recovery_is_bounded_and_never_multiplies_model_retries(error):
    class BrokenGraph:
        calls = 0

        async def aget_state(self, config):
            return SimpleNamespace(values={})

        async def ainvoke(self, *args, **kwargs):
            self.calls += 1
            raise error

    async def run():
        graph, state, saved = BrokenGraph(), {}, []

        async def save(value):
            saved.append(copy.deepcopy(value))

        expected = RuntimeError if isinstance(error, ConnectionError) else ModelUnavailable
        with pytest.raises(expected):
            await invoke_module(graph, {}, thread_id="retry", task="分析", state=state, save=save)
        if isinstance(error, ConnectionError):
            assert graph.calls == 3 and state["subagent_retries"] == 2
            assert [s["subagent_retries"] for s in saved] == [1, 2]
            with pytest.raises(RuntimeError):
                await invoke_module(
                    graph, {}, thread_id="retry", task="恢复", state=state, save=save
                )
            assert graph.calls == 4  # 恢复仍无额外重试机会。
        else:
            assert graph.calls == 1 and not saved

    asyncio.run(run())


class Selector:
    def __init__(self, ids):
        self.ids, self.calls, self.batch = ids, 0, None

    async def complete(self, prompt):
        self.calls += 1
        if self.batch is None:
            self.batch = json.loads(prompt.rsplit("\n", 1)[-1])
        return Completion(
            content=json.dumps(
                {
                    "reviews": [
                        {
                            "supported": True, "unsupported_claims": [],
                            "unresolved_references": [], "evidence_ids": [self.ids],
                        }
                    ]
                }
            ),
            model="fixture",
        )


def evidence_fixture(cross_source=False):
    rows = [
        block() | {"page_no": 2, "bbox": [1, 2, 3, 4]},
        block(2, 10)
        if cross_source
        else block() | {"block_id": "duplicate", "element_id": 3, "offset": 1},
    ]
    rows[1] |= {"page_no": 8, "bbox": [4, 3, 2, 1]}
    seen = {r["block_id"]: r for r in rows}
    field = submitted_field("质保", "质保三年")
    field["values"][0]["citations"].append({"block_id": rows[1]["block_id"], "quote": "质保三年"})
    return validate_items([field], seen), seen


def test_selector_sees_only_ids_and_text_and_keeps_best_citation_location():
    items, evidence = evidence_fixture()
    selector = Selector(["duplicate"])
    asyncio.run(
        verify_items(selector, items, explain=True, evidence=evidence, select_evidence=True)
    )
    value = selector.batch[0]["values"][0]
    assert all(set(r) == {"id", "text"} for r in value["citations"] + value["context"])
    refs = items[0]["values"][0]["citations"]
    assert len(refs) == 1 and refs[0]["block_id"] == "duplicate"
    assert refs[0]["page_no"] == 8 and refs[0]["bbox"] == [4, 3, 2, 1]


def test_compact_review_does_not_expand_long_neighbours_back_to_full_text():
    items, evidence = evidence_fixture()
    items[0]["field"] = "投标人须知前附表的质保"
    for row in evidence.values():
        row["content"] += "这是一段很长的其它条款。" * 2000
    selector = Selector(["duplicate"])
    asyncio.run(verify_items(selector, items, explain=True, evidence=evidence,
                             select_evidence=True))
    context = selector.batch[0]["values"][0]["context"]
    assert sum(len(r["text"]) for r in context) < 3000
    assert all("已截断" in r["text"] for r in context)


@pytest.mark.parametrize("ids", [["invented"], [], ["s1r1c0", "s1r1c0"]])
def test_selector_rejects_fabricated_empty_or_duplicate_ids_with_bounded_correction(ids):
    items, evidence = evidence_fixture()
    before = copy.deepcopy(items)
    selector = Selector(ids)
    with pytest.raises(InvalidModelOutput):
        asyncio.run(
            verify_items(selector, items, explain=True, evidence=evidence, select_evidence=True)
        )
    assert selector.calls == 3 and items == before


def test_selector_cannot_drop_one_side_of_cross_file_evidence():
    items, evidence = evidence_fixture(cross_source=True)
    with pytest.raises(InvalidModelOutput, match="各方"):
        asyncio.run(
            verify_items(
                Selector(["s1r1c0"]), items, explain=True, evidence=evidence, select_evidence=True
            )
        )
    asyncio.run(
        verify_items(
            Selector(list(evidence)), items, explain=True, evidence=evidence, select_evidence=True
        )
    )
    assert len(items[0]["values"][0]["citations"]) == 2


def test_verified_batches_choose_one_sufficient_set_without_mixing_scope():
    items, _ = evidence_fixture()
    first = items[0] | {"verification": "supported"}
    second = copy.deepcopy(first)
    second["values"][0]["citations"] = second["values"][0]["citations"][1:]
    other_lot = copy.deepcopy(first)
    other_lot["values"][0]["value"] = "标段二质保三年"
    select_verified_repeats([first, second, other_lot])
    assert len(first["values"][0]["citations"]) == 1
    assert len(other_lot["values"][0]["citations"]) == 2


def test_same_title_summaries_keep_distinct_requirements_and_evidence():
    async def run():
        rows = [
            block() | {"content": "设备A质保三年，自验收合格之日起算。"},
            block() | {
                "block_id": "equipment-b", "element_id": 2, "offset": 1,
                "content": "设备B质保三年，自交货起算。",
            },
        ]
        records = [
            summary_record(key=row["block_id"], text=note, citations=[
                {"block_id": row["block_id"], "quote": row["content"]},
            ])
            for row, note in zip(rows, ("设备A自验收起算", "设备B自交货起算"), strict=True)
        ]
        router = ScriptedRouter([
            *research_calls(query="质保期"),
            *[
                call("submit_analysis", submission([entry], final=index == 1), index + 2)
                for index, entry in enumerate(records)
            ],
        ])
        state = {}

        async def accept(items):
            for entry in items:
                entry["verification"] = "supported"

        graph, files = build(router, session(rows), state, review_support=accept)
        await invoke_module(graph, files, thread_id="distinct-note-evidence", task="分析")
        merged = state["draft"]["fields"]
        assert len(merged) == 2
        assert [item["output"]["content"] for item in merged] == [r["content"] for r in records]
        # 同名事项不能抹去设备和起算条件，各自的原文定位都须保留。
        refs = [ref for item in merged for ref in item["values"][0]["citations"]]
        assert {(ref["block_id"], ref["quote"]) for ref in refs} == {
            (row["block_id"], row["content"]) for row in rows
        }

    asyncio.run(run())


def test_later_review_batch_failure_preserves_already_verified_fact_and_failure_count():
    async def run():
        research = session([block()])
        await research.search("质保", "project")
        entries = validate_items([
            submitted_field("已核实", "质保三年"), submitted_field("未核实", "质保三年")
        ], research.seen)
        for entry in entries:
            entry["verification"] = "pending"
        state = {"staged_items": entries, "pending_final": {"research_summary": "分批校验"}}
        saved = []

        async def review(items):
            items[0]["verification"] = "supported"
            raise ModelOutputTruncated("后续校验批次输出被截断")

        async def save(value):
            saved.append(copy.deepcopy(value))

        middleware = ResearchMiddleware(research, state, noop, save, review_support=review)
        feedback = await middleware.run_review_step()
        assert [e["field"] for e in state["staged_items"]] == ["已核实"]
        assert saved[-1]["unavailable_submissions"] == 1
        assert "pending_final" not in saved[-1] and "draft" not in state
        assert json.loads(feedback["messages"][0].content)["remaining_attempts"] == 2

    asyncio.run(run())
