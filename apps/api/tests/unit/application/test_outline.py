"""章节树还原：挂树、兜底与顺序。

章节树是前端 OutlineNav 的数据源，挂错分支比少一层更难发现——用户看到的是
「这个标题怎么跑到那一章下面去了」，不会意识到是后端拼树拼错了。
"""

from __future__ import annotations

from typing import Any

from tender.application.extraction import build_outline


def _title(
    row_id: int,
    text: str,
    *,
    parent_id: int | None = None,
    page: int = 1,
    level: int = 1,
) -> dict[str, Any]:
    return {
        "id": row_id,
        "parent_id": parent_id,
        "anchor": f"p{page}b{row_id}",
        "page_no": page,
        "level": level,
        "text": text,
    }


def test_nested_titles_are_attached_to_their_parents() -> None:
    tree = build_outline(
        [
            _title(1, "第一章"),
            _title(2, "1.1 小节", parent_id=1, level=2),
            _title(3, "1.1.1 细节", parent_id=2, level=3),
            _title(4, "第二章"),
        ]
    )

    assert [node["text"] for node in tree] == ["第一章", "第二章"]
    assert [child["text"] for child in tree[0]["children"]] == ["1.1 小节"]
    assert [child["text"] for child in tree[0]["children"][0]["children"]] == ["1.1.1 细节"]
    assert tree[1]["children"] == []


def test_sibling_order_follows_input_order() -> None:
    tree = build_outline(
        [
            _title(1, "甲"),
            _title(2, "乙", page=2),
            _title(3, "丙", page=3),
        ]
    )

    assert [node["anchor"] for node in tree] == ["p1b1", "p2b2", "p3b3"]


def test_missing_parent_falls_back_to_root() -> None:
    """父节点不在入参里（被过滤掉或不是标题）时不许猜层级，直接挂根。"""
    tree = build_outline([_title(2, "孤儿小节", parent_id=99, level=2)])

    assert len(tree) == 1
    assert tree[0]["anchor"] == "p1b2"
    assert tree[0]["children"] == []


def test_level_is_kept_as_documented_not_recomputed() -> None:
    """层级原样透出：解析给的是几级就是几级，展示层重算会掩盖解析问题。"""
    tree = build_outline([_title(1, "怪标题", level=99)])

    assert tree[0]["level"] == 99


def test_empty_input_returns_empty_tree() -> None:
    assert build_outline([]) == []
