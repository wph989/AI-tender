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
from tender.application.analysis.protocol import ResearchLedger, SubmissionRecord
from tender.application.analysis.skills import MODULES, RESOURCE_ROOT, skill_snapshot
from tender.application.analysis.topic_flow import TopicFlow

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



def business_record(record):
    from tender.application.knowledge.content import fingerprint

    SubmissionRecord.model_validate(record)
    payload = {k: v for k, v in record.items() if k not in {"work_ids", "block_ids", "id"}}
    name = payload["content"].get("要求摘要", next(iter(payload["content"].values())))
    payload.setdefault("title", ("；".join(name) if isinstance(name, list) else name)[:300])
    payload.setdefault("key", "example-" + fingerprint(record)[:24])
    return SynthesisRecord.model_validate(payload | {
        "citations": [{"block_id": bid} for bid in record["block_ids"]],
        "structuring": "complete",
    })


def legacy_submission(submission):
    return {"records": [business_record(r).model_dump() for r in submission["records"]],
            "final": submission["final"]}


def example_rows(value, *, cross_file=False):
    # 模型只收到 id/text；位置和来源由工具侧保存，再由真实引用校验回填。
    return [block(sid=3 if cross_file and i else 1) | {
        "block_id": item["id"], "content": item["text"],
        "element_id": i + 1, "offset": i, "page_no": i + 1,
    } for i, item in enumerate(value["blocks"])]


@pytest.mark.parametrize("key", MODULES)
def test_native_and_historical_schemas_keep_existing_public_shape(key):
    expected = LEGACY["schemas"][key]
    actual = output_schema(SNAPSHOT, key)
    public_shape = copy.deepcopy(actual)
    for section in public_shape["sections"]:
        section.pop("scalar_columns", None)
        section.pop("title_column", None)
    assert public_shape == expected
    assert output_schema(LEGACY["snapshot"], key) == expected
    # 原生声明不依赖 Markdown 或硬编码专题分支，也无需访问当前磁盘。
    path = key + "/references/output_schema.json"
    assert output_schema({path: SNAPSHOT[path]}, key) == actual


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
    public = output_schema(frozen, key)
    for section in public["sections"]:
        section.pop("title_column", None)
        section.pop("scalar_columns", None)
    assert public == LEGACY["schemas"][key]


@pytest.mark.parametrize("path", EXAMPLE_PATHS, ids=lambda p: str(p.relative_to(RESOURCE_ROOT)))
def test_packaged_examples_pass_real_record_and_citation_validation(path):
    key = path.relative_to(RESOURCE_ROOT).parts[0]
    cases = examples(path)
    assert cases, "输出说明和示例必须包含真实 JSON 工具参数"
    for value in cases:
        seen = {row["block_id"]: row for row in example_rows(value)}
        state = {"output_schema": output_schema(SNAPSHOT, key), "staged_items": []}
        assert value["submissions"][-1]["final"] is True
        for index, submission in enumerate(value["submissions"]):
            assert isinstance(submission["records"], list)
            assert submission["final"] == (index == len(value["submissions"]) - 1)
            raw = [business_record(r) for r in submission["records"]]
            entries = prepare_records(raw, state, seen, key)
            state["staged_items"].extend(entries)
            for gap in submission.get("gaps", []):
                GapInput.model_validate(gap)
            for item in entries:
                assert item["output"]["content"] == item["business"]["content"]
                for ref in item["business"]["citations"]:
                    assert ref["quote"] in seen[ref["block_id"]]["content"]
                    assert ref["page_no"] == seen[ref["block_id"]]["page_no"]


