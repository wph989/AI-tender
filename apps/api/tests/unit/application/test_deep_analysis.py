"""用真实 DeepAgents 图验证权限、工具执行、纠正与 checkpoint 恢复。"""

import asyncio
import copy
import json

import pytest
from langchain_core.messages import AIMessage, message_to_dict
from langgraph.checkpoint.memory import InMemorySaver
from test_analysis_research import block, session

from tender.application.analysis_research import AgentLimits
from tender.application.analysis_skills import verify_items
from tender.application.deep_analysis import (
    RoutedAgentModel,
    build_module_agent,
    invoke_module,
    split_absence_claims,
    validate_project_claims,
)
from tender.ports.llm import Completion

KEY = "project_basic_info_parsing"
SKILL = {
    KEY
    + "/SKILL.md": "---\nname: project_basic_info_parsing\ndescription: 分析概况\n---\n检索项目概况"
}


class ScriptedRouter:
    def __init__(self, calls):
        self.calls = list(calls)
        self.requests = []

    async def chat(self, messages, tools):
        self.requests.append((messages, tools))
        call = self.calls.pop(0)
        return Completion(
            content="",
            model="fixture",
            agent_message=message_to_dict(AIMessage(content="", tool_calls=[call])),
        )


def call(name, args, number):
    return {"name": name, "args": args, "id": "call_" + str(number), "type": "tool_call"}


def test_graph_uses_native_tools_and_resumes_completed_checkpoint_without_model_calls():
    async def run():
        research = session([block()])
        router = ScriptedRouter(
            [
                call("read_file", {"file_path": f"/skills/{KEY}/SKILL.md"}, 1),
                call("search_document", {"query": "质保要求"}, 2),
                call(
                    "submit_analysis",
                    {
                        "items": [
                            {
                                "kind": "fact",
                                "title": "质保",
                                "text": "质保三年",
                                "presentation": "paragraph",
                                "cells": {},
                                "citations": [{"block_id": "s1r1c0", "quote": "质保三年"}],
                            }
                        ],
                        "relations": [],
                        "research_summary": "检索质保条款，未发现本模块概况事实",
                        "final": False,
                    },
                    3,
                ),
                call(
                    "submit_analysis",
                    {
                        "items": [],
                        "relations": [],
                        "research_summary": "已完成检索与分批提交",
                    },
                    4,
                ),
            ]
        )
        state, saved, reserved = {}, [], []

        async def save(value):
            saved.append(copy.deepcopy(value))

        async def reserve():
            reserved.append(True)

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=reserve,
            save=save,
        )
        await invoke_module(graph, files, thread_id="module1", task="分析项目概况")
        names = {t["function"]["name"] for t in router.requests[0][1]}
        assert names == {
            "read_file",
            "list_documents",
            "search_document",
            "search_knowledge",
            "read_document",
            "submit_analysis",
        }
        assert state["draft"]["items"][0]["citations"][0]["quote"] == "质保三年"
        assert len(reserved) == 4
        assert saved[-2]["staged_items"][0]["text"] == "质保三年"
        assert "draft" not in saved[-2]
        assert saved[-1]["research"]["seen"]
        await invoke_module(graph, files, thread_id="module1", task="不能重复执行")
        assert len(router.requests) == 4

    asyncio.run(run())


def test_invalid_submission_can_be_corrected_and_skill_path_is_denied():
    async def run():
        research = session([block()])
        router = ScriptedRouter(
            [
                call("read_file", {"file_path": "/skills/other/SKILL.md"}, 1),
                call(
                    "submit_analysis",
                    {"items": [], "relations": [], "research_summary": "未检索就提交"},
                    2,
                ),
                call("search_document", {"query": "质保"}, 3),
                call(
                    "submit_analysis",
                    {"items": [], "relations": [], "research_summary": "检索质保，概况无相关内容"},
                    4,
                ),
            ]
        )
        state = {}

        async def noop(*_):
            pass

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
        )
        await invoke_module(graph, files, thread_id="module2", task="分析")
        first = state["tool_results"]["call_1"]["data"]["content"]
        assert "denied" in first.lower()
        assert state["invalid_submissions"] == 1
        assert "draft" in state
        assert len(router.requests) == 4

    asyncio.run(run())


