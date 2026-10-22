"""正文逐条选证经过真实校验入口，并随独立业务 JSON 保存，不能借整项来源冒充绑定。"""

import asyncio
import copy
import json

import pytest
from test_analysis_research import block

from tender.application.analysis.data import (
    SynthesisRecord,
    display_items,
    module_data,
    prepare_records,
)
from tender.application.analysis.skills import verify_items
from tender.application.knowledge.service import visible_items
from tender.domain.shared.errors import InvalidModelOutput
from tender.ports.llm.chat import Completion


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
        citations=[{"block_id": row["block_id"], "quote": row["content"]} for row in rows],
    )
    items = prepare_records([record], state, seen, "tech_requirement_parsing")
    state["staged_items"] = items
    return state, items, seen


class Reviewer:
    def __init__(self, choices=None, *, supported=True):
        self.choices = choices or [["budget", "term"], ["budget"], ["term"], ["budget", "term"]]
        self.supported = supported
        self.requests = []

    async def complete(self, prompt):
        payload = next(line for line in prompt.splitlines() if line.startswith("[{"))
        self.requests.append(json.loads(payload))
        return Completion(content=json.dumps({"reviews": [{
            "supported": self.supported,
            "unsupported_claims": [] if self.supported else ["第3个值缺少服务期依据"],
            "unresolved_references": [], "evidence_ids": self.choices,
        }]}), model="fixture")


def review(items, seen, reviewer):
    asyncio.run(verify_items(reviewer, items, explain=True, select_evidence=True, evidence=seen))


def test_content_selects_own_sources_and_round_trips_without_conflicting_values():
    state, items, seen = prepared()
    original = copy.deepcopy(items[0]["values"])
    reviewer = Reviewer()
    review(items, seen, reviewer)

    assert len(reviewer.requests) == 1
    sent = reviewer.requests[0][0]["values"]
    assert len(sent) == 4
    assert [value.get("content_path") for value in sent] == [
        None, ["背景", 0], ["背景", 1], ["背景", 2],
    ]
    # 保留整项审查及一个公开 value，正文单元不是该事项的多个冲突版本。
    assert items[0]["values"] == original
    assert [len(group) for group in items[0]["output"]["citations"]["背景"]] == [1, 1, 2]
    assert len(display_items(items)[0]["values"]) == 1

    data = module_data(state)
    record = data["records"][0]
    bindings = record["content_evidence"]["背景"]
    assert [[data["evidence"][key]["block_id"] for key in group] for group in bindings] == [
        ["budget"], ["term"], ["budget", "term"],
    ]
    assert {key for group in bindings for key in group} <= set(record["evidence_ids"])


def test_content_keeps_verified_alternative_that_whole_record_did_not_select():
    state, items, seen = prepared(alternate=True)
    review(items, seen, Reviewer([["budget", "term"], ["alternate"], ["term"], ["budget", "term"]]))
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
        citations=[{"block_id": row["block_id"], "quote": row["content"]}
                   for row in seen.values()],
    )
    items = prepare_records([record], state, seen, "tech_requirement_parsing")
    reviewer = Reviewer([["budget", "term"], ["budget"], ["term"]])
    review(items, seen, reviewer)
    state["staged_items"] = items
    data = module_data(state)
    stored = data["records"][0]
    # 此处验证排版和引用可以独立往返；可控审查模型不代表真实模型的归纳准确率。
    assert stored["content"] == content
    assert [value["value"] for value in reviewer.requests[0][0]["values"]][1:] == [
        "背景：**预算**：2130万元。", "背景：**服务期**：2年。",
    ]
    assert len(reviewer.requests) == 1
    assert [[data["evidence"][key]["quote"] for key in group]
            for group in stored["content_evidence"]["背景"]] == [
        ["项目预算为2130万元。"], ["服务期为2年。"],
    ]