@pytest.mark.parametrize("path", EXAMPLE_PATHS, ids=lambda p: str(p.relative_to(RESOURCE_ROOT)))
def test_packaged_examples_accept_minimal_topic_progress_without_extra_empty_submission(path):
    from types import SimpleNamespace

    key = path.relative_to(RESOURCE_ROOT).parts[0]
    topics = json.loads(SNAPSHOT[key + "/references/coverage.json"])
    for value in examples(path):
        seen = {row["block_id"]: row for row in example_rows(value)}
        state = {"output_schema": output_schema(SNAPSHOT, key), "business_topics": topics}
        flow = TopicFlow(state, SimpleNamespace(seen=seen))
        # 模拟此前检索已经归档原文；局部样例不声明整份文件所有主题已完成。
        for block_id in seen:
            flow.associate(block_id, [topic["key"] for topic in topics])
        for submission in value["submissions"]:
            prepared = prepare_records([business_record(r)
                                        for r in submission["records"]], state, seen, key)
            updates = [u for item, record in zip(prepared, submission["records"], strict=True)
                       for u in ResearchLedger(flow).record_updates([item], record["work_ids"])]
            merged = {}
            for update in updates:
                token = (update.topic, json.dumps(update.scope_value(), sort_keys=True))
                if token in merged:
                    merged[token].record_keys.extend(update.record_keys)
                else:
                    merged[token] = update
            updates = flow.prepare_updates(prepared, list(merged.values()))
            flow.validate_records(prepared, updates)
            available = {i["business"]["key"] for i in [*state.get("staged_items", []), *prepared]}
            flow.apply(updates, available)
            state.setdefault("staged_items", []).extend(prepared)
        if any(s["records"] for s in value["submissions"]):
            assert value["submissions"][-1]["records"], "有据批次可直接请求完成检查"


@pytest.mark.parametrize("key", MODULES)
def test_thirteen_topic_review_packets_keep_domain_rules_properties_and_quotes(key):
    from tender.application.analysis.data import semantic_payload
    from tender.application.analysis.review import batches, fits, validate

    # 使用随项目人工编写的领域样例验证传输完整性；不以模型替身证明语义准确率。
    path = next(p for p in EXAMPLE_PATHS if p.relative_to(RESOURCE_ROOT).parts[0] == key
                and any(s["records"] for v in examples(p) for s in v["submissions"]))
    value = next(v for v in examples(path) if any(s["records"] for s in v["submissions"]))
    research = session(example_rows(value))
    research.seen = {row["block_id"]: row for row in example_rows(value)}
    topics = json.loads(SNAPSHOT[key + "/references/coverage.json"])
    skill = load_module_skill(SNAPSHOT, key)
    rules = skill["model_rules"] + "\n\n" + skill["output_rules"]
    state = {"output_schema": output_schema(SNAPSHOT, key), "business_topics": topics,
             "review_rules": rules}
    flow = TopicFlow(state, research)
    flow.data["protocol"] = "research-v2"
    records = [business_record(r) for s in value["submissions"] for r in s["records"]]
    prepared = prepare_records(records, state, research.seen, key)
    state["staged_items"] = prepared
    flow.entries[0].update(record_keys=[i["business"]["key"] for i in prepared],
                           evidence_ids=list(research.seen))
    packets, _ = batches(flow, topics[0]["key"], [])
    seen = {}
    for packet in packets:
        assert fits(packet, research.limits)
        assert packet["domain_rules"] == rules
        for row in packet["records"]:
            seen[row["record_id"]] = row["business"]
        validate({"reviews": {row["record_id"]: {
            "supported": True, "issues": [],
            "block_ids": row["block_ids"],
        } for row in packet["records"]}, "issues": []}, packet)
        assert all(span["text"] == research.seen[span["id"]]["content"]
                   for span in packet["evidence"] + packet["context_evidence"])
    assert seen.keys() == {i["id"] for i in prepared}
    for item in prepared:
        expected = {k: v for k, v in semantic_payload(item["business"]).items()
                    if k not in {"text", "category", "structuring"} and v not in (None, "", [], {})}
        if not any(expected.get("conditions", {}).get(k)
                   for k in ("expression", "terms", "exceptions")):
            expected.pop("conditions", None)
        assert seen[item["id"]] == expected


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
    submissions = [legacy_submission(submission) for submission in value["submissions"]]
    chunks = [submission["records"][i:i + 3] for submission in submissions
              for i in range(0, len(submission["records"]), 3)]
    script = [*research_calls(query=MODULES[key]), *[
        call("submit_analysis", {"records": records, "final": i == len(chunks) - 1}, f"record-{i}")
        for i, records in enumerate(chunks)
    ]]
    state, _, _ = asyncio.run(execute(script, research=research, snapshot=SNAPSHOT, key=key))
    actual = state["draft"]["business_data"]["records"]
    expected = [r for submission in value["submissions"] for r in submission["records"]]
    assert [r["key"] for r in actual] == [business_record(r).key for r in expected]
    assert [r["content"] for r in actual] == [r["content"] for r in expected]
    assert all(r["evidence_ids"] and "citations" not in r for r in actual)
    if key == "price_requirement_parsing":
        assert actual[0]["scope"] != actual[1]["scope"]
        assert "超限处理" not in actual[1]["content"]
    elif key == "scoring_standard_parsing":
        assert len(actual) == 1
        assert "得6分" in str(actual[0]["content"]) and "扣1分" in str(actual[0]["content"])
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
        call("submit_analysis", legacy_submission(value["submissions"][0]) | {"gaps": [{
            "key": "deposit-search", "topic": "amount", "scope": {"kind": "common", "lot_refs": []},
            "code": "search_exhausted", "detail": "本次未找到保证金依据",
        }]}, "finish"),
    ], research=session(example_rows(value)), snapshot=SNAPSHOT, key=key))
    business = state["draft"]["business_data"]
    assert business["records"] == []
    assert any(gap["key"] == "deposit-search" for gap in business["gaps"])


