"""合并审查的身份、引用与预算边界，使用真实图和独立模型替身。"""

import asyncio
import copy

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import summary_record
from test_analysis_research import block, session
from test_analysis_topic_flow import snapshot
from test_deep_analysis import KEY, ScriptedRouter, call

from tender.application.analysis.agent import RoutedAgentModel, build_module_agent, invoke_module
from tender.application.analysis.data import module_data
from tender.application.analysis.protocol import PROTOCOL_VERSION
from tender.application.analysis.review import validate
from tender.domain.shared.errors import InvalidModelOutput


def approve(payload):
    return {
        "reviews": {
            row["record_id"]: {
                "supported": True,
                "issues": [],
                "bindings": {v["value_id"]: v["candidate_ids"] for v in reversed(row["values"])},
            }
            for row in reversed(payload["records"])
        },
        "issues": [],
        "context_requests": [],
    }


async def execute(records, *, review=None, tail=(), limits=None, search_args=None,
                  research_steps=None, keys=("a",), synthesis_steps=None, evidence_rows=None):
    state, saved, reviewed = {}, [], []
    records = [record | {"work_ids": record.get("work_ids", ["w1"])} for record in records]

    async def save(value):
        saved.append(copy.deepcopy(value))

    async def check(payload):
        reviewed.append(copy.deepcopy(payload))
        return await review(payload) if review else approve(payload)

    async def reserve():
        pass

    async def forbidden(items):
        raise AssertionError("新协议不应再调用独立支持性校验")

    router = ScriptedRouter(
        [
            call("list_documents", {}, "docs"),
            call("search_document", search_args or {"query": "质保", "topic_keys": ["a"]},
                 "search"),
            *(research_steps if research_steps is not None else [call(
                "update_research",
                {
                    "updates": [
                        {
                            "work_ids": ["w1"],
                            "detail": "已核对三年质保",
                            "evidence_ids": ["s1r1c0"],
                            "scope": {"kind": "common", "lot_refs": []},
                        }
                    ]
                },
                "research",
            )]),
            *(synthesis_steps if synthesis_steps is not None else [call(
                "submit_analysis",
                {"records": records[:1], "final": False},
                "stage",
            ),
            call(
                "submit_analysis",
                {"records": records[1:], "final": True},
                "final",
            )]),
        ]
        + list(tail)
    )
    graph, files = build_module_agent(
        key=KEY,
        model=RoutedAgentModel(router=router),
        research=session(evidence_rows or [block()], limits=limits),
        state=state,
        snapshot=snapshot(keys) | {"__analysis_flow_version__": PROTOCOL_VERSION},
        checkpointer=InMemorySaver(),
        reserve_tool=reserve,
        save=save,
        review_support=forbidden,
        review_combined=check,
    )
    await invoke_module(graph, files, thread_id="compact", task="按核对项研究后统一输出")
    return state, saved, router, reviewed


def test_more_than_three_records_are_staged_then_reviewed_together_once():
    async def run():
        records = [summary_record(key=f"item-{i}", title=f"独立事项{i}") for i in range(7)]
        state, saved, router, reviewed = await execute(records)
        assert len(reviewed) == 1
        assert len(reviewed[0]["records"]) == 7
        assert len(reviewed[0]["citations"]) == 1
        assert len(module_data(state)["records"]) == 7
        assert all(not module_data(s)["records"] for s in saved if "draft" not in s)
        first_tools = [t["function"]["name"] for t in router.requests[0][1]]
        final_tools = [t["function"]["name"] for t in router.requests[-1][1]]
        assert "submit_analysis" not in first_tools
        assert "submit_analysis" in final_tools and "search_document" not in final_tools
        for record in module_data(state)["records"]:
            assert record["content_evidence"]

    asyncio.run(run())


