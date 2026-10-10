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
from tender.application.knowledge import validate_items
from tender.domain.errors import ExtractionUnavailable, InvalidModelOutput, ModelOutputTruncated
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
            agent_message=message_to_dict(
                call if isinstance(call, AIMessage) else AIMessage(content="", tool_calls=[call])
            ),
        )


def call(name, args, number):
    if name == "submit_analysis":
        args = {"final": True, **args}
    return {"name": name, "args": args, "id": "call_" + str(number), "type": "tool_call"}


def submitted_field(field, value, quote="质保三年", block_id="s1r1c0"):
    """构造一条字段-值条目：field 是字段名，证据逐值绑定在 values 上。"""
    return {
        "field": field,
        "group": "",
        "sort_order": 0,
        "values": [{"value": value, "citations": [{"block_id": block_id, "quote": quote}]}],
        "note": "",
    }


def test_narrative_response_must_continue_to_validated_submission():
    async def run():
        research = session([block()])
        router = ScriptedRouter(
            [
                call("search_document", {"query": "质保"}, 1),
                AIMessage(content="## 解析完成\n质保三年。"),
                call(
                    "submit_analysis",
                    {
                        "fields": [submitted_field("质保", "质保三年")],
                        "relations": [],
                        "research_summary": "已检索并核对质保原文",
                    },
                    2,
                ),
            ]
        )
        state, saved = {}, []

        async def save(value):
            saved.append(copy.deepcopy(value))

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
            save=save,
        )
        await invoke_module(graph, files, thread_id="narrative-recovery", task="分析")
        # 后备模型常返回自然语言；它不能成为完成标志，也不能直接写入报告。
        assert len(router.requests) == 3
        assert state["draft"]["fields"][0]["values"][0]["citations"][0]["quote"] == "质保三年"
        assert "submit_analysis" in router.requests[-1][0][-1]["data"]["content"]
        assert any(s.get("consecutive_unsubmitted_responses") == 1 for s in saved)

    asyncio.run(run())


