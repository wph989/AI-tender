"""验证来源身份、检索回退与共用 JSON 纠正；避免只验证实现的字符串写法。"""

import asyncio

import pytest

from tender.application.analysis_skills import json_completion
from tender.application.knowledge import cosine, rank_chunks, split_elements, validate_items
from tender.application.knowledge_retrieval import retrieve_chunks
from tender.domain.errors import (
    ExtractionFailed,
    ExtractionUnavailable,
    InvalidModelOutput,
    ModelRefused,
)
from tender.ports.llm import Completion


def block(source=1, text="投标人须具有甲级资质，不接受联合体。"):
    return {
        "block_id": f"s{source}r1c0",
        "source_id": source,
        "collection_id": source,
        "project_id": source,
        "project_file_id": source,
        "version_id": source,
        "parse_run_id": 1,
        "element_id": source,
        "anchor": "p1b1",
        "page_no": 1,
        "bbox": [0.1, 0.1, 0.8, 0.3],
        "file_name": f"文件{source}.pdf",
        "purpose": "tender",
        "content": text,
        "chapter": "资格条件",
        "offset": 0,
    }


def item(row):
    return {
        "field": "资格要求",
        "group": "资格条件",
        "sort_order": 0,
        "values": [
            {
                "value": row["content"],
                "citations": [{"block_id": row["block_id"], "quote": row["content"]}],
            }
        ],
        "note": "",
    }


def test_long_tables_are_fully_covered():
    content = "".join(f"第{i}项技术条件。" for i in range(2500))
    chunks = split_elements([{"id": 1, "type": "table", "html": "<table>" + content + "</table>"}])
    covered = set()
    for chunk in chunks:
        covered.update(range(chunk["char_start"], chunk["char_end"]))
    assert covered == set(range(len(" " + content + " ")))
    assert any("第2499项" in c["content"] for c in chunks)


def test_same_anchor_in_different_files_keeps_identity():
    a, b = block(1), block(2)
    items = validate_items([item(a), item(b)], {a["block_id"]: a, b["block_id"]: b})
    assert [i["values"][0]["citations"][0]["source_id"] for i in items] == [1, 2]
    first = items[0]["values"][0]["citations"][0]["version_id"]
    assert first != items[1]["values"][0]["citations"][0]["version_id"]


def test_unread_or_fabricated_quotes_are_rejected():
    row = block()
    with pytest.raises(ValueError, match="未读取"):
        validate_items([item(row)], {})
    bad = item(row)
    bad["values"][0]["citations"][0]["quote"] = "任何企业均可投标"
    with pytest.raises(ValueError, match="逐字"):
        validate_items([bad], {row["block_id"]: row})


def test_hybrid_retrieval_adds_semantic_match_without_keyword_match():
    rows = [
        {"content": "投标保证金", "embedding": [1.0, 0.0]},
        {"content": "应提供担保文件", "embedding": [0.9, 0.1]},
    ]
    assert len(rank_chunks(rows, "保证金")) == 1
    assert len(rank_chunks(rows, "保证金", [1.0, 0.0])) == 2
    with pytest.raises(ValueError, match="维度"):
        cosine([1.0], [1.0, 0.0])


def test_slow_search_embedding_falls_back_to_citable_fulltext_and_closes_client():
    row = block(text="历史设备质保期五年。")

    class Store:
        def embedding_config(self):
            return {"signature": "test-space"}

        def readable_chunks(self, source):
            return [row]

    class SlowEmbedding:
        canceled = False
        closed = False

        async def embed(self, texts):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.canceled = True
                raise

        async def aclose(self):
            self.closed = True

    async def run():
        client = SlowEmbedding()
        hits, info = await asyncio.wait_for(retrieve_chunks(
            Store(), [{"is_parseable": True, "parse_status": "completed"}], "质保期",
            lambda: None, lambda _: client, embedding_timeout=0.01,
        ), timeout=1)
        assert hits[0]["content"] == row["content"]
        assert hits[0]["anchor"] == row["anchor"]
        assert info["mode"] == "keyword" and info["semantic_source_ids"] == []
        assert "等待超时" in info["warning"]
        assert client.canceled and client.closed

    asyncio.run(run())




@pytest.mark.parametrize("first", ["需要读取补充通知", InvalidModelOutput("非法 JSON")])
def test_json_correction_requests_an_action_instead_of_inventing_one(first):
    prompts = []

    class Model:
        async def complete(self, prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                if isinstance(first, Exception):
                    raise first
                return Completion(first, "test")
            return Completion('{"action":"read","source_id":2}', "test")

    result = asyncio.run(json_completion(Model(), "执行模块"))
    assert result == {"action": "read", "source_id": 2}
    assert len(prompts) == 2 and "不能只说明计划" in prompts[1]


def test_repeated_invalid_json_stops_after_two_corrections():
    calls = []

    class Model:
        async def complete(self, prompt):
            calls.append(prompt)
            return Completion("说明：{}", "test")

    with pytest.raises(InvalidModelOutput):
        asyncio.run(json_completion(Model(), "执行模块"))
    assert len(calls) == 3


@pytest.mark.parametrize(
    "error", [ExtractionUnavailable("超时"), ExtractionFailed("配置无效"), ModelRefused("拒绝")]
)
def test_json_correction_never_retries_connection_configuration_or_refusal(error):
    calls = []

    class Model:
        async def complete(self, prompt):
            calls.append(prompt)
            raise error

    with pytest.raises(type(error)):
        asyncio.run(json_completion(Model(), "执行模块"))
    assert len(calls) == 1
