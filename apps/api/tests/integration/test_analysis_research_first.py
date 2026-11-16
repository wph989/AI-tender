"""原生PostgreSQL验证研究检查点、统一展示及到期发布的所有权边界。"""

import asyncio
import copy
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import test_deepagents_runtime
from test_deepagents_runtime import prepared_runtime, publishable_state, report

from tender.application.analysis.drafts import AGENT_PROTOCOL, DraftWorkspace
from tender.application.analysis.topic_flow import OUTPUT_MODE, OUTPUT_MODE_KEY
from tender.config.registry import ConfigRegistry
from tender.core.di import create_analysis_service

env = test_deepagents_runtime.env
pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要隔离数据库集成验证"
)


def state_with_notes():
    state = publishable_state("project_basic_info_parsing")
    state["topic_flow"] = {"output_mode": OUTPUT_MODE, "phase": "research",
                           "audit": {"round": 0, "results": {}},
                           "entries": {"identity": {"topic": "identity", "title": "身份",
                               "scope": {"kind": "common", "lot_refs": []},
                               "status": "researching", "checked": ["名称"], "checks": ["名称"],
                               "blocked_checks": [],
                               "detail": "已找到项目名称", "tasks": {}, "evidence_ids": ["s1r1c0"],
                               "record_keys": ["warranty"], "references": [],
                               "findings": {"名称": {"detail": "测试项目",
                                                     "evidence_ids": ["s1r1c0"]}},
                           }}}
    return state


def agent_state_with_notes():
    state = {}
    book = DraftWorkspace(state, {}, "project_basic_info_parsing")
    book.book["notes"] = {"note-1": {"id": "note-1", "topic": "身份", "status": "open",
        "detail": "已读公告，继续核对补充附件范围", "block_ids": []}}
    return state


def test_new_report_freezes_research_before_output(env):
    current = report(env, topic_flow=True)
    assert current["skill_snapshot"]["__analysis_flow_version__"] == AGENT_PROTOCOL
    assert "analysis_workflow/SKILL.md" in current["skill_snapshot"]
    assert OUTPUT_MODE_KEY not in current["skill_snapshot"]


def test_research_notes_are_saved_while_business_records_remain_hidden(env):
    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    try:
        state = state_with_notes()
        runtime.save(state)
        runtime.reserve("model")
        row = env.db.rows("SELECT state,model_calls FROM agent_module_run WHERE id=:id",
                          {"id": runtime.run["id"]})[0]
        module = env.db.rows("SELECT items,business_data FROM analysis_module WHERE id=:id",
                             {"id": runtime.run["module_id"]})[0]
        assert row["state"]["topic_flow"]["entries"] == state["topic_flow"]["entries"]
        assert row["model_calls"] == 1
        assert module["items"] == [] and module["business_data"]["records"] == []
        assert module["business_data"]["progress"]["phase"] == "research"
        # 综合阶段同样只保留检查点，不能把第一批业务条目提前展示。
        state["topic_flow"]["phase"] = "synthesis"
        runtime.save(state)
        assert env.db.rows("SELECT items FROM analysis_module WHERE id=:id",
                           {"id": runtime.run["module_id"]})[0]["items"] == []
    finally:
        runtime.release()


def test_deadline_releases_only_verified_current_records_and_keeps_notes(env):
    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    try:
        state = state_with_notes()
        runtime.save(state)
        env.db.execute("UPDATE agent_module_run SET deadline_at=now()-interval '1 second' "
                       "WHERE id=:id", {"id": runtime.run["id"]})
        runtime.finish("partial", "已到期，保留核实结果", state=state)
        row = env.db.rows("SELECT state,status FROM agent_module_run WHERE id=:id",
                          {"id": runtime.run["id"]})[0]
        module = env.db.rows("SELECT items,business_data FROM analysis_module WHERE id=:id",
                             {"id": runtime.run["module_id"]})[0]
        assert row["status"] == "partial" and row["state"]["topic_flow"]["phase"] == "partial"
        assert row["state"]["topic_flow"]["entries"] == state["topic_flow"]["entries"]
        assert [i["id"] for i in module["items"]] == ["keep"]
        assert [i["id"] for i in module["business_data"]["records"]] == ["keep"]
    finally:
        runtime.release()


def test_expired_old_owner_cannot_release_staged_results(env):
    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    try:
        state = state_with_notes()
        runtime.save(state)
        before = copy.deepcopy(state)
        env.db.execute("UPDATE agent_module_run SET owner=CAST(:owner AS UUID) WHERE id=:id",
                       {"id": runtime.run["id"], "owner": str(uuid4())})
        with pytest.raises(InterruptedError):
            runtime.finish("partial", "旧执行者尝试发布", state=state)
        assert state == before
        module = env.db.rows("SELECT items FROM analysis_module WHERE id=:id",
                             {"id": runtime.run["module_id"]})[0]
        assert not module["items"]
    finally:
        runtime.release()


