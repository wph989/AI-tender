"""校验失败必须给模型足够的信息修正，且不能把错误正文再次回显到上下文。"""

import asyncio

import pytest
from agent_fixtures import summary_record
from test_analysis_research import block

from tender.application.analysis.data import SynthesisRecord, prepare_records
from tender.application.analysis.output import output_schema, record_output
from tender.application.analysis.skills import skill_snapshot
from tender.application.knowledge.answer_evidence import json_completion
from tender.application.knowledge.content import validate_items
from tender.domain.shared.errors import InvalidModelOutput
from tender.ports.llm.chat import Completion


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
