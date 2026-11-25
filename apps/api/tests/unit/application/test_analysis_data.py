"""单标段编制基线：范围、条件、完整清单、版本身份与未决事项。"""

import copy

import pytest
from pydantic import ValidationError
from test_analysis_research import block

from tender.application.analysis.data import (
    BusinessRecord,
    ContextError,
    ContextInput,
    assemble_dataset,
    build_context,
    module_data,
    module_records,
    prepare_records,
)

KEY = "project_basic_info_parsing"
COMMON = {"kind": "common", "lot_refs": []}
LOTS = [{"lot_id": 1, "code": "A", "title": "A标段", "aliases": []},
        {"lot_id": 2, "code": "B", "title": "B标段", "aliases": []}]


@pytest.mark.parametrize("evidence_ids", [None, [], ["valid", "missing"]])
def test_incomplete_evidence_cannot_fall_back_to_inline_citations(evidence_ids):
    record = {"id": "r", "verification": "supported", "citations": [{"quote": "旧内联引用"}]}
    if evidence_ids is not None:
        record["evidence_ids"] = evidence_ids
    data = {"records": [record], "evidence": {"valid": {"quote": "独立证据"}}}
    original = copy.deepcopy(data)
    result = module_records(data)
    assert result[0]["citations"] == [] and result[0]["verification"] == "unavailable"
    assert data == original


def test_empty_hydrated_result_is_reused_and_missing_module_is_projected(monkeypatch):
    from tender.application.analysis import data

    calls = []
    original = data.module_records

    def project(business):
        calls.append(business)
        return original(business)

    monkeypatch.setattr(data, "module_records", project)
    modules = [{"module_key": key, "title": key, "status": "completed",
                "business_data": {"records": [], "marker": key}}
               for key in ("hydrated", "missing")]
    result = assemble_dataset(modules, [], {"hydrated": []})
    assert [business["marker"] for business in calls] == ["missing"]
    assert result["readiness"] == "unavailable"


def record(key="r", text="质保三年", scope=None, **kwargs):
    if scope and scope["kind"] == "lots":
        # 范围测试的合法样本也须在原文中明确标段，才能进入下游选择逻辑。
        text = "、".join(scope["lot_refs"]) + "：" + text
    return BusinessRecord(
        key=key, title=kwargs.pop("title", key), text=text,
        content={"内容": text},
        kind=kwargs.pop("kind", "requirement"), scope=scope or COMMON,
        citations=[{"block_id": "s1r1c0"}], structuring="complete", **kwargs,
    )


def data_state():
    # 此处只验证范围和依赖算法，使用合法输出声明，正文仍走生产生成规则。
    return {"output_schema": {"version": "1", "sections": [
        {"title": "*", "layout": "tree", "columns": ["内容"]},
    ]}}


def dataset(records, *, topics=None, gaps=None, lots=None, key=KEY):
    state = data_state()
    content = "\n".join(r.text for r in records)
    seen = {"s1r1c0": block() | {"content": content}}
    items = prepare_records(records, state, seen, key)
    for item in items:
        item["verification"] = "supported"
    state["agent_workspace"] = {"finalized": True, "final_ids": [i["id"] for i in items]}
    state.update(staged_items=items, business_topics=topics or [],
                 business_gaps=gaps or [])
    module = {"module_key": key, "title": "测试专题", "status": "completed",
              "business_data": module_data(state)}
    return assemble_dataset([module], lots if lots is not None else LOTS)


def test_multi_lot_selection_is_required_and_never_combines_lots():
    data = dataset([
        record("common"), record("a", scope={"kind": "lots", "lot_refs": ["A"]}),
        record("b", scope={"kind": "lots", "lot_refs": ["B"]}),
    ])
    with pytest.raises(ContextError, match="选择一个"):
        build_context(data, ContextInput(snapshot_id=1, purpose="outline"))
    ctx = build_context(data, ContextInput(snapshot_id=1, purpose="outline", lot_id=1))
    assert {r["key"] for r in ctx["requirements"]} == {"common", "a"}
    with pytest.raises(ContextError, match="不属于"):
        build_context(data, ContextInput(snapshot_id=1, purpose="check", lot_id=3))
    with pytest.raises(ValidationError):
        ContextInput(snapshot_id=1, purpose="outline", lot_id=[1, 2])


def test_unknown_scope_and_other_lot_gaps_are_separated():
    data = dataset([
        record("a", scope={"kind": "lots", "lot_refs": ["A"]}),
        record("mystery", scope={"kind": "lots", "lot_refs": ["未知包"]}),
    ], gaps=[{"key": "b", "topic": "price", "code": "missing_source", "detail": "B补充文件缺失",
              "scope": {"kind": "lots", "lot_refs": ["B"]}}])
    ctx = build_context(data, ContextInput(snapshot_id=1, purpose="check", lot_id=1))
    assert [r["key"] for r in ctx["requirements"]] == ["a"]
    assert [r["key"] for r in ctx["unresolved"]] == ["mystery"]
    assert not any(g["detail"] == "B补充文件缺失" for g in ctx["gaps"])
    assert ctx["readiness"] == "partial"


def test_content_requires_applicable_record_ids_and_check_paginates_without_omission():
    data = dataset([record("a"), record("b", scope={"kind": "lots", "lot_refs": ["B"]}),
                    record("c")])
    ctx = build_context(data, ContextInput(snapshot_id=1, purpose="check", lot_id=1, limit=1))
    assert ctx["total_requirements"] == 2 and len(ctx["requirement_manifest"]) == 2
    assert ctx["next_offset"] == 1
    page = build_context(data, ContextInput(snapshot_id=1, purpose="check", lot_id=1, offset=1))
    assert page["next_offset"] is None
    assert ctx["requirements"][0]["id"] != page["requirements"][0]["id"]
    with pytest.raises(ContextError):
        build_context(data, ContextInput(snapshot_id=1, purpose="content", lot_id=1))
    other = next(r["id"] for r in data["requirements"] if r["key"] == "b")
    with pytest.raises(ContextError):
        build_context(data, ContextInput(snapshot_id=1, purpose="content", lot_id=1,
                                         requirement_ids=[other]))


