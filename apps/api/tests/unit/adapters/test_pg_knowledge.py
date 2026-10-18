"""使用真实 Connection 结果验证列映射，避免替身掩盖 ORM 实体与扁平行的差异。"""

from datetime import datetime

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, Table, create_engine, insert

from tender.adapters.pg.models import KnowledgeCollection
from tender.adapters.pg.repositories.knowledge.store import KnowledgeStore


@pytest.fixture
def collection_db():
    database = create_engine("sqlite://")
    metadata = MetaData()
    projects = Table(
        "project",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("deleted_at", DateTime),
    )
    files = Table(
        "project_file",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("project_id", Integer),
        Column("deleted_at", DateTime),
    )
    KnowledgeCollection.__table__.to_metadata(metadata)
    metadata.create_all(database)
    try:
        yield database, projects, files
    finally:
        database.dispose()


def test_collection_overview_empty(collection_db):
    database, _, _ = collection_db
    assert KnowledgeStore(database, 1).collection_overview() == []


def test_collection_overview_returns_columns_counts_and_scoped_rows(collection_db):
    database, projects, files = collection_db
    created_at = datetime(2026, 10, 14)
    collections = [
        {
            "id": identifier,
            "company_id": 2 if identifier == 4 else 1,
            "name": f"知识库 {identifier}",
            "purpose": "历史资料",
            "upload_project_id": identifier,
            "is_project": identifier == 2,
            "created_at": created_at,
            "deleted_at": created_at if identifier == 5 else None,
        }
        for identifier in range(1, 7)
    ]
    with database.begin() as connection:
        connection.execute(
            insert(projects),
            [
                {"id": identifier, "deleted_at": created_at if identifier == 6 else None}
                for identifier in range(1, 7)
            ],
        )
        connection.execute(insert(KnowledgeCollection), collections)
        connection.execute(
            insert(files),
            [
                {"id": 1, "project_id": 1, "deleted_at": None},
                {"id": 2, "project_id": 1, "deleted_at": None},
                {"id": 3, "project_id": 3, "deleted_at": None},
                {"id": 4, "project_id": 1, "deleted_at": created_at},
            ],
        )

    overview = KnowledgeStore(database, 1).collection_overview()

    assert overview == [
        {**collections[2], "file_count": 1},
        {**collections[0], "file_count": 2},
        {**collections[1], "file_count": 0},
    ]
