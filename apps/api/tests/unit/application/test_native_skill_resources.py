"""直接校验随应用打包的声明和样例，避免提示词与真实工具契约逐渐分叉。"""

import asyncio
import copy
import json
import re
from pathlib import Path

import pytest
from synthesis_fixtures import research_calls
from test_analysis_research import block, session, source
from test_analysis_synthesis import execute
from test_deep_analysis import call

from tender.application.analysis.data import GapInput, SynthesisRecord, prepare_records
from tender.application.analysis.output import output_schema
from tender.application.analysis.policy import load_module_skill
from tender.application.analysis.skills import MODULES, RESOURCE_ROOT, skill_snapshot

LEGACY = json.loads((
    Path(__file__).resolve().parents[2] / "fixtures/analysis/legacy_skill_formats.json"
).read_text(encoding="utf-8"))
SNAPSHOT = skill_snapshot()
EXAMPLE_PATHS = sorted(
    p for p in RESOURCE_ROOT.rglob("*.md") if p.name in {"examples.md", "output_format.md"}
)


def examples(path):
    return [json.loads(body) for body in re.findall(
        r"```json\s*\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S
    )]


def example_rows(value, *, cross_file=False):
    # 模型只收到 id/text；位置和来源由工具侧保存，再由真实引用校验回填。
    return [block(sid=3 if cross_file and i else 1) | {
        "block_id": item["id"], "content": item["text"],
        "element_id": i + 1, "offset": i, "page_no": i + 1,
    } for i, item in enumerate(value["blocks"])]


@pytest.mark.parametrize("key", MODULES)
def test_native_and_historical_schemas_keep_existing_public_shape(key):
    expected = LEGACY["schemas"][key]
    assert output_schema(SNAPSHOT, key) == expected
    assert output_schema(LEGACY["snapshot"], key) == expected
    # 原生声明不依赖 Markdown 或硬编码专题分支，也无需访问当前磁盘。
    path = key + "/references/output_schema.json"
    assert output_schema({path: SNAPSHOT[path]}, key) == expected


@pytest.mark.parametrize("invalid", [
    "{", "null", "[]", '{"version":"2","sections":[]}',
    '{"version":"1","sections":[]}',
    '{"version":"1","sections":[{"title":"X","layout":"grid","columns":["Y"]}]}',
    '{"version":"1","sections":[{"title":" ","layout":"list","columns":["Y"]}]}',
    '{"version":"1","sections":[{"title":"X","layout":"list","columns":[]}]}',
    '{"version":"1","sections":[{"title":"X","layout":"list","columns":["Y","Y"]}]}',
    '{"version":"1","sections":[{"title":"X","layout":"list","columns":["Y"],'
    '"extra":true}]}',
    None,
])
def test_damaged_native_schema_never_falls_back_to_legacy(invalid):
    key = "tech_requirement_parsing"
    snapshot = LEGACY["snapshot"] | {key + "/references/output_schema.json": invalid}
    with pytest.raises(ValueError, match="JSON 输出声明无效"):
        output_schema(snapshot, key)
    with pytest.raises(ValueError, match="JSON 输出声明无效"):
        load_module_skill(snapshot, key)


def test_duplicate_sections_are_rejected():
    key = "tech_requirement_parsing"
    path = key + "/references/output_schema.json"
    value = json.loads(SNAPSHOT[path])
    value["sections"].append(value["sections"][0])
    with pytest.raises(ValueError, match="JSON 输出声明无效"):
        output_schema({path: json.dumps(value)}, key)


def test_frozen_category_loading_and_hash_do_not_mix_versions():
    key = "tech_requirement_parsing"
    categories = ["goods", "engineering", "goods", "unknown"]
    old = load_module_skill(LEGACY["snapshot"], key, categories=categories)
    assert not any("/goods/" in p or "/engineering/" in p for p in old["references"])
    frozen = copy.deepcopy(SNAPSHOT)
    new = load_module_skill(frozen, key, categories=categories)
    assert new["references"].count(key + "/references/goods/extraction_rules.md") == 1
    assert key + "/references/engineering/extraction_rules.md" in new["references"]
    assert not any("/service/" in p or "/unknown/" in p for p in new["references"])
    assert not any("/service/" in p for p in load_module_skill(frozen, key)["references"])
    changed = frozen | {key + "/references/goods/extraction_rules.md": "未来版本的细则"}
    assert load_module_skill(changed, key, categories=categories)["sha256"] != new["sha256"]
    assert load_module_skill(frozen, key, categories=categories) == new
    assert load_module_skill(LEGACY["snapshot"], key, categories=categories) == old
    path = key + "/references/output_schema.json"
    schema = json.loads(frozen[path])
    schema["sections"][0]["columns"].append("未来字段")
    changed = frozen | {path: json.dumps(schema)}
    assert load_module_skill(changed, key)["sha256"] != load_module_skill(frozen, key)["sha256"]
    assert output_schema(frozen, key) == LEGACY["schemas"][key]


