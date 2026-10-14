"""配置中心 API：三层配置的读写、发布、门禁、逐条确认与回滚（设计文档 08）。

这一层只做参数校验、SQL 与响应整形：
- 值解析 / diff / 权限矩阵在 `tender/config/schema.py`
- 门禁与影响清单在 `tender/config/gate.py`
- 审计与逐条确认在 `tender/config/audit.py`

角色来源是 `x-role` 头（默认 admin，本地单租户部署），actor 是 `x-actor`；
真实鉴权接入前，未知角色按最小权限（只读）处理——宁可在页面上表现为"改不了"，
也不要把写权限默认开给一个拼错的角色名。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, func, insert, select, update
from sqlalchemy.engine import Connection

from tender.adapters.pg.locks import acquire_xact_lock
from tender.adapters.pg.models import ConfigAudit, ConfigRelease, RegressionRun
from tender.api.common import configs, engine
from tender.api.errors import ApiProblem
from tender.config import audit, gate, schema
from tender.config.gate import ImpactItem
from tender.config.registry import ActiveConfig, ConfigRegistry
from tender.core import settings

router = APIRouter(prefix="/api/v1/config", tags=["config"])

_SECRET_MASK = "******"


class ReleaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # values 是"相对 based_on（默认当前 active）的覆盖补丁"；
    # 落库时解析成完整值（08 第 7 节：release.values 存全量，不存 diff）。
    values: dict[str, Any] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=1000)
    based_on: int | None = None


class ImpactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=100)
    ref: str = Field(min_length=1, max_length=500)


class AcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ImpactRef] = Field(min_length=1, max_length=500)
    comment: str | None = Field(default=None, max_length=1000)


class ActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # force 只对软门槛有效；硬门槛没有绕过入口（08 第 5 节）。
    force: bool = False
    reason: str | None = Field(default=None, max_length=1000)


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000)


def _role(request: Request) -> str:
    raw = (request.headers.get("x-role") or "admin").strip().lower()
    return raw if raw in schema.READERS else "viewer"


def _actor(request: Request) -> str:
    return (request.headers.get("x-actor") or "local-user")[:200]


def _mask(entry: schema.ConfigItem, value: Any) -> Any:
    return _SECRET_MASK if entry.value_type == "secret" else value


def _mask_stored(key: str, value: Any) -> Any:
    """历史版本里的 key 可能已经不在登记表里（被移除的配置项），掩码要能容忍。"""
    entry = schema.ITEMS_BY_KEY.get(key)
    return _SECRET_MASK if entry is not None and entry.value_type == "secret" else value


def _release_row(connection: Connection, release_id: int, company_id: int) -> Mapping[str, Any]:
    row = (
        connection.execute(
            select(ConfigRelease).where(
                ConfigRelease.id == release_id, ConfigRelease.company_id == company_id
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ApiProblem(404, "not_found", "配置版本不存在")
    return row


def _active_row(connection: Connection, company_id: int) -> Mapping[str, Any] | None:
    return (
        connection.execute(
            select(ConfigRelease)
            .where(ConfigRelease.company_id == company_id, ConfigRelease.status == "active")
            .order_by(ConfigRelease.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )


def _changed_against_active(
    connection: Connection,
    company_id: int,
    values: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """与当前 active 的解析值逐项 diff；没有 active 时与默认值比。"""
    active = _active_row(connection, company_id)
    base = schema.resolve_values(dict(active["values"]) if active is not None else {})
    return schema.diff_values(base, schema.resolve_values(values))


def _regression_for(connection: Connection, release_id: int) -> dict[str, Any] | None:
    """回归报告：取最近一次**已完成**的回放；没有报告就是冷启动，门禁只校验影响清单。

    只认 finished_at 非空的报告：正在跑的或半途失败的（replay_error 会写完成时间）都不能
    拿来做"不倒退"的凭证，回放在跑时按未产出报告处理。
    """
    row = (
        connection.execute(
            select(RegressionRun)
            .where(
                RegressionRun.release_id == release_id,
                RegressionRun.finished_at.is_not(None),
            )
            .order_by(RegressionRun.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


def _impact_for(
    connection: Connection,
    release_id: int,
    values: Mapping[str, Any],
) -> tuple[tuple[ImpactItem, ...], list[tuple[str, str]]]:
    company_id = settings.company_id()
    changed = _changed_against_active(connection, company_id, values)
    regression = _regression_for(connection, release_id)
    failures = list((regression or {}).get("failures") or [])
    impact = gate.build_impact(changed.keys(), regression_failures=failures)
    return impact, audit.load_acks(connection, release_id)


def _audit_rows(
    connection: Connection,
    *,
    company_id: int,
    release_id: int | None,
    limit: int,
) -> list[dict[str, Any]]:
    query = (
        select(
            ConfigAudit.id,
            ConfigAudit.release_id,
            ConfigAudit.actor,
            ConfigAudit.action,
            ConfigAudit.diff,
            ConfigAudit.reason,
            ConfigAudit.created_at,
            ConfigRelease.version_no,
        )
        .select_from(ConfigAudit)
        .join(ConfigRelease, ConfigRelease.id == ConfigAudit.release_id)
        .where(ConfigRelease.company_id == company_id)
    )
    if release_id is not None:
        query = query.where(ConfigAudit.release_id == release_id)
    rows = connection.execute(query.order_by(ConfigAudit.id.desc()).limit(limit)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/items")
def list_items(request: Request) -> dict[str, Any]:
    """配置项定义 + 当前生效值：页面按三层分组渲染，并标出哪些项被 release 覆盖。"""
    registry: ConfigRegistry = configs(request)
    active = registry.active(settings.company_id())
    overrides = dict(active.values) if active is not None else {}
    role = _role(request)
    items = []
    for entry in schema.ITEMS:
        current = active.resolved[entry.key] if active is not None else entry.default
        items.append(
            {
                "key": entry.key,
                "layer": entry.layer,
                "value_type": entry.value_type,
                "description": entry.description,
                "requires_gate": entry.requires_gate,
                "default": _mask(entry, entry.default),
                "value": _mask(entry, current),
                "overridden": entry.key in overrides,
                "writable": role in schema.WRITERS[entry.layer]
                and entry.key not in schema.READONLY_REASONS,
                "readonly_reason": schema.READONLY_REASONS.get(entry.key),
                **schema.value_rules(entry.key),
            }
        )
    return {
        "role": role,
        "items": items,
        "active": (
            None
            if active is None
            else {"release_id": active.release_id, "version_no": active.version_no}
        ),
    }


@router.get("/releases")
def list_releases(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    db: Engine = engine(request)
    query = select(
        ConfigRelease.id,
        ConfigRelease.version_no,
        ConfigRelease.status,
        ConfigRelease.note,
        ConfigRelease.created_by,
        ConfigRelease.created_at,
        ConfigRelease.based_on,
        ConfigRelease.regression_run_id,
    ).where(ConfigRelease.company_id == settings.company_id())
    if status:
        query = query.where(ConfigRelease.status == status)
    with db.connect() as connection:
        rows = (
            connection.execute(query.order_by(ConfigRelease.version_no.desc()).limit(limit))
            .mappings()
            .all()
        )
    return {"items": [dict(row) for row in rows]}


@router.post("/releases", status_code=201)
def create_release(payload: ReleaseCreate, request: Request) -> dict[str, Any]:
    """创建配置版本：只动 L1 立即生效；含 L2/L3 生成 draft，等回归与确认走完再激活。"""
    role = _role(request)
    actor = _actor(request)
    if not payload.values:
        raise ApiProblem(400, "invalid_argument", "没有需要修改的配置项")
    try:
        denial = schema.write_denial(role, payload.values.keys())
    except schema.UnknownConfigKey as exc:
        raise ApiProblem(400, "unknown_config_key", str(exc)) from exc
    if denial is not None:
        raise ApiProblem(403, "forbidden", denial)
    for key, value in payload.values.items():
        message = schema.validate_value(key, value)
        if message is not None:
            raise ApiProblem(400, "invalid_argument", message)

    registry: ConfigRegistry = configs(request)
    company_id = settings.company_id()
    db: Engine = engine(request)
    with db.begin() as connection:
        acquire_xact_lock(connection, f"config-release:{company_id}")
        if payload.based_on is not None:
            base_row = _release_row(connection, payload.based_on, company_id)
        else:
            base_row = _active_row(connection, company_id)
        base_values = dict(base_row["values"]) if base_row is not None else {}
        resolved = schema.resolve_values({**base_values, **payload.values})
        message = schema.validate_values(resolved)
        if message is not None:
            raise ApiProblem(400, "invalid_argument", message)
        changed = schema.diff_values(schema.resolve_values(base_values), resolved)
        gated = schema.gated_keys(changed.keys())
        version_no = int(
            connection.execute(
                select(func.coalesce(func.max(ConfigRelease.version_no), 0) + 1).where(
                    ConfigRelease.company_id == company_id
                )
            ).scalar_one()
        )
        if not gated:
            # L1 立即生效：先归档旧 active，再插入新 active——ux_release_active 只允许一个；
            # L2/L3 只落 draft，不碰当前 active。
            connection.execute(
                update(ConfigRelease)
                .where(ConfigRelease.company_id == company_id, ConfigRelease.status == "active")
                .values(status="archived")
            )
        status = "draft" if gated else "active"
        release_id = int(
            connection.execute(
                insert(ConfigRelease)
                .values(
                    company_id=company_id,
                    version_no=version_no,
                    values=resolved,
                    status=status,
                    based_on=base_row["id"] if base_row is not None else None,
                    note=payload.note,
                    created_by=actor,
                )
                .returning(ConfigRelease.id)
            ).scalar_one()
        )
        audit.write_audit(
            connection,
            release_id=release_id,
            actor=actor,
            action="create",
            diff=changed,
            reason=payload.note,
        )
        if status == "active":
            audit.write_audit(
                connection,
                release_id=release_id,
                actor=actor,
                action="activate",
                diff=changed,
                reason="L1 即时生效（不改变解析与抽取结果）",
            )

    if status == "active":
        # 提交后再广播失效：缓存里出现数据库没有的值比缓存过期难查得多。
        registry.refresh(
            company_id,
            ActiveConfig(
                release_id=release_id,
                version_no=version_no,
                values=resolved,
                resolved=resolved,
            ),
        )
    return {
        "id": release_id,
        "version_no": version_no,
        "status": status,
        "changed": changed,
        "gated": sorted(gated),
        "note": payload.note,
    }


@router.get("/releases/{release_id}")
def get_release(release_id: int, request: Request) -> dict[str, Any]:
    """版本详情：全量值（secret 掩码）+ 相对 active 的 diff + 影响清单 + 门禁预览 + 审计。"""
    db: Engine = engine(request)
    company_id = settings.company_id()
    with db.connect() as connection:
        row = _release_row(connection, release_id, company_id)
        values = dict(row["values"])
        resolved = schema.resolve_values(values)
        changed = _changed_against_active(connection, company_id, values)
        impact, acks = _impact_for(connection, release_id, values)
        regression = _regression_for(connection, release_id)
        result = gate.evaluate_gate(impact=impact, acknowledged=acks, regression=regression)
        audits = _audit_rows(connection, company_id=company_id, release_id=release_id, limit=200)
    return {
        "id": row["id"],
        "version_no": row["version_no"],
        "status": row["status"],
        "note": row["note"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "based_on": row["based_on"],
        "overrides": {key: _mask_stored(key, value) for key, value in values.items()},
        "values": {key: _mask_stored(key, value) for key, value in resolved.items()},
        "changed": changed,
        "impact": gate.impact_state(impact, acks),
        "gate": result.as_dict(),
        "regression": regression,
        "audit": audits,
    }


@router.post("/releases/{release_id}/acknowledge")
def acknowledge_release(
    release_id: int,
    payload: AcknowledgeRequest,
    request: Request,
) -> dict[str, Any]:
    """影响清单逐条确认：每条的确认人都要能回答"谁、何时、确认了哪一条"（09 第 7.1 节）。"""
    role = _role(request)
    actor = _actor(request)
    if role != "admin":
        raise ApiProblem(403, "forbidden", "只有 admin 能确认变更影响清单")
    db: Engine = engine(request)
    company_id = settings.company_id()
    with db.begin() as connection:
        row = _release_row(connection, release_id, company_id)
        if row["status"] != "draft":
            raise ApiProblem(409, "release_not_draft", "只有 draft 版本需要确认影响清单")
        impact, _ = _impact_for(connection, release_id, dict(row["values"]))
        allowed = {(entry.kind, entry.ref) for entry in impact}
        requested = [(entry.kind, entry.ref) for entry in payload.items]
        unknown = [
            {"kind": kind, "ref": ref} for kind, ref in requested if (kind, ref) not in allowed
        ]
        if unknown:
            raise ApiProblem(
                400,
                "unknown_impact_item",
                "确认项不在本次变更影响清单里",
                detail={"unknown": unknown},
            )
        audit.insert_acks(
            connection,
            release_id=release_id,
            actor=actor,
            items=[ImpactItem(kind, ref) for kind, ref in requested],
            comment=payload.comment,
        )
        audit.write_audit(
            connection,
            release_id=release_id,
            actor=actor,
            action="acknowledge",
            diff={"items": [{"kind": kind, "ref": ref} for kind, ref in requested]},
            reason=payload.comment,
        )
        impact_state = gate.impact_state(impact, audit.load_acks(connection, release_id))
    return {
        "id": release_id,
        "acked": [{"kind": kind, "ref": ref} for kind, ref in requested],
        "impact": impact_state,
    }


@router.post("/releases/{release_id}/activate")
def activate_release(
    release_id: int,
    payload: ActivateRequest,
    request: Request,
) -> dict[str, Any]:
    """激活 draft：硬门槛不过返回 422；软门槛需要 force + 理由（会记进审计）。"""
    role = _role(request)
    actor = _actor(request)
    if role != "admin":
        raise ApiProblem(403, "forbidden", "只有 admin 能激活 L2/L3 配置")
    if payload.force and not (payload.reason and payload.reason.strip()):
        raise ApiProblem(400, "invalid_argument", "强制激活必须填写理由")
    db: Engine = engine(request)
    company_id = settings.company_id()
    with db.begin() as connection:
        acquire_xact_lock(connection, f"config-release:{company_id}")
        row = _release_row(connection, release_id, company_id)
        if row["status"] != "draft":
            raise ApiProblem(409, "release_not_draft", "只有 draft 版本可以激活")
        values = dict(row["values"])
        impact, acks = _impact_for(connection, release_id, values)
        regression = _regression_for(connection, release_id)
        result = gate.evaluate_gate(
            impact=impact,
            acknowledged=acks,
            regression=regression,
            force=payload.force,
        )
        if not result.passed:
            raise ApiProblem(
                422,
                "gate_failed",
                "配置未通过门禁，不能激活",
                detail={
                    "blockers": list(result.blockers),
                    "soft_breaches": list(result.soft_breaches),
                    "impact": gate.impact_state(impact, acks),
                },
            )
        changed = _changed_against_active(connection, company_id, values)
        connection.execute(
            update(ConfigRelease)
            .where(ConfigRelease.company_id == company_id, ConfigRelease.status == "active")
            .values(status="archived")
        )
        connection.execute(
            update(ConfigRelease).where(ConfigRelease.id == release_id).values(status="active")
        )
        audit.write_audit(
            connection,
            release_id=release_id,
            actor=actor,
            action="force_activate" if payload.force else "activate",
            diff=changed,
            reason=payload.reason,
        )
        version_no = int(row["version_no"])
        resolved = schema.resolve_values(values)
    registry: ConfigRegistry = configs(request)
    registry.refresh(
        company_id,
        ActiveConfig(
            release_id=release_id,
            version_no=version_no,
            values=values,
            resolved=resolved,
        ),
    )
    return {"id": release_id, "status": "active", "gate": result.as_dict(), "changed": changed}


@router.post("/releases/{release_id}/rollback")
def rollback_release(
    release_id: int,
    payload: RollbackRequest,
    request: Request,
) -> dict[str, Any]:
    """一键回滚：把历史 release 直接置回 active，不重建配置（避免遗漏）。"""
    role = _role(request)
    actor = _actor(request)
    if role != "admin":
        raise ApiProblem(403, "forbidden", "只有 admin 能回滚配置")
    db: Engine = engine(request)
    company_id = settings.company_id()
    with db.begin() as connection:
        acquire_xact_lock(connection, f"config-release:{company_id}")
        target = _release_row(connection, release_id, company_id)
        if target["status"] == "draft":
            raise ApiProblem(409, "release_not_rollbackable", "draft 版本请先通过门禁再激活")
        if target["status"] == "active":
            raise ApiProblem(409, "already_active", "该版本当前就是生效版本")
        current = _active_row(connection, company_id)
        target_resolved = schema.resolve_values(dict(target["values"]))
        base = (
            schema.resolve_values(dict(current["values"]))
            if current is not None
            else schema.default_values()
        )
        changed = schema.diff_values(base, target_resolved)
        if current is not None:
            connection.execute(
                update(ConfigRelease)
                .where(ConfigRelease.id == current["id"])
                .values(status="rolled_back")
            )
        connection.execute(
            update(ConfigRelease).where(ConfigRelease.id == release_id).values(status="active")
        )
        audit.write_audit(
            connection,
            release_id=release_id,
            actor=actor,
            action="rollback",
            diff=changed,
            reason=payload.reason,
        )
        version_no = int(target["version_no"])
        values = dict(target["values"])
    registry: ConfigRegistry = configs(request)
    registry.refresh(
        company_id,
        ActiveConfig(
            release_id=release_id,
            version_no=version_no,
            values=values,
            resolved=target_resolved,
        ),
    )
    return {"id": release_id, "status": "active", "changed": changed}


@router.get("/audit")
def list_audit(
    request: Request,
    release_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """变更审计：谁 / 何时 / 哪个 key / 旧值 / 新值 / 理由（08 第 6 节）。"""
    db: Engine = engine(request)
    with db.connect() as connection:
        rows = _audit_rows(
            connection,
            company_id=settings.company_id(),
            release_id=release_id,
            limit=limit,
        )
    return {"items": rows}
