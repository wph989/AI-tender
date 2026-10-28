"""离线执行真实元素写入，并模拟 PostgreSQL 单语句参数上限。"""

import sqlite3
from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import Integer, MetaData, create_engine, select
from sqlalchemy.sql import Insert, Select, Update

from tender.adapters.pg.models import Element
from tender.adapters.pg.repositories.documents.pipeline import DocumentPipelineRepository
from tender.application.documents.middle_json import NormalizedElement
from tender.ports.documents.parser import MiddleJson, ParseJobStatus
from tender.worker.documents import tasks


@pytest.mark.parametrize("element_count", [0, 2, 4096])
def test_poll_parse_persists_elements_within_parameter_limit(monkeypatch, element_count):
    repository = DocumentPipelineRepository(Mock(), Mock())
    monkeypatch.setattr(tasks, "_repository", repository)
    elements = [
        NormalizedElement(
            page_no=1,
            order_no=ordinal,
            anchor=f"p1b{ordinal}",
            element_type="title" if ordinal == 1 else "text",
            level=1 if ordinal == 1 else None,
            parent_index=None if ordinal == 1 else 0,
            bbox=None,
            text=f"段落 {ordinal}",
            html=None,
            source="native",
            continues_prev=False,
            mineru_locator=f"pages/0/blocks/{ordinal - 1}",
        )
        for ordinal in range(1, element_count + 1)
    ]
    job = {
        "id": "parse-test",
        "status": "running",
        "stage": "parsing",
        "version_id": 11,
        "run_id": 12,
        "project_id": 13,
        "config_snapshot": {},
        "version_page_count": 1,
    }
    monkeypatch.setattr(repository, "job", lambda *_: job)
    monkeypatch.setattr(
        tasks,
        "_runtime_values",
        lambda *_: {
            "job.timeout.parse_minutes": 10,
            "job.poll.max_attempts": 10,
        },
    )
    monkeypatch.setattr(repository, "execution_start", lambda *_: datetime.now(UTC))
    monkeypatch.setattr(tasks._locks, "lock", lambda *_, **__: nullcontext(True))
    monkeypatch.setattr(tasks, "_store", Mock(return_value=Mock()))
    monkeypatch.setattr(tasks, "normalize_middle_json", Mock(return_value=elements))
    monkeypatch.setattr(
        tasks,
        "_poll",
        AsyncMock(
            return_value=(
                ParseJobStatus("remote-test", "completed", None, True),
                MiddleJson(b'{"pages": [{}]}', {"pages": [{}]}, "2.0", "test"),
            )
        ),
    )

    database = create_engine("sqlite://")
    element_table = Element.__table__.to_metadata(MetaData())
    # SQLite 仅对 INTEGER 主键自增；只调整测试副本，不改业务模型。
    element_table.c.id.type = Integer()
    element_table.create(database)
    try:
        with database.begin() as persisted:
            # SQLite 默认上限更高，主动压到 PG 的 65535，捕获整批拼成一条 SQL 的回归。
            persisted.connection.driver_connection.setlimit(
                sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 65535
            )

            def execute(statement, parameters=None):
                if isinstance(statement, (Insert, Update)):
                    is_element = statement.table.name == "element"
                else:
                    is_element = isinstance(statement, Select) and any(
                        table.name == "element" for table in statement.get_final_froms()
                    )
                if is_element:
                    return persisted.execute(statement, parameters)
                # 非元素查询不连接业务库，项目类型固定为知识库，避免触发后续模型任务。
                result = Mock(rowcount=1)
                result.mappings.return_value.all.return_value = []
                result.mappings.return_value.first.return_value = job
                result.scalar_one.return_value = "knowledge"
                return result

            connection = Mock()
            connection.execute.side_effect = execute
            engine = Mock()
            engine.begin.side_effect = lambda: nullcontext(connection)
            engine.connect.side_effect = lambda: nullcontext(connection)
            repository.engine = engine

            tasks.poll_parse.run(job["id"])

            rows = persisted.execute(select(Element).order_by(Element.order_no)).mappings().all()
            assert len(rows) == element_count
            for index, row in enumerate(rows):
                assert row["version_id"] == 11
                assert row["run_id"] == 12
                assert row["anchor"] == elements[index].anchor
                assert row["text"] == elements[index].text
                assert row["parent_id"] == (None if index == 0 else rows[0]["id"])
            finished = {
                call.args[0].table.name: call.args[0].compile().params["status"]
                for call in connection.execute.call_args_list
                if isinstance(call.args[0], Update) and "status" in call.args[0].compile().params
            }
            assert finished == {"parse_run": "completed", "job": "completed"}
    finally:
        database.dispose()
