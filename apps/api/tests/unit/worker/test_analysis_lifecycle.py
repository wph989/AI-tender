"""异常收尾不能让控制器持续续租、其余模块永远等不到配额。"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from tender.application.analysis import execution as deep_analysis
from tender.application.analysis.contract import RUNTIME_VERSION
from tender.ports.repository.knowledge.store import KnowledgeStore
from tender.worker.knowledge import tasks as knowledge


@pytest.fixture
def executor():
    return deep_analysis.AnalysisExecutor(
        None, model_factory=Mock(), embedding_gateway=Mock(), rerank_gateway=Mock(),
        checkpoints=Mock(),
    )


@pytest.fixture
def controller(monkeypatch, executor):
    report = {"id": 16, "coverage": {}}
    db = Mock(spec=KnowledgeStore)
    executor.db = db
    db.report_active_modules.return_value = [{"id": 930}, {"id": 931}]
    monkeypatch.setattr(deep_analysis, "prepare_report", lambda *_: (report, []))
    monkeypatch.setattr(deep_analysis, "check_report_access", lambda *_: None)
    publish = Mock()
    monkeypatch.setattr(deep_analysis, "publish_data_snapshot", publish)
    return db, report, publish


@pytest.mark.parametrize("broken_step", ["abandon", "release"])
def test_cleanup_failure_stops_controller_and_releases_waiters(
    controller, monkeypatch, broken_step, executor
):
    db, report, publish = controller
    released = set()
    cleanup_error = f"{broken_step}：运行收尾失败"

    class Runtime:
        def __init__(self, db, report, module, sources):
            self.run_id = module["id"]
            # 领取逻辑会读取运行时限；夹具需到达预期的收尾故障，不能先因缺少状态退出。
            self.run = {}

        def check_access(self):
            pass

        def claim(self):
            if self.run_id == 930:
                raise RuntimeError("成果写入失败")
            return False

        def abandon(self, status, error):
            if self.run_id == 930 and broken_step == "abandon":
                raise RuntimeError(cleanup_error)
            assert status in {"failed", "canceled"}

        def release(self):
            released.add(self.run_id)
            if self.run_id == 930 and broken_step == "release":
                raise RuntimeError(cleanup_error)

    monkeypatch.setattr(deep_analysis, "AgentRuntime", Runtime)

    async def scenario():
        # 外层超时仅用于暴露旧控制器的永久等待，不能充当业务任务的退出机制。
        await asyncio.wait_for(executor.analyze_report(report), timeout=3)

    asyncio.run(scenario())
    db.finish_task.assert_called_once_with("report", 16, "failed", cleanup_error)
    db.finish_report.assert_not_called()
    assert released == {930, 931}
    publish.assert_called_once_with(db, 16)


def test_handled_module_failure_allows_other_modules_to_complete(controller, monkeypatch, executor):
    db, report, publish = controller
    rows = [
        {"id": 930, "status": "pending", "items": []},
        {"id": 931, "status": "pending", "items": []},
    ]
    db.report_modules.return_value = rows

    async def execute(report, module, sources):
        if module["id"] == 930:
            rows[0]["status"] = "failed"
            return
        await asyncio.sleep(0.01)
        rows[1]["status"] = "completed"

    monkeypatch.setattr(executor, "execute_module", execute)
    asyncio.run(executor.analyze_report(report))
    db.finish_task.assert_not_called()
    db.finish_report.assert_called_once_with(16, status="partial", summary=[], error=None)
    publish.assert_called_once_with(db, 16)


@pytest.mark.parametrize("missing", ["column", "table"])
def test_schema_guard_runs_before_loading_full_report(monkeypatch, missing):
    db = Mock(spec=KnowledgeStore)
    db.accessible_report_status.return_value = "running"
    db.schema_columns.return_value = {("analysis_module", "business_data")}
    db.schema_tables.return_value = {"analysis_data_snapshot"}
    if missing == "table":
        db.schema_columns.return_value.add(("analysis_report", "derived_lot_ids"))
        db.schema_tables.return_value.clear()
    db.report_for_analysis.side_effect = RuntimeError("ORM 全列查询访问了未迁移的列")
    monkeypatch.setattr(knowledge, "_store", lambda: db)

    asyncio.run(knowledge._analyze_project(16))

    db.report_for_analysis.assert_not_called()
    db.finish_task.assert_called_once()
    assert db.finish_task.call_args.args[:3] == ("report", 16, "failed")
    assert "请先执行数据库迁移" in db.finish_task.call_args.args[3]


@pytest.mark.parametrize("status", [None, "completed", "failed", "canceled"])
def test_schema_guard_does_not_touch_inaccessible_or_terminal_reports(monkeypatch, status):
    db = Mock(spec=KnowledgeStore)
    db.accessible_report_status.return_value = status
    db.snapshot_pending.return_value = False
    monkeypatch.setattr(knowledge, "_store", lambda: db)

    asyncio.run(knowledge._analyze_project(16))

    db.report_for_analysis.assert_not_called()
    db.schema_columns.assert_not_called()
    db.finish_task.assert_not_called()


def test_ready_schema_allows_analysis(monkeypatch):
    from tender.application.shared.schema_guard import REQUIRED_COLUMNS, REQUIRED_TABLES

    db = Mock(spec=KnowledgeStore)
    db.accessible_report_status.return_value = "running"
    db.schema_columns.return_value = set(REQUIRED_COLUMNS)
    db.schema_tables.return_value = set(REQUIRED_TABLES)
    report = {"id": 16, "status": "running", "runtime_version": RUNTIME_VERSION}
    db.report_for_analysis.return_value = report
    analyze = AsyncMock()
    monkeypatch.setattr(knowledge, "_store", lambda: db)
    monkeypatch.setattr(deep_analysis.AnalysisExecutor, "analyze_report", analyze)

    asyncio.run(knowledge._analyze_project(16))

    analyze.assert_awaited_once_with(report)
    db.finish_task.assert_not_called()
