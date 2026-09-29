"""路由共享的数据访问助手；所有资源读都带单租户 company_id 条件。"""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import Request
from sqlalchemy import Engine, text
from sqlalchemy.engine import RowMapping

from tender.config import schema
from tender.config.registry import ConfigRegistry
from tender.core import settings
from tender.ports.blob_store import BlobStore
from tender.ports.converter import OfficeConverter
from tender.ports.task_queue import TaskQueue


def engine(request: Request) -> Engine:
    return request.app.state.components.engine


def blobs(request: Request) -> BlobStore:
    return request.app.state.components.blobs


def converter(request: Request) -> OfficeConverter:
    return request.app.state.components.converter


def configs(request: Request) -> ConfigRegistry:
    return request.app.state.components.configs


def queue(request: Request) -> TaskQueue:
    return request.app.state.components.queue


def role(request: Request) -> str:
    """角色来自 `x-role` 头（本地单租户部署，默认 admin）；未知角色按最小权限处理。"""
    raw = (request.headers.get("x-role") or "admin").strip().lower()
    return raw if raw in schema.READERS else "viewer"


def actor(request: Request) -> str:
    return (request.headers.get("x-actor") or "local-user")[:200]


def project_row(db: Engine, project_id: int) -> RowMapping:
    with db.connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT id, company_id, name, project_no, owner, status, created_at
                   FROM project
                   WHERE id = :project_id AND company_id = :company_id
                     AND deleted_at IS NULL"""
                ),
                {"project_id": project_id, "company_id": settings.company_id()},
            )
            .mappings()
            .first()
        )
    if row is None:
        from tender.api.errors import ApiProblem

        raise ApiProblem(404, "not_found", "项目不存在")
    return row


def project_file_row(db: Engine, project_id: int, file_id: int) -> RowMapping:
    with db.connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT pf.*, p.company_id, p.deleted_at AS project_deleted_at,
                          v.original_key AS version_original_key
                   FROM project_file AS pf
                   JOIN project AS p ON p.id = pf.project_id
                   LEFT JOIN document_version AS v ON v.id = pf.version_id
                   WHERE pf.project_id = :project_id AND pf.id = :file_id
                     AND p.company_id = :company_id AND p.deleted_at IS NULL
                     AND pf.deleted_at IS NULL"""
                ),
                {
                    "project_id": project_id,
                    "file_id": file_id,
                    "company_id": settings.company_id(),
                },
            )
            .mappings()
            .first()
        )
    if row is None:
        from tender.api.errors import ApiProblem

        raise ApiProblem(404, "not_found", "项目文件不存在")
    return row


