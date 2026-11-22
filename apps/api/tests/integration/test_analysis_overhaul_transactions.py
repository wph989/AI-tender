"""真实事务验证冷启动清理与新运行入账原子性，历史检查点保持可追溯。"""

import json
import os

import pytest
import test_deepagents_runtime
from test_deepagents_runtime import prepared_runtime
from test_knowledge_flow import add_source

from tender.adapters.pg.repositories.knowledge.store import KnowledgeSession
from tender.application.analysis.drafts import AGENT_PROTOCOL, DraftWorkspace
from tender.application.analysis.output import output_schema
from tender.application.analysis.runtime import AgentRuntime
from tender.application.knowledge.content import source_signature
from tender.config.registry import ConfigRegistry
from tender.core.di import create_analysis_service

env = test_deepagents_runtime.env
pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要隔离数据库集成验证",
)
KEY = "project_basic_info_parsing"


def agent_state_with_notes():
    # 缺件与自查持久化使用现行工作区，不依赖历史研究阶段。
    return {"agent_workspace": {
        "protocol": AGENT_PROTOCOL, "notes": {"n1": {"text": "待补附件甲"}},
        "reviews": {"old": {"status": "passed"}}, "finalized": True,
        "issues": {"missing": {"action": "provide_input", "detail": "待补附件甲"}},
    }}


def terminal_module(env, status):
    runtime = prepared_runtime(env)
    assert runtime.claim()
    old = {"research": {"seen": {"historical": {"content": "旧研究内容"}}},
           "stop_reason": {"message": "旧停止原因"}}
    try:
        runtime.save(old)
        runtime.finish(status, state=old)
    finally:
        runtime.release()
    summary = [{"field": "旧成果", "module_keys": [KEY], "values": []}]
    env.db.execute("UPDATE analysis_module SET items=CAST(:items AS JSONB),"
                   "business_data=CAST(:business AS JSONB) WHERE id=:id", {
                       "id": runtime.run["module_id"], "items": json.dumps(summary),
                       "business": json.dumps({"quality_status": "needs_review"}),
                   })
    env.db.execute("UPDATE analysis_report SET status=:status,summary=CAST(:summary AS JSONB) "
                   "WHERE id=:id", {"id": runtime.report["id"], "status": status,
                                    "summary": json.dumps(summary)})
    return runtime, old


@pytest.mark.parametrize("status", ["completed", "failed", "partial", "canceled"])
def test_restart_keeps_formal_projection_and_history_until_final_in_real_postgres(env, status):
    runtime, old = terminal_module(env, status)
    service = create_analysis_service(env.engine, 1, ConfigRegistry(env.engine))
    service.retry_report(runtime.report["id"], module_keys=[KEY], mode="restart",
                         max_output_tokens=None, timeout_seconds=None)
    runs = env.db.rows("SELECT * FROM agent_module_run WHERE module_id=:id ORDER BY attempt",
                       {"id": runtime.run["module_id"]})
    assert runs[0]["state"] == old
    assert runs[-1]["attempt"] == 2
    assert runs[-1]["thread_id"] != runs[0]["thread_id"]
    assert runs[-1]["state"] == {"execution_mode": "restart"}
    module = env.db.rows("SELECT * FROM analysis_module WHERE id=:id",
                         {"id": runtime.run["module_id"]})[0]
    assert module["items"][0]["field"] == "旧成果"
    assert module["business_data"] == {"quality_status": "needs_review"}
    assert env.db.report(runtime.report["id"])["summary"] == module["items"]


def test_restart_rolls_back_cleanup_when_new_run_insert_fails(env, monkeypatch):
    runtime, _ = terminal_module(env, "completed")
    service = create_analysis_service(env.engine, 1, ConfigRegistry(env.engine))
    before = env.db.rows("SELECT * FROM analysis_module WHERE id=:id",
                         {"id": runtime.run["module_id"]})[0]

    def fail(*args, **kwargs):
        raise RuntimeError("新运行入账失败")

    monkeypatch.setattr(KnowledgeSession, "insert_module_run", fail)
    with pytest.raises(RuntimeError, match="入账失败"):
        service.retry_report(runtime.report["id"], module_keys=[KEY], mode="restart",
                             max_output_tokens=None, timeout_seconds=None)
    assert env.db.rows("SELECT * FROM analysis_module WHERE id=:id",
                       {"id": runtime.run["module_id"]})[0] == before
    assert len(env.db.rows("SELECT id FROM agent_module_run WHERE module_id=:id",
                           {"id": runtime.run["module_id"]})) == 1