def test_repeated_narrative_responses_stop_with_bounded_corrections():
    async def run():
        router = ScriptedRouter([AIMessage(content="分析已完成") for _ in range(3)])
        state = {}

        async def noop(*args):
            pass

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=session([block()]),
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
        )
        with pytest.raises(ValueError, match="未调用.*工具"):
            await invoke_module(graph, files, thread_id="narrative-limit", task="分析")
        assert len(router.requests) == 3
        assert "draft" not in state

    asyncio.run(run())


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
                        "fields": [submitted_field("质保", "质保三年")],
                        "relations": [],
                        "research_summary": "检索质保条款，未发现本模块概况事实",
                        "final": False,
                    },
                    3,
                ),
                call(
                    "submit_analysis",
                    {
                        "fields": [],
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
        assert state["draft"]["fields"][0]["values"][0]["citations"][0]["quote"] == "质保三年"
        assert len(reserved) == 4
        assert saved[-2]["staged_items"][0]["values"][0]["value"] == "质保三年"
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
                    {"fields": [], "relations": [], "research_summary": "未检索就提交"},
                    2,
                ),
                call("search_document", {"query": "质保"}, 3),
                call(
                    "submit_analysis",
                    {"fields": [], "relations": [], "research_summary": "检索质保，概况无相关内容"},
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
                        "fields": [],
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
                        "fields": [],
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
    field = {
        "field": title,
        "values": [
            {
                "value": text,
                "citations": [{"project_id": p, "source_id": s, "quote": q} for p, s, q in refs],
            }
        ],
    }
    with pytest.raises(ValueError):
        validate_project_claims([field], 10)


def test_explicit_negative_requirement_and_two_sided_revision_are_accepted():
    validate_project_claims(
        [
            {
                "field": "职称",
                "values": [
                    {
                        "value": "不要求特定职称",
                        "citations": [
                            {"project_id": 10, "source_id": 1, "quote": "不要求特定职称"}
                        ],
                    }
                ],
            },
            {
                "field": "交货期",
                "values": [
                    {
                        "value": "补充通知调整为45日",
                        "citations": [
                            {"project_id": 10, "source_id": 1, "quote": "原交货期30日"},
                            {"project_id": 10, "source_id": 2, "quote": "调整为45日"},
                        ],
                    }
                ],
            },
        ],
        10,
    )


def test_revision_keeps_original_and_amendment_citations_after_alignment():
    """原条款用于证明修订前状态，不能因不含修订后的值就改引到补充文件。"""
    original = block() | {"content": "原交货期30日"}
    amendment = block(2, 10) | {"content": "补充通知调整为45日"}
    items = validate_items(
        [{
            "field": "交货期",
            "values": [{
                "value": "补充通知调整为45日",
                "citations": [
                    {"block_id": row["block_id"], "quote": row["content"]}
                    for row in (original, amendment)
                ],
            }],
        }],
        {row["block_id"]: row for row in (original, amendment)},
    )
    validate_project_claims(items, 10)
    refs = items[0]["values"][0]["citations"]
    assert [(ref["source_id"], ref["quote"]) for ref in refs] == [
        (1, "原交货期30日"), (2, "补充通知调整为45日")
    ]


def test_split_absence_claims_routes_gaps_and_keeps_scope_errors_strict():
    gap = {
        "field": "条款未约定",
        "values": [
            {
                "value": "文件未约定违约金",
                "citations": [{"project_id": 10, "source_id": 1, "quote": "质保三年"}],
            }
        ],
    }
    valid = {
        "field": "质保",
        "values": [
            {
                "value": "质保三年",
                "citations": [{"project_id": 10, "source_id": 1, "quote": "质保三年"}],
            }
        ],
    }
    reference_only = {
        "field": "历史",
        "values": [
            {
                "value": "历史五年",
                "citations": [{"project_id": 20, "source_id": 2, "quote": "历史五年"}],
            }
        ],
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
                        "fields": [
                            submitted_field("质保", "质保三年"),
                            submitted_field("质保金", "文件未约定质保金比例"),
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
        assert [item["values"][0]["value"] for item in state["draft"]["fields"]] == ["质保三年"]
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
                    {"fields": [{"text": "不可回填的大草稿" * 2000}], "relations": []},
                    3,
                ),
                call(
                    "submit_analysis",
                    {"fields": [], "relations": [], "research_summary": "已检索，无相关事项"},
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
        "field": "限价",
        "values": [
            {
                "value": "78万元，全部标段适用",
                "citations": [{"quote": "最高限价78万元"}],
            }
        ],
        "verification": "supported",
    }
    asyncio.run(verify_items(Reviewer(), [item], explain=True))
    assert item["verification"] == "unsupported"
    assert "全部标段" in item["verification_issues"][0]


@pytest.mark.parametrize(
    "note",
    [
        "供应商无需承担质保义务",
        "节点类型：材料章节；层级：2；上级路径：投标函",
    ],
)
def test_support_review_checks_claims_in_notes(note):
    class Reviewer:
        async def complete(self, prompt):
            payload = json.loads(prompt.rsplit("\n", 1)[-1])[0]
            # 正文值正确不能掩盖备注的免责断言或无依据的父级，校验器必须拿到备注。
            assert payload["note"] == note
            assert "note和group中的业务断言须由本字段的引用支持" in prompt
            return Completion(
                content=json.dumps(
                    {
                        "reviews": [
                            {
                                "supported": False,
                                "unsupported_claims": ["备注断言没有原文支持"],
                            }
                        ]
                    }
                ),
                model="fixture",
            )

    item = submitted_field("质保", "质保三年") | {"note": note}
    asyncio.run(verify_items(Reviewer(), [item], explain=True))
    assert item["verification"] == "unsupported"


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

    with pytest.raises(InvalidModelOutput, match="逐项断言"):
        asyncio.run(verify_items(Reviewer(), [{"field": "限价", "values": []}], explain=True))


def test_out_of_range_read_arguments_return_error_message_and_keep_module_alive():
    async def run():
        research = session([block()])
        router = ScriptedRouter(
            [
                call("read_document", {"source_id": 1, "offset": -1, "limit": 6}, 1),
                call("search_document", {"query": "质保"}, 2),
                call(
                    "submit_analysis",
                    {
                        "fields": [],
                        "relations": [],
                        "research_summary": "参数越界提示后继续检索并提交",
                    },
                    3,
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
        await invoke_module(graph, files, thread_id="bad-read-args", task="分析")
        # 越界参数只回传错误提示，模型可改用正确参数继续，模块不因此失败。
        assert state["tool_results"]["call_1"]["data"]["status"] == "error"
        assert "1到12块" in state["tool_results"]["call_1"]["data"]["content"]
        assert state["draft"]["fields"] == []

    asyncio.run(run())


def test_evidence_budget_feedback_keeps_module_alive():
    async def run():
        research = session([block(), block(2, 20)], limits=AgentLimits(max_evidence_blocks=1))
        router = ScriptedRouter(
            [
                call("search_document", {"query": "质保"}, 1),
                call("read_document", {"source_id": 2, "offset": 0}, 2),
                call(
                    "submit_analysis",
                    {
                        "fields": [],
                        "relations": [],
                        "research_summary": "证据预算已满，基于已有证据提交换取支持性校验",
                    },
                    3,
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
        await invoke_module(graph, files, thread_id="evidence-cap", task="分析")
        # 预算提示回传模型而不是终止模块；补跑继承的历史证据因此不会让模块立即失败。
        assert state["tool_results"]["call_2"]["data"]["status"] == "error"
        assert "证据块预算" in state["tool_results"]["call_2"]["data"]["content"]
        assert state["draft"]["fields"] == []

    asyncio.run(run())


def test_valid_batches_reset_consecutive_submission_errors_and_keep_all_results():
    async def run():
        script = [call("search_document", {"query": "质保"}, 1)]
        for index in range(3):
            script.extend(
                [
                    call("submit_analysis", {"fields": [], "relations": []}, 2 + index * 2),
                    call(
                        "submit_analysis",
                        {
                            "fields": [submitted_field(f"质保事项{index}", "质保三年")],
                            "relations": [],
                            "research_summary": "分批核对原文",
                            "final": index == 2,
                        },
                        3 + index * 2,
                    ),
                ]
            )
        router, state = ScriptedRouter(script), {}

        async def noop(*args):
            pass

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=session([block()]),
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
        )
        await invoke_module(graph, files, thread_id="intermittent-corrections", task="分析")
        assert len(state["draft"]["fields"]) == 3
        assert state["invalid_submissions"] == 3
        assert state["consecutive_invalid_submissions"] == 0
        schema = next(
            t["function"]["parameters"]
            for t in router.requests[0][1]
            if t["function"]["name"] == "submit_analysis"
        )
        # 限制单批输出体积，避免整个大模块在一个请求里生成数万token。
        assert schema["properties"]["fields"]["maxItems"] == 3
        assert "outline_nodes" not in schema["properties"]

    asyncio.run(run())


def test_final_submission_error_is_saved_with_the_actionable_reason():
    async def run():
        router = ScriptedRouter(
            [call("submit_analysis", {"fields": [], "relations": []}, i) for i in range(3)]
        )
        state = {}

        async def noop(*args):
            pass

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=session([block()]),
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
        )
        with pytest.raises(ValueError, match="research_summary"):
            await invoke_module(graph, files, thread_id="last-error", task="分析")
        assert state["tool_results"]["call_2"]["data"]["status"] == "error"
        assert "draft" not in state

    asyncio.run(run())


def test_same_field_submitted_in_two_batches_merges_into_one_row():
    """同一字段跨批次补交只出现一行：值取并集去重，引用按位置去重。"""

    async def run():
        row = block() | {"content": "质保三年；质保五年"}
        research = session([row])
        script = [
            call("search_document", {"query": "质保"}, 1),
            call(
                "submit_analysis",
                {
                    "fields": [submitted_field("质保期", "质保三年")],
                    "relations": [],
                    "research_summary": "先提交第一批",
                    "final": False,
                },
                2,
            ),
            call(
                "submit_analysis",
                {
                    "fields": [submitted_field("质保期", "质保五年", quote="质保五年")],
                    "relations": [],
                    "research_summary": "补充第二批",
                    "final": True,
                },
                3,
            ),
        ]
        router, state = ScriptedRouter(script), {}

        async def noop(*args):
            pass

        async def verify(items):
            for entry in items:
                entry["verification"] = "supported"

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
            review_support=verify,
        )
        await invoke_module(graph, files, thread_id="merge-same-field", task="分析")
        fields = state["draft"]["fields"]
        assert len(fields) == 1
        assert [value["value"] for value in fields[0]["values"]] == ["质保三年", "质保五年"]

    asyncio.run(run())


@pytest.mark.parametrize("relation_supported", [True, False])
def test_outline_batches_preserve_parent_relationships_and_verify_each_result_once(
    relation_supported,
):
    async def run():
        key = "bid_format_outline_parsing"
        raw = block() | {"content": "投标文件由投标函、报价表组成。"}
        nodes = [
            {
                "id": node_id,
                "name": name,
                "node_type": kind,
                "parent_id": parent,
                "requirements": [],
                "citations": [{"block_id": "s1r1c0", "quote": raw["content"]}],
            }
            for node_id, name, kind, parent in [
                ("root", "投标文件", "group", None),
                ("letter", "投标函", "section", "root"),
            ]
        ]
        router = ScriptedRouter(
            [
                call("search_document", {"query": "投标文件格式"}, 1),
                call(
                    "submit_analysis",
                    {"outline_nodes": nodes[:1], "research_summary": "先核对父级", "final": False},
                    2,
                ),
                call(
                    "submit_analysis",
                    {"outline_nodes": nodes[1:], "research_summary": "再核对材料", "final": False},
                    3,
                ),
                call(
                    "submit_analysis",
                    {"outline_nodes": [], "research_summary": "已提交全部格式"},
                    4,
                ),
            ]
        )
        state, reviewed, reviewed_notes, reviewed_relations = {}, [], [], []

        async def noop(*args):
            pass

        async def verify(items):
            fields = [item for item in items if item.get("kind") != "relation"]
            reviewed.extend(item["field"] for item in fields)
            # 字段备注中的归属必须送审，最终派生关系也须单独验证后才能进入图谱。
            reviewed_notes.extend(item["note"] for item in fields)
            reviewed_relations.extend(item for item in items if item.get("kind") == "relation")
            for item in items:
                item["verification"] = (
                    "unsupported"
                    if item.get("kind") == "relation" and not relation_supported
                    else "supported"
                )

        graph, files = build_module_agent(
            key=key,
            model=RoutedAgentModel(router=router),
            research=session([raw]),
            state=state,
            snapshot={key + "/SKILL.md": SKILL[KEY + "/SKILL.md"]},
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
            review_support=verify,
        )
        await invoke_module(graph, files, thread_id="outline-batches", task="分析格式")
        assert reviewed == ["投标文件", "投标函"]
        assert len(reviewed_relations) == 1
        assert all("层级：" in note for note in reviewed_notes)
        assert len(state["draft"]["fields"]) == 2
        assert "上级路径：投标文件" in state["draft"]["fields"][1]["note"]
        assert state["draft"]["fields"][1]["verification"] == "supported"
        assert len(state["draft"]["relations"]) == int(relation_supported)

    asyncio.run(run())


@pytest.mark.parametrize("same_requirement", [False, True])
def test_outline_keeps_same_named_nodes_under_different_parents(same_requirement):
    """不同父级下的同名材料各自保留；同名同要求也不能共用结果 id 或重复送审。"""
    async def run():
        key = "bid_format_outline_parsing"
        second_requirement = "须盖章" if same_requirement else "须签字"
        content = f"商务标。甲标段营业执照须盖章。乙标段营业执照{second_requirement}。"
        row = block() | {"content": content}
        nodes = [{
            "id": node_id, "name": name, "parent_id": parent, "node_type": kind,
            "requirements": requirements,
            "citations": [{"block_id": row["block_id"], "quote": content}],
        } for node_id, name, parent, kind, requirements in [
            ("root", "商务标", None, "group", []),
            ("lot-a", "甲标段", "root", "section", []),
            ("license-a", "营业执照", "lot-a", "section", ["须盖章"]),
            ("lot-b", "乙标段", "root", "section", []),
            ("license-b", "营业执照", "lot-b", "section", [second_requirement]),
        ]]
        router = ScriptedRouter([
            call("search_document", {"query": "格式"}, 1),
            call("submit_analysis", {
                "outline_nodes": nodes[:3], "research_summary": "甲标段", "final": False,
            }, 2),
            call("submit_analysis", {
                "outline_nodes": nodes[3:], "research_summary": "乙标段", "final": False,
            }, 3),
            call("submit_analysis", {
                "outline_nodes": [], "research_summary": "已提交全部格式",
            }, 4),
        ])
        state, reviewed = {}, []

        async def noop(*args):
            pass

        async def verify(items):
            reviewed.extend(copy.deepcopy(item) for item in items if item.get("kind") != "relation")
            for item in items:
                item["verification"] = "supported"

        graph, files = build_module_agent(
            key=key, model=RoutedAgentModel(router=router), research=session([row]),
            state=state, snapshot={key + "/SKILL.md": SKILL[KEY + "/SKILL.md"]},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop, review_support=verify,
        )
        await invoke_module(graph, files, thread_id="outline-same-name", task="分析格式")
        fields = state["draft"]["fields"]
        assert len(fields) == len({item["id"] for item in fields}) == 5
        licenses = [item for item in fields if item["field"] == "营业执照"]
        assert [item["note"].split("上级路径：")[1] for item in licenses] == [
            "商务标 / 甲标段", "商务标 / 乙标段"
        ]
        assert [item["values"][0]["value"] for item in licenses] == ["须盖章", second_requirement]
        assert len([item for item in reviewed if item["field"] == "营业执照"]) == 2
        assert len(state["draft"]["relations"]) == 4

    asyncio.run(run())


def test_unmodified_staged_fields_are_reused_without_second_review_before_final_submission():
    async def run():
        from tender.application.knowledge import validate_items

        research = session([block()])
        await research.search("质保", "project")
        item = validate_items(
            [
                {
                    "field": "质保",
                    "values": [
                        {
                            "value": "质保三年",
                            "citations": [{"block_id": "s1r1c0", "quote": "质保三年"}],
                        }
                    ],
                }
            ],
            research.seen,
        )[0]
        item["verification"] = "supported"
        # 已通过校验的暂存字段在最终提交时标记为 reusable，不再重复送审；
        # 只有新增或修改过的字段才需要再次校验。
        state = {"staged_items": [item], "staged_items_verified": True}
        reviewed = []
        router = ScriptedRouter(
            [
                call(
                    "submit_analysis",
                    {
                        "fields": [],
                        "relations": [],
                        "research_summary": "继续上次暂存结果并完成",
                    },
                    1,
                )
            ]
        )

        async def noop(*args):
            pass

        async def verify(items):
            reviewed.extend(copy.deepcopy(items))
            for entry in items:
                entry["verification"] = "supported"

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
            review_support=verify,
        )
        await invoke_module(graph, files, thread_id="carried-reuse", task="继续分析")
        assert reviewed == []
        assert state["draft"]["fields"][0]["verification"] == "supported"

    asyncio.run(run())


@pytest.mark.parametrize("error_type", [ExtractionUnavailable, InvalidModelOutput])
def test_review_failure_terminates_module_but_keeps_verified_fields(error_type):
    """校验请求失败或格式纠正耗尽后不再让主 Agent 原样重交（次数会相乘），已通过字段必须保留。"""

    async def run():
        research = session([block()])
        state = {}
        router = ScriptedRouter(
            [
                call("search_document", {"query": "质保"}, 1),
                call(
                    "submit_analysis",
                    {
                        "fields": [submitted_field("质保", "质保三年")],
                        "relations": [],
                        "research_summary": "先暂存一条",
                        "final": False,
                    },
                    2,
                ),
                call(
                    "submit_analysis",
                    {
                        "fields": [submitted_field("质保期", "三年")],
                        "relations": [],
                        "research_summary": "提交第二条",
                        "final": True,
                    },
                    3,
                ),
            ]
        )
        saved = []

        async def noop(*args):
            pass

        async def verify(items):
            # 一批一次送审：第一批通过后立即暂存；第二批服务失败只终止模块，不带坏已存成果。
            if items[0]["field"] == "质保期":
                raise error_type("校验服务失败或响应结构不完整")
            for item in items:
                item["verification"] = "supported"

        async def save(current):
            saved.append([entry["field"] for entry in current.get("staged_items", [])])

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=save,
            review_support=verify,
        )
        with pytest.raises(RuntimeError, match="已通过字段保留"):
            await invoke_module(graph, files, thread_id="review-fatal", task="分析")
        # 已通过批次逐条落库；失败批次不写成果，模型没有被要求重交整批，避免校验次数相乘。
        assert [entry["field"] for entry in state["staged_items"]] == ["质保"]
        assert ["质保"] in saved
        assert router.calls == []
        assert "pending_final" not in state

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["unsupported", "truncated"])
def test_failed_final_review_requires_a_new_final_submission(failure):
    """最终提交失败后允许补读和分批纠正，直到新的 final=true 才能完成。"""
    async def run():
        router = ScriptedRouter([
            call("search_document", {"query": "质保"}, 1),
            call("submit_analysis", {
                "fields": [submitted_field("质保", "质保五年")],
                "relations": [], "research_summary": "首次提交",
            }, 2),
            call("read_document", {"source_id": 1, "offset": 0, "limit": 1}, 3),
            call("submit_analysis", {
                "fields": [submitted_field("质保", "质保三年")],
                "relations": [], "research_summary": "已纠正，继续核对", "final": False,
            }, 4),
            call("submit_analysis", {
                "fields": [], "relations": [], "research_summary": "重新确认完成",
            }, 5),
        ])
        state, saved, reviewed = {}, [], []

        async def noop(*args):
            pass

        async def save(current):
            saved.append(copy.deepcopy(current))

        async def verify(items):
            reviewed.append(items[0]["values"][0]["value"])
            if len(reviewed) == 1 and failure == "truncated":
                raise ModelOutputTruncated("校验输出截断")
            for item in items:
                item["verification"] = "unsupported" if len(reviewed) == 1 else "supported"
                item["verification_issues"] = ["原文为三年"] if len(reviewed) == 1 else []

        graph, files = build_module_agent(
            key=KEY, model=RoutedAgentModel(router=router), research=session([block()]),
            state=state, snapshot=SKILL, checkpointer=InMemorySaver(), reserve_tool=noop,
            save=save, review_support=verify,
        )
        await invoke_module(graph, files, thread_id="failed-final-" + failure, task="分析")
        assert router.calls == []
        assert reviewed == ["质保五年", "质保三年"]
        assert state["draft"]["research_summary"] == "重新确认完成"
        assert state["draft"]["fields"][0]["values"][0]["value"] == "质保三年"
        # 补读后的持久状态也必须撤销收尾意图，否则恢复检查点时仍可能提前结束。
        after_read = next(s for s in saved if "call_3" in s.get("tool_results", {}))
        assert "pending_final" not in after_read and "draft" not in after_read

    asyncio.run(run())


def test_truncated_review_asks_for_smaller_batches_and_stops_after_three():
    """校验输出被截断时结果不算数：回传拆分提示，第三次仍截断则终止且不写任何成果。"""

    async def run():
        research = session([block()])
        state = {}
        router = ScriptedRouter(
            [
                call("search_document", {"query": "质保"}, 1),
                *[
                    call(
                        "submit_analysis",
                        {
                            "fields": [submitted_field("质保", "质保三年")],
                            "relations": [],
                            "research_summary": "提交质保",
                        },
                        number,
                    )
                    for number in (2, 3, 4)
                ],
            ]
        )
        attempts = []

        async def noop(*args):
            pass

        async def verify(items):
            attempts.append(len(items))
            raise ModelOutputTruncated("校验输出达到token上限")

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
            review_support=verify,
        )
        with pytest.raises(RuntimeError, match="拆分纠正已达3次上限"):
            await invoke_module(graph, files, thread_id="review-truncated", task="分析")
        assert attempts == [1, 1, 1]
        # 校验是 Agent 图的节点：登记工具本身成功，截断反馈作为运行时消息回给主 Agent。
        assert state["tool_results"]["call_2"]["data"]["status"] == "success"
        assert any(
            "每次只提交1条" in str(message.get("data", {}).get("content", ""))
            for messages, _tools in router.requests
            for message in messages
        )
        assert state["unavailable_submissions"] == 3
        # 截断不是字段内容错误：不占用字段纠错次数，也没有任何成果被暂存。
        assert "field_failures" not in state
        assert state.get("staged_items", []) == [] and "draft" not in state

    asyncio.run(run())


def test_repeated_field_structure_errors_stop_after_three_but_keep_other_fields():
    """同一字段连续三次结构错误才终止模块；同批其它字段不受牵连，已被逐字段暂存。"""

    async def run():
        research = session([block()])
        state = {}
        # 结构合法但引用了未读块：只有这种字段才走逐字段内容纠错，而不是工具参数被直接打回。
        broken = {
            "field": "报价",
            "group": "",
            "sort_order": 0,
            "values": [
                {"value": "100万", "citations": [{"block_id": "s9r9c9", "quote": "报价"}]}
            ],
            "note": "",
        }
        router = ScriptedRouter(
            [
                call("search_document", {"query": "质保"}, 1),
                *[
                    call(
                        "submit_analysis",
                        {
                            "fields": [submitted_field("质保", "质保三年"), broken],
                            "relations": [],
                            "research_summary": "提交两条",
                        },
                        number,
                    )
                    for number in (2, 3, 4)
                ],
            ]
        )

        async def noop(*args):
            pass

        async def verify(items):
            for item in items:
                item["verification"] = "supported"

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
            review_support=verify,
        )
        with pytest.raises(RuntimeError, match="同一字段纠正已达3次上限"):
            await invoke_module(graph, files, thread_id="field-failures", task="分析")
        assert state["field_failures"] == {":报价": 3}
        assert [entry["field"] for entry in state["staged_items"]] == ["质保"]

    asyncio.run(run())


def test_omitted_final_only_stages_results_until_explicit_completion():
    async def run():
        first = call(
            "submit_analysis",
            {
                "fields": [],
                "relations": [],
                "research_summary": "第一批检索结果",
            },
            2,
        )
        first["args"].pop("final")
        router = ScriptedRouter(
            [
                call("search_document", {"query": "质保"}, 1),
                first,
                call(
                    "submit_analysis",
                    {
                        "fields": [],
                        "relations": [],
                        "research_summary": "全部检索已完成",
                        "final": True,
                    },
                    3,
                ),
            ]
        )
        state, saved = {}, []

        async def noop(*args):
            pass

        async def save(value):
            saved.append(copy.deepcopy(value))

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=session([block()]),
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=save,
        )
        await invoke_module(graph, files, thread_id="explicit-final", task="分析")
        assert len(router.requests) == 3
        assert "draft" not in saved[-2]
        assert state["draft"]["research_summary"] == "全部检索已完成"

    asyncio.run(run())


