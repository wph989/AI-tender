"""单标段编制基线：范围、条件、完整清单、版本身份与未决事项。"""

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError
from synthesis_fixtures import research_calls
from test_analysis_research import block, session
from test_deep_analysis import KEY as MODULE
from test_deep_analysis import SKILL, ScriptedRouter, call

from tender.application.analysis_data import (
    BusinessRecord,
    ContextError,
    ContextInput,
    CoverageInput,
    assemble_dataset,
    build_context,
    display_items,
    module_data,
    prepare_coverage,
    prepare_records,
)
from tender.application.analysis_data_store import accessible_data
from tender.application.analysis_policy import correction_count, progress_signature
from tender.application.deep_analysis import RoutedAgentModel, build_module_agent, invoke_module
from tender.application.knowledge import merge_field_entries

KEY = "project_basic_info_parsing"
COMMON = {"kind": "common", "lot_refs": []}
LOTS = [{"lot_id": 1, "code": "A", "title": "A标段", "aliases": []},
        {"lot_id": 2, "code": "B", "title": "B标段", "aliases": []}]


def record(key="r", text="质保三年", scope=None, **kwargs):
    return BusinessRecord(
        key=key, title=kwargs.pop("title", key), text=text,
        kind=kwargs.pop("kind", "requirement"), scope=scope or COMMON,
        citations=[{"block_id": "s1r1c0", "quote": text}], structuring="complete", **kwargs,
    )


