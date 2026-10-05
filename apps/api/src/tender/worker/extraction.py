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

from sqlalchemy import create_engine, text

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

_engine = create_engine(settings.database_url(), pool_pre_ping=True)
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
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": lock_key},
            ).scalar_one()
        )
        connection.commit()
        try:
            yield acquired
        finally:
            if acquired:
                connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:lock_key, 0))"),
                    {"lock_key": lock_key},
                )
                connection.commit()


def _load_job(job_id: str) -> Mapping[str, Any] | None:
    with _engine.connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT j.*, pf.display_name, p.company_id AS project_company_id,
                          p.deleted_at AS project_deleted_at
                       FROM job AS j
                       JOIN project_file AS pf ON pf.id = j.project_file_id
                       JOIN project AS p ON p.id = j.project_id
                       WHERE j.id = :job_id"""
                ),
                {"job_id": job_id},
            )
            .mappings()
            .first()
        )
    return row


def _load_elements(version_id: int, run_id: int) -> list[dict[str, Any]]:
    with _engine.connect() as connection:
        rows = (
            connection.execute(
                text(
                    """SELECT id, run_id, page_no, order_no, anchor, type, level, parent_id,
                              bbox_x0, bbox_y0, bbox_x1, bbox_y1, text, html, source, continues_prev
                       FROM element
                       WHERE version_id = :version_id AND run_id = :run_id
                       ORDER BY page_no, order_no"""
                ),
                {"version_id": version_id, "run_id": run_id},
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
                text("SELECT id FROM lot WHERE project_id = :project_id AND code = :code LIMIT 1"),
                {"project_id": project_id, "code": candidate.code},
            ).scalar_one_or_none()
            if existing is None:
                next_sort = int(
                    connection.execute(
                        text(
                            "SELECT COALESCE(max(sort_no), -1) + 1 FROM lot "
                            "WHERE project_id = :project_id"
                        ),
                        {"project_id": project_id},
                    ).scalar_one()
                )
                connection.execute(
                    text(
                        """INSERT INTO lot (project_id, code, name, sort_no)
                           VALUES (:project_id, :code, :name, :sort_no)"""
                    ),
                    {
                        "project_id": project_id,
                        "code": candidate.code,
                        "name": candidate.name,
                        "sort_no": next_sort,
                    },
                )
        rows = (
            connection.execute(
                text(
                    "SELECT id, code, name FROM lot "
                    "WHERE project_id = :project_id ORDER BY sort_no, id"
                ),
                {"project_id": project_id},
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
    columns = ",".join(data)
    values = ",".join(":" + key for key in data)
    # 首次先插入 running；返回后只补写同一请求，不新增第二条调用账。
    with _engine.begin() as c:
        c.execute(
            text(f"""INSERT INTO llm_call_log({columns}) VALUES ({values})
            ON CONFLICT (invocation_id,request_ordinal) DO UPDATE SET
            status=EXCLUDED.status,http_status=EXCLUDED.http_status,latency_ms=EXCLUDED.latency_ms,
            prompt_tokens=EXCLUDED.prompt_tokens,completion_tokens=EXCLUDED.completion_tokens,
            error_message=EXCLUDED.error_message"""),
            data,
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
                text(
                    """SELECT m.id AS model_row_id, m.model_id, m.display_name, m.timeout_seconds,
                              m.temperature, m.max_tokens, m.extra_retries,m.api_mode,p.protocol,
                              m.parameters,m.capabilities,
                              p.name AS provider_name,p.auth_mode,p.api_key_ciphertext,
                              p.id AS provider_id, p.base_url
                       FROM llm_feature_model AS fm
                       JOIN llm_model AS m ON m.id = fm.model_id
                       JOIN llm_provider AS p ON p.id = m.provider_id
                       WHERE fm.feature_key = :feature_key
                         AND m.enabled AND m.deleted_at IS NULL AND m.kind='language'
                         AND m.capabilities @> '["json_output"]'::jsonb
                         AND p.enabled AND p.deleted_at IS NULL
                       ORDER BY fm.priority"""
                ),
                {"feature_key": feature_key},
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


def _routing_model(feature_key: str, purpose: str) -> RoutingModel:
    candidates = _load_candidates(feature_key, purpose)
    with _engine.connect() as c:
        policy = (
            c.execute(text("SELECT * FROM llm_feature WHERE key=:key"), {"key": feature_key})
            .mappings()
            .first()
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

    return RoutingModel(
        feature_key,
        purpose,
        candidates,
        create_model_gateway,
        _log_call,
        failover_limit=policy["failover_limit"] if policy else 3,
        max_total_requests=policy["max_total_requests"] if policy else 6,
        deadline_seconds=policy["deadline_seconds"] if policy else 600,
        recheck=recheck,
        reserve=_log_call,
    )


def _refresh_conflict(
    connection: Any,
    project_id: int,
    field_key: str,
    lot_id: int | None,
) -> None:
    lock_key = f"conflict:{project_id}:{field_key}:{lot_id or 0}"
    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": lock_key},
    )
    rows = (
        connection.execute(
            text(
                """SELECT DISTINCT ON (e.version_id) e.id, e.version_id, e.value_json,
                          pf.role, pf.created_at
                   FROM extraction AS e
                   JOIN field_instance AS fi ON fi.id = e.instance_id
                   JOIN project_file AS pf ON pf.version_id = e.version_id
                   WHERE pf.project_id = :project_id AND pf.deleted_at IS NULL
                     AND NOT EXISTS (
                         SELECT 1 FROM project_file AS replacement
                         WHERE replacement.replaces_id = pf.id
                           AND replacement.deleted_at IS NULL
                     )
                     AND pf.role IN ('main','clarification','addendum')
                     AND e.is_current = true AND e.field_key = :field_key
                     AND e.status <> 'not_found' AND e.value_json IS NOT NULL
                     AND fi.lot_id IS NOT DISTINCT FROM :lot_id
                   ORDER BY e.version_id,
                            CASE pf.role WHEN 'addendum' THEN 0
                                 WHEN 'clarification' THEN 1 ELSE 2 END,
                            pf.created_at DESC, e.id DESC"""
            ),
            {"project_id": project_id, "field_key": field_key, "lot_id": lot_id},
        )
        .mappings()
        .all()
    )
    existing_id = connection.execute(
        text(
            """SELECT id FROM extraction_conflict
               WHERE project_id = :project_id AND field_key = :field_key
                 AND lot_id IS NOT DISTINCT FROM :lot_id AND status = 'open'
               ORDER BY id DESC LIMIT 1 FOR UPDATE"""
        ),
        {"project_id": project_id, "field_key": field_key, "lot_id": lot_id},
    ).scalar_one_or_none()
    distinct_values = {
        json.dumps(row["value_json"], ensure_ascii=False, sort_keys=True) for row in rows
    }
    if len(rows) < 2 or len(distinct_values) < 2:
        if existing_id is not None:
            # 新结果已经消除了差异，关闭旧的 open 记录但不自动指定胜出值。
            connection.execute(
                text(
                    """UPDATE extraction_conflict
                       SET status = 'dismissed', resolved_id = NULL
                       WHERE id = :id"""
                ),
                {"id": existing_id},
            )
        return
    candidate_ids = [int(row["id"]) for row in rows]
    if existing_id is None:
        connection.execute(
            text(
                """INSERT INTO extraction_conflict
                       (project_id, field_key, lot_id, candidate_ids)
                   VALUES (:project_id, :field_key, :lot_id, CAST(:candidate_ids AS BIGINT[]))"""
            ),
            {
                "project_id": project_id,
                "field_key": field_key,
                "lot_id": lot_id,
                "candidate_ids": candidate_ids,
            },
        )
    else:
        connection.execute(
            text(
                "UPDATE extraction_conflict SET candidate_ids = CAST(:ids AS BIGINT[]) "
                "WHERE id = :id"
            ),
            {"ids": candidate_ids, "id": existing_id},
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
            text("SELECT progress FROM job WHERE id = :job_id FOR UPDATE"),
            {"job_id": job["id"]},
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
            text(
                """SELECT id FROM field_instance
                   WHERE version_id = :version_id AND field_key = :field_key
                     AND lot_id IS NOT DISTINCT FROM :lot_id
                   FOR UPDATE"""
            ),
            {"version_id": version_id, "field_key": field_key, "lot_id": lot_id},
        ).scalar_one_or_none()
        if instance_id is None:
            instance_id = connection.execute(
                text(
                    """INSERT INTO field_instance (version_id, field_key, lot_id)
                       VALUES (:version_id, :field_key, :lot_id) RETURNING id"""
                ),
                {"version_id": version_id, "field_key": field_key, "lot_id": lot_id},
            ).scalar_one()

        previous = (
            connection.execute(
                text(
                    """SELECT id, attempt_no FROM extraction
                   WHERE instance_id = :instance_id AND is_current = true
                   FOR UPDATE"""
                ),
                {"instance_id": instance_id},
            )
            .mappings()
            .first()
        )
        attempt_no = int(
            connection.execute(
                text(
                    "SELECT COALESCE(max(attempt_no), 0) + 1 FROM extraction "
                    "WHERE instance_id = :instance_id"
                ),
                {"instance_id": instance_id},
            ).scalar_one()
        )
        machine_attempt_no = int(
            connection.execute(
                text(
                    """SELECT COALESCE(max(machine_attempt_no), 0) + 1
                       FROM extraction WHERE instance_id = :instance_id AND run_id = :run_id"""
                ),
                {"instance_id": instance_id, "run_id": run_id},
            ).scalar_one()
        )
        trigger = str(
            (job.get("config_snapshot") or {}).get("trigger", "first")
            if isinstance(job.get("config_snapshot"), dict)
            else "first"
        )
        if previous is not None:
            connection.execute(
                text("UPDATE extraction SET is_current = false, updated_at = now() WHERE id = :id"),
                {"id": previous["id"]},
            )
        value_json = result.get("value")
        extraction_id = connection.execute(
            text(
                """INSERT INTO extraction
                       (instance_id, version_id, run_id, attempt_no, machine_attempt_no,
                        trigger, hint, field_key, group_key, value_json, value_text,
                        confidence, status, strategy, evidence_count, supersedes_id,
                        is_current, created_by, field_def_version, llm_model_id, llm_model_name)
                   VALUES
                       (:instance_id, :version_id, :run_id, :attempt_no, :machine_attempt_no,
                        :trigger, :hint, :field_key, :group_key, CAST(:value_json AS JSONB),
                        :value_text, :confidence, :status, :strategy, :evidence_count,
                        :supersedes_id, true, :created_by, 1, :llm_model_id, :llm_model_name)
                   RETURNING id"""
            ),
            {
                "instance_id": instance_id,
                "version_id": version_id,
                "run_id": run_id,
                "attempt_no": attempt_no,
                "machine_attempt_no": machine_attempt_no,
                "trigger": trigger,
                "hint": (job.get("config_snapshot") or {}).get("hint")
                if isinstance(job.get("config_snapshot"), dict)
                else None,
                "field_key": field.key,
                "group_key": field.group_key,
                "value_json": json.dumps(value_json, ensure_ascii=False),
                "value_text": result.get("value_text", "未找到"),
                "confidence": float(result.get("confidence", 0)),
                "status": result.get("status", "need_review"),
                "strategy": result.get("strategy", "llm"),
                "evidence_count": len(evidence_items),
                "supersedes_id": previous["id"] if previous is not None else None,
                "llm_model_id": result.get("registry_model_id"),
                "llm_model_name": result.get("model"),
                "created_by": (job.get("config_snapshot") or {}).get("actor", "system")
                if isinstance(job.get("config_snapshot"), dict)
                else "system",
            },
        ).scalar_one()
        for sequence, item in enumerate(evidence_items, start=1):
            element = item["element"]
            connection.execute(
                text(
                    """INSERT INTO evidence
                           (extraction_id, version_id, seq, anchor, element_id, page_no,
                            bbox_x0, bbox_y0, bbox_x1, bbox_y1, char_start, char_end,
                            quote, quote_source, match_type)
                       VALUES
                           (:extraction_id, :version_id, :seq, :anchor, :element_id, :page_no,
                            :bbox_x0, :bbox_y0, :bbox_x1, :bbox_y1, :char_start, :char_end,
                            :quote, :quote_source, :match_type)"""
                ),
                {
                    "extraction_id": extraction_id,
                    "version_id": version_id,
                    "seq": sequence,
                    "anchor": item["anchor"],
                    "element_id": element["id"],
                    "page_no": element["page_no"],
                    "bbox_x0": element["bbox_x0"],
                    "bbox_y0": element["bbox_y0"],
                    "bbox_x1": element["bbox_x1"],
                    "bbox_y1": element["bbox_y1"],
                    "char_start": item.get("char_start"),
                    "char_end": item.get("char_end"),
                    "quote": item.get("quote") or element.get("text") or "",
                    "quote_source": element.get("source") or "native",
                    "match_type": item.get("match_type", "manual"),
                },
            )
        connection.execute(
            text(
                """UPDATE field_instance SET current_extraction_id = :extraction_id
                   WHERE id = :instance_id"""
            ),
            {"extraction_id": extraction_id, "instance_id": instance_id},
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
                text(
                    """INSERT INTO review_task (extraction_id, reason)
                       VALUES (:extraction_id, :reason)"""
                ),
                {"extraction_id": extraction_id, "reason": reason},
            )
        connection.execute(
            text(
                """UPDATE job SET progress = CAST(:progress AS JSONB), error_code = NULL,
                       error_message = NULL, updated_at = :now
                   WHERE id = :job_id"""
            ),
            {
                "job_id": job["id"],
                "progress": json.dumps(progress, ensure_ascii=False),
                "now": datetime.now(UTC),
            },
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
        status = connection.execute(
            text("SELECT status FROM job WHERE id = :job_id"), {"job_id": job_id}
        ).scalar_one_or_none()
    return status == "canceled"


def _set_job_state(
    job_id: str, status: str, code: str | None = None, message: str | None = None
) -> None:
    finished = status in _TERMINAL
    with _engine.begin() as connection:
        connection.execute(
            text(
                """UPDATE job SET status = :status, stage = 'extracting',
                       error_code = :code, error_message = :message, updated_at = :now,
                       finished_at = CASE WHEN :finished THEN :now ELSE NULL END
                   WHERE id = :job_id
                     AND (status <> 'canceled' OR :status = 'canceled')"""
            ),
            {
                "job_id": job_id,
                "status": status,
                "code": code,
                "message": message[:2000] if message else None,
                "now": datetime.now(UTC),
                "finished": finished,
            },
        )


def _mark_field_error(job_id: str, field_key: str, message: str) -> None:
    with _engine.begin() as connection:
        row = (
            connection.execute(
                text("SELECT progress, config_snapshot FROM job WHERE id = :job_id FOR UPDATE"),
                {"job_id": job_id},
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
            text(
                """UPDATE job SET progress = CAST(:progress AS JSONB), updated_at = :now
                   WHERE id = :job_id"""
            ),
            {
                "job_id": job_id,
                "progress": json.dumps(progress, ensure_ascii=False),
                "now": datetime.now(UTC),
            },
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
            text(
                """INSERT INTO job
                       (id, company_id, project_id, project_file_id, version_id, run_id,
                        status, stage, progress, config_snapshot, config_snapshot_id)
                   VALUES
                       (:id, :company_id, :project_id, :project_file_id, :version_id, :run_id,
                        'pending', 'extracting', CAST(:progress AS JSONB),
                        CAST(:snapshot AS JSONB), :config_snapshot_id)"""
            ),
            {
                "id": job_id,
                "company_id": settings.company_id(),
                "project_id": project_id,
                "project_file_id": project_file_id,
                "version_id": version_id,
                "run_id": run_id,
                "progress": json.dumps(
                    {"stage": "extracting", "fields_total": len(keys), "fields_done": 0}
                ),
                "snapshot": json.dumps(snapshot, ensure_ascii=False),
                "config_snapshot_id": snapshot_id,
            },
        )
    # 这里不再直接投递：beat 按 extract.max_inflight 差额派发（worker/dispatch.py）。
    return job_id
