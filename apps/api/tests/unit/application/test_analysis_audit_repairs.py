"""以真实请求和状态反例验证解析分析报告中的八类缺陷。"""

import asyncio
import copy
import json

import pytest
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    message_to_dict,
    messages_from_dict,
)
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import COMMON, noop, submission, summary_record
from test_analysis_argument_failures import request
from test_analysis_prompt_budget import FakeRequest
from test_analysis_research import block, session
from test_analysis_topic_flow import execute, prepared_flow, search
from test_deep_analysis import call

from tender.application.analysis.agent import (
    AnalysisSummarizationMiddleware,
    ResearchMiddleware,
    RoutedAgentModel,
    build_module_agent,
    context_size,
    invoke_module,
)
from tender.application.analysis.policy import load_module_skill, tool_key
from tender.application.analysis.protocol import PROTOCOL_VERSION
from tender.application.analysis.research import WorkClosed
from tender.application.analysis.search_control import TopicSearch
from tender.application.analysis.skills import skill_snapshot
from tender.application.analysis.topic_flow import FLOW_KEY, FLOW_VERSION, TopicIncomplete
from tender.ports.llm.chat import Completion


@pytest.mark.parametrize("protocol", [FLOW_VERSION, PROTOCOL_VERSION])
@pytest.mark.parametrize("key,rule", [
    ("project_basic_info_parsing", "单文件、同一项目或只有一个已知标段"),
    ("scoring_standard_parsing", "分值加总只用于核对"),
    ("bid_format_outline_parsing", "目录是“功能角色”"),
])
def test_actual_second_request_keeps_domain_rules_and_counter_sees_them(
    monkeypatch, key, rule, protocol,
):
    class Captured(Exception):
        pass

    class Router:
        def __init__(self):
            self.requests = []

        async def chat(self, messages, tools):
            self.requests.append(messages)
            # 这里统计的是发往路由的最终消息和工具，须与摘要门禁的计量一致。
            assert context_size(messages_from_dict(messages), tools=tools) == counted[-1][3]
            if len(self.requests) == 2:
                raise Captured()
            return Completion(content="", model="offline", agent_message=message_to_dict(
                AIMessage(content="", tool_calls=[call("list_documents", {}, "docs")]),
            ))

    counted = []
    original = SummarizationMiddleware._count_tokens

    def trace(self, messages, system, tools):
        value = original(self, messages, system, tools)
        counted.append((str(system), bool(tools), self._counter_accepts_tools, value))
        return value

    monkeypatch.setattr(SummarizationMiddleware, "_count_tokens", trace)

    async def run():
        router = Router()
        graph, files = build_module_agent(
            key=key, model=RoutedAgentModel(router=router), research=session([block()]),
            state={}, snapshot=skill_snapshot() | {FLOW_KEY: protocol},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop,
            categories=["engineering"],
        )
        with pytest.raises(Captured):
            await invoke_module(graph, files, thread_id=key, task="离线捕获")
        assert all(rule in str(messages) for messages in router.requests)
        assert any(rule in text and tools and accepted for text, tools, accepted, _ in counted)

    asyncio.run(run())


def test_omitted_work_does_not_spend_checks_that_have_not_been_attempted():
    flow, _, research = prepared_flow()
    flow.entries[0].update(checks=["确认预算", "确认截止时间"], checked=[],
                           requested_status="researching")
    flow.sync()
    control = TopicSearch(flow)
    for index in range(3):
        selected = control.begin("search_document", {"topic_keys": ["a"], "query": f"预算{index}"})
        control.end(selected, {"blocks": []}, set(research.seen))
    with pytest.raises(WorkClosed):
        control.begin("search_document", {"topic_keys": ["a"], "query": "预算再次"})
    assert flow.entries[0]["blocked_checks"] == []
    selected = control.begin("search_document", {
        "topic_keys": ["a"], "query": "截止日期", "work": "确认截止时间",
    })
    assert selected[0]["work"] == "确认截止时间"
    assert selected[0]["id"] not in control.ledger