def test_tool_result_replays_after_crash_without_duplicate_retrieval():
    async def run():
        checkpointer = InMemorySaver()
        state, persisted = {}, {}
        research = session([block()])
        router = ScriptedRouter(
            [
                call("search_document", {"query": "质保"}, 1),
                call(
                    "submit_analysis",
                    {
                        "items": [],
                        "relations": [],
                        "research_summary": "已检索质保，无本模块其它事实",
                    },
                    2,
                ),
            ]
        )

        async def crash_save(value):
            persisted.update(copy.deepcopy(value))
            raise ConnectionError("模拟工具持久化后、图提交前崩溃")

        async def noop(*args):
            pass

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=checkpointer,
            reserve_tool=noop,
            save=crash_save,
        )
        with pytest.raises(ConnectionError):
            await invoke_module(graph, files, thread_id="crash", task="分析")
        restored = session([block()])
        restored.seen = persisted["research"]["seen"]
        restored.events = persisted["research"]["events"]
        restored.tool_calls = persisted["research"]["tool_calls"]
        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=restored,
            state=persisted,
            snapshot=SKILL,
            checkpointer=checkpointer,
            reserve_tool=noop,
            save=noop,
        )
        await invoke_module(graph, files, thread_id="crash", task="恢复")
        assert "draft" in persisted
        assert restored.tool_calls == 1
        assert len(router.requests) == 2

    asyncio.run(run())


def test_context_compaction_preserves_original_evidence_and_only_writes_history():
    class SummaryRouter(ScriptedRouter):
        summaries = 0

        async def chat(self, messages, tools):
            if not tools:
                self.summaries += 1
                return Completion(
                    content="",
                    model="fixture",
                    agent_message=message_to_dict(
                        AIMessage(content="已读质保条款，需要从原文证据账补读；摘要不作为引用。")
                    ),
                )
            return await super().chat(messages, tools)

    async def run():
        original = block() | {"content": "质保三年。" * 2500}
        research = session([original], limits=AgentLimits(context_tokens=8000))
        router = SummaryRouter(
            [
                call("search_document", {"query": "质保"}, 1),
                call("read_document", {"source_id": 1, "offset": 0, "limit": 1}, 2),
                call("search_document", {"query": "质量保证"}, 3),
                call(
                    "submit_analysis",
                    {
                        "items": [],
                        "relations": [],
                        "research_summary": "已检索质保并在压缩后补读原文",
                    },
                    4,
                ),
            ]
        )

        async def noop(*args):
            pass

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state={},
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
        )
        result = await invoke_module(graph, files, thread_id="compact", task="分析")
        assert router.summaries > 0
        assert research.seen[original["block_id"]]["content"] == original["content"]
        created = set(result["files"]) - set(files)
        assert created and all(path.startswith("/conversation_history/") for path in created)
        assert result["files"][f"/skills/{KEY}/SKILL.md"] == files[f"/skills/{KEY}/SKILL.md"]

    asyncio.run(run())


@pytest.mark.parametrize(
    "title,text,refs",
    [
        ("条款未约定", "文件未约定违约金", [(10, 1, "质保三年")]),
        ("报价", "文件未明示税率", [(10, 1, "报价包含税费")]),
        ("限价", "未划分标段，全项目适用", [(10, 1, "最高限价78万元")]),
        ("历史建议", "本项目三年，历史五年", [(20, 2, "历史五年")]),
        ("交货期", "补充通知调整为45日", [(10, 2, "调整为45日")]),
    ],
)
def test_unsupported_absence_reference_only_and_one_sided_revision_are_rejected(title, text, refs):
    item = {
        "title": title,
        "text": text,
        "citations": [{"project_id": p, "source_id": s, "quote": q} for p, s, q in refs],
    }
    with pytest.raises(ValueError):
        validate_project_claims([item], 10)


def test_explicit_negative_requirement_and_two_sided_revision_are_accepted():
    validate_project_claims(
        [
            {
                "title": "职称",
                "text": "不要求特定职称",
                "citations": [{"project_id": 10, "source_id": 1, "quote": "不要求特定职称"}],
            },
            {
                "title": "交货期",
                "text": "补充通知调整为45日",
                "citations": [
                    {"project_id": 10, "source_id": 1, "quote": "原交货期30日"},
                    {"project_id": 10, "source_id": 2, "quote": "调整为45日"},
                ],
            },
        ],
        10,
    )