def test_support_review_batches_fields_without_mixing_their_verdicts():
    class Reviewer:
        def __init__(self):
            self.fields = []
            self.batches = []

        async def complete(self, prompt):
            batch = json.loads(prompt.rsplit("\n", 1)[-1])
            # 批量送审：一次请求覆盖至多3条，避免“字段数×提交轮次”次模型请求。
            assert 1 <= len(batch) <= 3
            self.batches.append(len(batch))
            self.fields.extend(item["field"] for item in batch)
            assert all("bbox" not in item["values"][0]["citations"][0] for item in batch)
            return Completion(
                content=json.dumps(
                    {
                        "reviews": [
                            {
                                "supported": item["field"] == "有据",
                                "unsupported_claims": []
                                if item["field"] == "有据"
                                else ["附加的适用范围无依据"],
                            }
                            for item in batch
                        ]
                    }
                ),
                model="fixture",
            )

    reviewer = Reviewer()
    items = [
        {
            "field": title,
            "values": [
                {
                    "value": "质保三年",
                    "citations": [{"quote": "质保三年", "bbox": [0, 0, 1, 1]}],
                }
            ],
        }
        for title in ("有据", "范围无据", "有据", "有据")
    ]
    asyncio.run(verify_items(reviewer, items, explain=True))
    # 4 条字段只发 2 次请求（3+1），逐条结论仍各自独立。
    assert reviewer.batches == [3, 1]
    assert reviewer.fields == ["有据", "范围无据", "有据", "有据"]
    assert [item["verification"] for item in items] == [
        "supported",
        "unsupported",
        "supported",
        "supported",
    ]