@pytest.mark.parametrize("path", EXAMPLE_PATHS, ids=lambda p: str(p.relative_to(RESOURCE_ROOT)))
def test_packaged_examples_pass_real_record_and_citation_validation(path):
    key = path.relative_to(RESOURCE_ROOT).parts[0]
    cases = examples(path)
    assert cases, "输出说明和示例必须包含真实 JSON 工具参数"
    for value in cases:
        seen = {row["block_id"]: row for row in example_rows(value)}
        state = {"output_schema": output_schema(SNAPSHOT, key), "staged_items": []}
        assert value["submissions"][-1]["final"] is True
        assert value["submissions"][-1]["records"] == []
        for index, submission in enumerate(value["submissions"]):
            assert len(submission["records"]) <= 1
            assert submission["final"] == (index == len(value["submissions"]) - 1)
            raw = [SynthesisRecord.model_validate(r) for r in submission["records"]]
            entries = prepare_records(raw, state, seen, key)
            state["staged_items"].extend(entries)
            for gap in submission.get("gaps", []):
                GapInput.model_validate(gap)
            for item in entries:
                assert item["output"]["content"] == item["business"]["content"]
                for ref in item["business"]["citations"]:
                    assert ref["quote"] in seen[ref["block_id"]]["content"]
                    assert ref["page_no"] == seen[ref["block_id"]]["page_no"]


@pytest.mark.parametrize("key", [
    "deposit_requirement_parsing", "price_requirement_parsing", "biz_standard_parsing",
    "scoring_standard_parsing", "tech_requirement_parsing", "bid_format_outline_parsing",
    "general_module_parsing",
])
def test_native_example_survives_real_agent_graph_and_evidence_storage(key):
    value = examples(RESOURCE_ROOT / key / "references/output_format.md")[0]
    rows = example_rows(value, cross_file=key == "general_module_parsing")
    research = session(rows)
    research.sources = [source(sid) for sid in sorted({row["source_id"] for row in rows})]
    script = [*research_calls(query=MODULES[key]), *[
        call("submit_analysis", submission, f"record-{i}")
        for i, submission in enumerate(value["submissions"])
    ]]
    state, _, _ = asyncio.run(execute(script, research=research, snapshot=SNAPSHOT, key=key))
    actual = state["draft"]["business_data"]["records"]
    expected = [r for submission in value["submissions"] for r in submission["records"]]
    assert [r["key"] for r in actual] == [r["key"] for r in expected]
    assert [r["content"] for r in actual] == [r["content"] for r in expected]
    assert all(r["evidence_ids"] and "citations" not in r for r in actual)
    if key == "price_requirement_parsing":
        assert actual[0]["scope"] != actual[1]["scope"]
        assert "超限处理" not in actual[1]["content"]
    elif key == "scoring_standard_parsing":
        assert len(actual) == 1 and len(actual[0]["scoring"]["tiers"]) == 3
        assert actual[0]["scoring"]["deductions"]
    elif key == "tech_requirement_parsing":
        assert len(actual) == 2
        assert all("600mm" not in json.dumps(r["content"]) for r in actual)
    elif key == "bid_format_outline_parsing":
        assert actual[3]["parent_key"] == actual[2]["key"]
        assert actual[4].get("parent_key") is None
    elif key == "general_module_parsing":
        assert actual[-1]["predicate"] == "supersedes"
        evidence = state["draft"]["business_data"]["evidence"]
        assert {r["source_id"] for r in evidence.values()} == {1, 3}


def test_no_deposit_hit_keeps_gap_instead_of_emitting_exemption():
    key = "deposit_requirement_parsing"
    path = RESOURCE_ROOT / key / "references/examples.md"
    value = examples(path)[1]
    state, _, _ = asyncio.run(execute([
        *research_calls(query="保证金"),
        call("submit_analysis", value["submissions"][0], "finish"),
    ], research=session(example_rows(value)), snapshot=SNAPSHOT, key=key))
    business = state["draft"]["business_data"]
    assert business["records"] == []
    assert any(gap["key"] == "deposit-search" for gap in business["gaps"])


def test_example_cannot_cite_unread_or_invented_quote():
    key = "biz_standard_parsing"
    value = examples(RESOURCE_ROOT / key / "references/output_format.md")[0]
    seen = {row["block_id"]: row for row in example_rows(value)}
    raw = copy.deepcopy(value["submissions"][0]["records"][0])
    state = {"output_schema": output_schema(SNAPSHOT, key)}
    raw["citations"][0]["block_id"] = "unread"
    with pytest.raises(ValueError, match="未读取"):
        prepare_records([SynthesisRecord.model_validate(raw)], state, seen, key)
    raw["citations"][0] = {"block_id": "example-1", "quote": "预付全部价款"}
    with pytest.raises(ValueError, match="引用"):
        prepare_records([SynthesisRecord.model_validate(raw)], state, seen, key)
