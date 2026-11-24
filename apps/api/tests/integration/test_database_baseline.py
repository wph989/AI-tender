"""直接执行当前空库基线，验证新部署的首次运行、补跑与成功结算。"""

import importlib.util
import os
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tender.adapters.pg.repositories.analysis.runtime import AgentRunStore
from tender.adapters.pg.repositories.knowledge.store import KnowledgeStore
from tender.core.settings import database_url

pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库集成验证",
)


@pytest.fixture
def baseline():
    engine = create_engine(database_url(), connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection, connection.begin():
            schema = "test_baseline_" + uuid4().hex
            connection.execute(text(f"CREATE SCHEMA {schema}"))
            connection.execute(text(f"SET LOCAL search_path TO {schema}, public"))
            path = Path(__file__).resolve().parents[2] / "alembic/versions/0001_current_schema.py"
            spec = importlib.util.spec_from_file_location("new_database_baseline", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            # 从空命名空间执行部署基线，不能复制已经被现场修复过的 public 表来验证默认值。
            module._STATEMENTS = tuple(
                sql.replace("SCHEMA agent_runtime", f"SCHEMA {schema}_agents")
                for sql in module._STATEMENTS
            )
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
            project_id = connection.execute(text(
                "INSERT INTO project(name) VALUES ('新部署计数验证') RETURNING id",
            )).scalar_one()
            report_id = connection.execute(text("""
                INSERT INTO analysis_report(project_id, company_id, category, skill_version)
                VALUES (:project, 1, 'goods', 'baseline-test') RETURNING id
            """), {"project": project_id}).scalar_one()
            module_id = connection.execute(text("""
                INSERT INTO analysis_module(report_id, module_key, title)
                VALUES (:report, 'project_basic_info_parsing', '项目基本信息') RETURNING id
            """), {"report": report_id}).scalar_one()
            facade = SimpleNamespace(connect=lambda: nullcontext(connection))
            yield SimpleNamespace(connection=connection, schema=schema, module_id=module_id,
                                  store=KnowledgeStore(facade, 1))
            # 整笔测试事务回滚，包含所有表、序列和测试命名空间。
            connection.rollback()
    finally:
        engine.dispose()


def test_new_database_initial_and_retry_runs_count_successes(baseline):
    limits = {"max_model_calls": 5, "max_tool_calls": 5,
              "timeout_seconds": 60, "max_output_tokens": 1024}
    with baseline.store.transaction() as tx:
        tx.ensure_module_run(baseline.module_id, company_id=1, thread_id="first", limits=limits)
        tx.insert_module_run(module_id=baseline.module_id, attempt=2, thread_id="retry",
                             limits=limits, state={})
    connection = baseline.connection
    runs = connection.execute(text("""
        SELECT id, successful_model_calls, successful_tool_calls
        FROM agent_module_run ORDER BY attempt
    """)).mappings().all()
    assert len(runs) == 2
    assert all(row["successful_model_calls"] == row["successful_tool_calls"] == 0 for row in runs)
    # 复用真实结算实现：成功递增一次，失败与重复回执保持原计数。
    runtime = object.__new__(AgentRunStore)
    runtime.run = {"id": runs[0]["id"]}
    for kind, status in (("model", "ok"), ("tool", "ok"), ("model", "error")):
        key = kind + ":" + status
        connection.execute(text("""
            INSERT INTO agent_call_attempt(run_id, kind, call_key, status)
            VALUES (:run, :kind, :key, 'running')
        """), {"run": runtime.run["id"], "kind": kind, "key": key})
        assert runtime._settle(connection, kind, key, status, {})
        assert not runtime._settle(connection, kind, key, status, {})
    counters = connection.execute(text("""
        SELECT successful_model_calls, successful_tool_calls FROM agent_module_run ORDER BY attempt
    """)).all()
    assert counters == [(1, 1), (0, 0)]


@pytest.mark.parametrize("column", ["successful_model_calls", "successful_tool_calls"])
def test_new_database_rejects_null_success_counts(baseline, column):
    definitions = baseline.connection.execute(text("""
        SELECT is_nullable, column_default FROM information_schema.columns
        WHERE table_schema=:schema AND table_name='agent_module_run' AND column_name=:column
    """), {"schema": baseline.schema, "column": column}).one()
    assert definitions == ("NO", "0")
    # 单独的保存点验证非空约束，不让预期错误中止外层空库测试事务。
    with pytest.raises(IntegrityError) as error, baseline.connection.begin_nested():
        baseline.connection.execute(text(f"""
            INSERT INTO agent_module_run(module_id, company_id, thread_id, limits, {column})
            VALUES (:module, 1, 'null-probe', '{{}}'::jsonb, NULL)
        """), {"module": baseline.module_id})
    assert error.value.orig.sqlstate == "23502"