def test_submit_tool_issues_no_model_call_and_review_runs_once_per_batch():
    """提交工具只做确定性登记；支持性校验由 Agent 图一次批量发起，3条字段只发1次请求。"""

    async def run():
        research = session([block()])
        state = {}
        router = ScriptedRouter(
            [
                call("search_document", {"query": "质保"}, 1),
                call(
                    "submit_analysis",
                    {
                        "fields": [
                            submitted_field("质保", "质保三年"),
                            submitted_field("质保期", "三年"),
                            submitted_field("质保金", "三年"),
                        ],
                        "relations": [],
                        "research_summary": "三条字段一次提交",
                        "final": True,
                    },
                    2,
                ),
            ]
        )
        batches = []

        async def noop(*args):
            pass

        async def verify(items):
            # 批量送审：一批只调用一次，结论逐条写回；工具本身不得再单独送审。
            batches.append([item["field"] for item in items])
            for item in items:
                item["verification"] = "supported"

        graph, files = build_module_agent(
            key=KEY,
            model=RoutedAgentModel(router=router),
            research=research,
            state=state,
            snapshot=SKILL,
            checkpointer=InMemorySaver(),
            reserve_tool=noop,
            save=noop,
            review_support=verify,
        )
        await invoke_module(graph, files, thread_id="batched-review", task="分析")
        # 主循环请求数等于脚本轮次：提交工具没有夹带模型请求，校验不占主循环轮次。
        assert len(router.requests) == 2
        assert batches == [["质保", "质保期", "质保金"]]
        assert [entry["field"] for entry in state["draft"]["fields"]] == [
            "质保",
            "质保期",
            "质保金",
        ]

    asyncio.run(run())


