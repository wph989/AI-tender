"""完整迁移链验证旧抽取数据退役，全部操作在事务内的独立 schema 回滚。"""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from tender.core.settings import database_url

pytestmark = pytest.mark.skipif(os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要数据库")


def test_retirement_preserves_parsing_models_and_call_history():
    engine = create_engine(database_url(), connect_args={"connect_timeout": 8})
    schema = "retire_test_" + uuid4().hex
    try:
        with engine.connect() as connection, connection.begin() as transaction:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))
            root = Path(__file__).resolve().parents[2] / "alembic/versions"
            for path in sorted(root.glob("*.py")):
                spec = importlib.util.spec_from_file_location(path.stem, path)
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)
                if path.name.startswith("0013_"):
                    break
                for statement in migration._STATEMENTS:
                    connection.execute(
                        text(
                            statement.replace(
                                "SCHEMA agent_runtime",
                                f"SCHEMA {schema}_agents",
                            )
                        )
                    )
            # 保留真实外键：存在历史数据才能证明删表顺序及关联列清理有效。
            for statement in (
                "INSERT INTO project(id,name) VALUES (1,'迁移测试项目')",
                "INSERT INTO document(id,title) VALUES (1,'测试标书')",
                """INSERT INTO document_version
                    (id,document_id,version_no,sha256,mime,size_bytes,original_key,pdf_key,
                     pdf_sha256,is_converted)
                    VALUES (1,1,1,'abc','application/pdf',10,'o','p','abc',false)""",
                """INSERT INTO project_file(id,project_id,version_id,role,display_name)
                    VALUES (1,1,1,'main','测试标书')""",
                """INSERT INTO parse_run(id,version_id,provider_version,tier,schema_version,status)
                    VALUES (1,1,'fixture','basic','1','completed')""",
                """INSERT INTO field_instance(id,version_id,field_key) VALUES (1,1,'warranty')""",
                """INSERT INTO extraction
                    (id,instance_id,version_id,run_id,attempt_no,trigger,field_key,status,strategy)
                    VALUES (1,1,1,1,1,'first','warranty','auto','llm')""",
                "UPDATE field_instance SET current_extraction_id=1 WHERE id=1",
                """INSERT INTO regression_run(id,release_id,gold_total,pass_count,fail_count)
                    VALUES (1,1,0,0,0)""",
                "UPDATE config_release SET regression_run_id=1 WHERE id=1",
                "INSERT INTO llm_provider(id,name,base_url) VALUES (1,'测试供应商','http://test')",
                """INSERT INTO llm_model(id,provider_id,model_id,display_name)
                    VALUES (1,1,'fixture','测试模型')""",
                """INSERT INTO llm_feature_model(feature_key,model_id,priority)
                    VALUES ('extract',1,1),('retry',1,1),('analysis',1,1)""",
                """INSERT INTO llm_call_log(id,provider_id,model_id,feature_key,purpose,status,
                    latency_ms,extraction_id) VALUES (1,1,1,'extract','历史抽取','ok',100,1)""",
                """INSERT INTO job(id,project_id,project_file_id,stage,status)
                    VALUES ('extract-active',1,1,'extracting','running'),
                           ('export-active',1,1,'exporting','pending'),
                           ('extract-done',1,1,'extracting','completed'),
                           ('parse-active',1,1,'parsing','running')""",
            ):
                connection.execute(text(statement))
            for statement in migration._STATEMENTS:
                connection.execute(text(statement))
            tables = set(
                connection.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema=:schema"
                    ),
                    {"schema": schema},
                ).scalars()
            )
            assert not tables & {
                "field_instance",
                "extraction",
                "evidence",
                "review_task",
                "review_action",
                "extraction_conflict",
                "gold_item",
                "regression_run",
            }
            assert {
                "parse_run",
                "element",
                "analysis_report",
                "analysis_module",
                "llm_call_log",
            } <= tables
            columns = set(
                connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema=:schema"
                    ),
                    {"schema": schema},
                ).scalars()
            )
            assert not {"extraction_id", "regression_run_id"} & columns
            assert connection.execute(
                text("SELECT feature_key FROM llm_feature_model")
            ).scalars().all() == ["analysis"]
            assert not connection.execute(
                text("SELECT key FROM llm_feature WHERE key IN ('extract','retry')")
            ).all()
            assert not connection.execute(
                text("SELECT key FROM config_item WHERE key LIKE 'extract.%'")
            ).all()
            assert connection.execute(text("SELECT count(*) FROM parse_run")).scalar_one() == 1
            assert (
                connection.execute(text("SELECT feature_key FROM llm_call_log")).scalar_one()
                == "extract"
            )
            assert connection.execute(text("SELECT count(*) FROM config_release")).scalar_one() == 1
            jobs = dict(connection.execute(text("SELECT id,status FROM job")).all())
            assert jobs == {
                "extract-active": "canceled",
                "export-active": "canceled",
                "extract-done": "completed",
                "parse-active": "running",
            }
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM job WHERE status='canceled' "
                        "AND error_code='feature_retired'"
                        " AND finished_at IS NOT NULL"
                    )
                ).scalar_one()
                == 2
            )
            transaction.rollback()
    finally:
        engine.dispose()