def test_explicit_retry_keeps_research_notes_even_without_business_records(env):
    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    state = agent_state_with_notes()
    state["staged_items"] = []
    try:
        runtime.finish("failed", "研究后模型不可用", state=state)
    finally:
        runtime.release()
    env.db.execute("UPDATE analysis_report SET status='partial' WHERE id=:id",
                   {"id": runtime.report["id"]})
    create_analysis_service(env.engine, 1, ConfigRegistry(env.engine)).retry_report(
        runtime.report["id"], module_keys=["project_basic_info_parsing"],
        max_output_tokens=None, timeout_seconds=None, mode="resume",
    )
    row = env.db.rows("SELECT state,model_calls,tool_calls,attempt FROM agent_module_run "
                      "WHERE module_id=:id ORDER BY attempt DESC LIMIT 1",
                      {"id": runtime.run["module_id"]})[0]
    assert row["attempt"] == 2 and row["model_calls"] == row["tool_calls"] == 0
    assert row["state"]["agent_workspace"]["notes"] == state["agent_workspace"]["notes"]
    assert "topic_flow" not in row["state"]


def test_work_evidence_and_context_cursor_survive_database_checkpoint_without_resetting_budget(env):
    from tender.application.analysis.protocol import ResearchDelta, ResearchLedger
    from tender.application.analysis.research import ResearchSession
    from tender.application.analysis.topic_flow import TopicFlow

    async def unused(*args):
        raise AssertionError("读取研究检查点不应再次检索或调用模型")

    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    try:
        state = state_with_notes()
        state["staged_items"] = []
        state["business_topics"] = [{"key": "identity", "checks": ["名称", "金额"]}]
        state["topic_flow"] = {"protocol": "research-v2", "output_mode": OUTPUT_MODE,
                               "phase": "research", "entries": {}, "evidence_topics": {},
                               "audit": {"round": 0}}
        research = ResearchSession([], 10, unused, unused, unused)
        research.seen = {"s1r1c0": {"content": "项目名称原文" * 600, "project_id": 10}}
        flow = TopicFlow(state, research)
        book = ResearchLedger(flow)
        work_id = book.works()[0]["id"]
        book.update([ResearchDelta(work_ids=[work_id], detail="已核对项目名称",
                                   evidence_ids=["s1r1c0"],
                                   scope={"kind": "common", "lot_refs": []})])
        page = book.context([work_id], limit=1000)
        assert page["has_more"]
        runtime.save(state)
        runtime.reserve("model")
        row = env.db.rows("SELECT state,model_calls,tool_calls FROM agent_module_run WHERE id=:id",
                          {"id": runtime.run["id"]})[0]
        restored = ResearchLedger(TopicFlow(row["state"], research))
        expected = book.context([work_id], page["next_offset"], 1000, revision=page["revision"])
        assert restored.context([work_id], page["next_offset"], 1000,
                                revision=page["revision"]) == expected
        assert row["model_calls"] == 1 and row["tool_calls"] == 0
        module = env.db.rows("SELECT items FROM analysis_module WHERE id=:id",
                             {"id": runtime.run["module_id"]})[0]
        assert module["items"] == []
    finally:
        runtime.release()


def test_retry_restores_examined_notes_and_todos_before_any_check_is_completed(env):
    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    state = agent_state_with_notes()
    blocks = env.db.read_chunk_window(runtime.sources[0], 0, 1).rows
    state["research"] = {"seen": {r["block_id"]: r for r in blocks}, "events": [], "tool_calls": 2}
    try:
        runtime.save(state)
        runtime.reserve("model")
        runtime.reserve("tool")
        runtime.finish("partial", "草稿尚未形成时预算耗尽", state=state)
    finally:
        runtime.release()
    env.db.execute("UPDATE analysis_report SET status='partial' WHERE id=:id",
                   {"id": runtime.report["id"]})
    create_analysis_service(env.engine, 1, ConfigRegistry(env.engine)).retry_report(
        runtime.report["id"], module_keys=["project_basic_info_parsing"], mode="resume",
        max_output_tokens=None, timeout_seconds=None,
    )
    row = env.db.rows("SELECT * FROM agent_module_run WHERE module_id=:id "
                     "ORDER BY attempt DESC LIMIT 1", {"id": runtime.run["module_id"]})[0]
    assert row["attempt"] == 2 and row["model_calls"] == row["tool_calls"] == 0
    assert row["state"]["research"]["tool_calls"] == 0
    assert row["state"]["research"]["seen"] == state["research"]["seen"]
    assert row["state"]["agent_workspace"]["notes"] == state["agent_workspace"]["notes"]
    module = env.db.rows("SELECT items,business_data FROM analysis_module WHERE id=:id",
                         {"id": runtime.run["module_id"]})[0]
    assert module["items"] == [] and not module["business_data"].get("records")