def test_new_attachment_reopens_confirmed_missing_input_and_preserves_current_evidence(env):

    runtime = prepared_runtime(env)
    assert runtime.claim()
    state = agent_state_with_notes()
    row = env.db.read_chunk_window(runtime.sources[0], 0, 1).rows[0]
    state["research"] = {"seen": {row["block_id"]: row}, "events": [], "tool_calls": 2}
    state["agent_workspace"]["finalized"] = True
    try:
        runtime.save(state)
        runtime.finish("completed", state=state)
    finally:
        runtime.release()
    env.db.execute("UPDATE analysis_module SET business_data=CAST(:business AS JSONB) WHERE id=:id",
                   {"id": runtime.run["module_id"], "business": json.dumps({
                       "quality_status": "needs_input"})})
    env.db.execute("UPDATE analysis_report SET status='completed' WHERE id=:id",
                   {"id": runtime.report["id"]})
    with env.engine.begin() as c:
        add_source(c, runtime.report["project_id"], "附件甲：开标日期为2026年12月1日。")
    service = create_analysis_service(env.engine, 1, ConfigRegistry(env.engine))
    service.retry_report(runtime.report["id"], module_keys=[], mode="resume",
                         max_output_tokens=None, timeout_seconds=None)
    latest = env.db.rows("SELECT state FROM agent_module_run WHERE module_id=:id "
                         "ORDER BY attempt DESC LIMIT 1",
                         {"id": runtime.run["module_id"]})[0]["state"]
    assert row["block_id"] in latest["research"]["seen"]
    assert not latest["agent_workspace"]["finalized"]
    assert not latest["agent_workspace"]["reviews"]
    assert len(env.db.report(runtime.report["id"])["source_snapshot"]) == 2


@pytest.mark.parametrize("status", ["partial", "failed", "canceled"])
def test_new_attachment_interrupted_attempt_can_resume_its_reviewed_draft(env, status):
    runtime = prepared_runtime(env)
    report_id, module_id = runtime.report["id"], runtime.run["module_id"]
    row = env.db.read_chunk_window(runtime.sources[0], 0, 1).rows[0]
    state = {
        "output_schema": output_schema(runtime.report["skill_snapshot"], KEY),
        "authorized_sources": runtime.sources,
        "quality_input_signature": source_signature(
            runtime.report["source_snapshot"] + runtime.report["reference_snapshot"]),
        "research": {"seen": {row["block_id"]: row}},
    }
    book = DraftWorkspace(state, state["research"]["seen"], KEY)
    book.record_review([], [{
        "topic": "项目基本信息", "target": "开标日期", "detail": "待补附件甲",
        "action": "provide_input", "missing_input": {
            "file_name": "附件甲", "reference_ids": [row["block_id"]],
            "checked_source_ids": [row["source_id"]],
        },
    }], "missing")
    book.finalize([], "开标日期待补件")
    assert runtime.claim()
    try:
        runtime.save(state)
        runtime.finish("completed", draft=state["draft"], state=state)
    finally:
        runtime.release()
    formal = next(module for module in env.db.report_modules(report_id)
                  if module["id"] == module_id)
    assert formal["business_data"]["quality_status"] == "needs_input"
    # 模拟其他专题已完成，释放真实队列中的队首位置，让所选专题的新轮次能够领取。
    env.db.execute("UPDATE agent_module_run SET status='completed' WHERE module_id IN "
                   "(SELECT id FROM analysis_module WHERE report_id=:report AND id<>:module)",
                   {"report": report_id, "module": module_id})
    env.db.execute("UPDATE analysis_module SET status='completed' "
                   "WHERE report_id=:report AND id<>:module",
                   {"report": report_id, "module": module_id})
    env.db.execute("UPDATE analysis_report SET status='completed' WHERE id=:id", {"id": report_id})
    with env.engine.begin() as connection:
        add_source(connection, runtime.report["project_id"], "附件甲：开标日期为2026年12月1日。")
    service = create_analysis_service(env.engine, 1, ConfigRegistry(env.engine))
    service.retry_report(report_id, module_keys=[KEY], mode="resume",
                         max_output_tokens=None, timeout_seconds=None)
    prepared = test_deepagents_runtime.worker.prepare_report(env.db, env.db.report(report_id))
    assert prepared is not None
    current_report, sources = prepared
    latest = env.db.rows("SELECT * FROM agent_module_run WHERE module_id=:id "
                         "ORDER BY attempt DESC LIMIT 1", {"id": module_id})[0]
    current = AgentRuntime(env.db, current_report, latest, sources)
    assert current.claim()
    try:
        current_state = current.run["state"]
        signature = source_signature(current_report["source_snapshot"]
                                     + current_report["reference_snapshot"])
        current_state["quality_input_signature"] = signature
        current_state["authorized_sources"] = sources
        attachment = next(source for source in sources if source["source_id"] != row["source_id"])
        evidence = env.db.read_chunk_window(attachment, 0, 1).rows[0]
        seen = current_state["research"]["seen"]
        seen[evidence["block_id"]] = evidence
        book = DraftWorkspace(current_state, seen, KEY)
        accepted = book.save_records([{
            "kind": "fact", "group": "项目基本信息",
            "content": {"字段": "开标日期", "内容": "2026年12月1日"},
            "scope": {"kind": "common"}, "block_ids": [evidence["block_id"]],
        }], "draft")["accepted"][0]
        book.record_review([{
            "record_id": accepted["id"], "version": accepted["version"], "status": "passed",
            "reason": "已对照新附件核对开标日期", "block_ids": [evidence["block_id"]],
        }], [], "review")
        assert book.review_current(accepted["id"])
        if status == "partial":
            current_state["quality_status"] = "needs_review"
        current.save(current_state)
        current.finish(status, state=current_state)
    finally:
        current.release()
    env.db.execute("UPDATE analysis_report SET status=:status WHERE id=:id",
                   {"id": report_id, "status": status})
    service.retry_report(report_id, module_keys=[KEY], mode="resume",
                         max_output_tokens=None, timeout_seconds=None)
    runs = env.db.rows("SELECT * FROM agent_module_run WHERE module_id=:id ORDER BY attempt",
                       {"id": module_id})
    assert [run["attempt"] for run in runs] == [1, 2, 3]
    assert runs[1]["state"] == current_state
    carried = runs[-1]["state"]
    assert carried["quality_input_signature"] == signature
    assert carried["staged_items"] == current_state["staged_items"]
    assert carried["agent_workspace"]["reviews"] == current_state["agent_workspace"]["reviews"]
    assert not carried["agent_workspace"]["finalized"]
    assert DraftWorkspace(carried, carried["research"]["seen"], KEY).review_current(accepted["id"])
    module = next(module for module in env.db.report_modules(report_id)
                  if module["id"] == module_id)
    assert module["items"] == formal["items"]
    assert module["business_data"] == formal["business_data"]


