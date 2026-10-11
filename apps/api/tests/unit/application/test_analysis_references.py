"""转引原文确实存在，也不能代替需要展开的招标要求。"""

import asyncio
import copy
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_analysis_research import block, session, source
from test_deep_analysis import ScriptedRouter, call, submitted_field

from tender.application.analysis_skills import skill_snapshot, verify_items
from tender.application.deep_analysis import RoutedAgentModel, build_module_agent, invoke_module
from tender.application.knowledge import validate_items
from tender.domain.errors import InvalidModelOutput
from tender.ports.llm import Completion


class ReferenceReviewer:
    """独立校验器认为摘录真实，但明确指出尚未展开的内容。"""

    def __init__(self, gaps):
        self.gaps = gaps
        self.calls = 0

    async def complete(self, prompt):
        self.calls += 1
        # 格式纠正会在原始载荷后追加反馈，仍读取本批原始待检数据。
        items = json.loads(next(line for line in prompt.splitlines() if line.startswith("[{")))
        reviews = []
        for item in items:
            targets = [
                self.gaps[v["value"]] for v in item["values"] if v["value"] in self.gaps
            ]
            reviews.append({
                "supported": True,
                "unsupported_claims": [],
                "unresolved_references": targets,
                "evidence_ids": [[r["id"] for r in v["citations"]] for v in item["values"]],
            })
        return Completion(content=json.dumps({"reviews": reviews}), model="fixture")


@pytest.mark.parametrize("value,target", [
    ("详见第三章评标办法", "第三章评标办法"),
    ("评分细则载于《评分附件.pdf》", "评分附件.pdf"),
    ("按评标办法前附表规定执行", "评标办法前附表"),
    ("技术方案满分20分，各档得分条件详见附件2", "附件2中的各档得分条件"),
])
def test_textually_supported_reference_is_not_a_completed_requirement(value, target):
    row = block() | {"content": value}
    evidence = {row["block_id"]: row}
    items = validate_items([submitted_field("评分标准", value, quote=value)], evidence)
    asyncio.run(verify_items(
        ReferenceReviewer({value: target}), items, explain=True,
        evidence=evidence, select_evidence=True,
    ))
    assert items[0]["verification"] == "unsupported"
    issues = " ".join(items[0]["verification_issues"])
    assert target in issues and "search_document" in issues


@pytest.mark.parametrize("field,value", [
    ("评分标准", "每提供一项同类业绩得2分，最高6分（第三章评标办法）"),
    ("执行标准", "产品应符合GB/T 19001标准"),
    ("提交材料", "须按附件4格式提供投标函并加盖公章"),
    ("评标方法", "采用综合评分法"),
    ("补充修订", "补遗将第三章业绩评分由满分5分修改为满分6分"),
])
def test_substantive_requirement_with_reference_remains_valid(field, value):
    row = block() | {"content": value}
    evidence = {row["block_id"]: row}
    items = validate_items([submitted_field(field, value, quote=value)], evidence)
    asyncio.run(verify_items(
        ReferenceReviewer({}), items, explain=True, evidence=evidence, select_evidence=True,
    ))
    assert items[0]["verification"] == "supported"
    assert items[0]["values"][0]["citations"][0]["block_id"] == row["block_id"]


@pytest.mark.parametrize("gap_result", [None, "第三章", [""], [1]])
def test_reference_review_is_required_and_format_retries_are_bounded(gap_result):
    class InvalidReviewer(ReferenceReviewer):
        async def complete(self, prompt):
            completion = await super().complete(prompt)
            result = json.loads(completion.content)
            review = result["reviews"][0]
            if gap_result is None:
                review.pop("unresolved_references")
            else:
                review["unresolved_references"] = gap_result
            return Completion(content=json.dumps(result), model="fixture")

    row = block()
    evidence = {row["block_id"]: row}
    items = validate_items([submitted_field("质保", "质保三年")], evidence)
    before = copy.deepcopy(items)
    reviewer = InvalidReviewer({})
    with pytest.raises(InvalidModelOutput, match="unresolved_references"):
        asyncio.run(verify_items(
            reviewer, items, explain=True, evidence=evidence, select_evidence=True,
        ))
    assert reviewer.calls == 3 and items == before