def dataset(records, *, topics=None, coverage=None, gaps=None, lots=None, key=KEY):
    state = {}
    content = "\n".join(r.text for r in records)
    seen = {"s1r1c0": block() | {"content": content}}
    items = prepare_records(records, state, seen, key)
    for item in items:
        item["verification"] = "supported"
    state.update(staged_items=items, business_topics=topics or [], business_coverage=coverage or [],
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


def test_same_key_corrections_keep_identity_and_conditions_are_kept_for_review():
    state, seen = {}, {"s1r1c0": block() | {"content": "质保三年\n质保四年"}}
    first = prepare_records([record()], state, seen, KEY)[0]
    second = prepare_records([record(text="质保四年", title="更名", conditions={
        "expression": "不少于四年", "logic": "all", "terms": [
            {"subject": "质保期限", "operator": ">=", "value": "4", "unit": "年",
             "time_basis": None}], "exceptions": [],
    })], state, seen, KEY)[0]
    assert first["id"] == second["id"]
    assert second["business"]["conditions"]["terms"][0]["operator"] == ">="
    assert second["business"]["conditions"]["terms"][0]["time_basis"] is None


def test_deep_format_tree_is_preserved_and_cycles_are_rejected():
    records = [record(str(n), text=f"材料{n}", kind="format_node", node_type="section",
                      parent_key=str(n-1) if n else None) for n in range(5)]
    data = dataset(records, key="bid_format_outline_parsing", lots=[])
    assert len(data["format_nodes"]) == 5
    assert len(data["format_nodes"][-1]["parent_path"]) == 4
    records[0] = records[0].model_copy(update={"parent_key": "4"})
    with pytest.raises(ValueError, match="循环"):
        dataset(records, key="bid_format_outline_parsing")


def test_completed_modules_do_not_hide_unchecked_topics():
    data = dataset([record()], topics=[{"key": "score", "title": "评分细则"}])
    assert data["readiness"] == "partial"
    assert data["coverage"][0]["status"] == "unchecked"
    assert any(g["code"] == "coverage_unchecked" for g in data["gaps"])


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


def test_native_graph_submits_business_records_and_reuses_stable_identity():
    async def run():
        state, saved, reviewed = {}, [], []
        research = session([block()])
        first = record("warranty", title="质保")
        corrected = first.model_copy(update={"title": "质保期限"})
        def submission(value, final):
            return {"records": [synthesis_record(value)], "coverage": [], "gaps": [],
                    "research_summary": "已核对质保", "final": final}
        router = ScriptedRouter([
            *research_calls(),
            call("submit_analysis", submission(first, False), 2),
            call("submit_analysis", submission(corrected, True), 3),
        ])
        async def save(value):
            saved.append(copy.deepcopy(value))
        async def noop():
            pass
        async def review(items):
            reviewed.extend(copy.deepcopy(items))
            for item in items:
                item["verification"] = "supported"
        graph, files = build_module_agent(
            key=MODULE, model=RoutedAgentModel(router=router), research=research, state=state,
            snapshot={**SKILL, "__analysis_data_version__": "1",
                      MODULE + "/references/coverage.json": json.dumps([])},
            checkpointer=InMemorySaver(), reserve_tool=noop, save=save, review_support=review,
        )
        await invoke_module(graph, files, thread_id="native-business", task="解析", state=state,
                            save=save)
        records = state["draft"]["business_data"]["records"]
        assert len(records) == 1 and records[0]["title"] == "质保期限"
        assert reviewed[0]["id"] == reviewed[1]["id"]
        assert records[0]["scope"]["kind"] == "common"
        assert len(router.requests) == 5
    asyncio.run(run())


def test_display_projection_keeps_same_title_records_in_different_lots():
    items = prepare_records([
        record("a", title="质保", scope={"kind": "lots", "lot_refs": ["A"]}),
        record("b", title="质保", scope={"kind": "lots", "lot_refs": ["B"]}),
    ], {}, {"s1r1c0": block()}, KEY)
    for item in items:
        item["verification"] = "supported"
    projected = display_items(items)
    assert all("business" not in item for item in projected)
    assert len(merge_field_entries(projected)) == 2
    assert {item["record_id"] for item in projected} == {item["id"] for item in items}


def test_business_corrections_use_identity_and_keep_lot_budgets_separate():
    state = {}
    items = prepare_records([
        record("a", title="质保", scope={"kind": "lots", "lot_refs": ["A"]}),
        record("b", title="质保", scope={"kind": "lots", "lot_refs": ["B"]}),
    ], state, {"s1r1c0": block()}, KEY)
    assert correction_count(state, items[0]) == 1
    assert correction_count(state, items[1]) == 1
    corrected = copy.deepcopy(items[0])
    corrected["field"] = "改名"
    corrected["values"][0]["value"] = "修改后的条件"
    assert correction_count(state, corrected) == 2
    # 同一语义换 key 也不能绕过事实额度；不同标段的额度则仍独立。
    renamed = copy.deepcopy(items[1])
    renamed["id"] = "new-id"
    renamed["business"].update(id="new-id", key="new-key", title="改名")
    assert correction_count(state, renamed) == 2


def test_verified_scope_correction_counts_as_progress_but_title_change_does_not():
    item = prepare_records([record()], {}, {"s1r1c0": block()}, KEY)[0]
    item["verification"] = "supported"
    state = {"staged_items": [item]}
    before = progress_signature({}, state)
    item["field"] = item["business"]["title"] = "改名"
    assert progress_signature({}, state) == before
    item["business"]["scope"] = {"kind": "lots", "lot_refs": ["A"]}
    assert progress_signature({}, state) != before


def test_lot_coverage_does_not_silently_complete_other_lots():
    data = dataset([record("a", scope={"kind": "lots", "lot_refs": ["A"]})],
        topics=[{"key": "warranty", "title": "质保要求"}], coverage=[{
            "topic": "warranty", "scope": {"kind": "lots", "lot_refs": ["A"]},
            "status": "extracted", "record_keys": ["a"], "detail": "已核对A标段",
        }])
    b = build_context(data, ContextInput(snapshot_id=1, purpose="check", lot_id=2))
    assert any(c["topic"] == "warranty" and c["status"] == "unchecked" for c in b["coverage"])


def test_lot_specific_records_cannot_prove_common_topic_coverage():
    data = dataset([record("a", scope={"kind": "lots", "lot_refs": ["A"]})],
        topics=[{"key": "warranty", "title": "质保要求"}], coverage=[{
            "topic": "warranty", "scope": COMMON, "status": "extracted",
            "record_keys": ["a"], "detail": "公共要求已核对",
        }])
    assert data["coverage"][0]["status"] == "pending"


def test_not_applicable_proof_is_preserved_and_rechecked_on_read():
    seen = {"s1r1c0": block() | {"content": "本项目无需保证金"}}
    state = {"business_topics": [{"key": "deposit", "title": "保证金"}]}
    entries, items = prepare_coverage([CoverageInput(
        topic="deposit", scope=COMMON, status="not_applicable", detail="本项目无需保证金",
        citations=[{"block_id": "s1r1c0", "quote": "本项目无需保证金"}],
    )], state, seen, state["business_topics"], KEY)
    items[0]["verification"] = "supported"
    state.update(staged_items=items, business_coverage=entries)
    data = assemble_dataset([{
        "module_key": KEY, "title": "保证金", "status": "completed",
        "business_data": module_data(state),
    }], [])
    assert data["coverage"][0].get("citations")
    visible = accessible_data(SimpleNamespace(resolve=lambda ref: ref), data, [])
    assert visible["coverage"] == []
    assert visible["gaps"][0]["code"] == "source_unavailable"
    assert "无需保证金" not in json.dumps(visible, ensure_ascii=False)


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


@pytest.mark.parametrize("legacy_keys", [False, True])
def test_not_applicable_proofs_are_independent_for_each_lot(legacy_keys):
    state = {"business_topics": [{"key": "deposit", "title": "保证金"}]}
    quote = "A标段和B标段均无需保证金"
    entries, items = prepare_coverage([
        CoverageInput(topic="deposit", scope={"kind": "lots", "lot_refs": [lot]},
                      status="not_applicable", detail=f"{lot}标段无需保证金",
                      citations=[{"block_id": "s1r1c0", "quote": quote}])
        for lot in ("A", "B")
    ], state, {"s1r1c0": block() | {"content": quote}}, state["business_topics"], KEY)
    if not legacy_keys:
        assert len({item["business"]["key"] for item in items}) == 2
    for item in items:
        item["verification"] = "supported"
        if legacy_keys:
            # 已保存的旧检查点也必须按证明 ID 查找，不能再次按重复 key 丢掉前一标段。
            item["business"]["key"] = "coverage:deposit"
    state.update(staged_items=items, business_coverage=entries)
    data = assemble_dataset([{"module_key": KEY, "title": "保证金", "status": "completed",
                              "business_data": module_data(state)}], LOTS)
    assert [c["status"] for c in data["coverage"]] == ["not_applicable", "not_applicable"]
    assert all(c["citations"][0]["quote"] == quote for c in data["coverage"])


def synthesis_record(record):
    # 数据投影测试仍使用通用业务记录，真实图必须按其专题格式构造综合内容。
    if record.kind == "format_node":
        return record.model_dump() | {"content": {"编制要求": [record.text]}}
    return record.model_dump() | {
        "group": "项目基本信息", "content": {"字段": record.title, "内容": record.text},
    }


def business_submission(records=(), *, gaps=(), final=False):
    return {"records": [synthesis_record(r) for r in records], "coverage": [], "gaps": list(gaps),
            "research_summary": "已核对本批结果", "final": final}


async def run_business_batches(key, batches, rejected_text=None):
    state, saved = {}, []
    router = ScriptedRouter([
        *research_calls(query="项目要求"),
        *[call("submit_analysis", batch, index + 2) for index, batch in enumerate(batches)],
    ])

    async def save(value):
        saved.append(copy.deepcopy(value))

    async def noop():
        pass

    async def review(items):
        for item in items:
            item["verification"] = (
                "unsupported" if rejected_text in item["business"]["content"].values()
                or [rejected_text] in item["business"]["content"].values() else "supported"
            )

    content = "\n".join(r["text"] for batch in batches for r in batch["records"])
    graph, files = build_module_agent(
        key=key, model=RoutedAgentModel(router=router),
        research=session([block() | {"content": content}]), state=state,
        snapshot={**SKILL, key + "/SKILL.md": (
            f"---\nname: {key.replace('_', '-')}\ndescription: 测试解析\n---\n核对项目"
        ), "__analysis_data_version__": "1", key + "/references/coverage.json": "[]"},
        checkpointer=InMemorySaver(), reserve_tool=noop, save=save, review_support=review,
    )
    await invoke_module(graph, files, thread_id="business-regression", task="解析", state=state,
                        save=save)
    return state, saved, router


def test_partial_format_rollback_requires_repair_before_final_submission():
    key = "bid_format_outline_parsing"
    a = record("a", text="材料A", kind="format_node", node_type="section")
    b = record("b", text="材料B", kind="format_node", node_type="section", parent_key="a")
    moved_a = a.model_copy(update={"parent_key": "b"})
    moved_b = record("b", text="材料B错误条件", kind="format_node", node_type="section")
    state, saved, router = asyncio.run(run_business_batches(key, [
        business_submission([a]), business_submission([b]),
        business_submission([moved_a]), business_submission([moved_b]),
        business_submission(final=True), business_submission([a], final=True),
    ], rejected_text=moved_b.text))
    # 空 final 不能发布部分回退产生的环，必须让模型收到结构反馈并修正后再完成。
    assert len(router.requests) == 8
    assert any("循环" in str(messages) for messages, _ in router.requests)
    records = state["draft"]["business_data"]["records"]
    assert {r["key"]: r["parent_key"] for r in records} == {"a": None, "b": "a"}
    assert all("draft" not in s for s in saved if any(
        i.get("business", {}).get("parent_key") == "b" for i in s.get("staged_items", [])
    ))


@pytest.mark.parametrize("change", ["cycle", "renamed_parent", "unverified_parent_path"])
def test_snapshot_excludes_invalid_format_paths_after_partial_rollback(change):
    key, state = "bid_format_outline_parsing", {}
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


@pytest.mark.parametrize("keep_unresolved", [False, True])
def test_final_gaps_replace_history_only_after_successful_verification(keep_unresolved):
    missing = {"key": "reference", "topic": "warranty", "scope": COMMON,
               "code": "unresolved_reference", "detail": "质保条款转引待补读"}
    remaining = {**missing, "key": "other", "detail": "另一条要求尚未核对"}
    bad = record("warranty", text="质保错误条件")
    good = record("warranty", text="质保三年")
    final_gaps = [remaining] if keep_unresolved else []
    state, saved, _ = asyncio.run(run_business_batches(KEY, [
        business_submission(gaps=[missing, remaining]), business_submission([good]),
        business_submission([bad], final=True),
        business_submission([good], gaps=final_gaps, final=True),
    ], rejected_text=bad.text))
    failed_final = [s for s in saved if s.get("correction_failures") and "draft" not in s]
    assert failed_final
    assert all({g["key"] for g in s["business_gaps"]} == {"reference", "other"}
               for s in failed_final)
    data = state["draft"]["business_data"]
    assert data["gaps"] == final_gaps
    assert [r["content"]["内容"] for r in data["records"]] == [good.text]
