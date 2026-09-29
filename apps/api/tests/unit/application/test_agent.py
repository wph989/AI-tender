"""两遍式抽取的合并口径：低置信复抽、投票冲突、规则与模型的一致与分歧。

用假模型驱动，不碰网络：这里要盯的是「结果怎么合并」，不是「HTTP 怎么发」。
阶段 2 的验收指标（证据 404 率 = 0、幻觉率 = 0）就落在这些合并规则上，
所以低置信、复抽不一致、幻觉锚点三种情况都必须有用例钉住。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from tender.application.agent import extract_field
from tender.application.extraction import TextChunk, build_anchor_document
from tender.application.fields import FIELD_BY_KEY
from tender.ports.llm import Completion


class _FakeModel:
    """按预设脚本返回 JSON；脚本用尽即报错，避免「多调了一次」被静默吞掉。"""

    def __init__(self, *answers: dict[str, Any], model: str = "fake-model") -> None:
        self._answers = list(answers)
        self.model = model
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> Completion:
        self.prompts.append(prompt)
        if not self._answers:
            raise AssertionError("假模型被调用的次数超出预设脚本")
        answer = self._answers.pop(0)
        return Completion(
            content=json.dumps(answer, ensure_ascii=False),
            model=self.model,
            registry_model_id=42,
        )

    async def aclose(self) -> None:
        return None


class _BrokenJsonModel:
    async def complete(self, prompt: str) -> Completion:
        return Completion(content="这不是 JSON", model="broken")

    async def aclose(self) -> None:
        return None


def _answer(
    field_key: str,
    value: Any,
    quote: str,
    anchor: str,
    *,
    confidence: float = 0.9,
    not_found: bool = False,
    value_text: str | None = None,
) -> dict[str, Any]:
    return {
        "field_key": field_key,
        "value": value,
        "value_text": value_text if value_text is not None else str(value),
        "quote": quote,
        "evidence": [] if not_found else [anchor],
        "confidence": confidence,
        "not_found": not_found,
        "lot_code": None,
    }


def _element(
    anchor: str,
    text: str,
    *,
    element_id: int,
    order: int,
    type: str = "paragraph",
    level: int | None = None,
) -> dict[str, Any]:
    return {
        "id": element_id,
        "anchor": anchor,
        "type": type,
        "text": text,
        "page_no": 1,
        "order_no": order,
        "level": level,
        "parent_id": None,
        "html": None,
        "continues_prev": False,
    }


def _document(*texts: str) -> tuple[list[dict[str, Any]], list[TextChunk]]:
    elements = [
        _element(f"p1b{index}", text, element_id=index, order=index)
        for index, text in enumerate(texts, start=1)
    ]
    return build_anchor_document(elements)


def _two_chapters(*pairs: tuple[str, str]) -> tuple[list[dict[str, Any]], list[TextChunk]]:
    """每个 (标题, 正文) 各起一章，用来验证"按章分块后多块结果如何合并"。"""
    elements: list[dict[str, Any]] = []
    for index, (title, body) in enumerate(pairs):
        base = index * 2 + 1
        elements.append(
            _element(f"p1b{base}", title, element_id=base, order=base, type="title", level=1)
        )
        elements.append(_element(f"p1b{base + 1}", body, element_id=base + 1, order=base + 1))
    return build_anchor_document(elements)


def _run(
    model: Any,
    field_key: str,
    document: tuple[list[dict[str, Any]], list[TextChunk]],
    *,
    retry_model: Any = None,
    hint: str | None = None,
) -> dict[str, Any]:
    elements, chunks = document
    return asyncio.run(
        extract_field(
            model,
            FIELD_BY_KEY[field_key],
            elements,
            chunks,
            [],
            hint=hint,
            retry_model=retry_model,
        )
    )


def test_single_pass_keeps_value_evidence_and_model() -> None:
    model = _FakeModel(
        _answer("project_name", "某市政道路工程", "项目名称：某市政道路工程", "p1b1")
    )

    result = _run(model, "project_name", _document("项目名称：某市政道路工程"))

    assert result["status"] == "auto"
    assert result["value"] == "某市政道路工程"
    assert result["strategy"] == "llm"
    assert [item["anchor"] for item in result["evidence"]] == ["p1b1"]
    assert result["model"] == "fake-model"
    assert result["registry_model_id"] == 42
    assert len(model.prompts) == 1
    # 提示词必须带上字段与输出约束，模型才有机会返回可校验的 JSON。
    assert "<字段>project_name / 项目名称</字段>" in model.prompts[0]
    assert "<输出约束>" in model.prompts[0]


def test_low_confidence_triggers_independent_second_pass() -> None:
    first = _FakeModel(
        _answer(
            "project_name", "某市政道路工程", "项目名称：某市政道路工程", "p1b1", confidence=0.4
        )
    )
    retry = _FakeModel(
        _answer(
            "project_name", "某市政道路工程", "项目名称：某市政道路工程", "p1b1", confidence=0.7
        ),
        model="retry-model",
    )

    result = _run(first, "project_name", _document("项目名称：某市政道路工程"), retry_model=retry)

    # 两遍一致：置信度取两者较高值再加 0.08，证据按锚点去重。
    assert result["confidence"] == pytest.approx(0.78)
    assert result["status"] == "auto"
    assert len(result["evidence"]) == 1
    assert "独立复核轮次" not in first.prompts[0]
    assert "独立复核轮次" in retry.prompts[0]


def test_disagreeing_passes_become_conflict_with_both_values() -> None:
    text = "项目名称：某市政道路工程；备选：另一条道路工程"
    model = _FakeModel(
        _answer(
            "project_name", "某市政道路工程", "项目名称：某市政道路工程", "p1b1", confidence=0.4
        ),
        _answer("project_name", "另一条道路工程", "备选：另一条道路工程", "p1b1", confidence=0.8),
    )

    result = _run(model, "project_name", _document(text))

    assert result["status"] == "conflict"
    # 冲突一律记 0.5：两遍说法不一致时不给任何一方加权。
    assert result["confidence"] == pytest.approx(0.5)
    assert result["value"]["candidates"] == [
        {"source": "llm", "value": "某市政道路工程", "value_text": "某市政道路工程"},
        {"source": "llm", "value": "另一条道路工程", "value_text": "另一条道路工程"},
    ]


def test_second_pass_not_found_marks_conflict_and_keeps_first_value() -> None:
    model = _FakeModel(
        _answer(
            "project_name", "某市政道路工程", "项目名称：某市政道路工程", "p1b1", confidence=0.4
        ),
        _answer("project_name", None, "", "p1b1", confidence=0.2, not_found=True),
    )

    result = _run(model, "project_name", _document("项目名称：某市政道路工程"))

    assert result["status"] == "conflict"
    assert result["value"] == "某市政道路工程"
    assert [item["anchor"] for item in result["evidence"]] == ["p1b1"]


def test_not_found_answer_is_not_retried_and_has_no_evidence() -> None:
    model = _FakeModel(_answer("project_name", None, "", "p1b1", confidence=0.3, not_found=True))

    result = _run(model, "project_name", _document("项目名称：某市政道路工程"))

    assert result["status"] == "not_found"
    assert result["value"] is None
    assert result["evidence"] == []
    # 第一遍就明确"没找到"时不值得再花一次调用。
    assert len(model.prompts) == 1


def test_phantom_anchor_cannot_become_a_result() -> None:
    """幻觉锚点必须落 not_found：没有证据的结果一条都不许进库。"""
    model = _FakeModel(_answer("project_name", "某市政道路工程", "项目名称：某工程", "p9b9"))

    result = _run(model, "project_name", _document("项目名称：某市政道路工程"))

    assert result["status"] == "not_found"
    assert result["value"] is None
    assert result["evidence"] == []


def test_rule_and_model_agreement_lifts_confidence() -> None:
    model = _FakeModel(
        _answer(
            "tender_no",
            "招标编号：ABC-2024-001",
            "招标编号：ABC-2024-001",
            "p1b1",
            confidence=0.9,
        )
    )

    result = _run(model, "tender_no", _document("招标编号：ABC-2024-001"))

    assert result["strategy"] == "rule+llm"
    assert result["status"] == "auto"
    # (0.9 + 0.82) / 2 + 0.08：规则与模型互为佐证时抬高置信度。
    assert result["confidence"] == pytest.approx(0.94)
    assert len(result["evidence"]) == 1


def test_rule_disagreement_is_reported_as_conflict() -> None:
    model = _FakeModel(
        _answer("tender_no", "DEF-2025-002", "招标编号：ABC-2024-001", "p1b1", confidence=0.9)
    )

    result = _run(model, "tender_no", _document("招标编号：ABC-2024-001"))

    assert result["status"] == "conflict"
    assert {item["source"] for item in result["value"]["candidates"]} == {"llm", "rule"}


def test_list_field_unions_values_across_chapters() -> None:
    model = _FakeModel(
        _answer(
            "qualification_requirements",
            ["具备一级资质"],
            "资格要求：具备一级资质",
            "p1b2",
            value_text="具备一级资质",
        ),
        _answer(
            "qualification_requirements",
            ["具备一级资质", "具备安全生产许可证"],
            "资格要求：具备安全生产许可证",
            "p1b4",
            value_text="具备一级资质\n具备安全生产许可证",
        ),
    )
    document = _two_chapters(
        ("第一章 资格要求", "资格要求：具备一级资质"),
        ("第二章 其他要求", "资格要求：具备安全生产许可证"),
    )

    result = _run(model, "qualification_requirements", document)

    assert result["status"] == "auto"
    assert [item["value"] for item in result["value"]] == ["具备一级资质", "具备安全生产许可证"]
    assert [item["anchor"] for item in result["evidence"]] == ["p1b2", "p1b4"]
    assert result["strategy"] == "llm"


def test_not_found_chunk_is_skipped_when_another_chunk_has_the_value() -> None:
    model = _FakeModel(
        _answer("qualification_requirements", None, "", "p1b2", not_found=True),
        _answer(
            "qualification_requirements",
            ["具备安全生产许可证"],
            "资格要求：具备安全生产许可证",
            "p1b4",
            value_text="具备安全生产许可证",
        ),
    )
    document = _two_chapters(
        ("第一章 资格要求", "资格要求：具备一级资质"),
        ("第二章 其他要求", "资格要求：具备安全生产许可证"),
    )

    result = _run(model, "qualification_requirements", document)

    # 前一块"没找到"只是这一块没有，不能因此把后一块的命中一起丢掉。
    assert result["status"] == "auto"
    assert [item["value"] for item in result["value"]] == ["具备安全生产许可证"]
    assert [item["anchor"] for item in result["evidence"]] == ["p1b4"]


def test_list_field_conflict_keeps_both_passes() -> None:
    model = _FakeModel(
        _answer(
            "qualification_requirements",
            ["具备一级资质"],
            "资格要求：具备一级资质",
            "p1b2",
            confidence=0.4,
            value_text="具备一级资质",
        ),
        _answer(
            "qualification_requirements",
            ["具备二级资质"],
            "资格要求：具备一级资质",
            "p1b2",
            confidence=0.7,
            value_text="具备二级资质",
        ),
    )
    document = _two_chapters(("第一章 资格要求", "资格要求：具备一级资质"))

    result = _run(model, "qualification_requirements", document)

    assert result["status"] == "conflict"
    assert [item["value"] for item in result["value"]] == ["具备一级资质", "具备二级资质"]


def test_invalid_json_from_model_is_rejected() -> None:
    with pytest.raises(ValueError, match="非法 JSON"):
        _run(_BrokenJsonModel(), "project_name", _document("项目名称：某市政道路工程"))