@pytest.mark.parametrize("protocol", [FLOW_VERSION, PROTOCOL_VERSION])
def test_real_compaction_keeps_domain_rules_and_recognizes_idless_summary(monkeypatch, protocol):
    class Captured(Exception):
        pass

    class Router:
        def __init__(self):
            self.requests, self.summaries = [], []

        async def chat(self, messages, tools):
            if not tools:
                self.summaries.append(messages)
                return Completion(content="资料目录已读取，尚无核实成果", model="offline",
                                  agent_message=message_to_dict(AIMessage(content="资料目录已读取")))
            self.requests.append(messages)
            if len(self.requests) == 4:
                raise Captured()
            return Completion(content="", model="offline", agent_message=message_to_dict(
                AIMessage(content="", tool_calls=[call(
                    "list_documents", {}, str(len(self.requests)),
                )]),
            ))

    # 强制真实摘要路径，模型仍为本地替身，不以供应商耗时或上下文溢出来触发。
    monkeypatch.setattr(AnalysisSummarizationMiddleware, "_should_summarize",
                        lambda self, messages, total: len(messages) > 4)

    async def run():
        router, state = Router(), {}
        key = "scoring_standard_parsing"
        graph, files = build_module_agent(
            key=key, model=RoutedAgentModel(router=router), research=session([block()]),
            state=state, snapshot=skill_snapshot() | {FLOW_KEY: protocol},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=noop,
            categories=["engineering"],
        )
        with pytest.raises(Captured):
            await invoke_module(graph, files, thread_id="compact-rules", task="离线摘要复现")
        assert router.summaries
        assert all("分值加总只用于核对" in str(messages) for messages in router.requests)
        assert state.get("topic_summary_id")

    asyncio.run(run())


def test_archived_rule_file_can_be_read_again_after_summary():
    async def run():
        from deepagents.backends import StateBackend

        flow, state, research = prepared_flow()
        skill = load_module_skill(skill_snapshot(), "project_basic_info_parsing")
        path = "/skills/project-basic-info-parsing/references/output_format.md"
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow, skill=skill)
        middleware.summarizer = AnalysisSummarizationMiddleware(
            RoutedAgentModel(router=None), backend=StateBackend,
            context_tokens=24000, output_tokens=8192, token_counter=context_size,
        )
        old = [AIMessage(content="", tool_calls=[call(
            "read_file", {"file_path": path, "offset": 0, "limit": 10000}, "file",
        )]), ToolMessage(content="已读的完整输出说明", tool_call_id="call_file", name="read_file")]
        req = FakeRequest(messages=old)
        req.state = {"_summarization_event": {
            "cutoff_index": 2, "summary_message": HumanMessage(content="历史摘要",
                additional_kwargs={"lc_source": "summarization"}), "file_path": None,
        }}
        await middleware.topic_model_call(req, noop)
        await middleware.topic_model_call(req, noop)
        assert path not in middleware.loaded_skill_paths
        assert all(p in middleware.loaded_skill_paths for p in skill["domain_paths"])

    asyncio.run(run())


def test_check_and_task_progress_do_not_change_when_another_check_advances():
    flow, state, _ = prepared_flow()
    flow.entries[0].update(checks=["确认预算", "确认截止时间"], checked=[],
                           requested_status="researching")
    flow.sync()
    control = TopicSearch(flow)
    target = next(w for w in control.choices(["a"]) if w["work"] == "确认截止时间")
    before = control.signature(target)
    flow.entries[0]["checked"] = ["确认预算"]
    state["staged_items"][0]["business"]["content"] = {"内容": "无关预算变更"}
    assert control.signature(target) == before
    flow.entries[0]["checked"].append("确认截止时间")
    assert control.signature(target) != before


