"""校验失败必须给模型足够的信息修正，且不能把错误正文再次回显到上下文。"""

import asyncio
import copy
import json

import pytest
from synthesis_fixtures import summary_record
from test_analysis_combined_review import approve
from test_analysis_compact_protocol import ledger
from test_analysis_research import block

from tender.application.analysis.completeness import review_completeness
from tender.application.analysis.data import SynthesisRecord, prepare_records
from tender.application.analysis.output import output_schema, record_output
from tender.application.analysis.protocol import ResearchDelta
from tender.application.analysis.review import review_combined, validate
from tender.application.analysis.skills import json_completion, skill_snapshot
from tender.application.knowledge.content import validate_items
from tender.domain.shared.errors import InvalidModelOutput
from tender.ports.llm.chat import Completion


def packet():
    return {
        "topic": "a", "topics": ["a"], "records": [
            {"record_id": "r1", "block_ids": ["s1r1c0"]},
            {"record_id": "r2", "block_ids": ["s1r1c0"]},
        ],
        "record_index": [{"record_id": "r1"}, {"record_id": "r2"}],
        "evidence": [{"id": "s1r1c0", "unit_id": "unit1"}], "context_evidence": [],
    }


@pytest.mark.parametrize("field,wrong,expected", [
    ("topic", "wrong", "a"),
    ("detail", "", "非空"),
    ("kind", "wrong", "omission"),
    ("kind", [], "omission"),
    ("record_ids", ["foreign"], "r1"),
    ("evidence_ids", ["foreign"], "s1r1c0"),
    ("target", 123, "字符串"),
])
def test_review_issue_feedback_names_exact_field_and_allowed_values(field, wrong, expected):
    payload = packet()
    result = approve(payload)
    issue = {"topic": "a", "detail": "缺少具体条件", "kind": "omission",
             "record_ids": [], "evidence_ids": [], "target": "附件正文"}
    issue[field] = wrong
    result["issues"] = [issue]
    with pytest.raises(InvalidModelOutput) as caught:
        validate(result, payload)
    feedback = str(caught.value)
    assert "issues.0." + field in feedback
    assert expected in feedback


def test_review_collects_record_and_binding_errors_before_retry():
    payload = packet()
    result = approve(payload)
    result["reviews"].pop("r2")
    result["reviews"]["r1"]["block_ids"] = ["foreign"]
    with pytest.raises(InvalidModelOutput) as caught:
        validate(result, payload)
    feedback = str(caught.value)
    assert "reviews" in feedback and "r2" in feedback
    assert "reviews.r1.block_ids" in feedback and "s1r1c0" in feedback


def test_review_retry_receives_exact_binding_fix_and_finishes_next_request():
    async def run():
        payload = packet()

        class Model:
            def __init__(self):
                self.prompts = []

            async def complete(self, prompt):
                self.prompts.append(prompt)
                result = approve(payload)
                if len(self.prompts) == 1:
                    result["reviews"]["r1"]["block_ids"] = []
                else:
                    assert "reviews.r1.block_ids" in prompt and "s1r1c0" in prompt
                return Completion(content=json.dumps(result), model="fixture")

        from dataclasses import replace

        from test_llm_routing import _candidate

        from tender.application.llm.routing import RoutingModel

        client = Model()
        records = []
        model = RoutingModel("analysis", "fixture", [replace(_candidate("a", 1), extra_retries=1)],
                             lambda *args, **kwargs: client, records.append)
        result = await review_combined(model, payload)
        assert result == approve(payload) and len(client.prompts) == 2
        assert [record.status for record in records] == ["error", "ok"]

    asyncio.run(run())


def test_citation_feedback_collects_paths_and_read_instructions_for_all_bad_refs():
    item = {"field": "期限", "values": [{"value": "三年", "citations": [
        {"block_id": "foreign", "quote": "不能回显的错误正文"},
        {"block_id": "s1r1c0", "quote": "不能回显的错误正文"},
        {"block_id": "s1r1c0"},
    ]}]}
    with pytest.raises(ValueError) as caught:
        validate_items([item], {"s1r1c0": block()}, align=False)
    feedback = str(caught.value)
    for index in range(3):
        assert f"values.0.citations.{index}" in feedback
    assert "block_id" in feedback and "quote" in feedback
    assert "read_document" in feedback and "s1r1c0" in feedback
    assert "不能回显的错误正文" not in feedback


