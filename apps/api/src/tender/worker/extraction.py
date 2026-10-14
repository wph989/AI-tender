"""字段抽取 worker：结果与任务进度按字段同事务提交，重投递可跳过已完成字段。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    case,
    exists,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import aliased

from tender.adapters.pg.locks import acquire_xact_lock, release_lock, try_acquire_lock
from tender.adapters.pg.models import (
    Element,
    Evidence,
    Extraction,
    ExtractionConflict,
    FieldInstance,
    Job,
    LlmCallLog,
    LlmFeature,
    LlmFeatureModel,
    LlmModel,
    LlmProvider,
    Lot,
    Project,
    ProjectFile,
    ReviewTask,
)
from tender.adapters.pg.session import create_pg_engine
from tender.adapters.redis_cache import RedisConfigCache
from tender.application.agent import extract_field
from tender.application.extraction import build_anchor_document, identify_lots
from tender.application.fields import FIELD_BY_KEY, FIELDS
from tender.application.llm_routing import CallRecord, ModelCandidate, RoutingModel
from tender.config.registry import ConfigRegistry
from tender.core import settings
from tender.core.di import create_model_gateway
from tender.core.secrets import SecretKeyUnavailable, decrypt_secret
from tender.domain.errors import ExtractionFailed, ExtractionUnavailable
from tender.worker.celery_app import celery_app

_engine = create_pg_engine()
_config_registry_instance: ConfigRegistry | None = None


def _config_registry() -> ConfigRegistry:
    """进程内单例：任务创建时读一次活动配置（走 Redis 缓存），不必每次新建连接。"""
    global _config_registry_instance
    if _config_registry_instance is None:
        _config_registry_instance = ConfigRegistry(_engine, RedisConfigCache())
    return _config_registry_instance


_TERMINAL = frozenset({"completed", "partial", "failed", "canceled"})


@contextmanager
def _advisory_lock(lock_key: str) -> Iterator[bool]:
    with _engine.connect() as connection:
        acquired = try_acquire_lock(connection, lock_key)
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                release_lock(connection, lock_key)
                connection.commit()


def _load_job(job_id: str) -> Mapping[str, Any] | None:
    with _engine.connect() as connection:
        row = (
            connection.execute(
                select(
                    Job,
                    ProjectFile.display_name,
                    Project.company_id.label("project_company_id"),
                    Project.deleted_at.label("project_deleted_at"),
                )
                .select_from(Job)
                .join(ProjectFile, ProjectFile.id == Job.project_file_id)
                .join(Project, Project.id == Job.project_id)
                .where(Job.id == job_id)
            )
            .mappings()
            .first()
        )
    return row


def _load_elements(version_id: int, run_id: int) -> list[dict[str, Any]]:
    with _engine.connect() as connection:
        rows = (
            connection.execute(
                select(
                    Element.id,
                    Element.run_id,
                    Element.page_no,
                    Element.order_no,
                    Element.anchor,
                    Element.type,
                    Element.level,
                    Element.parent_id,
                    Element.bbox_x0,
                    Element.bbox_y0,
                    Element.bbox_x1,
                    Element.bbox_y1,
                    Element.text,
                    Element.html,
                    Element.source,
                    Element.continues_prev,
                )
                .where(Element.version_id == version_id, Element.run_id == run_id)
                .order_by(Element.page_no, Element.order_no)
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def _upsert_lots(project_id: int, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    detected = identify_lots(elements)
    with _engine.begin() as connection:
        for candidate in detected:
            if candidate.confidence < 0.75:
                continue
            existing = connection.execute(
                select(Lot.id)
                .where(Lot.project_id == project_id, Lot.code == candidate.code)
                .limit(1)
            ).scalar_one_or_none()
            if existing is None:
                next_sort = int(
                    connection.execute(
                        select(func.coalesce(func.max(Lot.sort_no), -1) + 1).where(
                            Lot.project_id == project_id
                        )
                    ).scalar_one()
                )
                connection.execute(
                    insert(Lot).values(
                        project_id=project_id,
                        code=candidate.code,
                        name=candidate.name,
                        sort_no=next_sort,
                    )
                )
        rows = (
            connection.execute(
                select(Lot.id, Lot.code, Lot.name)
                .where(Lot.project_id == project_id)
                .order_by(Lot.sort_no, Lot.id)
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def _field_keys(snapshot: Mapping[str, Any]) -> list[str]:
    requested = snapshot.get("field_keys")
    if isinstance(requested, list):
        keys = [key for key in requested if isinstance(key, str) and key in FIELD_BY_KEY]
        return list(dict.fromkeys(keys))
    return [field.key for field in FIELDS]


def _log_call(record: CallRecord) -> None:
    data = asdict(record)
    # 首次先插入 running；返回后只补写同一请求，不新增第二条调用账。
    insert_call = pg_insert(LlmCallLog).values(**data)
    with _engine.begin() as c:
        c.execute(
            insert_call.on_conflict_do_update(
                index_elements=["invocation_id", "request_ordinal"],
                set_={
                    "status": insert_call.excluded.status,
                    "http_status": insert_call.excluded.http_status,
                    "latency_ms": insert_call.excluded.latency_ms,
                    "prompt_tokens": insert_call.excluded.prompt_tokens,
                    "completion_tokens": insert_call.excluded.completion_tokens,
                    "error_message": insert_call.excluded.error_message,
                },
            )
        )


def _key_error_record(
    row: Mapping[str, Any], feature_key: str, purpose: str, message: str
) -> CallRecord:
    return CallRecord(
        provider_id=int(row["provider_id"]),
        model_id=int(row["model_row_id"]),
        feature_key=feature_key,
        purpose=purpose,
        status="error",
        http_status=None,
        latency_ms=0,
        prompt_tokens=None,
        completion_tokens=None,
        error_message=message,
    )


def _load_candidates(feature_key: str, purpose: str) -> list[ModelCandidate]:
    with _engine.connect() as connection:
        rows = (
            connection.execute(
                select(
                    LlmModel.id.label("model_row_id"),
                    LlmModel.model_id,
                    LlmModel.display_name,
                    LlmModel.timeout_seconds,
                    LlmModel.temperature,
                    LlmModel.max_tokens,
                    LlmModel.extra_retries,
                    LlmModel.api_mode,
                    LlmProvider.protocol,
                    LlmModel.parameters,
                    LlmModel.capabilities,
                    LlmProvider.name.label("provider_name"),
                    LlmProvider.auth_mode,
                    LlmProvider.api_key_ciphertext,
                    LlmProvider.id.label("provider_id"),
                    LlmProvider.base_url,
                )
                .select_from(LlmFeatureModel)
                .join(LlmModel, LlmModel.id == LlmFeatureModel.model_id)
                .join(LlmProvider, LlmProvider.id == LlmModel.provider_id)
                .where(
                    LlmFeatureModel.feature_key == feature_key,
                    LlmModel.enabled.is_(True),
                    LlmModel.deleted_at.is_(None),
                    LlmModel.kind == "language",
                    LlmModel.capabilities.contains(["json_output"]),
                    LlmProvider.enabled.is_(True),
                    LlmProvider.deleted_at.is_(None),
                )
                .order_by(LlmFeatureModel.priority)
            )
            .mappings()
            .all()
        )
    candidates: list[ModelCandidate] = []
    for row in rows:
        try:
            if row["auth_mode"] == "api_key" and not row["api_key_ciphertext"]:
                raise SecretKeyUnavailable("供应商未配置 API Key")
            api_key = (
                decrypt_secret(str(row["api_key_ciphertext"]))
                if row["api_key_ciphertext"] and row["auth_mode"] == "api_key"
                else None
            )
        except SecretKeyUnavailable as exc:
            # 解不开的密钥不能被静默跳过：先落一条失败记录，页面才看得到真正原因。
            _log_call(_key_error_record(row, feature_key, purpose, str(exc)))
            continue
        candidates.append(
            ModelCandidate(
                parameters_json=json.dumps(row["parameters"], sort_keys=True),
                capabilities=tuple(row["capabilities"]),
                extra_retries=int(row["extra_retries"]),
                protocol=row["protocol"],
                api_mode=row["api_mode"],
                provider_name=row["provider_name"],
                registry_model_id=int(row["model_row_id"]),
                provider_id=int(row["provider_id"]),
                display_name=str(row["display_name"]),
                model=str(row["model_id"]),
                base_url=str(row["base_url"]),
                api_key=api_key,
                timeout=float(row["timeout_seconds"]),
                temperature=float(row["temperature"]) if row["temperature"] is not None else None,
                max_tokens=int(row["max_tokens"]) if row["max_tokens"] is not None else None,
            )
        )
    return candidates


def _routing_model(
    feature_key: str,
    purpose: str,
    *,
    before_request=None,
    output_limit: int | None = None,
    on_call=None,
    remaining_seconds=None,
    extra_retries_limit: int | None = None,
) -> RoutingModel:
    from tender.adapters.pg.repositories.provider_cooldown import ProviderCooldown

    cooldown = ProviderCooldown(_engine)
    candidates = _load_candidates(feature_key, purpose)
    if extra_retries_limit is not None:
        candidates = [
            replace(candidate, extra_retries=min(candidate.extra_retries, extra_retries_limit))
            for candidate in candidates
        ]
    with _engine.connect() as c:
        policy = (
            c.execute(select(LlmFeature).where(LlmFeature.key == feature_key)).mappings().first()
        )

    def recheck(snapshot: ModelCandidate) -> ModelCandidate | None:
        current = next(
            (
                c
                for c in _load_candidates(feature_key, purpose)
                if c.registry_model_id == snapshot.registry_model_id
            ),
            None,
        )
        if current is None or (current.protocol, current.api_mode) != (
            snapshot.protocol,
            snapshot.api_mode,
        ):
            return None
        # 参数与次数固定于调用创建时；端点和密钥必须取同一最新供应商行。
        return replace(snapshot, base_url=current.base_url, api_key=current.api_key)

    def record_call(record):
        _log_call(record)
        if on_call:
            on_call(record)

    return RoutingModel(
        feature_key,
        purpose,
        candidates,
        create_model_gateway,
        record_call,
        failover_limit=policy["failover_limit"] if policy else 3,
        max_total_requests=policy["max_total_requests"] if policy else 6,
        deadline_seconds=policy["deadline_seconds"] if policy else 600,
        recheck=recheck,
        reserve=_log_call,
        before_request=before_request,
        output_limit=output_limit,
        cooldown_remaining=cooldown.remaining,
        defer_provider=cooldown.defer,
        remaining_seconds=remaining_seconds,
    )


def _refresh_conflict(
    connection: Any,
    project_id: int,
    field_key: str,
    lot_id: int | None,
) -> None:
    lock_key = f"conflict:{project_id}:{field_key}:{lot_id or 0}"
    acquire_xact_lock(connection, lock_key)
    replacement = aliased(ProjectFile)
    rows = (
        connection.execute(
            select(
                Extraction.id,
                Extraction.version_id,
                Extraction.value_json,
                ProjectFile.role,
                ProjectFile.created_at,
            )
            .select_from(Extraction)
            .join(FieldInstance, FieldInstance.id == Extraction.instance_id)
            .join(ProjectFile, ProjectFile.version_id == Extraction.version_id)
            .where(
                ProjectFile.project_id == project_id,
                ProjectFile.deleted_at.is_(None),
                ~exists().where(
                    replacement.replaces_id == ProjectFile.id,
                    replacement.deleted_at.is_(None),
                ),
                ProjectFile.role.in_(("main", "clarification", "addendum")),
                Extraction.is_current.is_(True),
                Extraction.field_key == field_key,
                Extraction.status != "not_found",
                Extraction.value_json.is_not(None),
                FieldInstance.lot_id.is_not_distinct_from(lot_id),
            )
            .ext(distinct_on(Extraction.version_id))
            .order_by(
                Extraction.version_id,
                case(
                    (ProjectFile.role == "addendum", 0),
                    (ProjectFile.role == "clarification", 1),
                    else_=2,
                ),
                ProjectFile.created_at.desc(),
                Extraction.id.desc(),
            )
        )
        .mappings()
        .all()
    )
    existing_id = connection.execute(
        select(ExtractionConflict.id)
        .where(
            ExtractionConflict.project_id == project_id,
            ExtractionConflict.field_key == field_key,
            ExtractionConflict.lot_id.is_not_distinct_from(lot_id),
            ExtractionConflict.status == "open",
        )
        .order_by(ExtractionConflict.id.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    distinct_values = {
        json.dumps(row["value_json"], ensure_ascii=False, sort_keys=True) for row in rows
    }
    if len(rows) < 2 or len(distinct_values) < 2:
        if existing_id is not None:
            # 新结果已经消除了差异，关闭旧的 open 记录但不自动指定胜出值。
            connection.execute(
                update(ExtractionConflict)
                .where(ExtractionConflict.id == existing_id)
                .values(status="dismissed", resolved_id=None)
            )
        return
    candidate_ids = [int(row["id"]) for row in rows]
    if existing_id is None:
        connection.execute(
            insert(ExtractionConflict).values(
                project_id=project_id,
                field_key=field_key,
                lot_id=lot_id,
                candidate_ids=candidate_ids,
            )
        )
    else:
        connection.execute(
            update(ExtractionConflict)
            .where(ExtractionConflict.id == existing_id)
            .values(candidate_ids=candidate_ids)
        )


def _persist_result(
    job: Mapping[str, Any],
    field_key: str,
    result: dict[str, Any],
    lot_by_code: dict[str, dict[str, Any]],
    *,
    failure_message: str | None = None,
) -> None:
    field = FIELD_BY_KEY[field_key]
    lot = lot_by_code.get(str(result.get("lot_code"))) if result.get("lot_code") else None
    lot_id = int(lot["id"]) if lot is not None else None
    version_id = int(job["version_id"])
    run_id = int(job["run_id"])
    evidence_items = result.get("evidence", [])
    if not isinstance(evidence_items, list):
        evidence_items = []
    with _engine.begin() as connection:
        stored_progress = connection.execute(
            select(Job.progress).where(Job.id == job["id"]).with_for_update()
        ).scalar_one_or_none()
        progress = dict(stored_progress) if isinstance(stored_progress, dict) else {}
        completed = progress.get("completed_fields")
        completed = list(completed) if isinstance(completed, list) else []
        if field_key not in completed:
            completed.append(field_key)
        failures = progress.get("field_failures")
        failures = dict(failures) if isinstance(failures, dict) else {}
        if failure_message:
            failures[field_key] = failure_message[:500]
        else:
            failures.pop(field_key, None)
        keys = _field_keys(
            job["config_snapshot"] if isinstance(job.get("config_snapshot"), dict) else {}
        )
        progress.update(
            {
                "stage": "extracting",
                "fields_total": len(keys),
                "fields_done": len(completed),
                "completed_fields": completed,
                "field_failures": failures,
            }
        )
        instance_id = connection.execute(
            select(FieldInstance.id)
            .where(
                FieldInstance.version_id == version_id,
                FieldInstance.field_key == field_key,
                FieldInstance.lot_id.is_not_distinct_from(lot_id),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if instance_id is None:
            instance_id = connection.execute(
                insert(FieldInstance)
                .values(version_id=version_id, field_key=field_key, lot_id=lot_id)
                .returning(FieldInstance.id)
            ).scalar_one()

        previous = (
            connection.execute(
                select(Extraction.id, Extraction.attempt_no)
                .where(Extraction.instance_id == instance_id, Extraction.is_current.is_(True))
                .with_for_update()
            )
            .mappings()
            .first()
        )
        attempt_no = int(
            connection.execute(
                select(func.coalesce(func.max(Extraction.attempt_no), 0) + 1).where(
                    Extraction.instance_id == instance_id
                )
            ).scalar_one()
        )
        machine_attempt_no = int(
            connection.execute(
                select(func.coalesce(func.max(Extraction.machine_attempt_no), 0) + 1).where(
                    Extraction.instance_id == instance_id, Extraction.run_id == run_id
                )
            ).scalar_one()
        )
        trigger = str(
            (job.get("config_snapshot") or {}).get("trigger", "first")
            if isinstance(job.get("config_snapshot"), dict)
            else "first"
        )
        if previous is not None:
            connection.execute(
                update(Extraction)
                .where(Extraction.id == previous["id"])
                .values(is_current=False, updated_at=func.now())
            )
        value_json = result.get("value")
        extraction_id = connection.execute(
            insert(Extraction)
            .values(
                instance_id=instance_id,
                version_id=version_id,
                run_id=run_id,
                attempt_no=attempt_no,
                machine_attempt_no=machine_attempt_no,
                trigger=trigger,
                hint=(job.get("config_snapshot") or {}).get("hint")
                if isinstance(job.get("config_snapshot"), dict)
                else None,
                field_key=field.key,
                group_key=field.group_key,
                value_json=value_json,
                value_text=result.get("value_text", "未找到"),
                confidence=float(result.get("confidence", 0)),
                status=result.get("status", "need_review"),
                strategy=result.get("strategy", "llm"),
                evidence_count=len(evidence_items),
                supersedes_id=previous["id"] if previous is not None else None,
                is_current=True,
                field_def_version=1,
                llm_model_id=result.get("registry_model_id"),
                llm_model_name=result.get("model"),
                created_by=(job.get("config_snapshot") or {}).get("actor", "system")
                if isinstance(job.get("config_snapshot"), dict)
                else "system",
            )
            .returning(Extraction.id)
        ).scalar_one()
        for sequence, item in enumerate(evidence_items, start=1):
            element = item["element"]
            connection.execute(
                insert(Evidence).values(
                    extraction_id=extraction_id,
                    version_id=version_id,
                    seq=sequence,
                    anchor=item["anchor"],
                    element_id=element["id"],
                    page_no=element["page_no"],
                    bbox_x0=element["bbox_x0"],
                    bbox_y0=element["bbox_y0"],
                    bbox_x1=element["bbox_x1"],
                    bbox_y1=element["bbox_y1"],
                    char_start=item.get("char_start"),
                    char_end=item.get("char_end"),
                    quote=item.get("quote") or element.get("text") or "",
                    quote_source=element.get("source") or "native",
                    match_type=item.get("match_type", "manual"),
                )
            )
        connection.execute(
            update(FieldInstance)
            .where(FieldInstance.id == instance_id)
            .values(current_extraction_id=extraction_id)
        )
        _refresh_conflict(connection, int(job["project_id"]), field.key, lot_id)
        if failure_message or result.get("status") in {"need_review", "conflict"}:
            reason = (
                "rule_conflict"
                if result.get("status") == "conflict"
                else "no_evidence"
                if failure_message or not evidence_items
                else "bad_quote"
            )
            connection.execute(
                insert(ReviewTask).values(extraction_id=extraction_id, reason=reason)
            )
        connection.execute(
            update(Job)
            .where(Job.id == job["id"])
            .values(
                progress=progress,
                error_code=None,
                error_message=None,
                updated_at=datetime.now(UTC),
            )
        )


def _failed_field_result() -> dict[str, Any]:
    return {
        "value": None,
        "value_text": "抽取失败，需人工处理",
        "confidence": 0,
        "status": "need_review",
        "strategy": "llm",
        "evidence": [],
        "lot_code": None,
    }


def _job_canceled(job_id: str) -> bool:
    """取消是协作式的：字段之间查一次状态，已取消就不再产出新结果。"""
    with _engine.connect() as connection:
        status = connection.execute(select(Job.status).where(Job.id == job_id)).scalar_one_or_none()
    return status == "canceled"


def _set_job_state(
    job_id: str, status: str, code: str | None = None, message: str | None = None
) -> None:
    now = datetime.now(UTC)
    finished = status in _TERMINAL
    # 已是 canceled 的任务不允许被别的状态覆盖；只有取消自己可以写回 canceled。
    conditions = (
        [Job.id == job_id] if status == "canceled" else [Job.id == job_id, Job.status != "canceled"]
    )
    with _engine.begin() as connection:
        connection.execute(
            update(Job)
            .where(*conditions)
            .values(
                status=status,
                stage="extracting",
                error_code=code,
                error_message=message[:2000] if message else None,
                updated_at=now,
                finished_at=now if finished else None,
            )
        )


def _mark_field_error(job_id: str, field_key: str, message: str) -> None:
    with _engine.begin() as connection:
        row = (
            connection.execute(
                select(Job.progress, Job.config_snapshot).where(Job.id == job_id).with_for_update()
            )
            .mappings()
            .one()
        )
        progress = dict(row["progress"]) if isinstance(row["progress"], dict) else {}
        failures = dict(progress.get("field_failures") or {})
        failures[field_key] = message[:500]
        completed = list(progress.get("completed_fields") or [])
        if field_key not in completed:
            completed.append(field_key)
        config = row["config_snapshot"] if isinstance(row["config_snapshot"], dict) else {}
        fields_total = len(_field_keys(config))
        progress.update(
            {
                "stage": "extracting",
                "fields_total": fields_total,
                "fields_done": len(completed),
                "completed_fields": completed,
                "field_failures": failures,
            }
        )
        connection.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(progress=progress, updated_at=datetime.now(UTC))
        )


async def _run_job(job: Mapping[str, Any]) -> None:
    version_id = int(job["version_id"])
    run_id = int(job["run_id"])
    elements, chunks = build_anchor_document(_load_elements(version_id, run_id))
    lots = _upsert_lots(int(job["project_id"]), elements)
    lot_by_code = {str(lot["code"]): lot for lot in lots if lot.get("code")}
    snapshot = job["config_snapshot"] if isinstance(job.get("config_snapshot"), dict) else {}
    keys = _field_keys(snapshot)
    if not keys:
        raise ExtractionFailed("当前没有可抽取的字段定义")
    # 带提示重跑整体走 retry 功能配置；首次抽取只在低置信复抽那一轮借用 retry 配置。
    trigger = str(snapshot.get("trigger", "first"))
    primary_feature = "retry" if trigger != "first" else "extract"
    primary_model = _routing_model(primary_feature, primary_feature)
    retry_model = primary_model
    try:
        if primary_feature != "retry":
            retry_model = _routing_model("retry", "retry")
        completed = set((job.get("progress") or {}).get("completed_fields", []))
        for field_key in keys:
            if field_key in completed:
                continue
            if _job_canceled(str(job["id"])):
                return
            field = FIELD_BY_KEY[field_key]
            try:
                result = await extract_field(
                    primary_model,
                    field,
                    elements,
                    chunks,
                    lots,
                    hint=snapshot.get("hint") if isinstance(snapshot.get("hint"), str) else None,
                    retry_model=retry_model,
                )
            except ExtractionUnavailable:
                raise
            except (ExtractionFailed, ValueError) as exc:
                _persist_result(
                    job,
                    field_key,
                    _failed_field_result(),
                    lot_by_code,
                    failure_message=str(exc),
                )
                continue
            _persist_result(job, field_key, result, lot_by_code)
    finally:
        await primary_model.aclose()
        if retry_model is not primary_model:
            await retry_model.aclose()


@celery_app.task(bind=True, name="tender.worker.tasks.extract_fields", max_retries=8)
def extract_fields(self: Any, job_id: str) -> None:
    with _advisory_lock(f"job:{job_id}") as acquired:
        if not acquired:
            raise self.retry(countdown=1)
        job = _load_job(job_id)
        if job is None or job["run_id"] is None or job["version_id"] is None:
            return
        if int(job["company_id"]) != settings.company_id() or job["project_deleted_at"] is not None:
            _set_job_state(job_id, "canceled", "project_unavailable", "项目已删除或不属于当前公司")
            return
        if job["status"] in _TERMINAL:
            return
        _set_job_state(job_id, "running")
        try:
            asyncio.run(_run_job(job))
        except ExtractionUnavailable as exc:
            if self.request.retries >= self.max_retries:
                _set_job_state(job_id, "failed", exc.code, str(exc))
                return
            _set_job_state(job_id, "pending", exc.code, str(exc))
            raise self.retry(
                exc=exc,
                countdown=min(60, 2 ** (self.request.retries + 1)),
            ) from exc
        except ExtractionFailed as exc:
            _set_job_state(job_id, "failed", exc.code, str(exc))
            return
        except Exception as exc:
            _set_job_state(job_id, "failed", "extraction_failed", str(exc))
            return
        final = _load_job(job_id)
        progress = (
            final.get("progress") if final and isinstance(final.get("progress"), dict) else {}
        )
        failures = progress.get("field_failures") if isinstance(progress, dict) else {}
        _set_job_state(
            job_id,
            "partial" if failures else "completed",
            "field_extraction_failed" if failures else None,
            "部分字段抽取失败，请按字段重新运行" if failures else None,
        )


def create_extraction_job(
    project_id: int,
    project_file_id: int,
    version_id: int,
    run_id: int,
    *,
    trigger: str = "first",
    actor: str = "system",
    hint: str | None = None,
    field_keys: list[str] | None = None,
) -> str:
    job_id = uuid4().hex
    keys = field_keys or [field.key for field in FIELDS]
    snapshot = {
        "mode": "initial" if trigger == "first" else "rerun",
        "trigger": trigger,
        "actor": actor,
        "hint": hint,
        "field_keys": keys,
    }
    # 先读活动配置（可能走 Redis 缓存）再开事务：不在事务里等网络。
    active_config = _config_registry().active(settings.company_id())
    with _engine.begin() as connection:
        snapshot_id = _config_registry().snapshot_for_job(connection, active_config)
        connection.execute(
            insert(Job).values(
                id=job_id,
                company_id=settings.company_id(),
                project_id=project_id,
                project_file_id=project_file_id,
                version_id=version_id,
                run_id=run_id,
                status="pending",
                stage="extracting",
                progress={"stage": "extracting", "fields_total": len(keys), "fields_done": 0},
                config_snapshot=snapshot,
                config_snapshot_id=snapshot_id,
            )
        )
    # 这里不再直接投递：beat 按 extract.max_inflight 差额派发（worker/dispatch.py）。
    return job_id