def test_semantic_completion_survives_checkpoint_without_per_check_notes_or_budget_reset(env):
    from tender.application.analysis.protocol import ResearchLedger
    from tender.application.analysis.research import ResearchSession
    from tender.application.analysis.search_control import TopicSearch
    from tender.application.analysis.topic_flow import TopicFlow

    async def unused(*args):
        raise AssertionError("恢复研究边界不得额外检索或调用模型")

    async def allow():
        pass

    runtime = prepared_runtime(env, topic_flow=True)
    assert runtime.claim()
    try:
        state = {"business_topics": [{"key": "identity", "checks": ["名称"]}]}
        research = ResearchSession(
            runtime.sources, runtime.report["project_id"], unused, unused, allow,
            compact_results=True,
        )
        flow = TopicFlow(state, research)
        flow.data.update(protocol="research-v2", output_mode=OUTPUT_MODE, phase="research")
        book = ResearchLedger(flow)
        work_id = book.works()[0]["id"]
        row = runtime.sources[0] | {
            "block_id": "s1r1c0", "content": "项目名称为测试项目", "offset": 0,
            "element_id": 0, "page_no": 1, "bbox": [], "score": 1.0,
        }

        async def retrieve(sources, query):
            return [row], {}

        research.retrieve = retrieve
        control = TopicSearch(flow)
        selected = control.begin("search_document", {"query": "项目名称", "work": work_id})
        result = asyncio.run(research.search("项目名称", "project"))
        flow.evidence(set(), ["identity"], result)
        control.end(selected, result, set())
        runtime.reserve("tool")
        # 阶段切换和预算分别落库，恢复不得重复扣费或先要求补写研究笔记。
        book.finish("已理解项目名称原文，开始统一综合")
        state["research"] = research.checkpoint()
        runtime.save(state)
        runtime.reserve("model")
        row = env.db.rows("SELECT state,model_calls,tool_calls FROM agent_module_run WHERE id=:id",
                          {"id": runtime.run["id"]})[0]
        restored = TopicFlow(row["state"], research)
        assert not restored.researching
        assert row["model_calls"] == 1 and row["tool_calls"] == 1
        assert ResearchLedger(restored).works()[0]["id"] == work_id
        assert not restored.entries[0].get("findings")
        assert restored.entries[0]["unreviewed_evidence"]
        assert restored.state["research_completed"]["project_searches"]
        assert not restored.state.get("draft")
        module = env.db.rows("SELECT items FROM analysis_module WHERE id=:id",
                             {"id": runtime.run["module_id"]})[0]
        assert not module["items"]
    finally:
        runtime.release()


@pytest.mark.parametrize("status", ["completed", "partial", "failed", "canceled"])
def test_debug_archive_starts_retention_after_confirmed_terminal_and_keeps_database(
    env, tmp_path, status,
):
    from tender.adapters.analysis.file_archive import FileAnalysisArchive

    runtime = prepared_runtime(env, topic_flow=True)
    archive = FileAnalysisArchive(tmp_path)
    runtime.archive = archive
    assert runtime.claim()
    try:
        state = state_with_notes()
        runtime.save(state)
        assert not list(tmp_path.glob("*.json"))
        runtime.finish(status, state=state)
        paths = list(tmp_path.glob("*.json"))
        assert len(paths) == 1
        value = json.loads(paths[0].read_text(encoding="utf-8"))
        actual = env.db.rows("SELECT status,finished_at,state FROM agent_module_run WHERE id=:id",
                             {"id": runtime.run["id"]})[0]
        assert value["execution"]["status"] == actual["status"] == status
        assert datetime.fromisoformat(value["execution"]["finished_at"]) == actual["finished_at"]
        assert value["topics"] == state["topic_flow"]
        assert (datetime.fromisoformat(value["expires_at"])
                >= actual["finished_at"] + timedelta(days=1))
        archive.now = lambda: actual["finished_at"] + timedelta(days=1, seconds=1)
        assert archive.cleanup() == 1
        assert env.db.rows("SELECT state FROM agent_module_run WHERE id=:id",
                           {"id": runtime.run["id"]})[0]["state"] == actual["state"]
    finally:
        archive.close()
        runtime.release()


def test_lost_owner_does_not_archive_stale_execution(env, tmp_path):
    from tender.adapters.analysis.file_archive import FileAnalysisArchive

    runtime = prepared_runtime(env, topic_flow=True)
    archive = FileAnalysisArchive(tmp_path, now=lambda: datetime.now(UTC))
    runtime.archive = archive
    assert runtime.claim()
    try:
        runtime.save(state_with_notes())
        env.db.execute("UPDATE agent_module_run SET owner=:owner WHERE id=:id",
                       {"id": runtime.run["id"], "owner": uuid4()})
        runtime.abandon("failed", "旧执行者结束")
        assert not list(tmp_path.glob("*.json"))
    finally:
        archive.close()
        runtime.release()


def test_archive_write_failure_does_not_roll_back_terminal_module(env):
    from unittest.mock import Mock

    runtime = prepared_runtime(env, topic_flow=True)
    runtime.archive = Mock()
    runtime.archive.write.side_effect = OSError("diagnostic disk unavailable")
    assert runtime.claim()
    try:
        runtime.finish("failed", state=state_with_notes())
        runtime.archive.write.assert_called_once()
        assert env.db.rows("SELECT status FROM agent_module_run WHERE id=:id",
                           {"id": runtime.run["id"]})[0]["status"] == "failed"
    finally:
        runtime.release()
