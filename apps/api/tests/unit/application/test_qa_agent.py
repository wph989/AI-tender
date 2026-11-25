"""用真实问答图和路由复现分批丢失、预算旁路及图谱证据未进入上下文的问题。"""

import asyncio
import json

import pytest
from agent_fixtures import call, submitted_field
from langchain_core.messages import AIMessage, message_to_dict
from test_analysis_research import block, session

from tender.application.knowledge.qa_agent import QABudgetExceeded, answer_with_agent
from tender.application.llm.routing import ModelCandidate, RoutingModel
from tender.application.shared.research import AgentLimits
from tender.domain.shared.errors import ModelUnavailable
from tender.ports.llm.chat import Completion


class Client:
    def __init__(self, actions):
        self.actions = list(actions)
        self.requests = []
        self.reviews = []
        self.closed = False

    async def chat(self, messages, tools):
        self.requests.append(messages)
        action = self.actions.pop(0)
        if isinstance(action, Exception):
            raise action
        return Completion(
            content="",
            model="fixture",
            agent_message=message_to_dict(AIMessage(content="", tool_calls=[action])),
        )

    async def complete(self, prompt):
        payload = json.loads(prompt.rsplit("\n", 1)[-1])
        self.reviews.extend(payload)
        return Completion(
            content=json.dumps(
                {"reviews": [{"supported": True, "unsupported_claims": []} for _ in payload]}
            ),
            model="fixture",
        )

    async def aclose(self):
        self.closed = True


def factory(client):
    def create(**limits):
        return RoutingModel(
            "knowledge_ask",
            "qa-test",
            [ModelCandidate(1, 1, "fixture", "fixture", "http://test", None, 10, None, 4096)],
            lambda *args, **kwargs: client,
            lambda record: None,
            retry_base_seconds=0,
            **limits,
        )

    return create


def submit(number, fields=None, **options):
    return call(
        "submit_analysis",
        {
            "fields": fields or [],
            "relations": [],
            "research_summary": f"第{number}批",
            **options,
        },
        number,
    )


async def answer(client, research, **options):
    return await answer_with_agent(
        model_factory=factory(client),
        sources=research.sources,
        project_id=10,
        question="质保要求",
        retrieve=research.retrieve,
        read=research.read,
        authorize=research.authorize,
        **options,
    )


def test_qa_denies_other_files_and_can_continue_with_authorized_sources():
    client = Client([
        call("read_file", {"file_path": "/private.txt"}, 1),
        call("search_document", {"query": "质保"}, 2),
        submit(3, [submitted_field("质保", "质保三年")], final=True),
    ])
    draft, _ = asyncio.run(answer(client, session([block()])))
    denied = next(
        message["data"]["content"] for message in client.requests[1]
        if message["type"] == "tool" and message["data"]["tool_call_id"] == "call_1"
    )
    assert "permission denied for read" in denied
    assert draft["fields"][0]["values"][0]["value"] == "质保三年"


def test_citation_feedback_allows_rereading_with_the_qa_tool_parameters():
    client = Client([
        call("search_document", {"query": "质保"}, 1),
        submit(2, [submitted_field("质保", "质保三年", quote="质保五年")], final=False),
        call("read_document", {"source_id": 1, "offset": 0, "limit": 1}, 3),
        submit(4, [submitted_field("质保", "质保三年")], final=True),
    ])
    draft, _ = asyncio.run(answer(client, session([block()])))
    feedback = next(
        message["data"]["content"] for message in client.requests[2]
        if message["type"] == "tool" and message["data"]["tool_call_id"] == "call_2"
    )
    # 问答按来源和偏移回读；共享引文错误不能诱导模型使用解析工具的邻段参数。
    assert "read_document" in feedback and "复制连续原文" in feedback
    assert "before" not in feedback and "after" not in feedback
    reread = next(
        message["data"] for message in client.requests[3]
        if message["type"] == "tool" and message["data"]["tool_call_id"] == "call_3"
    )
    assert reread["status"] == "success"
    assert json.loads(reread["content"])["blocks"][0]["block_id"] == "s1r1c0"
    assert draft["fields"][0]["values"][0]["value"] == "质保三年"
    assert len(client.requests) == 4


