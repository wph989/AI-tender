"""综合期提示预算：完整 Skill 只在关键轮次注入，成果摘要按增量下发。"""

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from synthesis_fixtures import noop
from test_analysis_guards import build
from test_analysis_research import block, session
from test_deep_analysis import KEY, ScriptedRouter

from tender.application.analysis import agent
from tender.application.analysis.agent import ResearchMiddleware
from tender.application.analysis.policy import load_module_skill
from tender.application.analysis.skills import skill_snapshot

# 只存在于完整参考文件中，摘要轮次不应重复注入。
FULL_ONLY = "项目概况提取细则"


class FakeRequest:
    def __init__(self, messages=(), system_message=None, tools=()):
        self.messages = list(messages)
        self.system_message = system_message or SystemMessage(content="")
        self.tools = list(tools)

    def override(self, **kwargs):
        clone = FakeRequest(self.messages, self.system_message, self.tools)
        clone.__dict__.update(kwargs)
        return clone


def loaded_skill():
    return load_module_skill(skill_snapshot(), KEY)


def checkpoint():
    return {
        "topics": [{
            "topic": "warranty", "status": "covered",
            "detail": "已核对质保主题", "evidence_ids": ["s1r1c0"],
        }],
        "references": [{
            "topic": "warranty", "from_block_id": "s1r1c0", "target": "附件甲",
            "status": "missing", "detail": "待核对",
        }],
        "document_gaps": [],
        "research_summary": "已完成检索",
        "project_searches": [],
    }


def staged(index, value, field):
    return {
        "id": f"item-{index}", "field": field,
        "values": [{"value": value}], "verification": "supported",
    }


def system_prompt(research, state, skill, *, messages=()):
    middleware = ResearchMiddleware(research, state, noop, noop, skill=skill)
    captured = []

    async def handler(request):
        captured.append(request)
        return request

    asyncio.run(middleware.awrap_model_call(FakeRequest(messages=messages), handler))
    assert len(captured) == 1
    return captured[0].system_message.content


def test_full_skill_injected_on_first_and_transition_rounds():
    skill, state, research = loaded_skill(), {}, session([block()])
    first = system_prompt(research, state, skill)
    assert FULL_ONLY in first
    assert state["skill_prompt_phase"] == "research"

    second = system_prompt(research, state, skill)
    assert FULL_ONLY not in second
    assert "## 执行流程" in second and "citations" in second and "支持性校验" in second

    state["research_completed"] = checkpoint()
    third = system_prompt(research, state, skill)
    assert FULL_ONLY in third
    assert state["skill_prompt_phase"] == "synthesis"


def test_digest_round_keeps_critical_sections_and_schema_keys():
    skill, state, research = loaded_skill(), {}, session([block()])
    system_prompt(research, state, skill)  # 首轮完整注入
    digest = system_prompt(research, state, skill)
    assert "## 执行流程" in digest
    assert "## 本项目的检索与输出" in digest
    assert "输出分类与内容键" in digest
    assert "项目与采购人" in digest
    assert len(digest) < len(skill["instructions"])


def test_summarization_event_reinjects_full_skill():
    skill, state, research = loaded_skill(), {}, session([block()])
    system_prompt(research, state, skill)
    summary = HumanMessage(
        content="历史对话摘要", id="summary-1",
        additional_kwargs={"lc_source": "summarization"},
    )
    again = system_prompt(research, state, skill, messages=[summary])
    assert FULL_ONLY in again
    assert state["skill_full_summary_id"] == "summary-1"
    later = system_prompt(research, state, skill, messages=[summary])
    assert FULL_ONLY not in later


def test_staged_digest_only_reports_new_verified_items():
    skill, research = loaded_skill(), session([block()])
    state = {
        "output_schema": {"sections": [
            {"title": "项目基本信息", "columns": ["字段", "内容"]},
        ]},
        "research_completed": checkpoint(),
        "staged_items": [staged(1, "旧值一", "旧字段一"), staged(2, "旧值二", "旧字段二")],
    }
    first = system_prompt(research, state, skill)
    assert "已有2个汇总条目" in first
    assert "旧字段一" in first and "旧字段二" in first
    assert "附件甲" in first

    state["staged_items"] = [*state["staged_items"], staged(3, "新值三", "新字段三")]
    second = system_prompt(research, state, skill)
    assert "已有3个汇总条目" in second
    assert "新字段三" in second
    assert "旧字段一" not in second and "旧字段二" not in second
    # 转引清单未变化，不再重复整段JSON，但未决转引仍以摘要保留。
    assert '"from_block_id"' not in second
    assert "未决转引：warranty→附件甲（missing）" in second
    assert "未变化，仅列主题" in second