def test_split_absence_claims_routes_gaps_and_keeps_scope_errors_strict():
    gap = {
        "title": "条款未约定",
        "text": "文件未约定违约金",
        "citations": [{"project_id": 10, "source_id": 1, "quote": "质保三年"}],
    }
    valid = {
        "title": "质保",
        "text": "质保三年",
        "citations": [{"project_id": 10, "source_id": 1, "quote": "质保三年"}],
    }
    reference_only = {
        "title": "历史",
        "text": "历史五年",
        "citations": [{"project_id": 20, "source_id": 2, "quote": "历史五年"}],
    }
    kept, gaps = split_absence_claims([gap, valid, reference_only], 10)
    assert gaps == [gap] and kept == [valid, reference_only]
    # 缺项目引用的条目不能借“缺口”之名绕开严格校验
    with pytest.raises(ValueError):
        validate_project_claims(kept, 10)


def test_absence_gap_item_is_moved_into_summary_without_rejecting():
    async def run():
        research = session([block()])
        router = ScriptedRouter(
            [
                call("search_document", {"query": "质保要求"}, 1),
                call(
                    "submit_analysis",
                    {
                        "items": [
                            {
                                "kind": "fact",
                                "title": "质保",
                                "text": "质保三年",
                                "presentation": "paragraph",
                                "cells": {},
                                "citations": [{"block_id": "s1r1c0", "quote": "质保三年"}],
                            },
                            {
                                "kind": "insufficient",
                                "title": "质保金",
                                "text": "文件未约定质保金比例",
                                "presentation": "paragraph",
                                "cells": {},
                                "citations": [{"block_id": "s1r1c0", "quote": "质保三年"}],
                            },
                        ],
                        "relations": [],
                        "research_summary": "已检索质保条款",
                    },
                    2,
                ),
            ]
        )
        state = {}

        async def noop(*_):
            pass

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
        )
        await invoke_module(graph, files, thread_id="gap-routing", task="分析")
        # 缺口条目不能作为结论，由运行时确定性转入检索总结，避免整批被拒
        assert [item["text"] for item in state["draft"]["items"]] == ["质保三年"]
        assert "文件未约定质保金比例" in state["draft"]["research_summary"]
        assert state["draft"]["research_summary"].startswith("已检索质保条款")
        assert "invalid_submissions" not in state

    asyncio.run(run())


def test_scope_and_schema_errors_are_bounded_feedback_without_leaking_bad_draft():
    async def run():
        research = session([block()], limits=AgentLimits(context_tokens=128000))
        router = ScriptedRouter(
            [
                call("read_document", {"source_id": 99, "offset": 0}, 1),
                call("search_document", {"query": "质保"}, 2),
                call(
                    "submit_analysis",
                    {"items": [{"text": "不可回填的大草稿" * 2000}], "relations": []},
                    3,
                ),
                call(
                    "submit_analysis",
                    {"items": [], "relations": [], "research_summary": "已检索，无相关事项"},
                    4,
                ),
            ]
        )
        state = {}

        async def noop(*args):
            pass

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
        )
        await invoke_module(graph, files, thread_id="bounded-errors", task="分析")
        assert state["tool_results"]["call_1"]["data"]["status"] == "error"
        error = state["tool_results"]["call_3"]["data"]["content"]
        assert len(error) < 800 and "不可回填的大草稿" not in error
        assert "research_summary" in error
        assert state["invalid_submissions"] == 1
        assert "draft" in state
        assert set(research.seen) == {"s1r1c0"}

    asyncio.run(run())


def test_support_review_rejects_unsupported_claim_even_when_model_flag_is_true():
    class Reviewer:
        async def complete(self, prompt):
            assert '"verification"' not in prompt
            return Completion(
                content=json.dumps(
                    {
                        "reviews": [
                            {
                                "supported": True,
                                "unsupported_claims": ["引文仅说明限价，不能证明全部标段适用"],
                            }
                        ]
                    }
                ),
                model="fixture",
            )

    item = {
        "title": "限价",
        "text": "78万元，全部标段适用",
        "cells": {},
        "citations": [{"quote": "最高限价78万元"}],
        "verification": "supported",
    }
    asyncio.run(verify_items(Reviewer(), [item], explain=True))
    assert item["verification"] == "unsupported"
    assert "全部标段" in item["verification_issues"][0]


@pytest.mark.parametrize(
    "result",
    [
        {"supported": [True]},
        {"reviews": [{"supported": True}]},
        {"reviews": [{"supported": True, "unsupported_claims": [None]}]},
    ],
)
def test_support_review_fails_closed_when_claim_review_is_missing(result):
    class Reviewer:
        async def complete(self, prompt):
            return Completion(content=json.dumps(result), model="fixture")

    with pytest.raises(ValueError, match="逐项断言"):
        asyncio.run(verify_items(Reviewer(), [{"title": "限价"}], explain=True))