def test_local_restart_keeps_other_modules_new_input_signal_in_real_postgres(env):

    runtime = prepared_runtime(env)
    report_id = runtime.report["id"]
    modules = env.db.report_modules(report_id)
    first = next(row for row in modules if row["module_key"] == KEY)
    other = next(row for row in modules if row["id"] != first["id"])
    old_signature = source_signature(runtime.report["source_snapshot"]
                                     + runtime.report["reference_snapshot"])
    state = agent_state_with_notes()
    state["quality_input_signature"] = old_signature
    state["agent_workspace"]["finalized"] = True
    # 不调用供应商，模拟两专题已确认缺件；其他专题已完成，避免混入无关补跑。
    env.db.execute("UPDATE agent_module_run SET status='completed' WHERE module_id IN "
                   "(SELECT id FROM analysis_module WHERE report_id=:id)",
                   {"id": report_id})
    env.db.execute("UPDATE analysis_module SET status='completed',"
                   "business_data=CAST(:business AS JSONB) WHERE report_id=:id",
                   {"id": report_id, "business": json.dumps({"quality_status": "verified"})})
    for module in (first, other):
        env.db.execute("UPDATE analysis_module SET business_data=CAST(:business AS JSONB) "
                       "WHERE id=:id", {"id": module["id"], "business": json.dumps({
                           "quality_status": "needs_input",
                           "quality_input_signature": old_signature})})
        env.db.execute("UPDATE agent_module_run SET state=CAST(:state AS JSONB) "
                       "WHERE module_id=:id", {"id": module["id"], "state": json.dumps(state)})
    env.db.execute("UPDATE analysis_report SET status='completed' WHERE id=:id",
                   {"id": report_id})
    with env.engine.begin() as connection:
        add_source(connection, runtime.report["project_id"], "附件甲：项目名称为测试项目。")
    service = create_analysis_service(env.engine, 1, ConfigRegistry(env.engine))
    service.retry_report(report_id, module_keys=[KEY], mode="restart",
                         max_output_tokens=None, timeout_seconds=None)
    report = env.db.report(report_id)
    assert len(report["source_snapshot"]) == 2
    # 模拟所选专题处理完新附件，释放执行锁条件后核对另一专题的页面及补跑契约。
    env.db.execute("UPDATE agent_module_run SET status='completed' WHERE module_id=:id",
                   {"id": first["id"]})
    env.db.execute("UPDATE analysis_module SET status='completed',"
                   "business_data=CAST(:business AS JSONB) WHERE id=:id", {
                       "id": first["id"], "business": json.dumps({
                           "quality_status": "verified", "quality_input_signature":
                           source_signature(report["source_snapshot"]
                                            + report["reference_snapshot"]),
                       })})
    env.db.execute("UPDATE analysis_report SET status='completed' WHERE id=:id",
                   {"id": report_id})
    visible = service.get_report(report_id)
    assert visible["stale"] is False
    assert next(row for row in visible["modules"] if row["id"] == other["id"])["input_changed"]
    assert not next(row for row in visible["modules"] if row["id"] == first["id"])["input_changed"]
    service.retry_report(report_id, module_keys=[], mode="resume",
                         max_output_tokens=None, timeout_seconds=None)
    latest = env.db.rows("SELECT * FROM agent_module_run WHERE module_id=:id "
                         "ORDER BY attempt DESC LIMIT 1", {"id": other["id"]})[0]
    assert latest["attempt"] == 2 and latest["state"]["execution_mode"] == "resume"
    assert not latest["state"]["agent_workspace"]["finalized"]