def test_prompt_budget_does_not_repeat_full_staged_dump():
    skill, research = loaded_skill(), session([block()])
    state = {
        "output_schema": {"sections": [
            {"title": "项目基本信息", "columns": ["字段", "内容"]},
        ]},
        "research_completed": checkpoint(),
        "staged_items": [staged(1, "旧值一", "旧字段一"), staged(2, "旧值二", "旧字段二")],
    }
    system_prompt(research, state, skill)
    budgeted = system_prompt(research, state, skill)
    assert "已有2个汇总条目" in budgeted
    assert "已保存成果" not in budgeted
    assert "旧字段一" not in budgeted and "旧字段二" not in budgeted


def test_skill_prompt_mode_event_only_emitted_when_mode_changes():
    skill, state, research = loaded_skill(), {}, session([block()])
    events = []
    middleware = ResearchMiddleware(
        research, state, noop, noop, skill=skill,
        event=lambda kind, detail: events.append((kind, detail)),
    )

    async def handler(request):
        return request

    for _ in range(3):
        asyncio.run(middleware.awrap_model_call(FakeRequest(), handler))

    modes = [detail["mode"] for kind, detail in events if kind == "skill_prompt_mode"]
    # 首轮完整注入、次轮切摘要各记一条；第三轮仍是摘要，不重复写事件。
    assert modes == ["full", "digest"]


def test_digest_fallback_uses_full_skill_when_sections_missing():
    snapshot = {
        KEY + "/SKILL.md": "只写领域知识，没有执行流程小节。",
        KEY + "/references/output_format.md": (
            "```markdown\n## 项目基本信息\n| 字段 | 内容 |\n|---|---|\n```"
        ),
    }
    loaded = load_module_skill(snapshot, KEY)
    assert loaded["digest"] == loaded["instructions"]
    state = {}
    research = session([block()])
    system_prompt(research, state, loaded)
    second = system_prompt(research, state, loaded)
    assert "只写领域知识" in second


@pytest.mark.parametrize("duration,remaining,closing", [(300, 1200, True), (2, 301, False)])
def test_measured_model_time_reserves_closing_rounds_after_restore(
    monkeypatch, duration, remaining, closing,
):
    async def run():
        clock = [0.0]
        monkeypatch.setattr(agent, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        research, state = session([block()]), {}
        # 使用真实构图初始化专题状态，避免把证据数量或自报覆盖当作完成标志。
        build(ScriptedRouter([]), research, state)
        await research.search("质保", "project")
        first = ResearchMiddleware(research, state, noop, noop)
        response = object()

        async def handler(request):
            clock[0] += duration
            return response

        assert await first.awrap_model_call(FakeRequest(), handler) is response
        assert state["model_round_seconds"] == duration
        # 重新创建中间件模拟恢复，统计来自应用状态而非进程内计时器。
        restored = ResearchMiddleware(
            research, state, noop, noop,
            budget_status=lambda: {"seconds_remaining": remaining, "finish_reserve_seconds": 300},
        )
        captured = []

        async def capture(request):
            captured.append(request)

        tools = [{"type": "function", "function": {"name": name}} for name in
                 ("search_document", "read_document", "complete_research", "submit_analysis")]
        await restored.awrap_model_call(FakeRequest(tools=tools), capture)
        names = [t["function"]["name"] for t in captured[0].tools]
        assert names == (
            ["complete_research"] if closing else [t["function"]["name"] for t in tools]
        )
        if closing:
            assert "unresolved/missing" in captured[0].system_message.text
        assert "draft" not in state and not state.get("research_completed")

    asyncio.run(run())


def test_failed_model_request_does_not_update_measured_round_time(monkeypatch):
    async def run():
        clock = [0.0]
        monkeypatch.setattr(agent, "time", SimpleNamespace(monotonic=lambda: clock[0]))
        state = {"model_round_seconds": 30.0}
        middleware = ResearchMiddleware(session([block()]), state, noop, noop)

        async def fail(request):
            clock[0] += 600
            raise ConnectionError("模型不可用")

        with pytest.raises(ConnectionError):
            await middleware.awrap_model_call(FakeRequest(), fail)
        assert state["model_round_seconds"] == 30.0

    asyncio.run(run())
