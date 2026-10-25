"""数据库内精确排名，仅返回有界候选；未建索引的资料保留原文回退。"""

from typing import Any

from sqlalchemy import (
    BigInteger,
    Double,
    Integer,
    Text,
    case,
    column,
    func,
    literal,
    select,
    union_all,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.sql.expression import Grouping

from tender.adapters.pg.models import Element, KnowledgeChunk, KnowledgeIndex
from tender.domain.knowledge.search import keywords
from tender.ports.repository.knowledge.retrieval import SearchCandidates


def _indexed_query(store, source):
    # 原文权限查询仍核对 company/source/file/version/run；索引只提供已持久化分块。
    return (
        store._blocks_query(source)
        .join(
            KnowledgeChunk,
            KnowledgeChunk.element_id == Element.id,
        )
        .join(KnowledgeIndex, KnowledgeIndex.id == KnowledgeChunk.index_id)
        .where(
            KnowledgeIndex.id == source["index_id"],
            KnowledgeIndex.source_id == source["source_id"],
            KnowledgeIndex.version_id == source["version_id"],
            KnowledgeIndex.run_id == source["parse_run_id"],
            KnowledgeIndex.status == "completed",
            KnowledgeIndex.chunk_version == "1",
        )
        .order_by(None)
    )


def _payload(row: dict, source: dict) -> dict:
    result = {
        **source,
        **row,
        "offset": row["ordinal"],
        "block_id": f"s{source['source_id']}r{source['parse_run_id']}c{row['ordinal']}",
    }
    if "bbox_x0" in result:
        coords = [result.pop("bbox_" + axis) for axis in ("x0", "y0", "x1", "y1")]
        result["bbox"] = [float(v) for v in coords] if all(v is not None for v in coords) else None
    return result


def _columns():
    return [
        KnowledgeChunk.ordinal,
        KnowledgeChunk.element_id,
        KnowledgeChunk.char_start,
        KnowledgeChunk.char_end,
        KnowledgeChunk.chapter,
        KnowledgeChunk.content,
        Element.anchor,
        Element.page_no,
        Element.bbox_x0,
        Element.bbox_y0,
        Element.bbox_x1,
        Element.bbox_y1,
    ]


def indexed_chunks(store, source: dict) -> list[dict] | None:
    with store.engine.connect() as connection:
        # 旧快照或尚未完成的索引允许走原文回退，不把索引缺失解释成文档无内容。
        valid = connection.execute(
            select(KnowledgeIndex.id).where(
                KnowledgeIndex.id == source["index_id"],
                KnowledgeIndex.status == "completed",
                KnowledgeIndex.run_id == source["parse_run_id"],
                KnowledgeIndex.chunk_version == "1",
            )
        ).scalar_one_or_none()
        if valid is None:
            return None
        query = (
            _indexed_query(store, source)
            .with_only_columns(*_columns())
            .order_by(
                KnowledgeChunk.ordinal,
            )
        )
        return [_payload(dict(row), source) for row in connection.execute(query).mappings()]


def search_candidates(
    store: Any,
    sources: list[dict],
    query: str,
    vector: list[float] | None,
    signature: str | None,
    *,
    limit: int,
    min_similarity: float | None,
) -> SearchCandidates:
    statements = []
    by_id = {source["source_id"]: source for source in sources}
    with store.engine.connect() as connection:
        ids = [s["index_id"] for s in sources if s.get("index_id")]
        ready = set(
            connection.execute(
                select(KnowledgeIndex.id).where(
                    KnowledgeIndex.id.in_(ids),
                    KnowledgeIndex.status == "completed",
                    KnowledgeIndex.chunk_version == "1",
                )
            ).scalars()
        )
    fallback = []
    for order, source in enumerate(sources):
        if source.get("index_id") in ready:
            embedding = (
                case(
                    (
                        (KnowledgeIndex.embedding_signature == signature)
                        & (func.cardinality(KnowledgeChunk.embedding) == len(vector or [])),
                        KnowledgeChunk.embedding,
                    ),
                    else_=None,
                )
                if vector is not None
                else literal(None, type_=ARRAY(Double))
            )
            statements.append(
                _indexed_query(store, source).with_only_columns(
                    literal(source["source_id"]).label("source_id"),
                    literal(order).label("source_order"),
                    *_columns(),
                    embedding.label("embedding"),
                )
            )
        else:
            # 仅尚未建成索引的资料重新分块；不能因索引暂不可用而漏掉其原文。
            for row in store.readable_chunks(source):
                bbox = row.get("bbox") or [None] * 4
                fallback.append(
                    (
                        source["source_id"],
                        order,
                        row["ordinal"],
                        row["element_id"],
                        row["char_start"],
                        row["char_end"],
                        row["chapter"],
                        row["content"],
                        row["anchor"],
                        row["page_no"],
                        *bbox,
                        None,
                    )
                )
    if fallback:
        # 此路径只处理未建索引的资料，已完成索引不向应用传输全文或向量。
        names = [
            ("source_id", BigInteger),
            ("source_order", Integer),
            ("ordinal", Integer),
            ("element_id", BigInteger),
            ("char_start", Integer),
            ("char_end", Integer),
            ("chapter", Text),
            ("content", Text),
            ("anchor", Text),
            ("page_no", Integer),
            ("bbox_x0", Double),
            ("bbox_y0", Double),
            ("bbox_x1", Double),
            ("bbox_y1", Double),
            ("embedding", ARRAY(Double)),
        ]
        # 一个 JSON 参数承载回退行，避免大文档的 VALUES 参数数量限制。
        records = [dict(zip((name for name, _ in names), row, strict=True)) for row in fallback]
        transient = (
            func.jsonb_to_recordset(literal(records, type_=JSONB))
            .table_valued(
                *(column(name, kind) for name, kind in names),
            )
            .render_derived(name="unindexed", with_types=True)
        )
        statements.append(select(transient))
    if not statements:
        return SearchCandidates([], [])
    candidates = union_all(*statements).cte("candidates")
    tokens = keywords(query)
    hits = sum(
        (
            case((func.strpos(func.lower(candidates.c.content), token) > 0, 1), else_=0)
            for token in tokens
        ),
        literal(0),
    )
    cosine = literal(None, type_=Double)
    if vector:
        dimensions = func.generate_subscripts(candidates.c.embedding, 1).column_valued("dim")
        other = Grouping(literal(vector, type_=ARRAY(Double)))[dimensions]
        item = candidates.c.embedding[dimensions]
        cosine = (
            select(
                func.coalesce(
                    func.sum(item * other)
                    / func.nullif(
                        func.sqrt(func.sum(item * item) * sum(v * v for v in vector)),
                        0,
                    ),
                    0,
                )
            )
            .correlate(candidates)
            .scalar_subquery()
        )
    scored = select(
        candidates,
        hits.label("hits"),
        candidates.c.embedding.is_not(None).label("semantic"),
        case((candidates.c.embedding.is_not(None), cosine), else_=hits / max(1, len(tokens))).label(
            "similarity"
        ),
    ).cte("scored")
    filtered = select(scored)
    if min_similarity is not None:
        filtered = filtered.where(scored.c.similarity >= min_similarity)
    eligible = filtered.cte("eligible")
    # 与原 Python 规则一致：先按原始相似度过滤，再分别排名并做 RRF；不会先截断召回。
    ties = [eligible.c.source_order.desc(), eligible.c.ordinal.desc()]
    ranked = select(
        eligible,
        func.row_number().over(order_by=[eligible.c.hits.desc(), *ties]).label("lex_rank"),
        func.row_number()
        .over(order_by=[eligible.c.semantic.desc(), eligible.c.similarity.desc(), *ties])
        .label("sem_rank"),
    ).cte("ranked")
    score = case((ranked.c.hits > 0, 1.0 / (60 + ranked.c.lex_rank)), else_=0) + case(
        (ranked.c.semantic, 1.0 / (60 + ranked.c.sem_rank)), else_=0
    )
    final = (
        select(
            *(
                ranked.c[name]
                for name in candidates.c.keys()
                if name not in {"embedding", "source_order"}
            ),
            score.label("score"),
        )
        .where(
            (ranked.c.hits > 0) | ranked.c.semantic,
        )
        .order_by(
            score.desc(),
            case((ranked.c.hits > 0, 0), else_=1),
            case((ranked.c.hits > 0, ranked.c.lex_rank), else_=ranked.c.sem_rank),
        )
        .limit(limit)
    )
    with store.engine.connect() as connection:
        semantic_ids = list(
            connection.execute(
                select(candidates.c.source_id)
                .where(
                    candidates.c.embedding.is_not(None),
                )
                .distinct()
            ).scalars()
        )
        rows = []
        for row in connection.execute(final).mappings():
            payload = dict(row)
            payload["score"] = float(payload["score"])
            rows.append(_payload(payload, by_id[row["source_id"]]))
    return SearchCandidates(rows, sorted(semantic_ids))
