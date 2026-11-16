"""同一真实Agent图自主执行草稿、自查、补读、修订与最终提交。"""

import asyncio
import copy
import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import noop
from test_analysis_research import block, session
from test_analysis_v3 import KEY, raw, schema
from test_deep_analysis import ScriptedRouter, call

from tender.application.analysis.agent import RoutedAgentModel, invoke_module
from tender.application.analysis.drafts import AGENT_PROTOCOL
from tender.application.analysis.skill_agent import (
    DraftSubmission,
    build_skill_agent,
    workspace_feedback,
)
from tender.application.analysis.skills import skill_snapshot


def test_encoded_array_error_explains_invalid_inner_json_without_echoing_body():
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as caught:
        DraftSubmission.model_validate({"records": '[{"content":"私密正文"}]}', "final": False})
    message = workspace_feedback(caught.value)
    assert "records" in message and "JSON" in message and "数组" in message
    assert "私密正文" not in message


def test_context_places_source_after_each_draft_and_pages_full_text_once():
    async def run():
        from tender.application.analysis.drafts import DraftWorkspace

        state = {"output_schema": schema()}
        source = block() | {"content": "原文条件与例外" * 1600}
        research = session([source])
        research.seen = {source["block_id"]: source}
        book = DraftWorkspace(state, research.seen, KEY)
        book.save_records([raw(content={"字段": f"事项{i}", "内容": "质保三年"})
                           for i in range(7)], "drafts")
        frozen = skill_snapshot() | {
            "__analysis_flow_version__": AGENT_PROTOCOL,
            KEY + "/references/output_schema.json": json.dumps(schema(), ensure_ascii=False),
        }
        graph, _ = build_skill_agent(
            key=KEY, model=RoutedAgentModel(router=ScriptedRouter([])),
            research=research, state=state, snapshot=frozen,
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop,
        )
        tool = graph.nodes["tools"].bound.tools_by_name["get_research_context"]
        result = await tool.ainvoke({"limit": 6})
        assert result["units"][0]["kind"] == "draft"
        assert result["units"][1]["kind"] == "evidence"
        units = list(result["units"])
        while result["next_offset"] is not None:
            result = await tool.ainvoke({"offset": result["next_offset"], "limit": 6})
            units.extend(result["units"])
        parts = [u for u in units if u["kind"] == "evidence"]
        assert len({u["start"] for u in parts}) == len(parts)
        assert json.loads("".join(u["text"] for u in parts))["content"] == source["content"]
        assert len([u for u in units if u["kind"] == "draft" and u["start"] == 0]) == 7

    asyncio.run(run())


def test_one_agent_can_research_after_review_and_publish_only_explicit_final():
    async def run():
        state, saves = {}, []

        class Router(ScriptedRouter):
            async def chat(self, messages, tools):
                if len(self.requests) in {2, 4, 5}:
                    item = state["staged_items"][0]
                    rid, version = item["id"], item["draft_version"]
                    if len(self.requests) == 4:
                        next_call = call(
                            "submit_analysis",
                            {
                                "records": [
                                    raw(
                                        id=rid,
                                        version=version,
                                        content={"字段": "质保", "内容": "三年，自验收之日起"},
                                    )
                                ],
                                "final": False,
                            },
                            4,
                        )
                    else:
                        next_call = call(
                            "record_review",
                            {
                                "records": [
                                    {
                                        "record_id": rid,
                                        "version": version,
                                        "status": "passed",
                                        "reason": "对照原文核清期限与起算点",
                                        "block_ids": ["s1r1c0"],
                                    }
                                ]
                            },
                            len(self.requests),
                        )
                    self.calls.insert(0, next_call)
                if len(self.requests) == 6:
                    self.calls.insert(
                        0,
                        call(
                            "submit_analysis",
                            {
                                "final": True,
                                "record_ids": [state["staged_items"][0]["id"]],
                                "summary": "核清质保要求",
                            },
                            6,
                        ),
                    )
                return await super().chat(messages, tools)

        router = Router(
            [
                call("search_document", {"query": "质保"}, 0),
                call("submit_analysis", {"records": [raw()], "final": False}, 1),
                call("read_document", {"block_id": "s1r1c0", "before": 0, "after": 0}, 3),
            ]
        )

        async def save(value):
            saves.append(copy.deepcopy(value))

        frozen = skill_snapshot() | {
            "__analysis_flow_version__": AGENT_PROTOCOL,
            KEY + "/references/output_schema.json": json.dumps(schema(), ensure_ascii=False),
        }
        graph, files = build_skill_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=session([block()]),
            state=state,
            snapshot=frozen,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=save,
        )
        await invoke_module(graph, files, thread_id="agent-led", task="按Skill分析质保")
        assert len(router.requests) == 7
        assert state["agent_workspace"]["finalized"]
        assert state["staged_items"][0]["draft_version"] == 2
        assert all("draft" not in snapshot for snapshot in saves[:-1])
        for _, tools in router.requests:
            names = {tool["function"]["name"] for tool in tools}
            assert {"search_document", "submit_analysis", "record_review", "read_document"} <= names
            assert "complete_research" not in names and "task" not in names
        assert "topic_flow" not in state

    asyncio.run(run())