def test_independent_omission_repairs_only_new_record_without_rechecking_old_one():
    async def run():
        count = 0

        async def review(payload):
            nonlocal count
            count += 1
            result = approve(payload)
            if count == 1:
                result["issues"] = [
                    {
                        "topic": "a",
                        "detail": "另有保修材料义务",
                        "target": "保修材料条款",
                        "evidence_ids": ["s1r1c0"],
                        "record_ids": [],
                        "kind": "omission",
                    }
                ]
            else:
                assert [r["key"] for r in payload["records"]] == ["additional"]
            return result

        tail = [
            call(
                "update_research",
                {
                    "updates": [
                        {"work_ids": ["w2"], "detail": "已核对保修材料", "evidence_ids": ["s1r1c0"]}
                    ]
                },
                "repair",
            ),
            call(
                "submit_analysis",
                {"records": [summary_record(key="additional", work_ids=["w1"])], "final": True},
                "repaired",
            ),
        ]
        state, _, _, reviewed = await execute([summary_record()], review=review, tail=tail)
        assert len(reviewed) == 2 and state["topic_flow"]["audit"]["round"] == 1
        assert len(module_data(state)["records"]) == 2

    asyncio.run(run())


def test_completed_review_replays_without_model_requests_and_detects_changed_evidence():
    async def run():
        from tender.application.analysis.review import audit_combined
        from tender.application.analysis.topic_flow import TopicFlow, TopicIncomplete

        state, _, _, _ = await execute([summary_record()])
        research = session([block()])
        research.seen = state["research"]["seen"]
        flow = TopicFlow(state, research)

        async def forbidden(*_):
            raise AssertionError("审查重放不应新增模型请求")

        async def save(*_):
            pass

        assert await audit_combined(flow, forbidden, save)
        research.seen["s1r1c0"]["content"] += "但易损件一年"
        with pytest.raises(TopicIncomplete, match="数据变化"):
            await audit_combined(flow, forbidden, save)

    asyncio.run(run())


def test_long_record_is_reviewed_by_body_units_and_published_only_after_all_parts():
    from tender.application.analysis.research import AgentLimits
    from tender.application.analysis.review import fits

    async def run():
        limits = AgentLimits(max_output_tokens=1000)
        record = summary_record(content={"字段": "质保范围", "内容": ["质保三年"] * 24})
        state, saved, _, reviewed = await execute([record], limits=limits)
        assert len(reviewed) > 1
        assert all(fits(payload, limits) for payload in reviewed)
        actual = module_data(state)["records"][0]
        assert len(actual["content_evidence"]["内容"]) == 24
        assert all(not module_data(s)["records"] for s in saved if "draft" not in s)

    asyncio.run(run())


@pytest.mark.parametrize("repeat", [False, True])
def test_split_record_can_load_its_full_context_once(repeat):
    from tender.application.analysis.research import AgentLimits
    from tender.application.analysis.review import fits
    from tender.application.analysis.topic_flow import TopicIncomplete

    async def run():
        limits = AgentLimits(max_output_tokens=1000)
        requested = []
        loaded = []

        async def review(payload):
            row = payload["records"][0]
            context_id = "record:" + row["record_id"]
            assert len(row["values"]) < 26
            if not payload["context_records"]:
                requested.append(context_id)
                return {"reviews": {}, "issues": [], "context_requests": [context_id]}
            full = payload["context_records"][0]
            assert full["record_id"] == row["record_id"] and len(full["values"]) == 26
            assert fits(payload, limits)
            loaded.append(context_id)
            return ({"reviews": {}, "issues": [], "context_requests": [context_id]}
                    if repeat else approve(payload))

        record = summary_record(content={"字段": "质保范围", "内容": ["质保三年"] * 24})
        if repeat:
            with pytest.raises(TopicIncomplete, match="重复请求"):
                await execute([record], limits=limits, review=review)
            assert len(requested) == len(loaded) == 1
        else:
            state, saved, _, reviewed = await execute([record], limits=limits, review=review)
            assert len(requested) == len(loaded) > 1
            assert len(reviewed) == len(requested) * 2
            assert len(module_data(state)["records"][0]["content_evidence"]["内容"]) == 24
            assert all(not module_data(s)["records"] for s in saved if "draft" not in s)

    asyncio.run(run())


