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


def test_independent_attachment_has_no_second_parent_in_values_or_relations():
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
    # 节点名是字段，编制要求各成一个值，层级/上级路径改由程序生成的 note 表达。
    assert training["field"] == "培训安排"
    assert training["group"] == "独立章节"
    assert [value["value"] for value in training["values"]] == ["单独提交"]
    assert "节点类型：材料章节" in training["note"]
    assert "层级：1" in training["note"] and "上级路径：无" in training["note"]
    assert all("培训安排" not in rel["object"] for rel in relations)
    license_item = items[2]
    assert license_item["group"] == "商务标"
    assert license_item["values"][0]["value"] == "营业执照须盖章"
    assert "上级路径：商务标 / 资格材料" in license_item["note"]
    assert "层级：2" in license_item["note"]
    assert license_item["values"][0]["citations"][0]["element_id"] == 7
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
    # 子节点窄摘录与父节点整块摘录来自同一元素，是同一处原文：只显示更完整的一条，
    # 避免同一位置出现多个定位按钮（同一元素里被包含的窄摘录不会给出新信息）。
    assert [ref["quote"] for ref in items[1]["values"][0]["citations"]] == [TEXT]
    # 关系引文必须复用校验后的引文行，携带块身份元数据，前端才能定位和高亮。
    assert relations[0]["citations"] == items[1]["values"][0]["citations"]
    # 汇集到的祖先引文只是值的证据，程序不会把模型判断升级成事实。
    assert items[1]["verification"] == "pending"
    unread = deepcopy(child)
    unread["citations"][0]["block_id"] = "outside"
    with pytest.raises(ValueError, match="未读取"):
        outline_result({"outline_nodes": [unread]}, SEEN)


def test_spliced_quote_error_identifies_the_node_to_repair():
    raw = node("qualification", "资格材料")
    raw["citations"] = [{"block_id": "b1", "quote": "商务标。资格材料：培训安排"}]
    with pytest.raises(ValueError, match="qualification（资格材料）引用校验失败"):
        outline_result({"outline_nodes": [raw]}, SEEN)
