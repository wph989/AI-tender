"""验证来源、全文覆盖与工具边界；避免只验证实现的字符串写法。"""

import asyncio
import json

import pytest

from tender.application.analysis_skills import DocumentTools, read_reference, run_module
from tender.application.knowledge import cosine, rank_chunks, split_elements, validate_items
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
        "kind": "fact",
        "title": "资格要求",
        "text": row["content"],
        "citations": [{"block_id": row["block_id"], "quote": row["content"]}],
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
    assert [i["citations"][0]["source_id"] for i in items] == [1, 2]
    assert items[0]["citations"][0]["version_id"] != items[1]["citations"][0]["version_id"]


def test_unread_or_fabricated_quotes_are_rejected():
    row = block()
    with pytest.raises(ValueError, match="未读取"):
        validate_items([item(row)], {})
    bad = item(row)
    bad["citations"][0]["quote"] = "任何企业均可投标"
    with pytest.raises(ValueError, match="逐字"):
        validate_items([bad], {row["block_id"]: row})


def test_tool_search_covers_all_sources_and_scope_cannot_escape():
    tools = DocumentTools([block(1), block(2)])
    result = tools.execute({"action": "search", "terms": ["甲级"]})
    assert {r["source_id"] for r in result["blocks"]} == {1, 2}
    with pytest.raises(ValueError, match="范围"):
        tools.execute({"action": "read", "source_id": 3})
    with pytest.raises(ValueError):
        read_reference("disqualified_items_parsing", "../../../../../core/settings.py")


def test_hybrid_retrieval_adds_semantic_match_without_keyword_match():
    rows = [
        {"content": "投标保证金", "embedding": [1.0, 0.0]},
        {"content": "应提供担保文件", "embedding": [0.9, 0.1]},
    ]
    assert len(rank_chunks(rows, "保证金")) == 1
    assert len(rank_chunks(rows, "保证金", [1.0, 0.0])) == 2
    with pytest.raises(ValueError, match="维度"):
        cosine([1.0], [1.0, 0.0])


def test_skill_executes_tools_and_independent_support_check():
    row = block()
    responses = [
        {"action": "search", "terms": ["资质"]},
        {"action": "finish", "items": [item(row)], "relations": []},
        {"supported": [False]},
    ]

    class Model:
        async def complete(self, prompt):
            return Completion(json.dumps(responses.pop(0), ensure_ascii=False), "test")

    items, relations, trace = asyncio.run(
        run_module(
            Model(),
            "personnel_requirement_parsing",
            [row],
            "engineering",
            [],
            [],
            [row["block_id"]],
            lambda: None,
        )
    )
    assert items[0]["kind"] == "insufficient"
    assert items[0]["verification"] == "unsupported"
    assert trace[0]["response"]["blocks"][0]["source_id"] == 1
    assert not relations and not responses