def test_repeated_context_request_stops_without_another_full_audit():
    from tender.application.analysis.topic_flow import TopicIncomplete

    async def run():
        count = 0

        async def request(payload):
            nonlocal count
            count += 1
            return {
                "reviews": {},
                "issues": [],
                "context_requests": [payload["available_context"][0]],
            }

        with pytest.raises(TopicIncomplete, match="重复请求"):
            await execute([summary_record()], review=request)
        assert count == 1

    asyncio.run(run())


def test_missing_or_foreign_ids_are_rejected_instead_of_positional_binding():
    async def run():
        _, _, _, reviewed = await execute([summary_record()])
        payload = reviewed[0]
        verdict = approve(payload)
        validate(verdict, payload)
        bad = copy.deepcopy(verdict)
        bad["reviews"] = {}
        with pytest.raises(InvalidModelOutput):
            validate(bad, payload)
        bad = copy.deepcopy(verdict)
        review = next(iter(bad["reviews"].values()))
        review["bindings"][next(iter(review["bindings"]))] = ["foreign"]
        with pytest.raises(InvalidModelOutput):
            validate(bad, payload)

    asyncio.run(run())


def test_cross_topic_dependency_changes_invalidate_only_related_review():
    async def run():
        from tender.application.analysis.review import _signature, batches
        from tender.application.analysis.topic_flow import TopicFlow

        state, _, _, _ = await execute([summary_record()])
        research = session([block()])
        research.seen = state["research"]["seen"]
        flow = TopicFlow(state, research)
        child = state["staged_items"][0]
        parent = copy.deepcopy(child)
        parent["id"] = "parent-id"
        parent["business"].update(key="parent", title="格式父节点")
        state["staged_items"].append(parent)
        child["business"]["parent_key"] = "parent"
        before = _signature(flow, "a")
        _, context = batches(flow, "a", [])
        old_key = context["cache_keys"][child["id"]]
        parent["business"]["conditions"] = {"expression": "仅A标段适用"}
        assert _signature(flow, "a") != before
        _, context = batches(flow, "a", [])
        assert context["cache_keys"][child["id"]] != old_key
        unrelated = copy.deepcopy(parent)
        unrelated["id"] = "unrelated-id"
        unrelated["business"]["key"] = "unrelated"
        before = _signature(flow, "a")
        state["staged_items"].append(unrelated)
        assert _signature(flow, "a") == before

    asyncio.run(run())


def test_new_protocol_refuses_incompatible_checkpoint_before_any_model_request():
    router = ScriptedRouter([])
    with pytest.raises(ValueError, match="旧检查点不能恢复"):
        build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=session([block()]),
            state={"topic_flow": {"entries": {}}},
            snapshot=snapshot(("a",)) | {"__analysis_flow_version__": PROTOCOL_VERSION},
            checkpointer=InMemorySaver(),
            reserve_tool=lambda: None,
            save=lambda _: None,
        )
    assert not router.requests


