"""直接校验随应用打包的声明和样例，避免提示词与真实工具契约逐渐分叉。"""

import copy
import json
import re

import pytest
from test_analysis_research import block

from tender.application.analysis.data import SynthesisRecord, prepare_records
from tender.application.analysis.drafts import DraftRecord, DraftWorkspace
from tender.application.analysis.output import output_schema
from tender.application.analysis.policy import load_module_skill
from tender.application.analysis.skills import MODULES, RESOURCE_ROOT, skill_snapshot
from tender.application.shared.validation import InputError

SNAPSHOT = skill_snapshot()
EXAMPLE_PATHS = sorted(
    p for p in RESOURCE_ROOT.rglob("*.md") if p.name in {"examples.md", "output_format.md"}
)


def examples(path):
    return [json.loads(body) for body in re.findall(
        r"```json\s*\n(.*?)\n```", path.read_text(encoding="utf-8"), re.S
    )]


def business_record(record):
    from tender.domain.shared.digest import fingerprint

    DraftRecord.model_validate(record)
    payload = {k: v for k, v in record.items() if k not in {"block_ids", "id"}}
    name = payload["content"].get("要求摘要", next(iter(payload["content"].values())))
    payload.setdefault("title", ("；".join(name) if isinstance(name, list) else name)[:300])
    payload.setdefault("key", "example-" + fingerprint(record)[:24])
    return SynthesisRecord.model_validate(payload | {
        "citations": [{"block_id": bid} for bid in record["block_ids"]],
        "structuring": "complete",
    })



def example_rows(value, *, cross_file=False):
    # 模型只收到 id/text；位置和来源由工具侧保存，再由真实引用校验回填。
    return [block(sid=3 if cross_file and i else 1) | {
        "block_id": item["id"], "content": item["text"],
        "element_id": i + 1, "offset": i, "page_no": i + 1,
    } for i, item in enumerate(value["blocks"])]


@pytest.mark.parametrize("key", MODULES)
def test_output_schema_comes_from_frozen_json(key):
    path = key + "/references/output_schema.json"
    assert output_schema({path: SNAPSHOT[path]}, key) == output_schema(SNAPSHOT, key)


@pytest.mark.parametrize("invalid", [
    "{", "null", "[]", '{"version":"2","sections":[]}',
    '{"version":"1","sections":[]}',
    '{"version":"1","sections":[{"title":"X","layout":"grid","columns":["Y"]}]}',
    '{"version":"1","sections":[{"title":" ","layout":"list","columns":["Y"]}]}',
    '{"version":"1","sections":[{"title":"X","layout":"list","columns":[]}]}',
    '{"version":"1","sections":[{"title":"X","layout":"list","columns":["Y","Y"]}]}',
    '{"version":"1","sections":[{"title":"X","layout":"list","columns":["Y"],'
    '"extra":true}]}',
])
def test_damaged_native_schema_never_falls_back_to_legacy(invalid):
    key = "tech_requirement_parsing"
    snapshot = SNAPSHOT | {key + "/references/output_schema.json": invalid}
    with pytest.raises(ValueError, match="JSON 输出声明无效"):
        output_schema(snapshot, key)


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
    frozen = copy.deepcopy(SNAPSHOT)
    for category in ("goods", "engineering", "service"):
        frozen[key + f"/references/{category}/extraction_rules.md"] = f"{category}专属细则"
    new = load_module_skill(frozen, key, categories=categories)
    assert new["model_rules"].count("goods专属细则") == 1
    assert "engineering专属细则" in new["model_rules"]
    assert "service专属细则" not in new["model_rules"]
    changed = frozen | {key + "/references/goods/extraction_rules.md": "未来版本的细则"}
    assert load_module_skill(changed, key, categories=categories)["sha256"] != new["sha256"]
    assert load_module_skill(frozen, key, categories=categories) == new
    path = key + "/references/output_schema.json"
    schema = json.loads(frozen[path])
    schema["sections"][0]["columns"].append("未来字段")
    changed = frozen | {path: json.dumps(schema)}
    assert load_module_skill(changed, key)["sha256"] != load_module_skill(frozen, key)["sha256"]


