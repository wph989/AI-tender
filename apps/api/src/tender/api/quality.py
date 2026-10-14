"""质量闭环 API：回归回放、回归集、字段统计与随机抽检（设计文档 09；接口清单见 05 第 2 节）。

取数全部在这里完成，`application/stats.py` 只做"数 → 率"的收尾计算。这么切的原因：
SQL 里的口径（哪些尝试算已复核、按 review_mode 分档）无法被纯函数测试覆盖，
所以它们必须写得足够直白，让口径与 `docs/质量/09` 第 3 节的表一一对应。

角色来自 `x-role` 头（默认 admin，本地单租户部署，见 `api/common.py`）：
- 触发回归回放 = admin：一次回放要花一批模型调用；
- 发起抽检 = operator/admin：抽检是运营动作，不需要改配置的权限。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, delete, exists, func, insert, select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.engine import Connection

from tender.adapters.pg.models import (
    ConfigRelease,
    Element,
    Evidence,
    Extraction,
    FieldInstance,
    GoldItem,
    RegressionRun,
    ReviewAction,
    ReviewTask,
)
from tender.api.common import configs, engine, queue, role
from tender.api.errors import ApiProblem
from tender.application import stats
from tender.config import audit, gate
from tender.config.gate import ImpactItem
from tender.config.registry import ConfigRegistry
from tender.core import settings

router = APIRouter(prefix="/api/v1", tags=["quality"])

_REGRESSION_TASK = "tender.worker.regression.run_regression"

# 统计只做"逐条"档为主口径：批量确认没有人真的看过（09 第 1 节），
# 抽检档是给批量档做校准用的，三者不能合成一个数。
_PRIMARY_MODE = "item"
_MODE_KEYS = ("item", "batch", "spot_check")


def _verdict(since: datetime | None) -> Any:
    """每个 attempt 的最后一次复核结论；抽检又看一遍时只认最新那次。

    一次尝试可能被复核多次（例如抽检又看了一遍），只认最后一次结论，
    否则同一个 attempt 会同时进分子和分母。
    """
    query = (
        select(
            ReviewAction.attempt_id,
            ReviewAction.action,
            ReviewAction.review_mode,
            ReviewAction.instance_id,
            ReviewAction.created_at,
        )
        .ext(distinct_on(ReviewAction.attempt_id))
        .order_by(
            ReviewAction.attempt_id,
            ReviewAction.created_at.desc(),
            ReviewAction.id.desc(),
        )
    )
    if since is not None:
        query = query.where(ReviewAction.created_at >= since)
    return query.subquery("verdict")


def _attempt_query(since: datetime | None) -> Any:
    v = _verdict(since)
    return (
        select(
            Extraction.field_key,
            Extraction.machine_attempt_no.label("attempt_no"),
            v.c.review_mode,
            v.c.action,
            func.count().label("n"),
        )
        .select_from(v)
        .join(Extraction, Extraction.id == v.c.attempt_id)
        .where(Extraction.machine_attempt_no.is_not(None))
        .group_by(
            Extraction.field_key,
            Extraction.machine_attempt_no,
            v.c.review_mode,
            v.c.action,
        )
    )


def _instance_query(since: datetime | None) -> Any:
    v = _verdict(since)
    reviewed = (
        select(
            FieldInstance.field_key,
            v.c.review_mode,
            Extraction.instance_id,
            Extraction.machine_attempt_no,
            v.c.action,
        )
        .select_from(v)
        .join(Extraction, Extraction.id == v.c.attempt_id)
        .join(FieldInstance, FieldInstance.id == Extraction.instance_id)
        .where(Extraction.machine_attempt_no.is_not(None))
        .subquery("reviewed")
    )
    reviewed_count = func.count(func.distinct(reviewed.c.instance_id))
    confirmed = reviewed.c.action == "confirm"
    return select(
        reviewed.c.field_key,
        reviewed.c.review_mode,
        reviewed_count.label("reviewed"),
        reviewed_count.filter(reviewed.c.machine_attempt_no <= 1).label("cum_1_total"),
        reviewed_count.filter((reviewed.c.machine_attempt_no <= 1) & confirmed).label("cum_1_pass"),
        reviewed_count.filter(reviewed.c.machine_attempt_no <= 2).label("cum_2_total"),
        reviewed_count.filter((reviewed.c.machine_attempt_no <= 2) & confirmed).label("cum_2_pass"),
        reviewed_count.filter(reviewed.c.machine_attempt_no <= 3).label("cum_3_total"),
        reviewed_count.filter((reviewed.c.machine_attempt_no <= 3) & confirmed).label("cum_3_pass"),
    ).group_by(reviewed.c.field_key, reviewed.c.review_mode)


def _manual_query(since: datetime | None) -> Any:
    v = _verdict(since)
    reviewed = (
        select(
            FieldInstance.field_key.label("field_key"),
            Extraction.instance_id.label("instance_id"),
        )
        .select_from(v)
        .join(Extraction, Extraction.id == v.c.attempt_id)
        .join(FieldInstance, FieldInstance.id == Extraction.instance_id)
        .where(Extraction.machine_attempt_no.is_not(None))
        .distinct()
        .subquery("reviewed")
    )
    manual = (
        select(Extraction.instance_id.label("instance_id"))
        .where(Extraction.trigger == "manual_edit")
        .distinct()
        .subquery("m")
    )
    reviewed_count = func.count(func.distinct(reviewed.c.instance_id))
    return (
        select(
            reviewed.c.field_key,
            reviewed_count.label("reviewed"),
            reviewed_count.filter(manual.c.instance_id.is_not(None)).label("manual"),
        )
        .select_from(reviewed)
        .outerjoin(manual, manual.c.instance_id == reviewed.c.instance_id)
        .group_by(reviewed.c.field_key)
    )


def _evidence_query(since: datetime | None) -> Any:
    """线上监控埋点（09 第 9 节）：404 率必须恒为 0；bbox 为空 = 降级成页级定位。"""
    query = (
        select(
            func.count().label("total"),
            func.count().filter(Evidence.bbox_x0.is_(None)).label("bbox_missing"),
            func.count().filter(Element.id.is_(None)).label("anchor_missing"),
        )
        .select_from(Evidence)
        .join(Extraction, Extraction.id == Evidence.extraction_id)
        .outerjoin(
            Element,
            (Element.version_id == Evidence.version_id)
            & (Element.run_id == Extraction.run_id)
            & (Element.anchor == Evidence.anchor),
        )
    )
    if since is not None:
        query = query.where(Evidence.created_at >= since)
    return query


def _spot_check_query(since: datetime | None, field_keys: list[str], size: int) -> Any:
    v = _verdict(since)
    query = (
        select(v.c.attempt_id, Extraction.field_key)
        .select_from(v)
        .join(Extraction, Extraction.id == v.c.attempt_id)
        .where(
            v.c.action == "confirm",
            v.c.review_mode == "batch",
            ~exists().where(
                ReviewAction.instance_id == v.c.instance_id,
                ReviewAction.review_mode == "spot_check",
                ReviewAction.created_at >= v.c.created_at,
            ),
        )
    )
    if field_keys:
        query = query.where(Extraction.field_key.in_(field_keys))
    return query.order_by(func.random()).limit(size)


class SpotCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: int = Field(default=40, ge=1, le=500)
    window: str = Field(default="7d", max_length=8)
    field_keys: list[str] = Field(default_factory=list, max_length=100)


def _window_start(raw: str) -> datetime | None:
    try:
        window = stats.parse_window(raw)
    except ValueError as exc:
        raise ApiProblem(400, "invalid_argument", str(exc)) from exc
    return datetime.now(UTC) - window if window is not None else None


def _changed_keys(connection: Connection, company_id: int, values: dict[str, Any]) -> list[str]:
    """与当前 active 的差异：影响清单的配置项部分（字段增删在 extract.fields 里体现）。"""
    from tender.config import schema

    active = (
        connection.execute(
            select(ConfigRelease.values)
            .where(ConfigRelease.company_id == company_id, ConfigRelease.status == "active")
            .order_by(ConfigRelease.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    base = schema.resolve_values(dict(active["values"]) if active is not None else {})
    return sorted(schema.diff_values(base, schema.resolve_values(values)).keys())


def _run_status(row: Any) -> str:
    if row["finished_at"] is not None:
        return "finished"
    return "running" if row["started_at"] is not None else "queued"


def _regression_mapping(row: Any) -> dict[str, Any]:
    """拼给 `gate.evaluate_gate` 的映射：字段口径与 regression_run 表一致。"""
    baseline = row["baseline_rate"]
    return {
        "gold_total": int(row["gold_total"]),
        "pass_count": int(row["pass_count"]),
        "baseline_rate": float(baseline) if baseline is not None else None,
        "failures": list(row["failures"] or []),
    }


@router.post("/config/releases/{release_id}/regression-runs", status_code=202)
def trigger_regression_run(release_id: int, request: Request) -> dict[str, Any]:
    """触发回归回放（低优先级队列，复用既有解析产物，见 worker/regression.py）。"""
    if role(request) != "admin":
        raise ApiProblem(403, "forbidden", "只有 admin 能触发回归回放")
    db: Engine = engine(request)
    company_id = settings.company_id()
    with db.begin() as connection:
        release = (
            connection.execute(
                select(ConfigRelease.id, ConfigRelease.status, ConfigRelease.values)
                .where(ConfigRelease.id == release_id, ConfigRelease.company_id == company_id)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if release is None:
            raise ApiProblem(404, "not_found", "配置版本不存在")
        if release["status"] != "draft":
            raise ApiProblem(409, "release_not_draft", "只有 draft 版本需要回归回放")
        inflight = connection.execute(
            select(RegressionRun.id)
            .where(RegressionRun.release_id == release_id, RegressionRun.finished_at.is_(None))
            .order_by(RegressionRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if inflight is not None:
            raise ApiProblem(
                409,
                "regression_in_flight",
                "该版本已有未完成的回归回放",
                detail={"regression_run_id": int(inflight)},
            )
        gold_total = int(
            connection.execute(select(func.count()).select_from(GoldItem)).scalar_one()
        )
        changed = _changed_keys(connection, company_id, dict(release["values"]))
        impact = [entry.as_dict() for entry in gate.build_impact(changed)]
        run_id = int(
            connection.execute(
                insert(RegressionRun)
                .values(
                    release_id=release_id,
                    gold_total=gold_total,
                    pass_count=0,
                    fail_count=0,
                    impact_items=impact,
                )
                .returning(RegressionRun.id)
            ).scalar_one()
        )
        connection.execute(
            update(ConfigRelease)
            .where(ConfigRelease.id == release_id)
            .values(regression_run_id=run_id)
        )
    try:
        task_id = queue(request).enqueue(_REGRESSION_TASK, (run_id,))
    except Exception as exc:  # broker 不可用是暂时的：把这次触发收干净，允许马上重试
        with db.begin() as connection:
            connection.execute(delete(RegressionRun).where(RegressionRun.id == run_id))
            connection.execute(
                update(ConfigRelease)
                .where(ConfigRelease.id == release_id, ConfigRelease.regression_run_id == run_id)
                .values(regression_run_id=None)
            )
        raise ApiProblem(
            503,
            "queue_unavailable",
            "任务队列暂时不可用，回归回放未开始",
            retryable=True,
        ) from exc
    # job_id 只是队列任务 id（没有结果后端），报告进度一律以 regression_run 为准。
    return {"job_id": task_id or f"regression-{run_id}", "regression_run_id": run_id}


@router.get("/regression-runs/{run_id}")
def get_regression_run(run_id: int, request: Request) -> dict[str, Any]:
    """回放报告 + 影响清单确认状态 + 门禁预览（05 第 3.9 节）。"""
    db: Engine = engine(request)
    company_id = settings.company_id()
    with db.connect() as connection:
        row = (
            connection.execute(
                select(
                    RegressionRun.id,
                    RegressionRun.release_id,
                    RegressionRun.gold_total,
                    RegressionRun.pass_count,
                    RegressionRun.fail_count,
                    RegressionRun.baseline_rate,
                    RegressionRun.anchor_hit,
                    RegressionRun.by_field,
                    RegressionRun.failures,
                    RegressionRun.impact_items,
                    RegressionRun.started_at,
                    RegressionRun.finished_at,
                    ConfigRelease.version_no,
                    ConfigRelease.status.label("release_status"),
                )
                .select_from(RegressionRun)
                .join(ConfigRelease, ConfigRelease.id == RegressionRun.release_id)
                .where(RegressionRun.id == run_id, ConfigRelease.company_id == company_id)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ApiProblem(404, "not_found", "回归回放不存在")
        acknowledged = audit.load_acks(connection, int(row["release_id"]))

    acked = set(acknowledged)
    stored_impact = row["impact_items"] if isinstance(row["impact_items"], list) else []
    impact = [
        {
            "kind": str(entry.get("kind", "")),
            "ref": str(entry.get("ref", "")),
            "acked": (str(entry.get("kind", "")), str(entry.get("ref", ""))) in acked,
        }
        for entry in stored_impact
        if isinstance(entry, dict)
    ]
    regression = _regression_mapping(row)
    pass_rate = stats.rate(regression["pass_count"], regression["gold_total"])
    baseline = regression["baseline_rate"]
    delta = (
        {"pass_rate": round(pass_rate - baseline, 4)}
        if pass_rate is not None and baseline is not None
        else None
    )
    status = _run_status(row)
    gate_view = None
    if status == "finished":
        gate_view = gate.evaluate_gate(
            impact=tuple(ImpactItem(str(entry["kind"]), str(entry["ref"])) for entry in impact),
            acknowledged=acknowledged,
            regression=regression,
        ).as_dict()
    failures = regression["failures"]
    return {
        "id": int(row["id"]),
        "release_id": int(row["release_id"]),
        "release_version_no": int(row["version_no"]),
        "status": status,
        "gold_total": regression["gold_total"],
        "pass_count": regression["pass_count"],
        "fail_count": int(row["fail_count"]),
        "pass_rate": pass_rate,
        "baseline_rate": baseline,
        "delta": delta,
        "anchor_hit": float(row["anchor_hit"]) if row["anchor_hit"] is not None else None,
        "skipped": sum(1 for entry in failures if entry.get("kind") == "gold_unavailable"),
        "by_field": list(row["by_field"] or []),
        "failures": failures,
        "impact": impact,
        "gate": gate_view,
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }


@router.get("/gold-items")
def list_gold_items(
    request: Request,
    field_key: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """回归集条目（可按字段过滤）：值 + 锚点 + 产出时的参数快照（09 第 4.3 节）。"""
    db: Engine = engine(request)
    with db.connect() as connection:
        query = select(
            GoldItem.id,
            GoldItem.source_instance_id,
            GoldItem.version_id,
            GoldItem.field_key,
            GoldItem.expected,
            GoldItem.expected_anchors,
            GoldItem.origin,
            GoldItem.param_snapshot,
            GoldItem.created_at,
        )
        counter = select(func.count()).select_from(GoldItem)
        if field_key:
            query = query.where(GoldItem.field_key == field_key)
            counter = counter.where(GoldItem.field_key == field_key)
        rows = (
            connection.execute(query.order_by(GoldItem.id.desc()).limit(limit).offset(offset))
            .mappings()
            .all()
        )
        total = int(connection.execute(counter).scalar_one())
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/stats/fields")
def field_stats(
    request: Request,
    scope: str = Query(default="all"),
    window: str = Query(default="90d"),
) -> dict[str, Any]:
    """字段类型级统计（09 第 3、8、9 节；05 第 3.12 节）。

    顶层数字是「逐条复核」档：批量确认没有人真看过，把它混进来会系统性抬高通过率。
    另外两档原样放在 `by_mode` 里，页面要展示"批量确认准确率"时自己取。
    """
    if scope != "all":
        raise ApiProblem(400, "invalid_argument", "当前只支持 scope=all")
    since = _window_start(window)
    db: Engine = engine(request)
    with db.connect() as connection:
        attempt_rows = connection.execute(_attempt_query(since)).mappings().all()
        instance_rows = connection.execute(_instance_query(since)).mappings().all()
        manual_rows = connection.execute(_manual_query(since)).mappings().all()
        evidence = connection.execute(_evidence_query(since)).mappings().one()

    attempts: dict[str, dict[str, dict[int, dict[str, int]]]] = {}
    for row in attempt_rows:
        by_mode = attempts.setdefault(str(row["field_key"]), {}).setdefault(
            str(row["review_mode"]), {}
        )
        by_attempt = by_mode.setdefault(int(row["attempt_no"]), {})
        by_attempt[str(row["action"])] = int(row["n"])
    instances: dict[str, dict[str, dict[str, int]]] = {}
    for row in instance_rows:
        # 字段与复核方式是分组维度，不是计数；有复核记录后不能把 item 等文本转成整数。
        data = {
            str(key): int(value)
            for key, value in dict(row).items()
            if key not in {"field_key", "review_mode"}
        }
        instances.setdefault(str(row["field_key"]), {})[str(row["review_mode"])] = data
    manual: dict[str, tuple[int, int]] = {
        str(row["field_key"]): (int(row["reviewed"]), int(row["manual"])) for row in manual_rows
    }

    registry: ConfigRegistry = configs(request)
    resolved = registry.resolved(settings.company_id())
    hide_threshold = float(resolved["extract.rerun.hide_threshold"])
    min_sample = int(resolved["extract.rerun.min_sample"])

    field_keys = sorted(set(attempts) | set(instances) | set(manual))
    items: list[dict[str, Any]] = []
    for key in field_keys:
        modes: dict[str, Any] = {}
        for mode in _MODE_KEYS:
            by_attempt = attempts.get(key, {}).get(mode, {})
            reviewed_attempts = sum(sum(counts.values()) for counts in by_attempt.values())
            first_total = sum(by_attempt.get(1, {}).values())
            first_pass = by_attempt.get(1, {}).get("confirm", 0)
            instance_data = instances.get(key, {}).get(mode, {})
            modes[mode] = {
                "reviewed_attempts": reviewed_attempts,
                "reviewed_instances": instance_data.get("reviewed", 0),
                "first_pass_rate": stats.rate(first_pass, first_total),
                "rescue_rate": {
                    str(attempt_no): stats.rate(
                        by_attempt.get(attempt_no, {}).get("confirm", 0),
                        sum(by_attempt.get(attempt_no, {}).values()),
                    )
                    for attempt_no in (2, 3)
                },
                "cumulative_pass": {
                    str(n): stats.rate(
                        instance_data.get(f"cum_{n}_pass", 0),
                        instance_data.get(f"cum_{n}_total", 0),
                    )
                    for n in (1, 2, 3)
                },
            }
        primary = modes[_PRIMARY_MODE]
        manual_total, manual_count = manual.get(key, (0, 0))
        items.append(
            {
                "field_key": key,
                "reviewed": primary["reviewed_instances"],
                "first_pass_rate": primary["first_pass_rate"],
                "rescue_rate": primary["rescue_rate"],
                "cumulative_pass": primary["cumulative_pass"],
                "manual_fallback_rate": stats.rate(manual_count, manual_total),
                "rerun_button": stats.rerun_button(
                    primary["reviewed_instances"],
                    primary["rescue_rate"]["2"],
                    hide_threshold=hide_threshold,
                    min_sample=min_sample,
                ),
                "by_mode": modes,
            }
        )
    evidence_total = int(evidence["total"])
    return {
        "scope": scope,
        "window": window,
        "items": items,
        "system": {
            "evidence_total": evidence_total,
            "anchor_404_rate": stats.rate(int(evidence["anchor_missing"]), evidence_total),
            "bbox_missing_rate": stats.rate(int(evidence["bbox_missing"]), evidence_total),
        },
    }


@router.post("/spot-checks", status_code=201)
def create_spot_check(payload: SpotCheckRequest, request: Request) -> dict[str, Any]:
    """生成随机抽检任务（09 第 6.1 节，05 第 3.13 节）。

    抽样框是「最后一次复核结论为批量确认的尝试」：逐条复核已经有人真看过，
    真正需要校准的是"没人真看"的那一档。抽出的任务进复核队列并打上 spot_check 标记。
    """
    if role(request) not in {"operator", "admin"}:
        raise ApiProblem(403, "forbidden", "只有 operator/admin 能发起抽检")
    since = _window_start(payload.window)
    db: Engine = engine(request)
    batch_id = uuid4().hex
    with db.begin() as connection:
        rows = (
            connection.execute(_spot_check_query(since, list(payload.field_keys), payload.size))
            .mappings()
            .all()
        )
        task_ids = [
            int(
                connection.execute(
                    insert(ReviewTask)
                    .values(extraction_id=int(row["attempt_id"]), reason="spot_check")
                    .returning(ReviewTask.id)
                ).scalar_one()
            )
            for row in rows
        ]
    # job_id 是本次抽样批次号：抽样是同步完成的，明细就是下面这些复核任务。
    return {"job_id": batch_id, "sampled": len(task_ids), "review_task_ids": task_ids}
