"""数据库内精确排名，仅返回有界候选；未建索引的资料保留原文回退。"""

from collections.abc import Mapping
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
from tender.domain.knowledge.text import (
    CHUNK_VERSION,
    chunk_bbox,
    chunk_block_id,
    iter_element_chunks,
)
from tender.ports.repository.knowledge.retrieval import SearchCandidates
from tender.ports.repository.knowledge.sources import ChunkWindow

# 索引「已建成」的唯一判定：三处查询必须同口径，读写版本也来自同一常量。
_READY_INDEX = (
    KnowledgeIndex.status == "completed",
    KnowledgeIndex.chunk_version == CHUNK_VERSION,
)


def _ready_index(index_id: int):
    return (KnowledgeIndex.id == index_id, *_READY_INDEX)


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
            *_ready_index(source["index_id"]),
            KnowledgeIndex.source_id == source["source_id"],
            KnowledgeIndex.version_id == source["version_id"],
            KnowledgeIndex.run_id == source["parse_run_id"],
        )
        .order_by(None)
    )


def _payload(row: Mapping[str, Any], source: dict) -> dict:
    result = {**source, **row}
    for axis in ("x0", "y0", "x1", "y1"):
        result.pop("bbox_" + axis, None)
    result.update(
        offset=row["ordinal"],
        block_id=chunk_block_id(source["source_id"], source["parse_run_id"], row["ordinal"]),
        bbox=chunk_bbox(row),
    )
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
        query = (
            _indexed_query(store, source)
            .with_only_columns(*_columns())
            .order_by(
                KnowledgeChunk.ordinal,
            )
        )
        rows = [_payload(dict(row), source) for row in connection.execute(query).mappings()]
        if rows:
            return rows
        # 空结果可能是索引失效而非文档无内容；只在空结果时补一次校验，保留原文回退。
        # 旧快照或尚未完成的索引允许走原文回退，不把索引缺失解释成文档无内容。
        valid = connection.execute(
            select(KnowledgeIndex.id).where(
                *_ready_index(source["index_id"]),
                KnowledgeIndex.run_id == source["parse_run_id"],
            )
        ).scalar_one_or_none()
        return [] if valid is not None else None


def read_chunk_window(store, source: dict, offset: int, limit: int) -> ChunkWindow:
    if offset < 0 or not 1 <= limit <= 12:
        raise ValueError("补读范围无效")
    with store.engine.connect() as connection:
        if source.get("index_id"):
            valid = connection.execute(select(KnowledgeIndex.id).where(
                *_ready_index(source["index_id"]),
                KnowledgeIndex.source_id == source["source_id"],
                KnowledgeIndex.version_id == source["version_id"],
                KnowledgeIndex.run_id == source["parse_run_id"],
            )).scalar_one_or_none()
            if valid is not None:
                query = _indexed_query(store, source)
                total = int(connection.execute(
                    query.with_only_columns(func.count()).order_by(None),
                ).scalar_one())
                rows = [_payload(dict(row), source) for row in connection.execute(
                    query.with_only_columns(*_columns()).where(
                        KnowledgeChunk.ordinal >= offset,
                        KnowledgeChunk.ordinal < offset + limit,
                    ).order_by(KnowledgeChunk.ordinal),
                ).mappings()]
                return ChunkWindow(rows, total, offset + limit < total)

        # 旧索引/未建索引只扫描所需前缀；不为取得精确总数读取其余全文。
        rows = []
        total = 0
        result = connection.execute(
            store._blocks_query(source).execution_options(stream_results=True, max_row_buffer=16),
        )
        with result:
            for element, chunk in iter_element_chunks(result.mappings()):
                total = chunk["ordinal"] + 1
                if chunk["ordinal"] >= offset + limit:
                    return ChunkWindow(rows, None, True)
                if chunk["ordinal"] >= offset:
                    position = {key: element[key] for key in (
                        "anchor", "page_no", "bbox_x0", "bbox_y0", "bbox_x1", "bbox_y1",
                    )}
                    rows.append(_payload(position | chunk, source))
        return ChunkWindow(rows, total, False)


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
                    *_READY_INDEX,
                )
            ).scalars()
        )
    indexed = []
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
            indexed.append(
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
    statements = [*indexed]
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
    # 每个分块只转换一次小写，命中计数复用，不再按 token 数重复扫描全文。
    lowered = select(
        candidates, func.lower(candidates.c.content).label("normalized_content")
    ).cte("lowered")
    tokens = keywords(query)
    hits = sum(
        (
            case((func.strpos(lowered.c.normalized_content, token) > 0, 1), else_=0)
            for token in tokens
        ),
        literal(0),
    )
    embedding = lowered.c.embedding
    cosine = literal(None, type_=Double)
    if vector:
        dimensions = func.generate_subscripts(embedding, 1).column_valued("dim")
        other = Grouping(literal(vector, type_=ARRAY(Double)))[dimensions]
        item = embedding[dimensions]
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
            .correlate(lowered)
            .scalar_subquery()
        )
    scored = select(
        *(lowered.c[name] for name in candidates.c.keys()),
        hits.label("hits"),
        ((hits > 0) & (hits / max(1, len(tokens)) >= (
            min_similarity if min_similarity is not None else 0
        ))).label("lexical"),
        (embedding.is_not(None) & (cosine >= (
            min_similarity if min_similarity is not None else -1
        ))).label("semantic"),
        cosine.label("similarity"),
    ).cte("scored")
    eligible = select(scored).where(scored.c.lexical | scored.c.semantic).cte("eligible")
    # 通道资格分别排名，另一通道不合格的候选不能挤占本通道的名次。
    ties = [eligible.c.source_order.desc(), eligible.c.ordinal.desc()]
    ranked = select(
        eligible,
        func.row_number().over(order_by=[eligible.c.lexical.desc(), eligible.c.hits.desc(),
                                        *ties]).label("lex_rank"),
        func.row_number()
        .over(order_by=[eligible.c.semantic.desc(), eligible.c.similarity.desc(), *ties])
        .label("sem_rank"),
    ).cte("ranked")
    score = case((ranked.c.lexical, 1.0 / (60 + ranked.c.lex_rank)), else_=0) + case(
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
            ranked.c.lexical | ranked.c.semantic,
        )
        .order_by(
            score.desc(),
            case((ranked.c.lexical, 0), else_=1),
            case((ranked.c.lexical, ranked.c.lex_rank), else_=ranked.c.sem_rank),
        )
        .limit(limit)
    )
    with store.engine.connect() as connection:
        semantic_ids = []
        if vector and indexed:
            # 回退分支的向量恒为空，语义资料集合只需在已建索引的分支上取。
            semantic_candidates = union_all(*indexed).cte("semantic_candidates")
            semantic_ids = list(
                connection.execute(
                    select(semantic_candidates.c.source_id)
                    .where(semantic_candidates.c.embedding.is_not(None))
                    .distinct()
                ).scalars()
            )
        rows = []
        for row in connection.execute(final).mappings():
            payload = dict(row)
            payload["score"] = float(payload["score"])
            rows.append(_payload(payload, by_id[row["source_id"]]))
    return SearchCandidates(rows, sorted(semantic_ids))
