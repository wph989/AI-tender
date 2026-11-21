"""在测试私有表上验证新增迁移，避免要求先升级业务数据库。"""

import importlib.util
from pathlib import Path

from sqlalchemy import text


def install_data_schema(connection, *, temporary=False):
    api_root = Path(__file__).resolve().parents[2]
    for version in ("0011_analysis_data.py", "0023_reviewed_analysis.py"):
        path = api_root / "alembic/versions" / version
        spec = importlib.util.spec_from_file_location("data_" + path.stem, path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        for statement in migration._STATEMENTS:
            statement = statement.replace("ADD COLUMN ", "ADD COLUMN IF NOT EXISTS ")
            if temporary:
                statement = statement.replace(
                    "CREATE TABLE analysis_data_snapshot",
                    "CREATE TEMP TABLE analysis_data_snapshot",
                ).replace(
                    "CREATE TABLE analysis_record_review",
                    "CREATE TEMP TABLE analysis_record_review",
                )
            connection.execute(text(statement))
