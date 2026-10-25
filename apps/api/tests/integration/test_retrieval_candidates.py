"""真实 SQL 与既有排名逐项对照，验证索引复用、有限返回与实时权限。"""

import os

import pytest
import test_knowledge_flow as fixtures
from sqlalchemy import event, insert, text
from test_knowledge_flow import add_source

from tender.adapters.pg.models import KnowledgeChunk, KnowledgeIndex
from tender.adapters.pg.repositories.knowledge.store import KnowledgeStore
from tender.api.knowledge import routes as knowledge
from tender.application.knowledge.content import rank_chunks

environment = fixtures.environment

pytestmark = pytest.mark.skipif(os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库")


def indexed_sources(environment, count=2):
    request, connection, pid = environment
    for _ in range(count):
        version, run = add_source(connection, pid, "资质等级要求")
        # 多个有相同词法/向量得分的块，才能验证同分次序及先过滤再融合。
        for ordinal, content in enumerate([
            "资质证书", "等级说明", "注册证书", "资质等级", "不相关正文", "资质等级",
        ], 2):
            connection.execute(text("""INSERT INTO element
                (version_id,run_id,page_no,order_no,anchor,type,text)
                VALUES (:version,:run,1,:ordinal,:anchor,'text',:content)"""),
                {"version": version, "run": run, "ordinal": ordinal,
                 "anchor": f"p1b{ordinal}", "content": content})
    own = knowledge.project_knowledge(pid, request)["collection_id"]
    db = KnowledgeStore(request.app.state.components.engine, 1)
    vectors = [[1.0, 0.0], [0.0, 1.0], [0.6, 0.8], [0.0, 0.0],
               [-1.0, 0.0], None, [1.0, 0.0, 0.0]]
    for source in db.sources([own]):
        chunks = db.readable_chunks(source)
        index_id = connection.execute(insert(KnowledgeIndex).values(
            source_id=source["source_id"], version_id=source["version_id"],
            run_id=source["parse_run_id"], status="completed", chunk_version="1",
            embedding_signature="test-space", dimension=2,
        ).returning(KnowledgeIndex.id)).scalar_one()
        connection.execute(insert(KnowledgeChunk), [{
            "index_id": index_id,
            **{key: row[key] for key in (
                "element_id", "ordinal", "char_start", "char_end", "chapter", "content",
            )}, "embedding": vectors[row["ordinal"]],
        } for row in chunks])
    return db, db.sources([own]), vectors


@pytest.mark.parametrize("query", ["资质 等级", "不存在的词"])
@pytest.mark.parametrize("vector", [None, [1.0, 0.0]])
@pytest.mark.parametrize("threshold", [None, 0.0, 0.6, 1.0])
def test_sql_ranking_matches_reference_with_mixed_sources(environment, query, vector, threshold):
    db, sources, vectors = indexed_sources(environment)
    _, connection, pid = environment
    add_source(connection, pid, "资质等级：尚未建立索引也应参与检索")
    sources = db.sources([sources[0]["collection_id"]])
    rows = []
    for source in sources:
        for row in db.readable_chunks(source):
            embedding = vectors[row["ordinal"]] if source.get("index_id") else None
            if vector and embedding is not None and len(embedding) == len(vector):
                row["embedding"] = embedding
            rows.append(row)
    expected = rank_chunks(rows, query, vector, limit=5, min_similarity=threshold)
    actual = db.search_candidates(sources, query, vector, "test-space",
                                  limit=5, min_similarity=threshold)
    assert [r["block_id"] for r in actual.rows] == [r["block_id"] for r in expected]
    assert [r["score"] for r in actual.rows] == pytest.approx([r["score"] for r in expected])
    assert all("embedding" not in row for row in actual.rows)
    assert actual.semantic_source_ids == ([s["source_id"] for s in sources[:2]] if vector else [])


def test_indexed_search_does_not_read_full_text_or_return_vectors(environment, monkeypatch):
    db, sources, _ = indexed_sources(environment)
    connection = environment[1]
    columns = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        columns.append([column[0] for column in cursor.description or []])

    # 确认走的是持久分块；仅删掉最终响应里的向量不足以证明数据库传输有界。
    monkeypatch.setattr(db, "blocks", lambda *_: pytest.fail("已建索引不应重新读取原文"))
    event.listen(connection, "after_cursor_execute", observe)
    try:
        result = db.search_candidates(sources, "资质", [1.0, 0.0], "test-space",
                                      limit=2, min_similarity=None)
    finally:
        event.remove(connection, "after_cursor_execute", observe)
    assert len(result.rows) == 2
    assert columns and all("embedding" not in names for names in columns)


@pytest.mark.parametrize("revoked", ["project", "project_file", "knowledge_collection", "company"])
def test_cached_sources_cannot_bypass_revoked_access(environment, revoked):
    db, sources, _ = indexed_sources(environment, count=1)
    connection = environment[1]
    if revoked == "company":
        db = KnowledgeStore(db.engine, 2)
    else:
        connection.execute(text(f"UPDATE {revoked} SET deleted_at=now()"))
    result = db.search_candidates(sources, "资质", [1.0, 0.0], "test-space",
                                  limit=10, min_similarity=None)
    assert result.rows == [] and result.semantic_source_ids == []
    assert db.readable_chunks(sources[0]) == []


@pytest.mark.parametrize("identity", ["version_id", "parse_run_id", "source_id", "index_id"])
def test_index_must_match_frozen_source_identity(environment, identity):
    db, sources, _ = indexed_sources(environment)
    invalid = {**sources[0], identity: sources[1][identity]}
    result = db.search_candidates([invalid], "资质", [1.0, 0.0], "test-space",
                                  limit=10, min_similarity=None)
    assert result.rows == [] and result.semantic_source_ids == []


def test_old_chunk_version_falls_back_without_using_stale_vectors(environment):
    db, sources, _ = indexed_sources(environment, count=1)
    environment[1].execute(text("UPDATE knowledge_index SET chunk_version='old'"))
    result = db.search_candidates(sources, "资质", [1.0, 0.0], "test-space",
                                  limit=10, min_similarity=None)
    assert result.rows and result.semantic_source_ids == []
