"""复现现场分类字段与内容键同时写错时，纠错反馈不能再隐藏下一处格式问题。"""

import copy

import pytest
from agent_fixtures import KEY, summary_record

from tender.application.analysis.output import output_schema, record_output
from tender.application.analysis.skills import skill_snapshot


@pytest.mark.parametrize("group", ["", "不存在的分类"])
def test_output_feedback_explains_group_and_content_errors_together(group):
    schema = output_schema(skill_snapshot(), KEY)
    bad = summary_record(
        group=group, category="甲方信息", content={"招标人名称": "不能回显的错误正文"},
    )
    original = copy.deepcopy(bad)
    with pytest.raises(ValueError) as caught:
        record_output(bad, schema)
    feedback = str(caught.value)
    assert "group" in feedback and "category" in feedback
    assert "甲方信息" in feedback
    assert "content" in feedback and "字段" in feedback and "内容" in feedback
    assert "不能回显的错误正文" not in feedback
    assert bad == original