def version_row(db: Engine, version_id: int) -> RowMapping:
    with db.connect() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT v.id, v.document_id, v.version_no, v.sha256, v.pdf_key, v.pdf_sha256,
                          v.original_key, v.mime, v.size_bytes, v.is_converted, v.converter,
                          v.converter_version, v.page_count, v.created_at, d.title, d.company_id
                   FROM document_version AS v
                   JOIN document AS d ON d.id = v.document_id
                   WHERE v.id = :version_id AND d.company_id = :company_id
                     AND d.deleted_at IS NULL"""
                ),
                {"version_id": version_id, "company_id": settings.company_id()},
            )
            .mappings()
            .first()
        )
    if row is None:
        from tender.api.errors import ApiProblem

        raise ApiProblem(404, "not_found", "文档版本不存在")
    return row


def bbox(row: RowMapping) -> list[float] | None:
    values = (row["bbox_x0"], row["bbox_y0"], row["bbox_x1"], row["bbox_y1"])
    if any(value is None for value in values):
        return None
    return [float(value) for value in values]


def start_rerun(
    db: Engine,
    configs: ConfigRegistry,
    extraction_id: int,
    *,
    hint: str | None,
    actor: str,
) -> dict[str, object]:
    """给一个当前字段实例排一次重跑任务。

    单字段重跑与项目级批量重跑共用这一份校验：只有当前尝试、且解析 run 未变化时才能重跑；
    同一实例有在途重跑时返回 409 rerun_in_flight，批量调用方按这个错误码跳过，而不是整批失败。
    """
    from tender.api.errors import ApiProblem

    company = settings.company_id()
    # 先读活动配置（可能走 Redis 缓存）再开事务：不在事务里等网络。
    active_config = configs.active(company)
    job_id = uuid4().hex
    with db.begin() as connection:
        row = (
            connection.execute(
                text(
                    """SELECT e.id, e.instance_id, e.version_id, e.run_id, e.field_key,
                              e.is_current, fi.lot_id, v.page_count, pf.project_id,
                              pf.id AS project_file_id, pr.status AS parse_status,
                              latest.id AS latest_run_id
                       FROM extraction AS e
                       JOIN field_instance AS fi ON fi.id = e.instance_id
                       JOIN document_version AS v ON v.id = e.version_id
                       JOIN document AS d ON d.id = v.document_id
                       JOIN parse_run AS pr ON pr.id = e.run_id
                       JOIN LATERAL (
                           SELECT project_file.id, project_file.project_id
                           FROM project_file
                           JOIN project ON project.id = project_file.project_id
                           WHERE project_file.version_id = e.version_id
                             AND project_file.deleted_at IS NULL
                             AND project_file.is_parseable = true
                             AND project.company_id = :company_id
                             AND project.deleted_at IS NULL
                           ORDER BY CASE project_file.role WHEN 'main' THEN 0 ELSE 1 END,
                                    project_file.sort_no, project_file.id
                           LIMIT 1
                       ) AS pf ON true
                       LEFT JOIN LATERAL (
                           SELECT id FROM parse_run
                           WHERE version_id = e.version_id
                           ORDER BY created_at DESC, id DESC LIMIT 1
                       ) AS latest ON true
                       WHERE e.id = :extraction_id AND d.company_id = :company_id
                         AND d.deleted_at IS NULL
                       FOR UPDATE OF e"""
                ),
                {"extraction_id": extraction_id, "company_id": settings.company_id()},
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ApiProblem(404, "not_found", "抽取结果不存在")
        if not row["is_current"]:
            raise ApiProblem(409, "attempt_not_current", "只能重跑当前字段结果")
        if row["run_id"] != row["latest_run_id"] or row["parse_status"] not in {
            "completed",
            "partial",
        }:
            raise ApiProblem(409, "anchor_not_found", "解析 run 已变化，请从当前版本重新抽取")
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"rerun:{row['instance_id']}"},
        )
        active = connection.execute(
            text(
                """SELECT id FROM job
                   WHERE status IN ('pending','submitting','running')
                     AND config_snapshot->>'instance_id' = :instance_id
                   LIMIT 1"""
            ),
            {"instance_id": str(row["instance_id"])},
        ).scalar_one_or_none()
        if active is not None:
            raise ApiProblem(409, "rerun_in_flight", "该字段已有重跑任务进行中", retryable=True)
        next_attempt = int(
            connection.execute(
                text(
                    """SELECT COALESCE(max(machine_attempt_no), 0) + 1
                       FROM extraction WHERE instance_id = :instance_id AND run_id = :run_id"""
                ),
                {"instance_id": row["instance_id"], "run_id": row["run_id"]},
            ).scalar_one()
        )
        trigger = "hinted_rerun" if hint else "user_rerun"
        snapshot = {
            "mode": "rerun",
            "trigger": trigger,
            "actor": actor,
            "hint": hint,
            "field_keys": [row["field_key"]],
            "instance_id": int(row["instance_id"]),
            "model": settings.llm_model(),
        }
        snapshot_id = configs.snapshot_for_job(connection, active_config)
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
                "company_id": company,
                "project_id": row["project_id"],
                "project_file_id": row["project_file_id"],
                "version_id": row["version_id"],
                "run_id": row["run_id"],
                "progress": json.dumps(
                    {"stage": "extracting", "fields_total": 1, "fields_done": 0}
                ),
                "snapshot": json.dumps(snapshot, ensure_ascii=False),
                "config_snapshot_id": snapshot_id,
            },
        )
    # 这里不再直接投递：beat 按 extract.max_inflight 差额派发（worker/dispatch.py）。
    return {
        "job_id": job_id,
        "instance_id": int(row["instance_id"]),
        "field_key": row["field_key"],
        "next_machine_attempt_no": next_attempt,
    }