def test_example_rejects_unread_location_and_ignores_legacy_quote():
    key = "biz_standard_parsing"
    value = examples(RESOURCE_ROOT / key / "references/output_format.md")[0]
    seen = {row["block_id"]: row for row in example_rows(value)}
    raw = copy.deepcopy(value["submissions"][0]["records"][0])
    state = {"output_schema": output_schema(SNAPSHOT, key)}
    raw["block_ids"][0] = "unread"
    with pytest.raises(ValueError, match="未读取"):
        prepare_records([business_record(raw)], state, seen, key)
    raw["block_ids"][0] = "example-1"
    item = prepare_records([business_record(raw)], state, seen, key)[0]
    assert item["values"][0]["citations"][0]["quote"] == seen["example-1"]["content"]


def test_fact_labels_cannot_be_parallel_arrays_in_new_snapshots():
    from tender.application.analysis.output import record_output

    key = "project_basic_info_parsing"
    record = {"key": "identity", "group": "项目基本信息", "content": {
        "字段": ["项目名称", "项目编号"], "内容": ["示例项目", "A-1"],
    }}
    with pytest.raises(ValueError, match="单个事项"):
        record_output(record, output_schema(SNAPSHOT, key))
    # 历史快照不改写、也不推断数组配对；前端按复合记录明确呈现。
    legacy_output = record_output(record, output_schema(LEGACY["snapshot"], key))
    assert legacy_output["content"] == record["content"]
    record["content"] = {"字段": "项目范围", "内容": ["安装设备", "完成调试"]}
    assert record_output(record, output_schema(SNAPSHOT, key))["content"] == record["content"]


def test_scalar_columns_must_belong_to_declared_columns():
    key = "project_basic_info_parsing"
    path = key + "/references/output_schema.json"
    value = json.loads(SNAPSHOT[path])
    value["sections"][0]["scalar_columns"] = ["不存在的字段"]
    with pytest.raises(ValueError, match="JSON 输出声明无效"):
        output_schema({path: json.dumps(value)}, key)