@pytest.mark.parametrize("first,second", [("投标 保证金", "投标保证金"), ("A&amp;B", "A&B")])
def test_actual_graph_does_not_merge_distinct_search_queries(first, second):
    async def run():
        research, queries = session([block()]), []

        async def retrieve(sources, query):
            queries.append(query)
            return [block()], {}

        research.retrieve = retrieve
        await execute([
            search("a", first, "first"), search("a", second, "second"),
            call("submit_analysis", submission([summary_record()]) | {
                "topic_updates": [{"topic": "a", "checked": ["核对独立事项及全部条件"]}]},
                 "finish"),
        ], keys=("a",), research=research)
        assert queries == [first, second]
        assert tool_key("search_document", {"query": first}) == tool_key(
            "search_document", {"query": " " + first + " "},
        )

    asyncio.run(run())


def test_targeted_audit_covers_other_changed_topics_and_done_checks_all_topics():
    async def run():
        flow, state, research = prepared_flow(("a", "b"))
        other = copy.deepcopy(state["staged_items"][0])
        other["business"]["key"] = "other"
        state["staged_items"].append(other)
        entry = next(e for e in flow.entries if e["topic"] == "b")
        entry.update(scope=COMMON, record_keys=["other"], evidence_ids=["s1r1c0"])
        issue = {"topic": "a", "detail": "核对例外", "target": "附件九第七条",
                 "record_keys": [], "evidence_ids": []}

        async def first(payload):
            return {"issues": [issue] if payload["topic"] == "a" else []}

        assert not await flow.audit(first, noop)
        assert issue["target"] in flow.prompt()
        other["business"]["content"] = {"内容": "修改后的日期"}
        audited = []

        async def targeted(payload):
            audited.append(payload)
            return {"issues": []}

        assert await flow.audit(targeted, noop)
        assert {p["topic"] for p in audited} == {"a", "b"}
        assert all(p["audit_issues"] for p in audited)
        # 已完成后重放不再请求；任何主题后续变化都必须使通过状态失效。
        assert await flow.audit(targeted, noop)
        assert len(audited) == 2
        research.seen["s1r1c0"]["content"] += "追加例外"
        with pytest.raises(TopicIncomplete, match="发生变化"):
            await flow.audit(targeted, noop)

    asyncio.run(run())


def test_closed_work_feedback_does_not_spend_global_argument_budget():
    async def run():
        flow, state, research = prepared_flow()
        middleware = ResearchMiddleware(research, state, noop, noop, topic_flow=flow)

        async def handler(req):
            raise AssertionError("完成的工作不应实际检索")

        result = await middleware.awrap_tool_call(request(
            "search_document", {"topic_keys": ["a"], "query": "重复查询"},
        ), handler)
        assert json.loads(result.content)["work_closed"]
        assert state.get("argument_failures", 0) == 0
        assert not state.get("read_tool_cache")

    asyncio.run(run())


def test_tool_schema_is_counted_and_irreducible_request_stops_before_model_call():
    async def run():
        from deepagents.backends import StateBackend

        middleware = AnalysisSummarizationMiddleware(
            RoutedAgentModel(router=None), backend=StateBackend,
            context_tokens=1000, output_tokens=100, keep=("messages", 4),
            token_counter=context_size,
        )
        tools = [{"type": "function", "function": {"name": "large", "description": "规则" * 1000,
                  "parameters": {"type": "object", "properties": {}}}}]
        messages = [SystemMessage(content="固定规则")]
        assert context_size(messages, tools=tools) > context_size(messages)
        invoked = []

        async def handler(req):
            invoked.append(req)
            raise AssertionError("已知超限不能进入模型")

        req = ModelRequest(model=RoutedAgentModel(router=None), system_message=messages[0],
                           messages=[], tools=tools, state={}, runtime=None)
        with pytest.raises(TopicIncomplete, match="上下文预算"):
            await middleware.awrap_model_call(req, handler)
        assert not invoked

    asyncio.run(run())
