"""转引先追踪到实质内容，再综合输出；未解决的转引独立于成果保留。"""

import asyncio
import json

import pytest
from synthesis_fixtures import COMMON, research_done, submission, summary_record
from test_analysis_references import ReferenceReviewer
from test_analysis_research import block, session, source
from test_analysis_synthesis import execute
from test_deep_analysis import call

from tender.application.analysis.skills import skill_snapshot, verify_items

KEY = "scoring_standard_parsing"
SNAPSHOT = skill_snapshot() | {
    KEY + "/references/coverage.json": json.dumps([{"key": "scoring", "title": "评分细则"}]),
}


def test_follows_target_file_before_publishing_actual_scoring_rules():
    async def run():
        index = block() | {"content": "评分标准详见《评分附件.pdf》"}
        heading = block(3, 10) | {"content": "第三章 评标办法"}
        detail = heading | {
            "block_id": "score-rule",
            "element_id": 4,
            "offset": 1,
            "content": "每提供一项同类业绩得2分，最高6分。",
        }
        research = session([index, heading, detail])
        research.sources.append(source(3, 10) | {"file_name": "评分附件.pdf"})
        queries = []

        async def retrieve(sources, query):
            queries.append(query)
            return ([index] if len(queries) == 1 else [heading]), {}

        research.retrieve = retrieve
        topics = [
            {
                "topic": "scoring",
                "status": "covered",
                "queries": ["评分标准", "业绩得分"],
                "evidence_ids": ["score-rule"],
                "detail": "已展开附件中的评分细则",
            }
        ]
        traces = [
            {
                "topic": "scoring",
                "from_block_id": index["block_id"],
                "target": "评分附件.pdf",
                "status": "resolved",
                "evidence_ids": ["score-rule"],
                "detail": "已读实际计分条款",
            }
        ]
        record = summary_record(
            key="performance",
            title="业绩评分",
            group="商务评分标准",
            content={
                "评分项": "同类业绩",
                "满分分值": "6分",
                "评分标准（原文摘录）": [detail["content"]],
            },
            citations=[{"block_id": "score-rule", "quote": detail["content"]}],
        )
        coverage = [
            {
                "topic": "scoring",
                "scope": COMMON,
                "status": "extracted",
                "record_keys": ["performance"],
                "detail": "已综合评分规则",
            }
        ]
        reviewer = ReferenceReviewer({})

        async def review(items):
            await verify_items(
                reviewer, items, explain=True, evidence=research.seen, select_evidence=True
            )

        state, saved, _ = await execute(
            [
                call("list_documents", {}, 0),
                call("search_document", {"query": "评分标准"}, 1),
                call("submit_analysis", submission([record], coverage=coverage), "early"),
                call("search_document", {"query": "业绩得分", "source_id": 3}, 2),
                call(
                    "read_document", {"block_id": heading["block_id"], "before": 0, "after": 1}, 3
                ),
                call("complete_research", research_done(topics, traces), 4),
                call("submit_analysis", submission([record], coverage=coverage), 5),
            ],
            research=research,
            snapshot=SNAPSHOT,
            key=KEY,
            review=review,
        )
        assert len(queries) == 2 and reviewer.calls == 1
        assert all(not s.get("staged_items") for s in saved if not s.get("research_completed"))
        item = state["draft"]["fields"][0]
        assert item["output"]["content"] == record["content"]
        assert [ref["block_id"] for ref in item["values"][0]["citations"]] == ["score-rule"]
        assert state["draft"]["business_data"]["gaps"] == []

    asyncio.run(run())


@pytest.mark.parametrize("target_missing", [True, False])
def test_missing_or_cyclic_reference_keeps_supported_method_and_explicit_gap(target_missing):
    async def run():
        index = block() | {"content": "评分标准详见附件A"}
        loop = index | {
            "block_id": "attachment-a",
            "element_id": 2,
            "offset": 1,
            "content": "附件A评分标准参见前附表",
        }
        valid = index | {
            "block_id": "method",
            "element_id": 3,
            "offset": 2,
            "content": "采用综合评分法",
        }
        research = session([index, loop, valid])

        async def retrieve(sources, query):
            return ([index, valid] if query == "评分" else [] if target_missing else [loop]), {}

        research.retrieve = retrieve
        topics = [
            {
                "topic": "scoring",
                "status": "unresolved",
                "queries": ["评分", "附件A"],
                "evidence_ids": ["method"],
                "detail": "仅核实评标方法，具体评分细则待核对",
            }
        ]
        traces = [
            {
                "topic": "scoring",
                "from_block_id": index["block_id"],
                "target": "附件A",
                "status": "missing" if target_missing else "cycle",
                "evidence_ids": [],
                "detail": "目标未提供" if target_missing else "附件A转回前附表",
            }
        ]
        record = summary_record(
            key="method",
            title="评标方法",
            group="评分总则",
            content={"总则要素": "评标方法", "原文内容": "采用综合评分法"},
            citations=[{"block_id": "method", "quote": valid["content"]}],
        )
        coverage = [
            {
                "topic": "scoring",
                "scope": COMMON,
                "status": "pending",
                "record_keys": ["method"],
                "detail": "评分细则待核对",
            }
        ]
        state, _, _ = await execute(
            [
                call("list_documents", {}, 0),
                call("search_document", {"query": "评分"}, 1),
                call("search_document", {"query": "附件A"}, 2),
                call("complete_research", research_done(topics, traces), 3),
                call("submit_analysis", submission([record], coverage=coverage), 4),
            ],
            research=research,
            snapshot=SNAPSHOT,
            key=KEY,
        )
        assert [item["field"] for item in state["draft"]["fields"]] == ["评标方法"]
        gaps = state["draft"]["business_data"]["gaps"]
        assert any(g["code"] == "unresolved_reference" and "附件A" in g["detail"] for g in gaps)

    asyncio.run(run())