def test_batches_accumulate_and_only_explicit_final_finishes():
    first = submitted_field("质保", "质保三年")
    second = submitted_field("服务期限", "质保三年")
    middle = submit(3, [second])
    # 省略 final 也应暂存，避免弱模型漏参时悄悄丢弃后续内容。
    middle["args"].pop("final")
    client = Client(
        [
            call("search_document", {"query": "质保"}, 1),
            submit(2, [first], final=False),
            middle,
            submit(4, final=True),
        ]
    )
    draft, _ = asyncio.run(answer(client, session([block()])))
    assert [entry["field"] for entry in draft["fields"]] == ["质保", "服务期限"]
    assert draft["research_summary"] == "第4批"
    assert len(client.requests) == 4 and len(client.reviews) == 2
    assert client.closed


@pytest.mark.parametrize("limit,chat_calls", [(1, 1), (2, 2)])
def test_model_budget_is_shared_by_chat_and_support_review(limit, chat_calls):
    client = Client(
        [
            call("search_document", {"query": "质保"}, 1),
            submit(2, [submitted_field("质保", "质保三年")]),
        ]
    )
    with pytest.raises(QABudgetExceeded, match="模型调用预算"):
        asyncio.run(answer(client, session([block()]), limits=AgentLimits(max_model_calls=limit)))
    assert len(client.requests) == chat_calls
    assert not client.reviews
    assert client.closed


def test_provider_retry_cannot_exceed_question_budget():
    client = Client(
        [
            ModelUnavailable("临时断连"),
            call("search_document", {"query": "质保"}, 1),
        ]
    )
    with pytest.raises(QABudgetExceeded, match="模型调用预算"):
        asyncio.run(answer(client, session([block()]), limits=AgentLimits(max_model_calls=1)))
    assert len(client.requests) == 1 and client.closed


def test_submission_also_consumes_tool_budget():
    client = Client(
        [
            call("search_document", {"query": "质保"}, 1),
            submit(2, [submitted_field("质保", "质保三年")]),
        ]
    )
    with pytest.raises(QABudgetExceeded, match="工具调用预算"):
        asyncio.run(answer(client, session([block()]), limits=AgentLimits(max_tool_calls=1)))
    assert not client.reviews and client.closed


def test_total_deadline_cancels_inflight_retrieval_and_closes_model():
    async def run():
        client = Client([call("search_document", {"query": "质保"}, 1)])
        research = session([block()])
        canceled = False

        async def slow_retrieve(sources, query):
            nonlocal canceled
            try:
                await asyncio.Event().wait()
            finally:
                canceled = True

        research.retrieve = slow_retrieve
        with pytest.raises(QABudgetExceeded, match="总时限"):
            await answer(client, research, limits=AgentLimits(timeout_seconds=1))
        assert canceled and client.closed

    asyncio.run(run())


def test_graph_only_evidence_reaches_model_and_can_be_cited():
    extra = block() | {"block_id": "s1r1c1", "element_id": 2, "offset": 1, "content": "需提交保函"}
    relation = {
        "subject": "质保",
        "predicate": "需要",
        "object": "保函",
        "scope": "",
        "condition": "",
        "citations": [{"block_id": extra["block_id"], "quote": extra["content"]}],
    }

    async def expand(sources, hits):
        return [*hits, extra], [relation]

    client = Client(
        [
            call("search_document", {"query": "质保"}, 1),
            submit(
                2, [submitted_field("材料", extra["content"], extra["content"], extra["block_id"])]
            ),
        ]
    )
    draft, research = asyncio.run(answer(client, session([block()]), expand=expand))
    tool_result = next(
        json.loads(message["data"]["content"])
        for message in client.requests[1]
        if message["type"] == "tool"
    )
    assert extra["block_id"] in {row["block_id"] for row in tool_result["blocks"]}
    assert tool_result["relations"] == [relation]
    assert research.events[-1]["relations"] == [relation]
    assert draft["fields"][0]["values"][0]["citations"][0]["block_id"] == extra["block_id"]


def test_graph_relations_cannot_expose_evidence_over_budget():
    extra = block() | {"block_id": "s1r1c1", "element_id": 2, "content": "需提交保函"}

    async def expand(sources, hits):
        return [*hits, extra], [{"citations": [{"block_id": extra["block_id"]}]}]

    client = Client(
        [
            call("search_document", {"query": "质保"}, 1),
            submit(2),
        ]
    )
    _, research = asyncio.run(
        answer(
            client,
            session([block()]),
            expand=expand,
            limits=AgentLimits(max_evidence_blocks=1),
        )
    )
    assert set(research.seen) == {block()["block_id"]}
    assert research.events[-1]["relations"] == []