def test_support_review_receives_block_text_and_neighbours_for_section_attribution():
    """摘录看不到条号归属；校验必须拿到同块原文和邻近块，否则正确条款会被反复判无依据。"""

    class Reviewer:
        def __init__(self):
            self.batch = None

        async def complete(self, prompt):
            self.batch = json.loads(prompt.rsplit("\n", 1)[-1])
            return Completion(
                content=json.dumps({"reviews": [{"supported": True, "unsupported_claims": []}]}),
                model="fixture",
            )

    evidence = {
        f"c{offset}": {
            "block_id": f"c{offset}",
            "element_id": f"e{offset}",
            "source_id": 13,
            "parse_run_id": 6,
            "offset": offset,
            "page_no": 19,
            "chapter": "",
            "content": content,
        }
        for offset, content in (
            (131, "评标办法前附表"),
            (132, "投标人须知前附表"),
            (133, "1.4.1 投标人资质条件、能力、信誉 详见第一章3. 投标人资格要求"),
            (134, "1.4.2 是否接受联合体投标 ■不接受"),
        )
    }
    items = [
        {
            "field": "资质条件",
            "values": [
                {
                    "value": "通信工程监理资质乙级及以上（投标人须知前附表第1.4.1项）",
                    "citations": [
                        {
                            "block_id": "c133",
                            "quote": "1.4.1 投标人资质条件、能力、信誉",
                            "page_no": 19,
                            "bbox": [0, 0, 1, 1],
                        }
                    ],
                }
            ],
        },
        {
            # 旧 attempt 的引文没有块身份，必须仍能按元素和原文回查上下文。
            "field": "联合体",
            "values": [
                {
                    "value": "不接受联合体投标",
                    "citations": [
                        {
                            "source_id": 13,
                            "parse_run_id": 6,
                            "element_id": "e134",
                            "quote": "1.4.2 是否接受联合体投标 ■不接受",
                        }
                    ],
                }
            ],
        },
    ]
    reviewer = Reviewer()
    asyncio.run(verify_items(reviewer, items[:1], explain=True, evidence=evidence))
    assert items[0]["verification"] == "supported"
    citation = reviewer.batch[0]["values"][0]["citations"][0]
    assert "bbox" not in citation
    assert citation["page_no"] == 19
    context = citation["block_context"]
    assert context["offset"] == 133
    assert "投标人须知前附表" in json.dumps(context, ensure_ascii=False)
    assert [row["offset"] for row in context["before"]][-1] == 132
    assert [row["offset"] for row in context["after"]] == [134]
    legacy = Reviewer()
    asyncio.run(verify_items(legacy, items[1:], explain=True, evidence=evidence))
    legacy_citation = legacy.batch[0]["values"][0]["citations"][0]
    legacy_context = legacy_citation["block_context"]
    assert legacy_context["offset"] == 134
    assert "1.4.2 是否接受联合体投标" in legacy_context["block"]
    # 没有章节/条号归属的条目只带同块原文，不展开邻近块。
    assert "before" not in legacy_context and "after" not in legacy_context
    # 未传证据的调用（例如项目问答）保持原载荷，不能凭空出现上下文。
    plain = Reviewer()
    asyncio.run(verify_items(plain, items[:1], explain=True))
    assert "block_context" not in plain.batch[0]["values"][0]["citations"][0]