def test_revoked_content_only_citation_hides_public_projection_without_mutating_verified_item():
    _, items, seen = prepared(alternate=True)
    review(items, seen, Reviewer([["budget", "term"], ["alternate"], ["term"], ["budget", "term"]]))
    original = copy.deepcopy(items)

    class Store:
        def resolve(self, ref, *, with_content):
            if ref["block_id"] == "alternate":
                raise LookupError("原文已不可访问")
            return ref

    projected = display_items(items)
    result = visible_items(Store(), projected)[0]
    assert result["verification"] == "unavailable"
    assert result["values"] == [] and "output" not in result
    assert items == original


@pytest.mark.parametrize("index,chosen", [(1, []), (1, ["unknown"]), (0, ["budget"])])
def test_cell_binding_must_be_present_authorized_and_preserve_whole_record_sources(index, chosen):
    state, items, seen = prepared()
    reviewer = Reviewer()
    reviewer.choices[index] = chosen
    with pytest.raises(InvalidModelOutput):
        review(items, seen, reviewer)
    assert "citations" not in items[0]["output"]
    assert module_data(state)["records"] == []


def test_one_unsupported_cell_prevents_publishing_a_false_binding():
    state, items, seen = prepared()
    review(items, seen, Reviewer(supported=False))
    assert items[0]["verification"] == "unsupported"
    assert "citations" not in items[0]["output"]
    assert module_data(state)["records"] == []


def test_long_content_shares_candidate_text_and_context_in_one_review():
    state, _, _ = prepared()
    texts = [f"步骤{i}须完成迁移并确认回退条件。" for i in range(12)]
    rows = [block() | {
        "block_id": f"step{i}", "element_id": i + 1, "offset": i,
        "content": text + "实施前核对清单，完成后记录结果。" * 12,
    } for i, text in enumerate(texts)]
    seen = {row["block_id"]: row for row in rows}
    record = SynthesisRecord(
        key="migration", kind="requirement", title="迁移要求", group="项目背景",
        scope={"kind": "common", "lot_refs": []}, content={"背景": texts},
        citations=[{"block_id": row["block_id"], "quote": row["content"]} for row in rows],
    )
    items = prepare_records([record], state, seen, "tech_requirement_parsing")
    reviewer = Reviewer([list(seen), *[[key] for key in seen]])
    review(items, seen, reviewer)

    assert len(reviewer.requests) == 1
    payload = json.dumps(reviewer.requests[0], ensure_ascii=False)
    # 候选摘录和对应的块上下文各出现一次，正文单元增加不能重复发送整套原文。
    for row in rows:
        assert payload.count(row["content"]) == 2
    assert all(len(group) == 1 for group in items[0]["output"]["citations"]["背景"])


def test_shared_candidates_do_not_widen_each_values_authorized_sources():
    _, items, seen = prepared()
    refs = items[0]["values"][0]["citations"]
    items[0].pop("output")
    items[0]["values"] = [{"value": ref["quote"], "citations": [ref]} for ref in refs]
    reviewer = Reviewer([["budget"], ["term"]])
    review(items, seen, reviewer)
    sent = reviewer.requests[0][0]
    choices = [sent["evidence_sets"][value["evidence_set"]]["citations"]
               for value in sent["values"]]
    assert [[ref["id"] for ref in group] for group in choices] == [["budget"], ["term"]]
    # 同批出现并不代表本值可用；共享表示也不能放宽原有候选授权。
    with pytest.raises(InvalidModelOutput, match="只能选本值"):
        review(items, seen, Reviewer([["term"], ["term"]]))


def test_same_block_with_different_quotes_keeps_distinct_candidate_text():
    _, items, seen = prepared()
    ref = items[0]["values"][0]["citations"][0]
    quotes = [ref["quote"], "服务期为2年。"]
    seen["budget"]["content"] = "".join(quotes)
    items[0].pop("output")
    items[0]["values"] = [{"value": quote, "citations": [ref | {"quote": quote}]}
                          for quote in quotes]
    reviewer = Reviewer([["budget"], ["budget"]])
    review(items, seen, reviewer)
    sent = reviewer.requests[0][0]
    assert [sent["evidence_sets"][value["evidence_set"]]["citations"][0]["text"]
            for value in sent["values"]] == quotes
