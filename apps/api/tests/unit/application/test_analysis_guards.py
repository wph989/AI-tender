"""解析协议的行为回归：数据最小化、真实Skill加载、有界恢复和必要证据保留。"""

import asyncio
import copy
import re
from types import SimpleNamespace

import pytest
from agent_fixtures import KEY, submitted_field
from test_analysis_research import block, session

from tender.application.analysis.execution import invoke_module
from tender.application.analysis.policy import (
    load_module_skill,
)
from tender.application.analysis.skills import MODULES, skill_snapshot
from tender.application.knowledge.content import validate_items
from tender.application.shared.research import ToolArgumentError
from tender.domain.shared.errors import ModelUnavailable


async def noop(*args):
    pass


def test_compact_evidence_keeps_chapter_and_rereads_by_registered_id():
    async def run():
        rows = [
            block() | {"score": 0.99, "bbox": [1, 2, 3, 4], "page_no": 8},
            block()
            | {"block_id": "next", "element_id": 2, "offset": 1, "content": "但易损件仅保修一年"},
        ]
        research = session(rows)
        research.compact_results = True
        with pytest.raises(ToolArgumentError):
            await research.read_evidence("s1r1c0")
        result = await research.search("质保", "project")
        assert result["blocks"] == [{"id": r["block_id"], "text": r["content"],
                                    "source_id": r["source_id"], "chapter": r["chapter"]}
                                   for r in rows]
        assert "retrieval" not in result and "relations" not in result
        assert research.seen["s1r1c0"]["page_no"] == 8
        reread = await research.read_evidence("s1r1c0", 0, 1)
        assert reread["blocks"] == result["blocks"]
        assert research.events[-2]["action"] == "read_evidence"
        assert research.events[-1]["action"] == "read_result"
        assert research.events[-1]["block_ids"] == [r["block_id"] for r in rows]
        assert all(set(d) == {"id", "text"} for d in await research.documents())

    asyncio.run(run())


def test_retriever_cannot_mix_authorized_reference_into_project_scope():
    async def run():
        research = session([block(), block(2, 20)])

        async def mixed(*args):
            return [block(2, 20)], {}

        research.retrieve = mixed
        with pytest.raises(PermissionError, match="所选范围"):
            await research.search("质保", "project")
        assert not research.seen

    asyncio.run(run())


def test_project_skills_have_loadable_references_and_distinct_domain_rules():
    snapshot = skill_snapshot()
    for key in MODULES:
        loaded = load_module_skill(snapshot, key)
        assert loaded["model_rules"].strip()
        assert "read_document(source_id" not in loaded["model_rules"]
        text = snapshot[key + "/SKILL.md"]
        for reference in re.findall(r"`(references/[^`]+\.md)`", text):
            for category in ("engineering", "goods", "service"):
                assert key + "/" + reference.replace("<type_dir>", category) in snapshot
        modified = snapshot | {key + "/SKILL.md": text + "\n新的业务规则"}
        assert load_module_skill(modified, key)["sha256"] != loaded["sha256"]
    assert "纯参数清单" in snapshot["tech_requirement_parsing/SKILL.md"]
    # 模型引用稳定 key，最终 parent_id 由服务端生成，避免模型编造记录身份。
    assert "parent_key" in snapshot["bid_format_outline_parsing/SKILL.md"]
    with pytest.raises(ValueError, match="Skill"):
        load_module_skill({}, KEY)


@pytest.mark.parametrize(
    "error", [ConnectionError("本地连接中断"), ModelUnavailable("路由已耗尽")]
)
def test_subagent_recovery_is_bounded_and_never_multiplies_model_retries(error):
    class BrokenGraph:
        calls = 0

        async def aget_state(self, config):
            return SimpleNamespace(values={})

        async def ainvoke(self, *args, **kwargs):
            self.calls += 1
            raise error

    async def run():
        graph, state, saved = BrokenGraph(), {}, []

        async def save(value):
            saved.append(copy.deepcopy(value))

        expected = RuntimeError if isinstance(error, ConnectionError) else ModelUnavailable
        with pytest.raises(expected):
            await invoke_module(graph, {}, thread_id="retry", task="分析", state=state, save=save)
        if isinstance(error, ConnectionError):
            assert graph.calls == 3 and state["subagent_retries"] == 2
            assert [s["subagent_retries"] for s in saved] == [1, 2]
            with pytest.raises(RuntimeError):
                await invoke_module(
                    graph, {}, thread_id="retry", task="恢复", state=state, save=save
                )
            assert graph.calls == 4  # 恢复仍无额外重试机会。
        else:
            assert graph.calls == 1 and not saved

    asyncio.run(run())


def evidence_fixture(cross_source=False):
    rows = [
        block() | {"page_no": 2, "bbox": [1, 2, 3, 4]},
        block(2, 10)
        if cross_source
        else block() | {"block_id": "duplicate", "element_id": 3, "offset": 1},
    ]
    rows[1] |= {"page_no": 8, "bbox": [4, 3, 2, 1]}
    seen = {r["block_id"]: r for r in rows}
    field = submitted_field("质保", "质保三年")
    field["values"][0]["citations"].append({"block_id": rows[1]["block_id"], "quote": "质保三年"})
    return validate_items([field], seen), seen
