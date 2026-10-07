"""格式层级只保留一个父级事实，展示与关系从同一结构生成。"""

from copy import deepcopy

import pytest

from tender.application.analysis_outline import outline_result

TEXT = "商务标。资格材料：营业执照须盖章。技术标。响应表逐项填报。附件：培训安排，单独提交。"
SEEN = {"b1": {"content": TEXT, "source_id": 1, "element_id": 7}}


def node(key, name, parent=None, node_type="section", requirements=None):
    return {
        "id": key,
        "name": name,
        "node_type": node_type,
        "parent_id": parent,
        "requirements": requirements or [],
        "citations": [{"block_id": "b1", "quote": TEXT}],
    }


def test_independent_attachment_has_no_second_parent_in_text_cells_or_relations():
    nodes = [
        node("business", "商务标", node_type="group"),
        node("qualification", "资格材料", "business"),
        node("license", "营业执照", "qualification", requirements=["营业执照须盖章"]),
        node("technical", "技术标", node_type="group"),
        node("response", "响应表", "technical", requirements=["响应表逐项填报"]),
        node("training", "培训安排", requirements=["单独提交"]),
    ]
    items, relations = outline_result({"outline_nodes": nodes}, SEEN)
    training = items[-1]
    assert training["text"] == "培训安排；编制要求：单独提交"
    assert training["cells"]["逻辑标"] == "独立章节"
    assert training["cells"]["层级"] == "1" and training["cells"]["上级路径"] == ""
    assert all("培训安排" not in rel["object"] for rel in relations)
    assert items[2]["cells"]["上级路径"] == "商务标 / 资格材料"
    assert items[2]["cells"]["层级"] == "2"
    assert items[2]["citations"][0]["element_id"] == 7
    assert relations[1]["object"] == "商务标 / 资格材料 / 营业执照"


@pytest.mark.parametrize(
    "nodes",
    [
        [node("a", "商务标"), node("a", "技术标")],
        [node("a", "商务标", "missing")],
        [node("a", "商务标", "b"), node("b", "技术标", "a")],
        [node("a", "商务标", "b", "group"), node("b", "技术标")],
        [
            node("a", "商务标"),
            node("b", "资格材料", "a"),
            node("c", "营业执照", "b"),
            node("d", "响应表", "c"),
        ],
    ],
)
def test_invalid_forests_are_rejected_instead_of_displaying_inconsistent_hierarchy(nodes):
    with pytest.raises(ValueError):
        outline_result({"outline_nodes": nodes}, SEEN)


def test_parallel_free_text_and_relations_are_rejected():
    with pytest.raises(ValueError, match="不重复"):
        outline_result({"outline_nodes": [node("a", "培训安排")], "relations": []}, SEEN)
    raw = node("a", "培训安排") | {"text": "技术标附件"}
    with pytest.raises(ValueError, match="字段"):
        outline_result({"outline_nodes": [raw]}, SEEN)


def test_node_name_requirement_and_parent_must_have_read_evidence():
    for raw in [node("a", "不存在的材料"), node("a", "培训安排", requirements=["技术标附件"])]:
        with pytest.raises(ValueError, match="逐字"):
            outline_result({"outline_nodes": [raw]}, SEEN)
    child = node("b", "营业执照", "a")
    child["citations"] = [{"block_id": "b1", "quote": "营业执照须盖章"}]
    items, relations = outline_result({"outline_nodes": [node("a", "资格材料"), child]}, SEEN)
    assert [ref["quote"] for ref in items[1]["citations"]] == ["营业执照须盖章", TEXT]
    assert relations[0]["citations"] == items[1]["citations"]
    assert items[1]["kind"] == "judgment"  # 汇集证据不会直接把模型判断升级成事实。
    unread = deepcopy(child)
    unread["citations"][0]["block_id"] = "outside"
    with pytest.raises(ValueError, match="未读取"):
        outline_result({"outline_nodes": [unread]}, SEEN)


def test_spliced_quote_error_identifies_the_node_to_repair():
    raw = node("qualification", "资格材料")
    raw["citations"] = [{"block_id": "b1", "quote": "商务标。资格材料：培训安排"}]
    with pytest.raises(ValueError, match="qualification（资格材料）引用校验失败"):
        outline_result({"outline_nodes": [raw]}, SEEN)
