"""转引原文确实存在，也不能代替需要展开的招标要求。"""

import asyncio
import copy
import json

import pytest
from test_analysis_research import block
from test_deep_analysis import submitted_field

from tender.application.analysis.skills import verify_items
from tender.application.knowledge.content import validate_items
from tender.domain.shared.errors import InvalidModelOutput
from tender.ports.llm.chat import Completion


class ReferenceReviewer:
    """独立校验器认为摘录真实，但明确指出尚未展开的内容。"""

    def __init__(self, gaps):
        self.gaps = gaps
        self.calls = 0

    async def complete(self, prompt):
        self.calls += 1
        # 格式纠正会在原始载荷后追加反馈，仍读取本批原始待检数据。
        items = json.loads(next(line for line in prompt.splitlines() if line.startswith("[{")))
        reviews = []
        for item in items:
            targets = [self.gaps[v["value"]] for v in item["values"] if v["value"] in self.gaps]
            reviews.append(
                {
                    "supported": True,
                    "unsupported_claims": [],
                    "unresolved_references": targets,
                    "evidence_ids": [[r["id"] for r in v["citations"]] for v in item["values"]],
                }
            )
        return Completion(content=json.dumps({"reviews": reviews}), model="fixture")


@pytest.mark.parametrize(
    "value,target",
    [
        ("详见第三章评标办法", "第三章评标办法"),
        ("评分细则载于《评分附件.pdf》", "评分附件.pdf"),
        ("按评标办法前附表规定执行", "评标办法前附表"),
        ("技术方案满分20分，各档得分条件详见附件2", "附件2中的各档得分条件"),
    ],
)
def test_textually_supported_reference_is_not_a_completed_requirement(value, target):
    row = block() | {"content": value}
    evidence = {row["block_id"]: row}
    items = validate_items([submitted_field("评分标准", value, quote=value)], evidence)
    asyncio.run(
        verify_items(
            ReferenceReviewer({value: target}),
            items,
            explain=True,
            evidence=evidence,
            select_evidence=True,
        )
    )
    assert items[0]["verification"] == "unsupported"
    issues = " ".join(items[0]["verification_issues"])
    assert target in issues and "search_document" in issues


@pytest.mark.parametrize(
    "field,value",
    [
        ("评分标准", "每提供一项同类业绩得2分，最高6分（第三章评标办法）"),
        ("执行标准", "产品应符合GB/T 19001标准"),
        ("提交材料", "须按附件4格式提供投标函并加盖公章"),
        ("评标方法", "采用综合评分法"),
        ("补充修订", "补遗将第三章业绩评分由满分5分修改为满分6分"),
    ],
)
def test_substantive_requirement_with_reference_remains_valid(field, value):
    row = block() | {"content": value}
    evidence = {row["block_id"]: row}
    items = validate_items([submitted_field(field, value, quote=value)], evidence)
    asyncio.run(
        verify_items(
            ReferenceReviewer({}),
            items,
            explain=True,
            evidence=evidence,
            select_evidence=True,
        )
    )
    assert items[0]["verification"] == "supported"
    assert items[0]["values"][0]["citations"][0]["block_id"] == row["block_id"]


@pytest.mark.parametrize("gap_result", [None, "第三章", [""], [1]])
def test_reference_review_is_required_and_format_retries_are_bounded(gap_result):
    class InvalidReviewer(ReferenceReviewer):
        async def complete(self, prompt):
            completion = await super().complete(prompt)
            result = json.loads(completion.content)
            review = result["reviews"][0]
            if gap_result is None:
                review.pop("unresolved_references")
            else:
                review["unresolved_references"] = gap_result
            return Completion(content=json.dumps(result), model="fixture")

    row = block()
    evidence = {row["block_id"]: row}
    items = validate_items([submitted_field("质保", "质保三年")], evidence)
    before = copy.deepcopy(items)
    reviewer = InvalidReviewer({})
    with pytest.raises(InvalidModelOutput, match="unresolved_references"):
        asyncio.run(
            verify_items(
                reviewer,
                items,
                explain=True,
                evidence=evidence,
                select_evidence=True,
            )
        )
    assert reviewer.calls == 3 and items == before
