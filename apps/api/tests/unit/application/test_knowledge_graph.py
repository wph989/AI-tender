"""关系遍历必须在实时证据核验之后，避免不可读边成为扩展桥梁。"""

from collections import Counter
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tender.application.analysis.data import resolve_scope
from tender.application.knowledge.execution import graph_expand
from tender.domain.knowledge.text import retrieval_block_id
from tender.ports.repository.knowledge.sources import ChunkWindow

LOTS = [
    {"lot_id": 1, "code": "A", "title": "A标段", "aliases": ["A区"]},
    {"lot_id": 2, "code": "B", "title": "B标段", "aliases": ["B区"]},
]


def graph():
    source = {"source_id": 1, "collection_id": 1, "version_id": 1, "parse_run_id": 1}
    blocks = [{**source, "block_id": retrieval_block_id(1, 1, i), "element_id": i + 1,
               "offset": i} for i in range(3)]
    scope = {"kind": "common", "lot_ids": [], "lot_refs": []}
    nodes = [{"id": str(i), "title": f"节点{i}", "verification": "supported"}
             for i in range(3)]
    links = [{
        "subject_id": str(i), "object_id": str(i + 1), "verification": "supported",
        "scope": scope, "predicate": "requires", "text": f"依赖{i}",
        "citations": [blocks[i], blocks[i + 1]],
    } for i in range(2)]
    calls = Counter()

    def resolve(ref):
        calls[ref["block_id"]] += 1

    db = SimpleNamespace(
        relation_snapshot=lambda _: {"data": {
            "facts": nodes, "requirements": [], "format_nodes": [], "relations": links,
        }},
        collections_for_project=lambda _: [1], resolve=resolve,
        readable_chunks=Mock(side_effect=AssertionError("关系扩展不应读取全文")),
        read_chunk_window=Mock(side_effect=lambda _, offset, limit: ChunkWindow(
            blocks[offset:offset + limit], len(blocks), offset + limit < len(blocks),
        )),
    )
    return db, source, blocks, links, calls


def test_graph_two_hops_reuses_shared_evidence():
    db, source, blocks, _, calls = graph()
    hits, links = graph_expand(db, 1, [blocks[0]], [source])
    assert hits == blocks
    assert [link["condition"] for link in links] == ["依赖0", "依赖1"]
    assert calls == {block["block_id"]: 1 for block in blocks}
    assert [call.args[1:] for call in db.read_chunk_window.call_args_list] == [(1, 1), (2, 1)]


def test_unreadable_first_edge_cannot_reveal_a_valid_second_edge():
    db, source, blocks, links, calls = graph()
    # 失效证据只在首边，次边本身可读；次边不能经失效首边进入上下文。
    links[0]["citations"].append({**blocks[0], "block_id": "revoked"})
    original = db.resolve

    def resolve(ref):
        original(ref)
        if ref["block_id"] == "revoked":
            raise LookupError("来源已撤销")

    db.resolve = resolve
    hits, expanded = graph_expand(db, 1, [blocks[0]], [source])
    assert hits == [blocks[0]] and expanded == []
    assert blocks[2]["block_id"] not in calls


@pytest.mark.parametrize("reason", ["unknown_scope", "unverified", "endpoint", "version", "access"])
def test_graph_rejects_unconfirmed_or_out_of_scope_edges(reason):
    db, source, blocks, links, calls = graph()
    if reason == "unknown_scope":
        links[0]["scope"] = {"kind": "unknown", "lot_refs": []}
    elif reason == "unverified":
        links[0]["verification"] = "unavailable"
    elif reason == "endpoint":
        db.relation_snapshot(1)["data"]["facts"][0]["verification"] = "unavailable"
    elif reason == "version":
        source = {**source, "parse_run_id": 2}
    else:
        db.collections_for_project = lambda _: []
    hits, expanded = graph_expand(db, 1, [blocks[0]], [source])
    assert hits == [blocks[0]] and expanded == []
    assert not calls


def test_graph_second_hop_does_not_cross_scope():
    db, source, blocks, links, _ = graph()
    links[1]["scope"] = resolve_scope({"kind": "lots", "lot_refs": ["A"]}, LOTS)
    hits, expanded = graph_expand(db, 1, [blocks[0]], [source])
    assert hits == blocks[:2] and len(expanded) == 1


@pytest.mark.parametrize("lot_refs", [["B", "A"], ["A标段", "B标段"], ["A区", "B区"]])
def test_graph_second_hop_matches_same_lots_with_different_references(lot_refs):
    db, source, blocks, links, _ = graph()
    # 用生产范围解析生成快照，避免复用同一 scope 对象掩盖名称和顺序差异。
    links[0]["scope"] = resolve_scope({"kind": "lots", "lot_refs": ["A", "B"]}, LOTS)
    links[1]["scope"] = resolve_scope({"kind": "lots", "lot_refs": lot_refs}, LOTS)
    hits, expanded = graph_expand(db, 1, [blocks[0]], [source])
    assert hits == blocks
    assert [link["condition"] for link in expanded] == ["依赖0", "依赖1"]
    assert expanded[1]["scope"] == "、".join(lot_refs)


@pytest.mark.parametrize("first_refs,next_refs", [(["A"], ["B"]), (["A", "B"], ["A"])])
def test_graph_second_hop_keeps_different_lot_sets_separate(first_refs, next_refs):
    db, source, blocks, links, calls = graph()
    links[0]["scope"] = resolve_scope({"kind": "lots", "lot_refs": first_refs}, LOTS)
    links[1]["scope"] = resolve_scope({"kind": "lots", "lot_refs": next_refs}, LOTS)
    hits, expanded = graph_expand(db, 1, [blocks[0]], [source])
    assert hits == blocks[:2] and len(expanded) == 1
    assert blocks[2]["block_id"] not in calls


def test_graph_does_not_read_when_all_referenced_blocks_already_hit():
    db, source, blocks, _, calls = graph()
    hits, links = graph_expand(db, 1, list(blocks), [source])
    assert hits == blocks and len(links) == 2
    assert calls == {block["block_id"]: 1 for block in blocks}
    db.read_chunk_window.assert_not_called()


def test_graph_expands_only_referenced_block_within_shared_long_element():
    db, source, blocks, links, _ = graph()
    # 同一长元素的块共用 element_id 与位置，按元素扩展会带入无关条款。
    blocks[:] = [{**blocks[0], "block_id": retrieval_block_id(1, 1, i), "offset": i,
                 "locations": [{"element_id": 1}]} for i in range(15)]
    links[:] = [dict(links[0], citations=[blocks[0], blocks[12], blocks[2]])]
    hits, expanded = graph_expand(db, 1, [blocks[0]], [source])
    assert hits == [blocks[0], blocks[2], blocks[12]] and len(expanded) == 1
    assert [call.args[1:] for call in db.read_chunk_window.call_args_list] == [(2, 1), (12, 1)]


def test_graph_ignores_unreferenced_block_returned_by_window():
    db, source, blocks, links, _ = graph()
    links[:] = [links[0]]
    db.read_chunk_window.return_value = ChunkWindow([blocks[2]], None, False)
    db.read_chunk_window.side_effect = None
    hits, expanded = graph_expand(db, 1, [blocks[0]], [source])
    assert hits == [blocks[0]] and len(expanded) == 1
