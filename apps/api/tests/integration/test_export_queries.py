"""在连接内临时表上执行真实 PostgreSQL 导出查询，覆盖复核派生状态与筛选。

显式开启 TENDER_RUN_DB_TESTS=1 才连接本地配置库；临时表遮蔽同名业务表，
事务回滚后即消失，验证查询歧义时不读取或改写真实标书。
"""

from __future__ import annotations

import os
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from tender.api.exports import _export_rows
from tender.core import settings
from tender.worker import exports as worker_exports

pytestmark = pytest.mark.skipif(
    os.environ.get("TENDER_RUN_DB_TESTS") != "1", reason="需要显式开启 PostgreSQL 集成验证"
)


@pytest.fixture
def export_connection():
    engine = create_engine(settings.database_url())
    try:
        with engine.connect() as connection, connection.begin() as transaction:
            for table in (
                "extraction", "field_instance", "lot", "extraction_conflict", "review_action",
                "document", "document_version", "project_file", "evidence",
            ):
                # 只复制列形状：临时数据不需要建立与真实业务表相连的外键。
                connection.execute(text(
                    f"CREATE TEMP TABLE {table} ON COMMIT DROP AS "
                    f"SELECT * FROM public.{table} WITH NO DATA"
                ))
            for statement in (
                "INSERT INTO document(id,company_id) VALUES (1,1)",
                "INSERT INTO document_version(id,document_id) VALUES (1,1)",
                """INSERT INTO project_file(id,project_id,version_id,display_name,role,sort_no)
                   VALUES (1,1,1,'联调.pdf','main',0)""",
                """INSERT INTO field_instance(id,version_id,field_key)
                   VALUES (1,1,'budget_amount'),(2,1,'project_name'),(3,1,'tender_no')""",
                """INSERT INTO extraction(id,instance_id,version_id,field_key,group_key,
                       value_text,status,is_current)
                   VALUES (1,1,1,'budget_amount','basic_info','120000','need_review',true),
                          (2,2,1,'project_name','basic_info','项目','auto',true),
                          (3,3,1,'tender_no','basic_info','T-1','need_review',true)""",
                """INSERT INTO review_action(id,instance_id,attempt_id,action)
                   VALUES (1,1,1,'confirm'),(2,2,2,'reject')""",
            ):
                connection.execute(text(statement))
            yield connection
            transaction.rollback()
    finally:
        engine.dispose()


@pytest.mark.parametrize("include,expected", [
    ("all", ["verified", "rejected", "need_review"]),
    ("verified", ["verified"]),
    ("review", ["need_review"]),
])
def test_sync_and_worker_export_review_status(export_connection, monkeypatch, include, expected):
    monkeypatch.setattr(settings, "company_id", lambda: 1)
    monkeypatch.setattr(worker_exports, "_engine", SimpleNamespace(
        connect=lambda: nullcontext(export_connection)
    ))
    sync_rows = _export_rows(export_connection, 1, 1, None, include, 100)
    queued_rows = worker_exports._export_rows({
        "project_id": 1, "config_snapshot": {"include": include},
    })
    assert [row["复核状态"] for row in sync_rows] == expected
    assert queued_rows == sync_rows
