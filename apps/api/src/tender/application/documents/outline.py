"""按解析元素的真实父子关系还原章节树，避免展示层猜测层级。"""
from typing import Any


def build_outline(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把一次 parse_run 的标题元素还原成章节树。

    不改层级、不补全缺失的父节点：层级错了要在解析阶段修，展示层猜层级只会掩盖问题。
    父节点一定排在子节点之前（worker 写入时已校验 parent_index < index），所以顺序遍历即可挂树；
    parent_id 指向的行不在入参里时挂到根，宁可少一层也不要挂到错误的分支下。
    """
    nodes: list[dict[str, Any]] = []
    by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        node = {
            "element_id": int(row["id"]),
            "anchor": row["anchor"],
            "page_no": row["page_no"],
            "level": row["level"],
            "text": row["text"] or "",
            "children": [],
        }
        parent_id = row.get("parent_id")
        parent = by_id.get(parent_id) if isinstance(parent_id, int) else None
        if parent is None:
            nodes.append(node)
        else:
            parent["children"].append(node)
        by_id[node["element_id"]] = node
    return nodes
