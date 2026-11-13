"""LLM 供应商、模型、功能绑定与调用账本的数据库访问。

本模块只执行 SQL、加锁和事务提交，不判断“能否删除”“是否需要重测”等业务规则。
需要跨多条语句保持一致的场景通过 ``LlmTransaction`` 完成，服务层不会直接持有
SQLAlchemy ``Connection``。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Connection,
    Engine,
    delete,
    exists,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from tender.adapters.pg.models import (
    KnowledgeCollection,
    KnowledgeIndex,
    KnowledgeSource,
    LlmCallLog,
    LlmFeature,
    LlmFeatureModel,
    LlmModel,
    LlmProvider,
    LlmTest,
    ProjectFile,
)
from tender.adapters.pg.repositories.llm.model_test import maintain_model_tests
from tender.ports.repository.llm.management import RecordConflict


def cooldown_seconds() -> Any:
    """按数据库时钟计算冷却剩余秒数，避免多实例各按本机时间判断。"""
    return func.greatest(
        0,
        func.extract("epoch", LlmProvider.rate_limited_until - func.clock_timestamp()),
    ).label("rate_limit_remaining_seconds")


def test_select() -> Any:
    return (
        select(
            LlmTest.id,
            LlmTest.provider_id,
            LlmTest.model_id,
            LlmTest.capability,
            LlmTest.provider_revision,
            LlmTest.model_revision,
            LlmTest.status,
            LlmTest.latency_ms,
            LlmTest.error_message,
            LlmTest.created_at,
            LlmTest.finished_at,
            LlmTest.result,
            LlmTest.invalidated_at,
            LlmProvider.config_revision.label("current_provider_revision"),
            LlmModel.config_revision.label("current_model_revision"),
        )
        .select_from(LlmTest)
        .join(LlmProvider, LlmProvider.id == LlmTest.provider_id)
        .outerjoin(LlmModel, LlmModel.id == LlmTest.model_id)
    )


class LlmTransaction:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def lock_provider(self, provider_id: int) -> dict[str, Any] | None:
        row = (
            self.connection.execute(
                select(LlmProvider)
                .where(LlmProvider.id == provider_id, LlmProvider.deleted_at.is_(None))
                .with_for_update()
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def insert_provider(self, values: Mapping[str, Any]) -> int:
        return int(
            self.connection.execute(
                insert(LlmProvider).values(**dict(values)).returning(LlmProvider.id)
            ).scalar_one()
        )

    def update_provider(self, provider_id: int, values: Mapping[str, Any]) -> None:
        if not values:
            return
        self.connection.execute(
            update(LlmProvider)
            .where(LlmProvider.id == provider_id)
            .values(**dict(values), updated_at=func.now())
        )

    def store_provider_key(
        self, provider_id: int, ciphertext: str | None, hint: str | None
    ) -> None:
        self.connection.execute(
            update(LlmProvider)
            .where(LlmProvider.id == provider_id)
            .values(
                credential_revision=LlmProvider.credential_revision + 1,
                api_key_updated_at=func.now(),
                api_key_ciphertext=ciphertext,
                api_key_hint=hint,
            )
        )

    def bump_provider_revision(self, provider_id: int, *, config_changed: bool) -> None:
        self.connection.execute(
            update(LlmProvider)
            .where(LlmProvider.id == provider_id)
            .values(
                revision=LlmProvider.revision + 1,
                config_revision=LlmProvider.config_revision + int(config_changed),
            )
        )

    def lock_provider_models(self, provider_id: int) -> list[int]:
        return list(
            self.connection.execute(
                select(LlmModel.id)
                .where(LlmModel.provider_id == provider_id)
                .order_by(LlmModel.id)
                .with_for_update()
            ).scalars()
        )

    def index_in_use(self, model_ids: list[int]) -> bool:
        if not model_ids:
            return False
        return (
            self.connection.execute(
                select(KnowledgeIndex.id)
                .select_from(KnowledgeIndex)
                .join(KnowledgeSource, KnowledgeSource.id == KnowledgeIndex.source_id)
                .join(ProjectFile, ProjectFile.id == KnowledgeSource.project_file_id)
                .join(
                    KnowledgeCollection,
                    KnowledgeCollection.id == KnowledgeSource.collection_id,
                )
                .where(
                    KnowledgeIndex.embedding_model_id.in_(model_ids),
                    ProjectFile.deleted_at.is_(None),
                    KnowledgeCollection.deleted_at.is_(None),
                    KnowledgeIndex.status.in_(("completed", "running")),
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def provider_has_binding(self, provider_id: int) -> bool:
        return (
            self.connection.execute(
                select(LlmFeatureModel.id)
                .select_from(LlmFeatureModel)
                .join(LlmModel, LlmModel.id == LlmFeatureModel.model_id)
                .where(LlmModel.provider_id == provider_id)
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def model_has_binding(self, model_id: int) -> bool:
        return (
            self.connection.execute(
                select(LlmFeatureModel.id)
                .where(LlmFeatureModel.model_id == model_id)
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def feature_keys_for_model(self, model_id: int) -> list[str]:
        return list(
            self.connection.execute(
                select(LlmFeatureModel.feature_key).where(
                    LlmFeatureModel.model_id == model_id
                )
            ).scalars()
        )

    def soft_delete_provider_models(self, provider_id: int) -> None:
        self.connection.execute(
            update(LlmModel)
            .where(LlmModel.provider_id == provider_id)
            .values(deleted_at=func.now())
        )

    def soft_delete_provider(self, provider_id: int) -> None:
        self.connection.execute(
            update(LlmProvider)
            .where(LlmProvider.id == provider_id)
            .values(deleted_at=func.now())
        )

    def lock_model(self, model_id: int) -> dict[str, Any] | None:
        row = (
            self.connection.execute(
                select(LlmModel)
                .where(LlmModel.id == model_id, LlmModel.deleted_at.is_(None))
                .with_for_update()
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def insert_model(self, values: Mapping[str, Any]) -> int:
        return int(
            self.connection.execute(
                insert(LlmModel).values(**dict(values)).returning(LlmModel.id)
            ).scalar_one()
        )

    def insert_models_if_absent(self, rows: list[Mapping[str, Any]]) -> int:
        created = 0
        for values in rows:
            inserted = (
                self.connection.execute(
                    pg_insert(LlmModel)
                    .values(**dict(values))
                    .on_conflict_do_nothing(
                        index_elements=["provider_id", "model_id"],
                        index_where=LlmModel.deleted_at.is_(None),
                    )
                    .returning(LlmModel.id)
                )
                .scalars()
                .all()
            )
            created += len(inserted)
        return created

    def update_model(self, model_id: int, values: Mapping[str, Any]) -> None:
        if not values:
            return
        self.connection.execute(
            update(LlmModel).where(LlmModel.id == model_id).values(**dict(values))
        )

    def invalidate_model_tests(self, model_id: int) -> None:
        self.connection.execute(
            update(LlmTest)
            .where(LlmTest.model_id == model_id)
            .values(invalidated_at=func.coalesce(LlmTest.invalidated_at, func.now()))
        )

    def bump_model_revision(self, model_id: int, *, config_changed: bool) -> None:
        self.connection.execute(
            update(LlmModel)
            .where(LlmModel.id == model_id)
            .values(
                updated_at=func.now(),
                revision=LlmModel.revision + 1,
                config_revision=LlmModel.config_revision + int(config_changed),
            )
        )

    def soft_delete_model(self, model_id: int) -> None:
        self.connection.execute(
            update(LlmModel).where(LlmModel.id == model_id).values(deleted_at=func.now())
        )

    def lock_models_for_binding(
        self, model_ids: list[int], *, kind: str, require_json: bool
    ) -> set[int]:
        if not model_ids:
            return set()
        conditions = [
            LlmModel.id.in_(model_ids),
            LlmModel.deleted_at.is_(None),
            LlmProvider.deleted_at.is_(None),
            LlmModel.kind == kind,
        ]
        if require_json:
            conditions.append(
                or_(
                    LlmModel.kind != "language",
                    LlmModel.capabilities.contains(["json_output"]),
                )
            )
        return set(
            self.connection.execute(
                select(LlmModel.id)
                .select_from(LlmModel)
                .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                .where(*conditions)
                .order_by(LlmModel.id)
                .with_for_update(of=LlmModel)
            ).scalars()
        )

    def lock_feature(self, feature_key: str) -> int | None:
        return self.connection.execute(
            select(LlmFeature.revision)
            .where(LlmFeature.key == feature_key)
            .with_for_update()
        ).scalar_one_or_none()

    def replace_feature_models(self, feature_key: str, rows: list[tuple[int, int]]) -> None:
        self.connection.execute(
            delete(LlmFeatureModel).where(LlmFeatureModel.feature_key == feature_key)
        )
        for model_id, priority in rows:
            self.connection.execute(
                insert(LlmFeatureModel).values(
                    feature_key=feature_key,
                    model_id=model_id,
                    priority=priority,
                )
            )

    def update_feature(self, feature_key: str, values: Mapping[str, Any]) -> None:
        self.connection.execute(
            update(LlmFeature).where(LlmFeature.key == feature_key).values(**dict(values))
        )

    def bump_feature_revision(self, feature_key: str) -> None:
        self.connection.execute(
            update(LlmFeature)
            .where(LlmFeature.key == feature_key)
            .values(revision=LlmFeature.revision + 1, updated_at=func.now())
        )

    def begin_test(self, row: Mapping[str, Any], capability: str, *, is_model: bool) -> int:
        call_id = None
        if is_model:
            call_id = self.connection.execute(
                insert(LlmCallLog)
                .values(
                    provider_id=row["provider_id"],
                    model_id=row["id"],
                    purpose="test",
                    status="running",
                    latency_ms=0,
                    provider_name_snapshot=row["provider_name"],
                    model_name_snapshot=row["display_name"],
                    model_key_snapshot=row["model_id"],
                )
                .returning(LlmCallLog.id)
            ).scalar_one()
        test_id = int(
            self.connection.execute(
                insert(LlmTest)
                .values(
                    provider_id=row["provider_id"] if is_model else row["id"],
                    model_id=row["id"] if is_model else None,
                    capability=capability,
                    provider_revision=row["provider_config_revision"]
                    if is_model
                    else row["config_revision"],
                    model_revision=row["config_revision"] if is_model else None,
                    timeout_seconds=float(row.get("timeout_seconds", 90)),
                    heartbeat_at=func.now() if is_model and row.get("kind") == "language" else None,
                    call_log_id=call_id,
                )
                .returning(LlmTest.id)
            ).scalar_one()
        )
        entity = LlmModel if is_model else LlmProvider
        values: dict[str, Any] = {
            "last_test_id": test_id,
            "last_test_status": "running",
            "last_test_error": None,
            "last_test_config_revision": row["config_revision"],
        }
        if is_model:
            values["last_test_provider_revision"] = row.get("provider_config_revision")
        self.connection.execute(
            update(entity)
            .where(
                entity.id == row["id"],
                entity.config_revision == row["config_revision"],
                func.coalesce(entity.last_test_id, 0) < test_id,
            )
            .values(**values)
        )
        return test_id

    def lock_test(self, test_id: int) -> dict[str, Any] | None:
        row = (
            self.connection.execute(select(LlmTest).where(LlmTest.id == test_id).with_for_update())
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def heartbeat_test(self, test_id: int) -> bool:
        # 只续期运行中的测试，清理后的未知状态不能被迟到心跳复活。
        return self.connection.execute(update(LlmTest).where(
            LlmTest.id == test_id, LlmTest.status == "running",
        ).values(heartbeat_at=func.now()).returning(LlmTest.id)).scalar_one_or_none() is not None

    def store_test_result(
        self,
        test_id: int,
        *,
        result: Mapping[str, Any],
        preview_data: bytes | None,
        preview_mime: str | None,
    ) -> None:
        self.connection.execute(
            update(LlmTest)
            .where(LlmTest.id == test_id)
            .values(result=dict(result), preview_data=preview_data, preview_mime=preview_mime)
        )

    def finish_test(
        self,
        row: Mapping[str, Any],
        test_id: int,
        *,
        status: str,
        error: str | None,
        latency_ms: int,
        is_model: bool,
    ) -> None:
        finished = self.connection.execute(
            update(LlmTest)
            .where(LlmTest.id == test_id, LlmTest.status == "running")
            .values(
                status=status,
                error_message=error,
                latency_ms=latency_ms,
                finished_at=func.now(),
            ).returning(LlmTest.id)
        ).scalar_one_or_none()
        if finished is None:
            return
        entity = LlmModel if is_model else LlmProvider
        values: dict[str, Any] = {
            "last_test_status": status,
            "last_test_at": func.now(),
            "last_test_error": error,
            "last_test_config_revision": row["config_revision"],
            "last_test_id": test_id,
        }
        if is_model:
            values["last_test_provider_revision"] = row.get("provider_config_revision")
        conditions = [
            entity.id == row["id"],
            entity.config_revision == row["config_revision"],
            entity.last_test_id == test_id,
            entity.deleted_at.is_(None),
        ]
        if is_model:
            conditions.append(
                exists().where(
                    LlmProvider.id == LlmModel.provider_id,
                    LlmProvider.config_revision == row.get("provider_config_revision"),
                    LlmProvider.deleted_at.is_(None),
                )
            )
        self.connection.execute(update(entity).where(*conditions).values(**values))

    def record_call(
        self,
        *,
        provider_id: int | None,
        model_id: int | None,
        feature_key: str | None,
        purpose: str,
        status: str,
        http_status: int | None,
        latency_ms: int,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        error_message: str | None,
        snapshot: Mapping[str, Any],
        vector_count: int | None,
        document_count: int | None,
        image_count: int | None,
        test_id: int | None,
    ) -> None:
        if test_id is not None:
            self.connection.execute(
                update(LlmCallLog)
                .where(
                    LlmCallLog.id
                    == select(LlmTest.call_log_id)
                    .where(LlmTest.id == test_id)
                    .scalar_subquery()
                )
                .values(
                    status=status,
                    http_status=http_status,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error_message=error_message,
                    vector_count=vector_count,
                    document_count=document_count,
                    image_count=image_count,
                )
            )
            return
        self.connection.execute(
            insert(LlmCallLog).values(
                provider_id=provider_id,
                model_id=model_id,
                feature_key=feature_key,
                purpose=purpose,
                status=status,
                http_status=http_status,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                error_message=error_message,
                provider_name_snapshot=snapshot.get("provider_name", snapshot.get("name")),
                model_name_snapshot=snapshot.get("display_name"),
                model_key_snapshot=snapshot.get("model_id"),
                vector_count=vector_count,
                document_count=document_count,
                image_count=image_count,
            )
        )


class LlmRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @contextmanager
    def transaction(self) -> Iterator[LlmTransaction]:
        try:
            with self.engine.begin() as connection:
                yield LlmTransaction(connection)
        except IntegrityError as exc:
            # 用例只识别数据冲突；数据库驱动异常不跨越仓储端口。
            raise RecordConflict() from exc

    def provider(self, provider_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(LlmProvider, cooldown_seconds()).where(
                        LlmProvider.id == provider_id,
                        LlmProvider.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def providers(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(LlmProvider, cooldown_seconds())
                    .where(LlmProvider.deleted_at.is_(None))
                    .order_by(LlmProvider.name)
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def model(self, model_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        LlmModel,
                        LlmProvider.name.label("provider_name"),
                        LlmProvider.base_url,
                        LlmProvider.api_key_ciphertext,
                        LlmProvider.protocol,
                        LlmProvider.auth_mode,
                        LlmProvider.config_revision.label("provider_config_revision"),
                        LlmProvider.enabled.label("provider_enabled"),
                    )
                    .select_from(LlmModel)
                    .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                    .where(
                        LlmModel.id == model_id,
                        LlmModel.deleted_at.is_(None),
                        LlmProvider.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def models(self, provider_id: int | None = None) -> list[dict[str, Any]]:
        statement = (
            select(
                LlmModel,
                LlmProvider.name.label("provider_name"),
                LlmProvider.enabled.label("provider_enabled"),
                LlmProvider.config_revision.label("provider_config_revision"),
                LlmProvider.protocol,
            )
            .select_from(LlmModel)
            .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
            .where(LlmModel.deleted_at.is_(None), LlmProvider.deleted_at.is_(None))
            .order_by(LlmProvider.name, LlmModel.display_name)
        )
        if provider_id is not None:
            statement = statement.where(LlmModel.provider_id == provider_id)
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def maintain_tests(self) -> None:
        maintain_model_tests(self.engine)

    def latest_tests(self, model_ids: list[int]) -> list[dict[str, Any]]:
        if not model_ids:
            return []
        latest = (
            select(func.max(LlmTest.id))
            .where(LlmTest.model_id.in_(model_ids))
            .group_by(LlmTest.model_id, LlmTest.capability)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                test_select().where(LlmTest.id.in_(latest)).order_by(LlmTest.id.desc())
            ).mappings().all()
        return [dict(row) for row in rows]

    def tests(self, model_id: int | None, limit: int) -> list[dict[str, Any]]:
        statement = test_select()
        if model_id is not None:
            statement = statement.where(LlmTest.model_id == model_id)
        with self.engine.connect() as connection:
            rows = connection.execute(
                statement.order_by(LlmTest.id.desc()).limit(limit)
            ).mappings().all()
        return [dict(row) for row in rows]

    def test(self, test_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                test_select().where(LlmTest.id == test_id)
            ).mappings().first()
        return dict(row) if row is not None else None

    def test_preview(self, test_id: int) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(LlmTest.preview_data, LlmTest.preview_mime).where(
                    LlmTest.id == test_id
                )
            ).mappings().first()
        return dict(row) if row is not None else None

    def feature_rows(self) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(
                        LlmFeatureModel.feature_key,
                        LlmFeatureModel.priority,
                        LlmModel.id.label("model_row_id"),
                        LlmModel.model_id,
                        LlmModel.display_name,
                        LlmModel.enabled,
                        LlmProvider.id.label("provider_id"),
                        LlmProvider.name.label("provider_name"),
                        LlmProvider.enabled.label("provider_enabled"),
                        LlmModel.kind,
                        LlmModel.extra_retries,
                    )
                    .select_from(LlmFeatureModel)
                    .join(LlmModel, LlmModel.id == LlmFeatureModel.model_id)
                    .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                    .where(LlmModel.deleted_at.is_(None), LlmProvider.deleted_at.is_(None))
                    .order_by(LlmFeatureModel.feature_key, LlmFeatureModel.priority)
                )
                .mappings()
                .all()
            )
            limits = {
                row["key"]: dict(row)
                for row in connection.execute(select(LlmFeature)).mappings().all()
            }
        return [dict(row) for row in rows], limits

    def calls(
        self,
        *,
        feature_key: str | None,
        model_id: int | None,
        status: str | None,
        invocation_id: UUID | None,
        limit: int,
        offset: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        conditions = []
        if feature_key is not None:
            conditions.append(LlmCallLog.feature_key == feature_key)
        if model_id is not None:
            conditions.append(LlmCallLog.model_id == model_id)
        if status is not None:
            conditions.append(LlmCallLog.status == status)
        if invocation_id is not None:
            conditions.append(LlmCallLog.invocation_id == invocation_id)
        order = (
            (LlmCallLog.request_ordinal.asc(),)
            if invocation_id
            else (LlmCallLog.created_at.desc(), LlmCallLog.id.desc())
        )
        with self.engine.connect() as connection:
            total = connection.execute(
                select(func.count()).select_from(LlmCallLog).where(*conditions)
            ).scalar_one()
            rows = (
                connection.execute(
                    select(
                        LlmCallLog,
                        func.coalesce(
                            LlmCallLog.model_name_snapshot, LlmModel.display_name
                        ).label("display_name"),
                        func.coalesce(
                            LlmCallLog.provider_name_snapshot, LlmProvider.name
                        ).label("provider_name"),
                    )
                    .select_from(LlmCallLog)
                    .outerjoin(LlmModel, LlmModel.id == LlmCallLog.model_id)
                    .outerjoin(LlmProvider, LlmProvider.id == LlmCallLog.provider_id)
                    .where(*conditions)
                    .order_by(*order)
                    .limit(limit)
                    .offset(offset)
                )
                .mappings()
                .all()
            )
        return int(total), [dict(row) for row in rows]

    def invalidate_provider_tests(self, provider_id: int) -> None:
        with self.transaction() as transaction:
            transaction.connection.execute(
                update(LlmTest)
                .where(
                    LlmTest.provider_id == provider_id,
                    LlmTest.provider_revision
                    != select(LlmProvider.config_revision)
                    .where(LlmProvider.id == LlmTest.provider_id)
                    .scalar_subquery(),
                )
                .values(invalidated_at=func.coalesce(LlmTest.invalidated_at, func.now()))
            )