def test_deep_format_tree_is_preserved_and_cycles_are_rejected():
    records = [record(str(n), text=f"材料{n}", kind="format_node", node_type="section",
                      parent_key=str(n-1) if n else None) for n in range(5)]
    data = dataset(records, key="bid_format_outline_parsing", lots=[])
    assert len(data["format_nodes"]) == 5
    assert len(data["format_nodes"][-1]["parent_path"]) == 4
    records[0] = records[0].model_copy(update={"parent_key": "4"})
    with pytest.raises(ValueError, match="循环"):
        dataset(records, key="bid_format_outline_parsing")


def test_lot_specific_addendum_does_not_replace_other_lots_common_requirement():
    data = dataset([
        record("old", text="原质保三年"),
        record("new", text="A标段质保四年", scope={"kind": "lots", "lot_refs": ["A"]}),
        record("change", text="A标段质保三年改为四年", kind="relation", predicate="supersedes",
               subject_key="new", object_key="old", scope={"kind": "lots", "lot_refs": ["A"]}),
    ])
    original = copy.deepcopy(data)
    a = build_context(data, ContextInput(snapshot_id=1, purpose="check", lot_id=1))
    b = build_context(data, ContextInput(snapshot_id=1, purpose="check", lot_id=2))
    assert [r["key"] for r in a["requirements"]] == ["new"]
    assert [r["key"] for r in b["requirements"]] == ["old"]
    assert data == original


def test_relation_scope_cannot_suppress_requirements_in_an_unrelated_lot():
    data = dataset([
        record("old"),
        record("new", text="A标段质保四年", scope={"kind": "lots", "lot_refs": ["A"]}),
        record("change", text="质保改为四年", kind="relation", predicate="supersedes",
               subject_key="new", object_key="old", scope={"kind": "lots", "lot_refs": ["B"]}),
    ])
    b = build_context(data, ContextInput(snapshot_id=1, purpose="check", lot_id=2))
    assert [r["key"] for r in b["requirements"]] == ["old"]
    assert any(g["code"] == "unresolved_relation" for g in b["gaps"])


def test_project_context_keeps_common_data_with_unresolved_applicability():
    data = dataset([record("common"), record("unknown", scope={"kind": "unknown", "lot_refs": []})],
                   lots=[])
    context = build_context(data, ContextInput(snapshot_id=1, purpose="check"))
    assert [r["key"] for r in context["requirements"]] == ["common"]
    assert [r["key"] for r in context["unresolved"]] == ["unknown"]


def test_incomplete_catalog_does_not_auto_select_the_only_known_lot():
    data = dataset([record()], lots=LOTS[:1], gaps=[{
        "key": "catalog", "topic": "lots", "scope": COMMON,
        "code": "lot_catalog_unknown", "detail": "其它标段尚未核对",
    }])
    with pytest.raises(ContextError, match="分标线索"):
        build_context(data, ContextInput(snapshot_id=1, purpose="check"))
    selected = build_context(data, ContextInput(snapshot_id=1, purpose="check", lot_id=1))
    assert selected["lot_id"] == 1 and selected["readiness"] == "partial"












@pytest.mark.parametrize("change", ["cycle", "renamed_parent", "unverified_parent_path"])
def test_snapshot_excludes_invalid_format_paths_after_partial_rollback(change):
    key, state = "bid_format_outline_parsing", data_state()
    records = [record(k, text=f"材料{k}", kind="format_node", node_type="section", parent_key=p)
               for k, p in (("a", None), ("b", "a"), ("c", "b"))]
    seen = {"s1r1c0": block() | {"content": "材料a 材料b 材料c"}}
    original = prepare_records(records, state, seen, key)
    state["staged_items"] = original
    if change == "cycle":
        corrected = prepare_records([
            records[0].model_copy(update={"parent_key": "b"}),
            records[1].model_copy(update={"parent_key": None}),
        ], state, seen, key)
    else:
        corrected = prepare_records([records[0].model_copy(update={"title": "更正后的A"})],
                                    state, seen, key)
    # 模拟 B 未通过后回退；失败或取消的模块也可能把这种暂存状态发布成部分成果。
    state["staged_items"] = [corrected[0], *original[1:]]
    if change == "unverified_parent_path":
        # C 自身已按新祖先路径重审，但 B 仍携带旧路径，C 不能越过无效父节点被使用。
        state["staged_items"][-1] = prepare_records([records[2]], state, seen, key)[0]
    for item in state["staged_items"]:
        item["verification"] = "supported"
    state["agent_workspace"] = {
        "finalized": True, "final_ids": [item["id"] for item in state["staged_items"]],
    }
    data = assemble_dataset([{"module_key": key, "title": "格式", "status": "failed",
                              "business_data": module_data(state)}], [])
    context = build_context(data, ContextInput(snapshot_id=1, purpose="outline"))
    assert {n["key"] for n in context["format_nodes"]} == (
        set() if change == "cycle" else {"a"}
    )
    assert {n["key"] for n in context["unresolved"]} == (
        {"a", "b", "c"} if change == "cycle" else {"b", "c"}
    )
    assert any(g["code"] == ("format_cycle" if change == "cycle" else "parent_path_changed")
               for g in context["gaps"])
