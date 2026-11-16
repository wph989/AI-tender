"""真实PostgreSQL验证大块入库、单次取证与预先合并的定位，不调用供应商。"""

import asyncio
import os

import pytest
import test_knowledge_flow as fixtures
from sqlalchemy import text

from tender.adapters.pg.repositories.knowledge.store import KnowledgeStore
from tender.application.knowledge.content import citation, validate_items
from tender.domain.knowledge.text import CHUNK_VERSION

environment = fixtures.environment
pytestmark = pytest.mark.skipif(os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库")


def grouped_source(environment):
    request, connection, pid = environment
    version, run = fixtures.add_source(connection, pid, "5. 开标要求")
    for order, (page, content) in enumerate(((1, "开标与投标截止同一时刻。"),
                                           (1, "仅限标段一。"),
                                           (2, "除另行通知外，迟到不予受理。"),
                                           (2, "6. 联系方式"), (2, "电话12345678")), 2):
        connection.execute(text('''INSERT INTO element
            (version_id,run_id,page_no,order_no,anchor,type,text,bbox_x0,bbox_y0,bbox_x1,bbox_y1)
            VALUES (:version,:run,:page,:order,:anchor,'text',:content,0.1,:top,0.8,:bottom)'''),
            {"version": version, "run": run, "page": page, "order": order,
             "anchor": f"p{page}b{order}", "content": content,
             "top": order * 0.1, "bottom": order * 0.1 + 0.05})
    db = KnowledgeStore(request.app.state.components.engine, 1)
    source = db.sources(db.collections_for_project(pid))[0]
    chunks = db.readable_chunks(source)
    return db, source, chunks


def test_index_persists_only_large_blocks_and_their_premerged_page_locations(environment):
    db, source, chunks = grouped_source(environment)
    assert len(chunks) == 2
    assert "仅限标段一" in chunks[0]["content"] and "除另行通知外" in chunks[0]["content"]
    assert "12345678" not in chunks[0]["content"]
    assert [p["page_no"] for p in chunks[0]["locations"]] == [1, 2]
    db.create_index(source)
    index_id = environment[1].execute(text('SELECT max(id) FROM knowledge_index')).scalar_one()
    db.complete_index(index_id, chunks=chunks, vectors=None, config=None)
    assert environment[1].execute(text('SELECT count(*) FROM knowledge_chunk')).scalar_one() == 2
    assert environment[1].execute(text(
        'SELECT chunk_version FROM knowledge_index')).scalar_one() == CHUNK_VERSION
    ready = db.sources([source["collection_id"]])[0]
    read_back = db.read_chunk_window(ready, 0, 1).rows[0]
    assert read_back["content"] == chunks[0]["content"]
    assert read_back["locations"] == chunks[0]["locations"]
    found = db.search_candidates([ready], "开标 同一时刻", None, None,
                                 limit=6, min_similarity=0.6).rows
    assert len(found) == 1 and found[0]["block_id"] == read_back["block_id"]


@pytest.mark.parametrize("indexed", [False, True])
def test_large_block_location_rechecks_permissions(environment, indexed):
    db, source, chunks = grouped_source(environment)
    if indexed:
        db.create_index(source)
        index_id = environment[1].execute(text('SELECT max(id) FROM knowledge_index')).scalar_one()
        db.complete_index(index_id, chunks=chunks, vectors=None, config=None)
    raw = [{"field": "开标", "values": [{"value": "开标与投标截止同一时刻，仅限标段一。",
            "citations": [{"block_id": chunks[0]["block_id"]}]}]}]
    result = validate_items(raw, {chunks[0]["block_id"]: chunks[0]},
                            source_locations=True, align=False)
    refs = result[0]["values"][0]["citations"]
    assert len(refs) == 2 and {ref["block_id"] for ref in refs} == {chunks[0]["block_id"]}
    for ref, place in zip(refs, chunks[0]["locations"], strict=True):
        resolved = db.resolve(ref, with_content=True)
        assert resolved["bbox"] == place["bbox"]
        assert resolved["page_no"] == place["page_no"]
        assert ref["quote"] in resolved["content"]
    environment[1].execute(text('UPDATE project_file SET deleted_at=now()'))
    with pytest.raises(LookupError):
        db.resolve(refs[0])


def test_model_receives_only_large_block_id_and_full_clause(environment):
    from tender.application.analysis.research import ResearchSession

    db, source, chunks = grouped_source(environment)

    async def retrieve(*_):
        return chunks[:1], {"mode": "keyword"}

    async def read(selected, offset, limit):
        return db.read_chunk_window(selected, offset, limit)

    async def authorize():
        pass

    research = ResearchSession([source], source["project_id"], retrieve, read, authorize,
                               compact_results=True)
    result = asyncio.run(research.search("开标", "project"))
    assert result["blocks"] == [{"id": chunks[0]["block_id"], "text": chunks[0]["content"],
                                "source_id": chunks[0]["source_id"],
                                "chapter": chunks[0]["chapter"]}]
    assert "g2c" in result["blocks"][0]["id"]
    assert citation(chunks[0], chunks[0]["content"])["locations"] == chunks[0]["locations"]


@pytest.mark.parametrize("indexed", [False, True])
@pytest.mark.parametrize("quote,pages,excerpts", [
    ("除另行通知外，迟到不予受理。", [2], ["除另行通知外，迟到不予受理。"]),
    ("仅限标段一。除另行通知外，迟到不予受理。", [1, 2],
     ["仅限标段一。", "除另行通知外，迟到不予受理。"]),
])
def test_short_qa_quote_resolves_to_its_actual_page_regions(environment, indexed, quote,
                                                         pages, excerpts):
    db, source, chunks = grouped_source(environment)
    if indexed:
        db.create_index(source)
        index_id = environment[1].execute(text('SELECT max(id) FROM knowledge_index')).scalar_one()
        db.complete_index(index_id, chunks=chunks, vectors=None, config=None)
    chunk = chunks[0]
    raw = [{"field": "开标要求", "values": [{"value": "迟到处理要求", "citations": [{
        "block_id": chunk["block_id"], "quote": quote,
    }]}]}]
    refs = validate_items(raw, {chunk["block_id"]: chunk}, align=False)[0]["values"][0]["citations"]
    assert [ref["page_no"] for ref in refs] == pages
    assert [ref["quote"] for ref in refs] == excerpts
    for ref in refs:
        resolved = db.resolve(ref, with_content=True)
        place = next(place for place in chunk["locations"] if place["page_no"] == ref["page_no"])
        assert resolved["page_no"] == place["page_no"]
        assert resolved["bbox"] == place["bbox"]
        assert ref["quote"] in resolved["content"]


def test_historical_attempt_reads_frozen_small_block_identity_after_index_upgrade(environment):
    from tender.domain.knowledge.text import split_elements

    db, source, chunks = grouped_source(environment)
    db.create_index(source)
    index_id = environment[1].execute(text('SELECT max(id) FROM knowledge_index')).scalar_one()
    db.complete_index(index_id, chunks=chunks, vectors=[[1.0, 0.0]] * len(chunks),
                      config={"id": None, "signature": "test-space"})
    ready = db.sources([source["collection_id"]])[0]
    legacy = ready | {"chunk_format_version": "1"}
    expected = split_elements(db.blocks(legacy))
    restored = db.read_chunk_window(legacy, 0, 12).rows
    assert [r["content"] for r in restored] == [r["content"] for r in expected]
    assert all(r["block_id"] == f"s{r['source_id']}r{r['parse_run_id']}c{r['offset']}"
               for r in restored)
    assert all("g2c" in r["block_id"] for r in db.readable_chunks(ready))
    found = db.search_candidates([legacy], "开标", [1.0, 0.0], "test-space",
                                 limit=6, min_similarity=0.6)
    assert found.rows and not found.semantic_source_ids