def test_distinct_synthesis_batches_make_progress_without_blocking_another_topic():
    async def run():
        from synthesis_fixtures import COMMON, noop

        state, saved, reviewed = {}, [], []
        facts = [("项目名称", "测试项目"), ("项目编号", "ABC123"), ("采购范围", "设备"),
                 ("预算", "100万元"), ("质保", "三年")]
        text = "。".join(name + "：" + value for name, value in facts) + "。"

        async def save(value):
            saved.append(copy.deepcopy(value))

        async def review(payload):
            reviewed.append(copy.deepcopy(payload))
            return approve(payload)

        script = [
            call("list_documents", {}, "documents"),
            call("search_document", {"query": "项目信息", "topic_keys": ["a", "b"]}, "search"),
            call("update_research", {"updates": [{
                "work_ids": ["w1", "w2"], "detail": text, "scope": COMMON,
                "evidence_ids": ["s1r1c0"],
            }]}, "research"),
        ]
        for index, (name, value) in enumerate(facts):
            script.append(call("submit_analysis", {
                "records": [summary_record(
                    key=f"fact-{index}", title=name, content={"字段": name, "内容": value},
                    quote=name + "：" + value, work_ids=["w2" if index == 0 else "w1"],
                )],
                "final": index == len(facts) - 1,
            }, f"batch-{index}"))
        router = ScriptedRouter(script)
        graph, files = build_module_agent(
            key=KEY, model=RoutedAgentModel(router=router),
            research=session([block() | {"content": text}]), state=state,
            snapshot=snapshot(("a", "b")) | {"__analysis_flow_version__": PROTOCOL_VERSION},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=save, review_combined=review,
        )
        await invoke_module(graph, files, thread_id="synthesis-progress", task="分批综合全部事项")
        assert not router.calls
        assert {p["topic"] for p in reviewed} == {"a", "b"}
        assert len(module_data(state)["records"]) == len(facts)
        assert all(e["status"] == "ready" for e in state["topic_flow"]["entries"].values())
        assert all(not module_data(s)["records"] for s in saved if "draft" not in s)
        assert all("连续无法推进" not in e["detail"]
                   for s in saved for e in s["topic_flow"]["entries"].values())

    asyncio.run(run())


@pytest.mark.parametrize("dependent", [False, True])
@pytest.mark.parametrize("affected_topic", ["a", "b"])
def test_unscoped_review_issue_preserves_unrelated_results_and_revokes_dependents(
    dependent, affected_topic,
):
    async def run():
        from synthesis_fixtures import noop

        from tender.application.analysis.review import audit_combined
        from tender.application.analysis.state import published_items
        from tender.application.analysis.topic_flow import TopicFlow, identity

        state, _, _, _ = await execute([summary_record()])
        research = session([block()])
        research.seen = state["research"]["seen"]
        flow = TopicFlow(state, research)
        first = state["staged_items"][0]
        second = copy.deepcopy(first)
        second.update(id="second-id", work_ids=["w2"])
        second["business"].update(key="second", title="另一个子主题的事项")
        state["staged_items"].append(second)
        entry = copy.deepcopy(flow.entries[0])
        entry.update(topic="b", title="另一子主题", record_keys=["second"])
        flow.data["entries"][identity("b", entry["scope"])] = entry
        affected, other = (first, second) if affected_topic == "a" else (second, first)
        if dependent:
            other["business"]["parent_key"] = affected["business"]["key"]
        flow.data["audit"] = {"round": 0, "results": {}}

        async def review(payload):
            verdict = approve(payload)
            if payload["topic"] == affected_topic:
                verdict["issues"] = [{
                    "topic": affected_topic, "kind": "scope", "detail": "本子主题范围待确认",
                    "target": "本子主题条款", "evidence_ids": [], "record_ids": [],
                }]
            return verdict

        assert not await audit_combined(flow, review, noop)
        assert affected["review_status"] == "needs_review"
        assert other["review_status"] == ("needs_review" if dependent else "current")
        expected_keys = {affected["business"]["key"]}
        if dependent:
            expected_keys.add(other["business"]["key"])
        assert all(set(issue["record_keys"]) == expected_keys
                   for issue in flow.data["audit"]["issues"])
        assert {issue["topic"] for issue in flow.data["audit"]["issues"]} == (
            {"a", "b"} if dependent else {affected_topic}
        )
        assert {i["id"] for i in published_items(state, final=True)} == (
            set() if dependent else {other["id"]}
        )
        assert not flow.data["audit"]["record_topics"].get(affected["id"])

    asyncio.run(run())
