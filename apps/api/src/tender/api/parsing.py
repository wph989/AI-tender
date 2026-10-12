"""按版本触发首次解析或管理员重新解析。"""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from tender.api.common import configs, engine, version_row
from tender.api.errors import ApiProblem
from tender.application.fields import FIELD_BY_KEY, FIELDS
from tender.config.schema import parse_options
from tender.core import settings

router = APIRouter(prefix="/api/v1/versions", tags=["parsing"])


class ParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: str | None = None
    ocr_mode: str | None = None
    force: bool = False
    reason: str | None = Field(default=None, max_length=1000)


def _validate(payload: ParseRequest) -> None:
    if payload.tier is not None and payload.tier not in {"flash", "basic", "standard", "advanced"}:
        raise ApiProblem(400, "invalid_argument", "tier 不受支持")
    if payload.ocr_mode is not None and payload.ocr_mode not in {"auto", "txt", "ocr"}:
        raise ApiProblem(400, "invalid_argument", "ocr_mode 不受支持")
    if payload.force and not (payload.reason and payload.reason.strip()):
        raise ApiProblem(400, "invalid_argument", "重新解析必须填写 reason")


def _create_parse_job(
    version_id: int,
    payload: ParseRequest,
    request: Request,
    *,
    force: bool,
) -> dict[str, object]:
    db = engine(request)
    version_row(db, version_id)
    company = settings.company_id()
    # 先读活动配置（可能走 Redis 缓存）再开事务：不在事务里等网络。
    active_config = request.app.state.components.configs.active(company)
    try:
        options = parse_options(
            active_config.resolved if active_config is not None else {},
            payload.tier, payload.ocr_mode,
        )
    except ValueError as exc:
        raise ApiProblem(400, "invalid_argument", str(exc)) from exc
    with db.begin() as connection:
        file_row = (
            connection.execute(
                text(
                    """SELECT pf.id AS project_file_id, pf.project_id, pf.display_name,
                              pf.is_parseable, p.company_id
                       FROM project_file AS pf
                       JOIN project AS p ON p.id = pf.project_id
                       WHERE pf.version_id = :version_id AND pf.deleted_at IS NULL
                         AND p.company_id = :company_id AND p.deleted_at IS NULL
                       ORDER BY CASE pf.role WHEN 'main' THEN 0 ELSE 1 END,
                                pf.sort_no, pf.id LIMIT 1
                       FOR UPDATE OF pf"""
                ),
                {"version_id": version_id, "company_id": settings.company_id()},
            )
            .mappings()
            .first()
        )
        if file_row is None or not file_row["is_parseable"]:
            raise ApiProblem(409, "version_not_parseable", "该版本没有可解析的项目文件")
        active = connection.execute(
            text(
                """SELECT id FROM job
                   WHERE version_id = :version_id
                     AND status IN ('pending','submitting','running')
                   ORDER BY created_at DESC LIMIT 1"""
            ),
            {"version_id": version_id},
        ).scalar_one_or_none()
        if active is not None:
            raise ApiProblem(409, "parse_in_flight", "该版本已有解析任务进行中", retryable=True)
        prior = connection.execute(
            text(
                """SELECT id FROM parse_run
                   WHERE version_id = :version_id
                     AND status IN ('pending','running','completed','partial')
                   ORDER BY created_at DESC, id DESC LIMIT 1"""
            ),
            {"version_id": version_id},
        ).scalar_one_or_none()
        if prior is not None and not force:
            raise ApiProblem(409, "parse_exists", "该版本已有解析结果；如需重建请使用 force")
        if force:
            # 新 run 会重建锚点；旧结果保留历史但暂时不能继续作为已确认结果展示。
            connection.execute(
                text(
                    """UPDATE extraction AS e SET status = 'need_review', updated_at = now()
                       FROM field_instance AS fi
                       WHERE fi.id = e.instance_id AND e.version_id = :version_id
                         AND e.is_current = true AND e.status = 'verified'"""
                ),
                {"version_id": version_id},
            )
        job_id = f"job_{uuid4().hex}"
        snapshot = {
            **options,
            "auto_parse": True,
            "trigger": "reparse" if force else "first",
            "reason": payload.reason.strip() if payload.reason else None,
            "actor": request.headers.get("x-actor", "local-user")[:200],
        }
        snapshot_id = request.app.state.components.configs.snapshot_for_job(
            connection, active_config
        )
        connection.execute(
            text(
                """INSERT INTO job
                       (id, company_id, project_id, project_file_id, version_id,
                        status, stage, progress, config_snapshot, config_snapshot_id)
                   VALUES
                       (:id, :company_id, :project_id, :project_file_id, :version_id,
                        'pending', 'submitting', '{}'::jsonb, CAST(:snapshot AS JSONB),
                        :config_snapshot_id)"""
            ),
            {
                "id": job_id,
                "company_id": company,
                "project_id": file_row["project_id"],
                "project_file_id": file_row["project_file_id"],
                "version_id": version_id,
                "snapshot": json.dumps(snapshot, ensure_ascii=False),
                "config_snapshot_id": snapshot_id,
            },
        )
    # 这里不再直接投递：闸门在提交侧（worker/dispatch.py），beat 按 parse.max_inflight 差额派发。
    return {
        "job_id": job_id,
        "version_id": version_id,
        "run_id": None,
        "force": force,
        "status": "pending",
    }


@router.post("/{version_id}/parse", status_code=202)
def parse_version(
    version_id: int,
    request: Request,
    payload: ParseRequest,
) -> dict[str, object]:
    _validate(payload)
    return _create_parse_job(version_id, payload, request, force=payload.force)