def test_invalid_batch_type_is_feedback_then_same_agent_saves_and_finishes():
    async def run():
        state = {}

        class Router(ScriptedRouter):
            async def chat(self, messages, tools):
                if len(self.requests) == 1:
                    assert messages[-1]["data"]["status"] == "error"
                    assert "records" in messages[-1]["data"]["content"]
                if len(self.requests) == 3:
                    assert state["staged_items"][0]["draft_version"] == 1
                return await super().chat(messages, tools)

        router = Router([
            call("submit_analysis", {"records": {"kind": "fact"}, "final": False}, 0),
            call("search_document", {"query": "质保"}, 1),
            call("submit_analysis", {"records": [raw()], "final": False}, 2),
            call("submit_analysis", {"final": True, "record_ids": [],
                                     "summary": "保留草稿待继续核对"}, 3),
        ])
        graph, files = build_skill_agent(
            key=KEY, model=RoutedAgentModel(router=router), research=session([block()]),
            state=state, snapshot=skill_snapshot() | {
                "__analysis_flow_version__": AGENT_PROTOCOL,
                KEY + "/references/output_schema.json": json.dumps(schema())},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop,
        )
        await invoke_module(graph, files, thread_id="bad-batch", task="分析")
        assert len(router.requests) == 4 and state["agent_workspace"]["finalized"]
        assert state["draft"]["fields"] == []

    asyncio.run(run())


def test_batch_search_replays_saved_child_without_spending_budget_twice():
    async def run():
        state, saved, reserved = {}, [], []
        checkpoint = InMemorySaver()
        router = ScriptedRouter([
            call("search_document_batch", {"queries": [{"query": "质保"}, {"query": "期限"}]}, 0),
            call("submit_analysis", {"final": True, "summary": "没有可确认结论"}, 1),
        ])

        async def begin(call_id):
            reserved.append(call_id)
            return call_id

        async def save(value):
            saved.append(copy.deepcopy(value))
            if len(saved) == 1:
                # 模拟第一个子查询已保存、父调用尚未回传就断开。
                raise ConnectionError("saved")

        def build(current, persist):
            return build_skill_agent(
                key=KEY, model=RoutedAgentModel(router=router), research=session([block()]),
                state=current, snapshot=skill_snapshot() | {
                    "__analysis_flow_version__": AGENT_PROTOCOL}, checkpointer=checkpoint,
                reserve_tool=noop, begin_tool=begin, save=persist,
            )

        graph, files = build(state, save)
        with pytest.raises(ConnectionError, match="saved"):
            await invoke_module(graph, files, thread_id="batch-replay", task="分析")
        restored = saved[-1]
        graph, files = build(restored, noop)
        await invoke_module(graph, files, thread_id="batch-replay", task="分析")
        children = [key for key in reserved if ":query:" in key]
        assert len(children) == len(set(children)) == 2
        assert restored["agent_workspace"]["finalized"]

    asyncio.run(run())


@pytest.mark.parametrize("invalid", [
    {"checked_source_ids": 1},
    {"checked_source_ids": [{}]},
    {"checked_source_ids": ["1"]},
    {"reference_ids": [{"block_id": "s1r1c0"}]},
    {"file_name": 123},
    {"file_name": "   "},
])
def test_malformed_missing_input_is_correctable_in_same_agent(invalid):
    async def run():
        state = {}
        proof = {"file_name": "商务规范书", "reference_ids": ["s1r1c0"],
                 "checked_source_ids": [1]}
        issue = {"topic": "a", "target": "商务规范书", "detail": "转引附件未提供",
                 "action": "provide_input", "block_ids": ["s1r1c0"]}

        class Router(ScriptedRouter):
            async def chat(self, messages, tools):
                if len(self.requests) == 2:
                    feedback = messages[-1]["data"]
                    assert feedback["status"] == "error"
                    assert "missing_input" in feedback["content"]
                    assert not state["agent_workspace"]["issues"]
                return await super().chat(messages, tools)

        router = Router([
            call("search_document", {"query": "商务规范书"}, 0),
            call("record_review", {"issues": [issue | {"missing_input": proof | invalid}]}, 1),
            call("record_review", {"issues": [issue | {"missing_input": proof}]}, 2),
            call("submit_analysis", {"final": True, "summary": "商务规范书待补"}, 3),
        ])
        graph, files = build_skill_agent(
            key=KEY, model=RoutedAgentModel(router=router), research=session([block()]),
            state=state, snapshot=skill_snapshot() | {"__analysis_flow_version__": AGENT_PROTOCOL},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop,
        )
        await invoke_module(graph, files, thread_id="missing-input-feedback", task="分析")
        assert len(router.requests) == 4
        assert state["agent_workspace"]["finalized"]
        assert len(state["agent_workspace"]["issues"]) == 1
        assert state["draft"]["business_data"]["quality_issues"][0]["missing_input"] == proof

    asyncio.run(run())
