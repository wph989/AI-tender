"""为私有测试表安装当前快照结构，复用基线约束而不重放历史迁移。"""

import importlib.util
from pathlib import Path

from sqlalchemy import text


def install_data_schema(connection, *, temporary=False):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/0001_current_schema.py"
    spec = importlib.util.spec_from_file_location("current_data_schema", path)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    for table in ("analysis_data_snapshot", "analysis_record_review"):
        statement = next(sql for sql in baseline._STATEMENTS
                         if sql.startswith(f"CREATE TABLE {table} ("))
        # 私有表用自己的序列；复用公共序列会让并行用例影响彼此。
        statement = statement.replace("id bigint NOT NULL,", "id BIGSERIAL PRIMARY KEY,", 1)
        if temporary:
            statement = statement.replace("CREATE TABLE", "CREATE TEMP TABLE", 1)
        connection.execute(text(statement))
        for sql in baseline._STATEMENTS:
            if sql.startswith(("CREATE INDEX ", "CREATE UNIQUE INDEX ")) and f" ON {table} " in sql:
                connection.execute(text(sql))