def test_output_reports_scalar_and_empty_cells_together_with_column_paths():
    record = summary_record(group="甲方信息", content={"字段": ["招标人"], "内容": ""})
    with pytest.raises(ValueError) as caught:
        record_output(record, output_schema(skill_snapshot(), "project_basic_info_parsing"))
    feedback = str(caught.value)
    assert "content.字段" in feedback and "单个" in feedback
    assert "content.内容" in feedback and "省略" in feedback


def test_research_feedback_reports_bad_work_and_evidence_before_updating_state():
    book, flow, state, _ = ledger()
    before = copy.deepcopy(state)
    with pytest.raises(ValueError) as caught:
        book.update([ResearchDelta(work_ids=["foreign"], evidence_ids=["foreign"],
                                   detail="不能回显的错误正文")])
    feedback = str(caught.value)
    assert "updates.0.work_ids" in feedback and "w1" in feedback
    assert "updates.0.evidence_ids" in feedback and "s1r1c0" in feedback
    assert "不能回显的错误正文" not in feedback
    assert state == before


def test_relation_feedback_identifies_endpoint_and_available_targets():
    good = SynthesisRecord.model_validate(summary_record(key="valid"))
    relation = SynthesisRecord.model_validate(summary_record(
        key="relation", kind="relation", predicate="requires",
        subject_key="missing", object_key="also-missing",
    ))
    with pytest.raises(ValueError) as caught:
        key = "project_basic_info_parsing"
        prepare_records([good, relation], {"output_schema": output_schema(skill_snapshot(), key)},
                        {"s1r1c0": block()}, key)
    feedback = str(caught.value)
    assert "subject_key" in feedback and "object_key" in feedback and "valid" in feedback


def test_completeness_schema_feedback_does_not_echo_invalid_payload():
    async def run():
        class Model:
            def __init__(self):
                self.calls = 0

            async def complete(self, prompt):
                self.calls += 1
                if self.calls > 1:
                    assert "issues" in prompt and "不能回显的错误正文" not in prompt
                    return Completion(content='{"issues":[]}', model="fixture")
                return Completion(content='{"issues":"不能回显的错误正文"}', model="fixture")

        payload = {"topic": "a", "evidence_ids": [], "record_keys": []}
        assert await review_completeness(Model(), payload) == {"issues": []}

    asyncio.run(run())


def test_json_retry_replaces_stale_error_and_preserves_all_current_field_fixes():
    async def run():
        prompts = []

        class Model:
            async def complete(self, prompt):
                prompts.append(prompt)
                return Completion(content="{}", model="fixture")

        count = 0

        def check(result):
            nonlocal count
            count += 1
            if count == 1:
                raise InvalidModelOutput("第一轮已修正的问题")
            if count == 2:
                raise InvalidModelOutput("第二轮当前问题" + "规则说明" * 110 + "末尾字段修法")

        assert await json_completion(Model(), "原始协议", validate=check) == {}
        assert "第一轮已修正的问题" not in prompts[2]
        assert "第二轮当前问题" in prompts[2] and "末尾字段修法" in prompts[2]

    asyncio.run(run())


@pytest.mark.parametrize("content,expected", [
    ('{"reviews":', "第1行第12列"),
    ('{"reviews":{},"reviews":{}}', "重复ID或字段：reviews"),
])
def test_json_syntax_and_duplicate_keys_receive_specific_fix_before_retry(content, expected):
    async def run():
        class Model:
            def __init__(self):
                self.calls = 0

            async def complete(self, prompt):
                self.calls += 1
                if self.calls == 1:
                    return Completion(content=content, model="fixture")
                assert expected in prompt
                return Completion(content="{}", model="fixture")

        model = Model()
        assert await json_completion(model, "返回JSON对象") == {} and model.calls == 2

    asyncio.run(run())


@pytest.mark.parametrize("field,wrong", [("reviews", []), ("issues", {})])
def test_review_root_type_feedback_names_field_before_dependent_validation(field, wrong):
    payload = packet()
    result = approve(payload) | {field: wrong}
    with pytest.raises(InvalidModelOutput) as caught:
        validate(result, payload)
    assert field in str(caught.value) and "须为" in str(caught.value)