def _window_evidence(rows):
    return {
        f"c{offset}": {
            "block_id": f"c{offset}",
            "element_id": f"e{offset}",
            "source_id": 13,
            "parse_run_id": 6,
            "offset": offset,
            "page_no": page,
            "chapter": "",
            "content": content,
        }
        for offset, page, content in rows
    }


def test_support_review_receives_distant_chapter_heading_without_crossing_source_or_gaps():
    """真实人员条款距离章标题20块；扩大语义上下文仍须隔离资料、版本和缺块区间。"""
    from tender.application.analysis_skills import EvidenceWindows

    class Reviewer:
        async def complete(self, prompt):
            self.batch = json.loads(prompt.rsplit("\n", 1)[-1])
            return Completion(
                content=json.dumps({"reviews": [{"supported": True, "unsupported_claims": []}]}),
                model="fixture",
            )

    evidence = _window_evidence(
        [(15, 3, "第一章招标公告")]
        + [(offset, 4, "招标公告正文。") for offset in range(16, 35)]
        + [(35, 5, "3.5 安全生产管理人员须提供安全培训合格证书。")]
    )
    evidence["c19"]["content"] = "第二章 投标人须知........19"
    evidence["c22"]["content"] = "第三章评标办法规定了相关要求。"
    evidence["c25"]["content"] = "第四章合同条款 第五章委托人要求"
    for source_id, parse_run_id in ((14, 6), (13, 7)):
        evidence[f"foreign-{source_id}-{parse_run_id}"] = evidence["c15"] | {
            "block_id": f"foreign-{source_id}-{parse_run_id}",
            "source_id": source_id,
            "parse_run_id": parse_run_id,
            "offset": 34,
            "content": "第六章其他项目",
        }
    items = [
        {
            "field": "人员证书",
            "values": [
                {
                    "value": "第一章招标公告3.5要求安全生产管理人员提供安全培训合格证书。",
                    "citations": [{"block_id": "c35", "quote": evidence["c35"]["content"]}],
                }
            ],
        }
    ]
    reviewer = Reviewer()
    asyncio.run(verify_items(reviewer, items, explain=True, evidence=evidence))
    context = reviewer.batch[0]["values"][0]["citations"][0]["block_context"]
    assert context["chapter_heading"] == {
        "offset": 15,
        "page_no": 3,
        "content": "第一章招标公告",
    }
    assert all(row["offset"] > 15 for row in context["before"])
    # 已读块回退可能缺少中途出现的新章；这种情况下宁可不提供归属候选。
    sparse = {key: row for key, row in evidence.items() if key != "c28"}
    assert "chapter_heading" not in EvidenceWindows(sparse).context({"block_id": "c35"})
    evidence["c30"]["content"] = "第二章 投标人须知"
    newer = EvidenceWindows(evidence).context({"block_id": "c35"})
    assert newer["chapter_heading"]["offset"] == 30