@router.post("/{version_id}/reparse", status_code=202)
def reparse_version(
    version_id: int,
    request: Request,
    payload: ParseRequest,
) -> dict[str, object]:
    _validate(payload.model_copy(update={"force": True}))
    return _create_parse_job(
        version_id, payload.model_copy(update={"force": True}), request, force=True
    )


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 空列表 = 全部字段类型，与 /projects/{id}/rerun 同口径。
    field_keys: list[str] = Field(default_factory=list, max_length=100)
    hint: str | None = Field(default=None, max_length=1000)


def _expand_extract_fields(payload: ExtractRequest) -> list[str]:
    """校验字段名并展开成待抽取清单；空列表展开为全部字段类型。

    抽出来单独一个函数是为了能直接断言「未知字段返回 400 而不是静默跳过」——
    静默跳过会让用户以为重跑覆盖了他选的字段，其实一条都没跑。
    """
    unknown = sorted({key for key in payload.field_keys if key not in FIELD_BY_KEY})
    if unknown:
        raise ApiProblem(400, "invalid_argument", f"未知字段：{', '.join(unknown)}")
    return list(payload.field_keys) or [field.key for field in FIELDS]


@router.post("/{version_id}/extract", status_code=202)
def extract_version(
    version_id: int,
    request: Request,
    payload: ExtractRequest,
) -> dict[str, object]:
    """只重跑抽取，复用既有解析产物（不重建锚点）。

    为什么单独开这个入口，而不是让用户走 reparse 或项目级 rerun：解析与抽取是两个
    独立 job，抽取失败（模型不可用 / 密钥缺失 / worker 崩溃）时 `parse_run` 往往已经
    是 completed、结果却一行都没有。此时 `/projects/{id}/rerun` 挑不到任何候选
    （它是从已有 extraction 行里筛的，必然返回 0），而 `/reparse` 要重建锚点、把已
    确认结果全部打回重新复核，代价高一个量级。这里只补一次抽取。

    界面上的「重跑抽取」就是这个端点：锚点、页面几何、已确认结果都不动。
    """
    keys = _expand_extract_fields(payload)
    db = engine(request)
    version_row(db, version_id)
    hint = payload.hint.strip() if payload.hint and payload.hint.strip() else None
    job_id = uuid4().hex
    company = settings.company_id()
    # 先读活动配置（可能走 Redis 缓存）再开事务：不在事务里等网络。
    active_config = configs(request).active(company)
    with db.begin() as connection:
        file_row = (
            connection.execute(
                text(
                    """SELECT pf.id AS project_file_id, pf.project_id, pf.is_parseable
                       FROM project_file AS pf
                       JOIN project AS p ON p.id = pf.project_id
                       WHERE pf.version_id = :version_id AND pf.deleted_at IS NULL
                         AND p.company_id = :company_id AND p.deleted_at IS NULL
                       ORDER BY CASE pf.role WHEN 'main' THEN 0 ELSE 1 END,
                                pf.sort_no, pf.id LIMIT 1"""
                ),
                {"version_id": version_id, "company_id": company},
            )
            .mappings()
            .first()
        )
        if file_row is None or not file_row["is_parseable"]:
            raise ApiProblem(409, "version_not_parseable", "该版本没有可解析的项目文件")
        run_row = (
            connection.execute(
                text(
                    """SELECT id, status FROM parse_run
                       WHERE version_id = :version_id
                       ORDER BY created_at DESC, id DESC LIMIT 1"""
                ),
                {"version_id": version_id},
            )
            .mappings()
            .first()
        )
        if run_row is None or run_row["status"] not in {"completed", "partial"}:
            raise ApiProblem(
                409,
                "parse_incomplete",
                "该版本还没有可用的解析结果，请先重新解析",
                retryable=True,
            )
        # 事务级互斥：并发点击不能各排一个抽取 job（与 start_rerun 同一套做法）。
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"extract:{version_id}"},
        )
        active = connection.execute(
            text(
                """SELECT id FROM job
                   WHERE version_id = :version_id AND stage = 'extracting'
                     AND status IN ('pending','submitting','running')
                   LIMIT 1"""
            ),
            {"version_id": version_id},
        ).scalar_one_or_none()
        if active is not None:
            raise ApiProblem(409, "rerun_in_flight", "该版本已有抽取任务进行中", retryable=True)
        run_id = int(run_row["id"])
        # trigger 不用 first：这不是首次抽取，走 retry 功能绑定的模型，也避免污染首次通过率。
        snapshot = {
            "mode": "rerun",
            "trigger": "hinted_rerun" if hint else "user_rerun",
            "actor": request.headers.get("x-actor", "local-user")[:200],
            "hint": hint,
            "field_keys": keys,
        }
        snapshot_id = configs(request).snapshot_for_job(connection, active_config)
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
                "project_id": file_row["project_id"],
                "project_file_id": file_row["project_file_id"],
                "version_id": version_id,
                "run_id": run_id,
                "progress": json.dumps(
                    {"stage": "extracting", "fields_total": len(keys), "fields_done": 0}
                ),
                "snapshot": json.dumps(snapshot, ensure_ascii=False),
                "config_snapshot_id": snapshot_id,
            },
        )
    # 不直接投递：beat 按 extract.max_inflight 差额派发（worker/dispatch.py）。
    return {
        "job_id": job_id,
        "version_id": version_id,
        "run_id": run_id,
        "field_keys": keys,
        "status": "pending",
    }