def test_reference_feedback_follows_target_file_then_submits_actual_scoring_rules():
    async def run():
        index = block() | {"content": "评分标准详见《评分附件.pdf》"}
        heading = block(3, 10) | {"content": "第三章 评标办法"}
        detail = heading | {
            "block_id": "score-rule", "element_id": 4, "offset": 1,
            "content": "每提供一项同类业绩得2分，最高6分。",
        }
        research = session([index, heading, detail])
        research.sources.append(source(3, 10) | {"file_name": "评分附件.pdf"})
        queries = []

        async def retrieve(sources, query):
            queries.append(query)
            return ([index] if len(queries) == 1 else [heading]), {}

        research.retrieve = retrieve
        router = ScriptedRouter([
            call("search_document", {"query": "评分标准"}, 1),
            call("submit_analysis", {
                "fields": [submitted_field("评分标准", index["content"], quote=index["content"])],
                "relations": [], "research_summary": "找到评分索引", "final": True,
            }, 2),
            call("list_documents", {}, 3),
            call("search_document", {"query": "业绩得分 评分标准", "source_id": 3}, 4),
            call("read_document", {"block_id": heading["block_id"], "before": 0, "after": 1}, 5),
            call("submit_analysis", {
                "fields": [submitted_field(
                    "业绩评分", detail["content"], quote=detail["content"], block_id="score-rule",
                )],
                "relations": [], "research_summary": "已展开评分附件中的实际评分规则",
                "final": True,
            }, 6),
        ])
        state, saved = {}, []
        reviewer = ReferenceReviewer({index["content"]: "评分附件.pdf"})

        async def noop(*args):
            pass

        async def save(value):
            saved.append(copy.deepcopy(value))

        async def review(items):
            await verify_items(
                reviewer, items, explain=True, evidence=research.seen, select_evidence=True,
            )

        graph, files = build_module_agent(
            key="scoring_standard_parsing", model=RoutedAgentModel(router=router),
            research=research, state=state, snapshot=skill_snapshot(),
            checkpointer=InMemorySaver(), reserve_tool=noop, save=save, review_support=review,
        )
        await invoke_module(graph, files, thread_id="follow-score-reference", task="分析评分标准")
        assert len(queries) == 2 and reviewer.calls == 2
        assert any("评分附件.pdf" in str(request[0]) for request in router.requests[2:])
        values = state["draft"]["fields"][0]["values"]
        assert values[0]["value"] == detail["content"]
        assert [ref["block_id"] for ref in values[0]["citations"]] == ["score-rule"]
        assert all(
            value["value"] != index["content"]
            for snapshot in saved for item in snapshot.get("staged_items", [])
            if item.get("verification") == "supported" for value in item["values"]
        )

    asyncio.run(run())


@pytest.mark.parametrize("target_missing", [True, False])
def test_missing_or_cyclic_reference_never_replaces_verified_requirements(target_missing):
    async def run():
        index = block() | {"content": "评分标准详见附件A"}
        loop = index | {
            "block_id": "attachment-a", "element_id": 2, "offset": 1,
            "content": "附件A评分标准参见前附表",
        }
        valid = index | {
            "block_id": "method", "element_id": 3, "offset": 2,
            "content": "采用综合评分法",
        }
        research = session([index, loop, valid])
        query_count = 0

        async def retrieve(sources, query):
            nonlocal query_count
            query_count += 1
            if query_count == 1:
                return [index, valid], {}
            return ([] if target_missing else [loop]), {}

        research.retrieve = retrieve

        def submission(row, number, extras=None):
            return call("submit_analysis", {
                "fields": [submitted_field(
                    "评分标准", row["content"], quote=row["content"], block_id=row["block_id"],
                ), *(extras or [])],
                "relations": [], "research_summary": "核对评分", "final": True,
            }, number)

        script = [
            call("search_document", {"query": "评分"}, 1),
            submission(index, 2, [submitted_field(
                "评标方法", valid["content"], quote=valid["content"], block_id="method",
            )]),
            call("search_document", {"query": "附件A评分标准"}, 3),
        ]
        if target_missing:
            script.append(call("submit_analysis", {
                "fields": [], "relations": [], "final": True,
                "research_summary": "检索附件A评分标准未取得正文，仅保留已核实评标方法",
            }, 4))
        else:
            script += [
                submission(loop, 4),
                call("search_document", {"query": "前附表评分细则"}, 5),
                submission(index, 6),
            ]
        router, state = ScriptedRouter(script), {}
        reviewer = ReferenceReviewer({index["content"]: "附件A", loop["content"]: "前附表"})

        async def noop(*args):
            pass

        async def review(items):
            await verify_items(
                reviewer, items, explain=True, evidence=research.seen, select_evidence=True,
            )

        graph, files = build_module_agent(
            key="scoring_standard_parsing", model=RoutedAgentModel(router=router),
            research=research, state=state, snapshot=skill_snapshot(),
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop, review_support=review,
        )
        if target_missing:
            await invoke_module(graph, files, thread_id="missing-reference", task="分析")
            assert "附件A" in state["draft"]["research_summary"]
            assert [e["field"] for e in state["draft"]["fields"]] == ["评标方法"]
        else:
            with pytest.raises(RuntimeError, match="纠正已达3次上限"):
                await invoke_module(graph, files, thread_id="cyclic-reference", task="分析")
            assert "draft" not in state and reviewer.calls == 3
        assert [e["field"] for e in state["staged_items"]] == ["评标方法"]

    asyncio.run(run())