def test_contract_section_heading_does_not_leak_into_next_chapter():
    """通用与专用合同条款的标题离条款很远，必须保留节归属并在新章边界清除。"""
    from tender.application.analysis_skills import EvidenceWindows

    evidence = _window_evidence([(n, 5, "合同正文。") for n in range(40)])
    for offset, content in (
        (0, "第四章合同条款及格式"),
        (1, "第一节通用合同条款"),
        (25, "第二节专用合同条款"),
        (35, "第五章委托人要求"),
    ):
        evidence[f"c{offset}"]["content"] = content
    windows = EvidenceWindows(evidence)
    assert windows.context({"block_id": "c20"})["section_heading"]["offset"] == 1
    assert windows.context({"block_id": "c30"})["section_heading"]["offset"] == 25
    later = windows.context({"block_id": "c39"})
    assert later["chapter_heading"]["offset"] == 35
    assert "section_heading" not in later


def test_support_review_merges_only_physically_adjacent_blocks_for_continuation():
    """同一句被分块切开时（“并应符合投标人”/“须知前附表的规定”）必须能合并阅读，
    但缺号的已读块不能拼进去，否则会把“相邻出现”误当原文依据。"""

    class Reviewer:
        def __init__(self):
            self.prompt = ""
            self.batch = None

        async def complete(self, prompt):
            self.prompt = prompt
            self.batch = json.loads(prompt.rsplit("\n", 1)[-1])
            return Completion(
                content=json.dumps({"reviews": [{"supported": True, "unsupported_claims": []}]}),
                model="fixture",
            )

    # c276 结尾没有句号，说明同一句延续到 c277；c275 是上一节的标题块。
    evidence = _window_evidence(
        (
            (275, 37, "3.4 投标保证金"),
            (
                276,
                37,
                "3.4.1 投标人在递交投标文件的同时应按投标人须知前附表规定的金额、"
                "形式递交，并应符合投标人",
            ),
            (277, 38, "须知前附表的 规定。"),
        )
    )
    items = [
        {
            "field": "联合体投标保证金递交",
            "values": [
                {
                    "value": (
                        "联合体投标的，其投标保证金可以由牵头人递交，"
                        "并应符合投标人须知前附表的规定。"
                    ),
                    "citations": [
                        {
                            "block_id": "c276",
                            "quote": "并应符合投标人",
                            "page_no": 37,
                            "bbox": [0, 0, 1, 1],
                        }
                    ],
                }
            ],
        }
    ]
    reviewer = Reviewer()
    asyncio.run(verify_items(reviewer, items, explain=True, evidence=evidence))
    assert items[0]["verification"] == "supported"
    context = reviewer.batch[0]["values"][0]["citations"][0]["block_context"]
    assert context["continuous"].startswith("〔块275〕")
    assert "〔引文块276〕" in context["continuous"]
    assert "须知前附表的 规定。" in context["continuous"]
    # 提示词必须把连续原文讲清楚，否则校验模型仍会把跨块续句判成无依据。
    assert "continuous" in reviewer.prompt and "跨块续句" in reviewer.prompt
    assert [row["offset"] for row in context["before"]] == [275]
    assert [row["offset"] for row in context["after"]] == [277]

    # 缺号时不能拼接：c136 之前只有 c132/c133 被读取，说明中间还有未读块。
    gap_evidence = _window_evidence(
        (
            (132, 19, "投标人须知前附表"),
            (133, 19, "1.1.2 招标人  招标人名称:中国通信工程有限公司"),
            (136, 22, "3.4.1 投标保证金  投标保证金金额:6万元整（不分标段）"),
        )
    )
    gap_items = [
        {
            "field": "投标保证金金额",
            "values": [
                {
                    "value": "投标人须知前附表3.4.1规定投标保证金金额6万元整（不分标段）。",
                    "citations": [
                        {
                            "block_id": "c136",
                            "quote": "3.4.1 投标保证金  投标保证金金额:6万元整（不分标段）",
                        }
                    ],
                }
            ],
        }
    ]
    gap_reviewer = Reviewer()
    asyncio.run(verify_items(gap_reviewer, gap_items, explain=True, evidence=gap_evidence))
    gap_context = gap_reviewer.batch[0]["values"][0]["citations"][0]["block_context"]
    assert "continuous" not in gap_context
    # 归属仍可由邻近标题块核对，标题块必须随载荷发出。
    assert [row["offset"] for row in gap_context["before"]] == [132, 133]
    assert "投标人须知前附表" in json.dumps(gap_context, ensure_ascii=False)

    # 前后块都已收句时不再拼接，避免把无关的上一段/下一段当成同一句续文。
    closed_evidence = _window_evidence(
        (
            (10, 5, "第二章 投标人须知。"),
            (11, 5, "投标人须知前附表第1.4.1项规定资质条件。"),
            (12, 5, "第一章 总则。"),
        )
    )
    closed_items = [
        {
            "field": "资质条件",
            "values": [
                {
                    "value": "投标人须知前附表第1.4.1项规定资质条件。",
                    "citations": [
                        {"block_id": "c11", "quote": "投标人须知前附表第1.4.1项规定资质条件。"}
                    ],
                }
            ],
        }
    ]
    closed_reviewer = Reviewer()
    asyncio.run(verify_items(closed_reviewer, closed_items, explain=True, evidence=closed_evidence))
    closed_context = closed_reviewer.batch[0]["values"][0]["citations"][0]["block_context"]
    assert "continuous" not in closed_context
