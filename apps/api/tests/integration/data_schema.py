"""在测试私有表上验证新增迁移，避免要求先升级业务数据库。"""

import importlib.util
from pathlib import Path

from sqlalchemy import text


def install_data_schema(connection, *, temporary=False):
    path = Path(__file__).resolve().parents[2] / "alembic/versions/0011_analysis_data.py"
    spec = importlib.util.spec_from_file_location("data_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    for statement in migration._STATEMENTS:
        statement = statement.replace("ADD COLUMN ", "ADD COLUMN IF NOT EXISTS ")
        if temporary:
            statement = statement.replace(
                "CREATE TABLE analysis_data_snapshot", "CREATE TEMP TABLE analysis_data_snapshot",
            )
        connection.execute(text(statement))
