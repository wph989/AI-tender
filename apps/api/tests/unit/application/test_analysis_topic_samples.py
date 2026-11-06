"""相同人工标注资料对比两种工具轨迹，记录离线请求量及输入估算，不调用供应商。"""

import asyncio
import json
import time
from pathlib import Path

import tiktoken
from langgraph.checkpoint.memory import InMemorySaver
from synthesis_fixtures import COMMON, noop, submission
from test_analysis_research import block, session
from test_deep_analysis import KEY, SKILL, ScriptedRouter, call

from tender.application.analysis.agent import RoutedAgentModel, build_module_agent, invoke_module
from tender.application.analysis.completeness import review_completeness
from tender.application.analysis.skills import verify_items
from tender.application.analysis.topic_flow import FLOW_KEY, FLOW_VERSION
from tender.ports.llm.chat import Completion

SAMPLE = json.loads((Path(__file__).parents[2] / "fixtures/analysis/topic_incremental.json")
                    .read_text(encoding="utf-8"))


async def run_sample(incremental):
    rows = [block() | value for value in SAMPLE["blocks"]]
    research = session(rows)

    async def retrieve(sources, query):
        return [rows[0 if query == "预算" else 1]], {"mode": "keyword"}

    research.retrieve = retrieve
    topics = [{"key": "budget", "title": "预算", "checks": ["金额与单位"]},
              {"key": "dates", "title": "日期", "checks": ["截止时点"]}]
    records = [{"key": r["key"], "title": r["title"], "kind": "requirement",
                "group": "项目基本信息", "scope": r.get("scope", COMMON),
                "conditions": r.get("conditions", {}),
                "content": {"字段": r["title"], "内容": r["text"]},
                "citations": [{"block_id": r["block_id"], "quote": r["quote"]}]}
               for r in SAMPLE["expected"]]
    snapshot = SKILL | {KEY + "/references/coverage.json": json.dumps(topics, ensure_ascii=False)}
    script = [call("list_documents", {}, "docs")]
    for index, (topic, record) in enumerate(zip(topics, records, strict=True)):
        search_args = {"query": "预算" if index == 0 else "截止"}
        if incremental:
            search_args["topic_keys"] = [topic["key"]]
        script.append(call("search_document", search_args, f"search{index}"))
        if not incremental:
            script.append(call("complete_research", {"topics": [{
                "topic": t["key"], "status": "covered" if i <= index else "searched_not_found",
                "queries": ["预算" if i == 0 or index == 0 else "截止"],
                "evidence_ids": [rows[i]["block_id"]] if i <= index else [],
                "detail": "核对本轮原文，具体缺口保留",
            } for i, t in enumerate(topics)], "research_summary": "核对本轮资料"}, f"done{index}"))
            if index:
                # 历史流程新增证据会清空暂存，必须重新提交第一项。
                script.append(call(
                    "submit_analysis", submission([records[0]], final=False), "repeat"
                ))
        args = submission([record], final=index == 1)
        if incremental:
            args["topic_updates"] = [{"topic": topic["key"], "scope": record["scope"],
                                      "status": "ready",
                                      "checked": topic["checks"], "record_keys": [record["key"]],
                                      "evidence_ids": [rows[index]["block_id"]],
                                      "detail": "逐项核对"}]
        script.append(call("submit_analysis", args, f"submit{index}"))
    if incremental:
        snapshot[FLOW_KEY] = FLOW_VERSION
    prompts, tools_used = [], []

    async def reserve_tool():
        tools_used.append(1)

    class Reviewer:
        async def complete(self, prompt):
            prompts.append(prompt)
            payload = json.loads(prompt.rsplit("\n", 1)[-1])
            if isinstance(payload, dict):
                return Completion(content='{"issues":[]}', model="offline")
            reviews = [{"supported": True, "unsupported_claims": [], "unresolved_references": [],
                        "evidence_ids": [[r["id"] for r in item["evidence_sets"][0]["citations"]]
                                         for _ in item["values"]]} for item in payload]
            return Completion(content=json.dumps({"reviews": reviews}), model="offline")

    async def review(items):
        await verify_items(Reviewer(), items, explain=True, evidence=research.seen,
                           select_evidence=True)

    async def audit(payload):
        return await review_completeness(Reviewer(), payload)

    router, state = ScriptedRouter(script), {}
    encoder = tiktoken.get_encoding("cl100k_base")
    started = time.monotonic()
    graph, files = build_module_agent(key=KEY, model=RoutedAgentModel(router=router),
                                     research=research, state=state, snapshot=snapshot,
                                     checkpointer=InMemorySaver(), reserve_tool=reserve_tool,
                                     save=noop,
                                     review_support=review, review_coverage=audit)
    await invoke_module(graph, files, thread_id="sample", task="解析预算和日期")
    inputs = prompts + [json.dumps(request, ensure_ascii=False) for request in router.requests]
    return state, {"model_requests": len(router.requests) + len(prompts),
                   "tool_calls": len(tools_used),
                   "input_tokens_estimate_cl100k_base": sum(len(encoder.encode(s)) for s in inputs),
                   "offline_duration_ms": round((time.monotonic() - started) * 1000)}


def test_annotated_sample_preserves_all_items_and_avoids_old_result_resubmission(tmp_path):
    legacy, before = asyncio.run(run_sample(False))
    current, after = asyncio.run(run_sample(True))
    for state in (legacy, current):
        actual = {i["business"]["key"]: i["business"] for i in state["draft"]["fields"]}
        assert set(actual) == {"budget", "dates"}
        for expected in SAMPLE["expected"]:
            item = actual[expected["key"]]
            assert item["content"]["内容"] == expected["text"]
            assert item["scope"] == expected.get("scope", COMMON)
            if expected.get("conditions"):
                assert item["conditions"] == expected["conditions"]
            assert item["citations"][0]["quote"] == expected["quote"]
    assert before["model_requests"] == 11 and after["model_requests"] == 9
    assert before["tool_calls"] == 9 and after["tool_calls"] == 6
    path = tmp_path / "topic_sample_metrics.json"
    path.write_text(json.dumps({"legacy": before, "topic_v1": after}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(path.read_text(encoding="utf-8"))