@pytest.mark.parametrize("path", EXAMPLE_PATHS, ids=lambda p: str(p.relative_to(RESOURCE_ROOT)))
def test_packaged_examples_pass_real_record_and_citation_validation(path):
    key = path.relative_to(RESOURCE_ROOT).parts[0]
    cases = examples(path)
    assert cases, "输出说明和示例必须包含真实 JSON 工具参数"
    for value in cases:
        seen = {row["block_id"]: row for row in example_rows(value)}
        state = {"output_schema": output_schema(SNAPSHOT, key), "staged_items": []}
        assert value["submissions"][-1]["final"] is False
        for submission in value["submissions"]:
            assert isinstance(submission["records"], list)
            assert submission["final"] is False
            raw = [business_record(r) for r in submission["records"]]
            entries = prepare_records(raw, state, seen, key)
            state["staged_items"].extend(entries)
            for item in entries:
                assert item["output"]["content"] == item["business"]["content"]
                for ref in item["business"]["citations"]:
                    assert ref["quote"] in seen[ref["block_id"]]["content"]
                    assert ref["page_no"] == seen[ref["block_id"]]["page_no"]


@pytest.mark.parametrize("path", EXAMPLE_PATHS, ids=lambda p: str(p.relative_to(RESOURCE_ROOT)))
def test_packaged_drafts_can_be_reviewed_and_finalized_without_stage_controller(path):
    key = path.relative_to(RESOURCE_ROOT).parts[0]
    for value in examples(path):
        seen = {row["block_id"]: row for row in example_rows(value)}
        state = {"output_schema": output_schema(SNAPSHOT, key)}
        book = DraftWorkspace(state, seen, key)
        for index, submission in enumerate(value["submissions"]):
            result = book.save_records(submission["records"], f"sample:{index}")
            assert not result["rejected"], result
        records = list(book.items().values())
        book.record_review([{"record_id": item["id"], "version": item["draft_version"],
            "status": "passed", "reason": "测试人工样例与原文逐项一致",
            "block_ids": [r["block_id"] for r in item["business"]["citations"]]}
            for item in records], [], "checked")
        assert "draft" not in state
        if any(item["business"]["scope"]["kind"] == "unknown" for item in records):
            with pytest.raises(InputError, match="适用范围"):
                book.finalize([item["id"] for item in records], "范围仍待确认")
            # 局部样例故意没有范围依据；模拟后续读到范围原文，再由Agent明确改稿。
            seen["scope-proof"] = block() | {
                "block_id": "scope-proof", "content": "本项目上述要求适用于全部标段。"
            }
            for item in records:
                row = copy.deepcopy(item["business"])
                if row["scope"]["kind"] != "unknown":
                    continue
                by_key = {i["business"]["key"]: i["id"] for i in book.items().values()}
                payload = {k: row[k] for k in DraftRecord.model_fields if k in row
                           and k not in {"id", "key"}}
                for field in ("parent_key", "subject_key", "object_key"):
                    if payload.get(field):
                        payload[field] = by_key[payload[field]]
                payload["requirement_keys"] = [by_key[k] for k in row["requirement_keys"]]
                payload.update(id=item["id"], version=item["draft_version"],
                               scope={"kind": "common", "lot_refs": []},
                               block_ids=[r["block_id"] for r in row["citations"]]
                               + ["scope-proof"])
                result = book.save_records([payload], "resolve:" + item["id"])
                assert not result["rejected"], result
            records = list(book.items().values())
            book.record_review([{"record_id": item["id"], "version": item["draft_version"],
                "status": "passed", "reason": "补读适用范围后复核全部样例",
                "block_ids": [r["block_id"] for r in item["business"]["citations"]]}
                for item in records], [], "scope-reviewed")
        book.finalize([item["id"] for item in records], "人工样例数据契约核对完成")
        assert len(state["draft"]["business_data"]["records"]) == len(records)


def test_example_rejects_unread_location_and_restores_original_quote():
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


def test_fact_labels_cannot_be_parallel_arrays():
    from tender.application.analysis.output import record_output

    key = "project_basic_info_parsing"
    record = {"key": "identity", "group": "项目基本信息", "content": {
        "字段": ["项目名称", "项目编号"], "内容": ["示例项目", "A-1"],
    }}
    with pytest.raises(ValueError, match="单个事项"):
        record_output(record, output_schema(SNAPSHOT, key))
    record["content"] = {"字段": "项目范围", "内容": ["安装设备", "完成调试"]}
    assert record_output(record, output_schema(SNAPSHOT, key))["content"] == record["content"]


def test_scalar_columns_must_belong_to_declared_columns():
    key = "project_basic_info_parsing"
    path = key + "/references/output_schema.json"
    value = json.loads(SNAPSHOT[path])
    value["sections"][0]["scalar_columns"] = ["不存在的字段"]
    with pytest.raises(ValueError, match="JSON 输出声明无效"):
        output_schema({path: json.dumps(value)}, key)
