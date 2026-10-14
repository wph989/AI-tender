"""回归回放 worker：在回归集上重跑抽取，产出 `regression_run` 报告。
设计口径见 docs/质量/09 第 3、4.3、6.2、7、10 节。

为什么只重跑抽取：`gold_item` 的锚点属于既有的 `parse_run` / `element`，重跑 MinerU 会让锚点
失效、必须重新框选——那是 09 第 5.3 节"重新解析"这条要二次确认的路径。回放复用 sha256 对应的
原件与解析产物，只把 LLM 抽取再跑一遍，所以转换与解析都不重复执行。

为什么没有 `job` 行：`job.project_id` / `project_file_id` 都是 NOT NULL（迁移 0002），
而回归回放不属于任何项目。它的生命周期记在 `regression_run` 自己身上
（started_at = 开始、finished_at = 结束），API 返回的任务 id 只用于日志关联。

失败口径（写进报告而不是只写日志，报告本身就是给人看的）：
- `value_mismatch` / `hallucination` / `anchor_404` / `extraction_failed` 计为失败；
- `gold_unavailable` 表示这条 gold 的文档或解析产物已清理，不计入通过率但在报告里列出；
- `replay_error` 表示整轮回放起不来（模型网关不可用等），门禁按硬门槛拦住激活。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, func, select, update

from tender.adapters.pg.models import (
    ConfigRelease,
    Element,
    GoldItem,
    Lot,
    ParseRun,
    ProjectFile,
    RegressionRun,
)
from tender.adapters.pg.session import create_pg_engine
from tender.application.agent import extract_field
from tender.application.extraction import TextChunk, build_anchor_document
from tender.application.fields import FIELD_BY_KEY
from tender.application.stats import rate, values_match
from tender.config import gate, schema
from tender.domain.errors import ExtractionFailed, ExtractionUnavailable
from tender.worker.celery_app import celery_app

# 复用交互抽取的装配：模型路由与 element 加载必须与生产同一条链路，
# 否则"回归通过"只证明回放脚本自己能跑。
from tender.worker.extraction import _advisory_lock, _load_elements, _routing_model

logger = logging.getLogger(__name__)

_engine: Engine = create_pg_engine()

# 失败分类：前四种计入分母/分母的"失败"一侧，gold_unavailable 只列明细。
_FAIL_KINDS = frozenset({"value_mismatch", "hallucination", "anchor_404", "extraction_failed"})
_REPORTED_KINDS = _FAIL_KINDS | {"gold_unavailable"}


@dataclass(slots=True)
class _Context:
    """一个 (version, parse_run) 的回放上下文：elements 只加载一次被多条 gold 复用。"""

    version_id: int
    run_id: int
    elements: list[dict[str, Any]]
    chunks: list[TextChunk]
    lots: list[dict[str, Any]]
    by_anchor: dict[str, dict[str, Any]]


@dataclass(slots=True)
class _Outcome:
    item: Mapping[str, Any]
    kind: str
    value: Any = None
    anchor_checked: bool = False
    anchor_resolved: bool = True
    message: str | None = None


def _load_run(run_id: int) -> Mapping[str, Any] | None:
    with _engine.connect() as connection:
        return (
            connection.execute(
                select(
                    RegressionRun.id,
                    RegressionRun.release_id,
                    RegressionRun.finished_at,
                    ConfigRelease.company_id,
                    ConfigRelease.values,
                    ConfigRelease.status.label("release_status"),
                )
                .join(ConfigRelease, ConfigRelease.id == RegressionRun.release_id)
                .where(RegressionRun.id == run_id)
            )
            .mappings()
            .first()
        )


def _mark_started(run_id: int) -> None:
    with _engine.begin() as connection:
        connection.execute(
            update(RegressionRun)
            .where(RegressionRun.id == run_id, RegressionRun.finished_at.is_(None))
            .values(started_at=func.now(), finished_at=None)
        )


def _mark_queued(run_id: int) -> None:
    """重试前把 started_at 清掉，页面才能区分"排队等重试"与"正在跑"。"""
    with _engine.begin() as connection:
        connection.execute(
            update(RegressionRun).where(RegressionRun.id == run_id).values(started_at=None)
        )


def _gold_items() -> list[dict[str, Any]]:
    """回归集是历史资产，不按项目清理：版本被删时条目仍保留，由回放标成 gold_unavailable。"""
    with _engine.connect() as connection:
        rows = (
            connection.execute(
                select(
                    GoldItem.id,
                    GoldItem.version_id,
                    GoldItem.field_key,
                    GoldItem.expected,
                    GoldItem.expected_anchors,
                    GoldItem.origin,
                ).order_by(GoldItem.id)
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def _run_for_anchors(version_id: int, anchors: Sequence[str]) -> int | None:
    """选 gold 锚点所在的 run（可能不是最新 run）。

    旧锚点只属于旧 run：拿最新 run 去查会误报 404，所以优先按锚点定位。
    gold 自己的锚点在所有解析产物里都查不到 = 这条的来源已经没了，
    返回 None 让调用方记成 `gold_unavailable`——宁可少算一条，
    也不要在换过解析产物的上下文里用旧期望值判对错。
    """
    with _engine.connect() as connection:
        if anchors:
            found = connection.execute(
                select(Element.run_id)
                .where(Element.version_id == version_id, Element.anchor.in_(list(anchors)))
                .order_by(Element.run_id.desc())
                .limit(1)
            ).scalar_one_or_none()
            return int(found) if found is not None else None
        latest = connection.execute(
            select(ParseRun.id)
            .where(
                ParseRun.version_id == version_id,
                ParseRun.status.in_(("completed", "partial")),
            )
            .order_by(ParseRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    return int(latest) if latest is not None else None


def _lots_for_version(version_id: int) -> list[dict[str, Any]]:
    with _engine.connect() as connection:
        rows = (
            connection.execute(
                select(Lot.id, Lot.code, Lot.name)
                .join(ProjectFile, ProjectFile.project_id == Lot.project_id)
                .where(ProjectFile.version_id == version_id, ProjectFile.deleted_at.is_(None))
                .order_by(Lot.sort_no, Lot.id)
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


def _context_for(
    version_id: int, anchors: Sequence[str], cache: dict[tuple[int, int], _Context]
) -> _Context | None:
    run_id = _run_for_anchors(version_id, anchors)
    if run_id is None:
        return None
    key = (version_id, run_id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    loaded = _load_elements(version_id, run_id)
    if not loaded:
        return None
    # 与交互抽取同一条口径：页眉页脚不进输入，锚点表也必须按同一份元素建，
    # 否则回放出来的证据会在反查时"查不到自己"。
    elements, chunks = build_anchor_document(loaded)
    context = _Context(
        version_id=version_id,
        run_id=run_id,
        elements=elements,
        chunks=chunks,
        lots=_lots_for_version(version_id),
        by_anchor={str(element["anchor"]): element for element in elements},
    )
    cache[key] = context
    return context


async def _replay_item(
    primary: Any,
    retry: Any,
    item: Mapping[str, Any],
    context: _Context,
) -> _Outcome:
    field_key = str(item["field_key"])
    field = FIELD_BY_KEY.get(field_key)
    if field is None:
        return _Outcome(item, "gold_unavailable", message=f"字段定义已不存在：{field_key}")
    try:
        result = await extract_field(
            primary,
            field,
            context.elements,
            context.chunks,
            context.lots,
            retry_model=retry,
        )
    except ExtractionUnavailable:
        # 模型网关不可用是全局问题：交给任务重试，不能把它记成这一条的失败。
        raise
    except (ExtractionFailed, ValueError) as exc:
        return _Outcome(item, "extraction_failed", message=str(exc)[:500])

    anchors = [str(evidence.get("anchor")) for evidence in result.get("evidence") or []]
    resolved = all(anchor in context.by_anchor for anchor in anchors)
    value = result.get("value")
    if value is not None and not anchors:
        kind = "hallucination"
    elif not resolved:
        kind = "anchor_404"
    elif values_match(item["expected"], value):
        kind = "pass"
    else:
        kind = "value_mismatch"
    return _Outcome(
        item,
        kind,
        value=value,
        anchor_checked=bool(anchors),
        anchor_resolved=resolved,
    )


async def _replay(gold: Sequence[Mapping[str, Any]]) -> list[_Outcome]:
    if not gold:
        return []
    primary = _routing_model("extract", "regression")
    retry = _routing_model("retry", "regression")
    cache: dict[tuple[int, int], _Context] = {}
    outcomes: list[_Outcome] = []
    try:
        for item in gold:
            version_id = int(item["version_id"])
            context = _context_for(version_id, list(item["expected_anchors"] or []), cache)
            if context is None:
                outcomes.append(
                    _Outcome(item, "gold_unavailable", message="找不到可复用的解析产物")
                )
                continue
            outcomes.append(await _replay_item(primary, retry, item, context))
    finally:
        await primary.aclose()
        if retry is not primary:
            await retry.aclose()
    return outcomes


def _baseline_rate(connection: Any, company_id: int) -> float | None:
    """当前 active 版本自己的回归通过率；没跑过则 None（门禁跳过不退步判定，冷启动口径）。"""
    row = (
        connection.execute(
            select(RegressionRun.pass_count, RegressionRun.gold_total)
            .join(ConfigRelease, ConfigRelease.id == RegressionRun.release_id)
            .where(
                ConfigRelease.company_id == company_id,
                ConfigRelease.status == "active",
                RegressionRun.finished_at.is_not(None),
                RegressionRun.gold_total > 0,
            )
            .order_by(RegressionRun.id.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return rate(int(row["pass_count"]), int(row["gold_total"]))


def _changed_keys(connection: Any, company_id: int, values: Mapping[str, Any]) -> list[str]:
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
    return sorted(schema.diff_values(base, schema.resolve_values(dict(values))).keys())


def _summarise(outcomes: Iterable[_Outcome], baseline: float | None) -> dict[str, Any]:
    outcomes = list(outcomes)
    replayed = [item for item in outcomes if item.kind != "gold_unavailable"]
    pass_count = sum(1 for item in replayed if item.kind == "pass")
    fail_count = sum(1 for item in replayed if item.kind in _FAIL_KINDS)
    by_field: dict[str, dict[str, Any]] = {}
    for item in replayed:
        entry = by_field.setdefault(
            str(item.item["field_key"]),
            {"field_key": str(item.item["field_key"]), "total": 0, "pass": 0},
        )
        entry["total"] += 1
        if item.kind == "pass":
            entry["pass"] += 1
    field_rows = []
    for entry in by_field.values():
        entry["fail"] = entry["total"] - entry["pass"]
        entry["pass_rate"] = rate(entry["pass"], entry["total"])
        field_rows.append(entry)
    field_rows.sort(key=lambda entry: entry["field_key"])

    failures: list[dict[str, Any]] = []
    for item in outcomes:
        if item.kind == "pass" or item.kind not in _REPORTED_KINDS:
            continue
        anchors = list(item.item["expected_anchors"] or [])
        failure: dict[str, Any] = {
            "kind": item.kind,
            "field_key": str(item.item["field_key"]),
            "anchor": str(anchors[0]) if anchors else None,
            "expected": item.item["expected"],
            "got": item.value,
        }
        if item.message:
            failure["message"] = item.message
        failures.append(failure)

    checked = [item for item in replayed if item.anchor_checked]
    anchor_hit = rate(sum(1 for item in checked if item.anchor_resolved), len(checked))
    if anchor_hit is None:
        # 没有任何证据可查时不能报 0：那是"没有样本"，不是"全都没查到"。
        anchor_hit = 1.0
    return {
        "gold_total": len(replayed),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "baseline_rate": baseline,
        "anchor_hit": anchor_hit,
        "by_field": field_rows,
        "failures": failures,
    }


def _save_report(
    run_id: int, release_id: int, company_id: int, values: Mapping[str, Any], report: dict[str, Any]
) -> None:
    with _engine.begin() as connection:
        changed = _changed_keys(connection, company_id, values)
        impact = gate.build_impact(changed, regression_failures=report["failures"])
        connection.execute(
            update(RegressionRun)
            .where(RegressionRun.id == run_id)
            .values(
                gold_total=report["gold_total"],
                pass_count=report["pass_count"],
                fail_count=report["fail_count"],
                baseline_rate=report["baseline_rate"],
                anchor_hit=report["anchor_hit"],
                by_field=report["by_field"],
                failures=report["failures"],
                impact_items=[entry.as_dict() for entry in impact],
                finished_at=func.now(),
            )
        )
        # 指针与报告一起落库：页面上"这个版本的回放报告是哪个"不再靠猜。
        connection.execute(
            update(ConfigRelease)
            .where(ConfigRelease.id == release_id)
            .values(regression_run_id=run_id)
        )


def _finish_error(run_id: int, message: str) -> None:
    """整轮起不来时也要把报告收口：留空会让门禁把这次变更当冷启动放过去。"""
    with _engine.begin() as connection:
        failures = [{"kind": "replay_error", "message": message[:1000]}]
        connection.execute(
            update(RegressionRun)
            .where(RegressionRun.id == run_id)
            .values(failures=failures, impact_items=[], finished_at=func.now())
        )


@celery_app.task(bind=True, name="tender.worker.regression.run_regression", max_retries=2)
def run_regression(self: Any, regression_run_id: int) -> None:
    with _advisory_lock(f"regression:{regression_run_id}") as acquired:
        if not acquired:
            raise self.retry(countdown=5)
        run = _load_run(regression_run_id)
        if run is None or run["finished_at"] is not None:
            # 同一消息被重复投递时不能重跑一遍：既浪费模型调用，也会把报告时间线搅乱。
            return
        _mark_started(regression_run_id)
        try:
            gold = _gold_items()
            with _engine.connect() as connection:
                baseline = _baseline_rate(connection, int(run["company_id"]))
            outcomes = asyncio.run(_replay(gold))
        except ExtractionUnavailable as exc:
            if self.request.retries < self.max_retries:
                _mark_queued(regression_run_id)
                raise self.retry(exc=exc, countdown=min(300, 30 * 2**self.request.retries)) from exc
            _finish_error(regression_run_id, str(exc))
            return
        except Exception as exc:
            logger.exception("回归回放失败：run=%s", regression_run_id)
            _finish_error(regression_run_id, f"回放执行失败：{exc}")
            return
        report = _summarise(outcomes, baseline)
        _save_report(
            regression_run_id,
            int(run["release_id"]),
            int(run["company_id"]),
            run["values"],
            report,
        )
        logger.info(
            "回归回放完成：run=%s 通过 %s/%s",
            regression_run_id,
            report["pass_count"],
            report["gold_total"],
        )


__all__ = ["run_regression", "_summarise", "_Outcome"]
