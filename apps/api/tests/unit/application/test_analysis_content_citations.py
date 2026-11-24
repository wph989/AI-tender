"""正文逐条选证经过真实校验入口，并随独立业务 JSON 保存，不能借整项来源冒充绑定。"""

import copy
import json
from unittest.mock import Mock

import pytest
from test_analysis_research import block

from tender.application.analysis.data import (
    SynthesisRecord,
    module_data,
    prepare_records,
)
from tender.application.analysis.service import AnalysisService
from tender.application.knowledge.service import visible_items
from tender.domain.analysis.contract import FLOW_VERSION, FLOW_VERSION_KEY, RUNTIME_VERSION


def prepared(*, alternate=False):
    rows = [
        block() | {"block_id": "budget", "content": "项目预算为2130万元。"},
        block(2, 20) | {"block_id": "term", "content": "服务期为2年。"},
    ]
    if alternate:
        rows.append(rows[0] | {"block_id": "alternate", "element_id": 30, "anchor": "p1b30"})
    seen = {row["block_id"]: row for row in rows}
    state = {"output_schema": {"version": "1", "sections": [
        {"title": "项目背景", "layout": "list", "columns": ["背景"]},
    ]}}
    record = SynthesisRecord(
        key="project", kind="fact", title="项目概况", group="项目背景",
        scope={"kind": "common", "lot_refs": []},
        content={"背景": [
            "项目预算为2130万元。", "服务期为2年。", "项目预算2130万元，服务期2年。",
        ]},
        citations=[{"block_id": row["block_id"]} for row in rows],
    )
    items = prepare_records([record], state, seen, "tech_requirement_parsing")
    state["agent_workspace"] = {
        "finalized": True, "final_ids": [i["id"] for i in items],
    }
    state["staged_items"] = items
    return state, items, seen


def bind_content(item, seen, groups):
    refs = {ref["block_id"]: ref for ref in item["values"][0]["citations"]}
    item["values"][0]["citations"] = [refs[k] for k in ("budget", "term")]
    # 构造已发布数据，以覆盖现行读取仍支持的独立正文引用。
    item["output"]["citations"] = {"背景": [[refs[k] for k in keys] for keys in groups]}
    item["verification"] = "supported"


def test_content_citations_round_trip_without_conflicting_values():
    state, items, seen = prepared()
    bind_content(items[0], seen, [["budget"], ["term"], ["budget", "term"]])

    data = module_data(state)
    record = data["records"][0]
    bindings = record["content_evidence"]["背景"]
    assert [[data["evidence"][key]["block_id"] for key in group] for group in bindings] == [
        ["budget"], ["term"], ["budget", "term"],
    ]
    assert {key for group in bindings for key in group} <= set(record["evidence_ids"])


def test_content_keeps_verified_alternative_that_whole_record_did_not_select():
    state, items, seen = prepared(alternate=True)
    bind_content(items[0], seen, [["alternate"], ["term"], ["budget", "term"]])
    assert [ref["block_id"] for ref in items[0]["values"][0]["citations"]] == ["budget", "term"]
    data = module_data(state)
    record = data["records"][0]
    key = record["content_evidence"]["背景"][0][0]
    assert key in record["evidence_ids"]
    assert data["evidence"][key]["block_id"] == "alternate"


def test_formatted_summary_keeps_original_quotes_and_per_cell_bindings():
    state, _, seen = prepared()
    content = {"背景": ["**预算**：2130万元。", "**服务期**：2年。"]}
    record = SynthesisRecord(
        key="summary", kind="fact", title="项目概况", group="项目背景",
        scope={"kind": "common", "lot_refs": []}, content=content,
        citations=[{"block_id": row["block_id"]}
                   for row in seen.values()],
    )
    items = prepare_records([record], state, seen, "tech_requirement_parsing")
    bind_content(items[0], seen, [["budget"], ["term"]])
    state["agent_workspace"] = {
        "finalized": True, "final_ids": [i["id"] for i in items],
    }
    state["staged_items"] = items
    data = module_data(state)
    stored = data["records"][0]
    assert stored["content"] == content
    assert [[data["evidence"][key]["quote"] for key in group]
            for group in stored["content_evidence"]["背景"]] == [
        ["项目预算为2130万元。"], ["服务期为2年。"],
    ]


def test_revoked_content_only_citation_hides_records_without_mutating_verified_item():
    state, items, seen = prepared(alternate=True)
    bind_content(items[0], seen, [["alternate"], ["term"], ["budget", "term"]])
    original = copy.deepcopy(items)

    class Store:
        def report(self, report_id):
            return {
                "project_id": 10, "source_snapshot": [], "reference_snapshot": [],
                "runtime_version": RUNTIME_VERSION,
                "skill_snapshot": {FLOW_VERSION_KEY: FLOW_VERSION,
                    "tech_requirement_parsing/references/output_schema.json":
                        json.dumps(state["output_schema"])},
            }

        def report_module(self, report_id, module_key):
            return {"module_key": module_key, "status": "completed",
                    "business_data": module_data(state)}

        def report_modules(self, report_id):
            raise AssertionError("正文读取不应加载所有专题")

        def collections_for_project(self, project_id):
            return [1, 2]

        def sources(self, collection_ids):
            return []

        def resolve(self, ref, *, with_content=False):
            if ref["block_id"] == "alternate":
                raise LookupError("原文已不可访问")
            return ref

    service = AnalysisService(Store(), 1, Mock(), Mock())
    result = service.get_module_records(1, "tech_requirement_parsing")
    assert result["records"] == [] and result["evidence"] == {}
    assert items == original


def test_shared_citation_is_resolved_once_per_response_and_rechecked_next_request():
    ref = block() | {"block_id": "s1r1g2c0", "quote": "质保三年", "project_id": 1,
                     "project_file_id": 1, "bbox": [0.1, 0.1, 0.8, 0.2], "page_no": 1}
    items = [{"id": str(index), "field": "质保", "output": True,
              "values": [{"value": "三年", "citations": [ref]}]} for index in range(3)]

    class Store:
        calls = 0
        revoked = False

        def resolve(self, citation, *, with_content):
            self.calls += 1
            if self.revoked:
                raise LookupError("来源已删除")
            return citation

    store = Store()
    assert all(item["values"] for item in visible_items(store, items, [1]))
    assert store.calls == 1
    store.revoked = True
    assert all(item["verification"] == "unavailable"
               for item in visible_items(store, items, [1]))
    assert store.calls == 2


@pytest.mark.parametrize("identity", ["collection_id", "project_id", "project_file_id"])
def test_same_block_cannot_reuse_a_resolution_for_another_source_identity(identity):
    ref = block() | {"block_id": "s1r1g2c0", "quote": "质保三年", "project_id": 1,
                     "project_file_id": 1, "bbox": [0.1, 0.1, 0.8, 0.2], "page_no": 1}
    changed = ref | {identity: 2}
    items = [{"id": str(index), "field": "质保", "output": True,
              "values": [{"value": "三年", "citations": [citation]}]}
             for index, citation in enumerate([ref, changed])]

    class Store:
        def resolve(self, citation, *, with_content):
            if citation[identity] != ref[identity]:
                raise LookupError("引用的来源身份不匹配")
            return citation

    result = visible_items(Store(), items, [1, 2])
    assert result[0]["values"]
    assert result[1]["verification"] == "unavailable"
