"""beat：读 L1 配置 → 数在途 → 只提交差额（设计文档 10 第 3.5 节）。

为什么把提交职责从 API 挪到这里：闸门必须落在**提交侧**。API 直接投递时，并发上限
只能等于 worker 池大小，改配置不会生效；beat 每个 tick 重新读配置，`*_max_inflight`
才真的是运行期参数（08 第 2.1 节）。

为什么在途数用数据库计数而不是 Redis 信号量：worker 崩溃或消息丢失时，job 行会以状态
收敛，而下调的配置只需"暂停新派发"（10 第 3.5 节第 4 条）；信号量要额外一套 TTL 与
回收逻辑才能达到同等可靠性。计数口径 =「已派发且未结束」，与"发往外部服务的在途请求"
在数量级上一致。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, create_engine, text

from tender.adapters.redis_cache import RedisConfigCache
from tender.config.registry import ConfigRegistry
from tender.core import settings
from tender.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_engine: Engine = create_engine(settings.database_url(), pool_pre_ping=True)
_registry: ConfigRegistry | None = None
_last_run_at = 0.0


@dataclass(frozen=True, slots=True)
class Stream:
    """一条派发线：哪些 stage 归它管、受哪个上限约束、投递哪个任务。"""

    name: str
    stages: tuple[str, ...]
    limit_key: str | None
    task_name: str


# 顺序即优先级：转换最轻、解析最贵，抽取依赖解析结果；导出只借道派发，不设闸门。
STREAMS: tuple[Stream, ...] = (
    Stream(
        "convert",
        ("converting", "probing"),
        "convert.max_inflight",
        "tender.worker.tasks.process_file",
    ),
    Stream("parse", ("submitting",), "parse.max_inflight", "tender.worker.tasks.submit_parse"),
    Stream(
        "extract",
        ("extracting",),
        "extract.max_inflight",
        "tender.worker.tasks.extract_fields",
    ),
    Stream("export", ("exporting",), None, "tender.worker.exports.export_project"),
)

_INFLIGHT_SQL = """
    SELECT count(*) FROM job
    WHERE company_id = :company_id
      AND status IN ('pending', 'submitting', 'running')
      AND finished_at IS NULL
      AND dispatched_at IS NOT NULL
      AND stage IN ({stages})
"""

# LIMIT NULL 在 PostgreSQL 里等价于不限量，导出线靠它一次派发完。
_PENDING_SQL = """
    SELECT id FROM job
    WHERE company_id = :company_id
      AND status = 'pending'
      AND finished_at IS NULL
      AND dispatched_at IS NULL
      AND stage IN ({stages})
    ORDER BY created_at, id
    LIMIT :max_rows
    FOR UPDATE SKIP LOCKED
"""

_MARK_DISPATCHED_SQL = """
    UPDATE job SET dispatched_at = now(), updated_at = now()
    WHERE id = :job_id AND dispatched_at IS NULL
"""


def registry() -> ConfigRegistry:
    """进程内单例：beat 每 5 秒跑一次，不该每次都新建 Redis 连接。"""
    global _registry
    if _registry is None:
        _registry = ConfigRegistry(_engine, RedisConfigCache())
    return _registry


def _stage_list(stream: Stream) -> str:
    """把 stage 常量拼成 IN 列表。

    stage 来自代码里的 `STREAMS`（不是请求参数），拼进 SQL 没有注入面；
    这样也避免依赖驱动对 Python 数组的适配，换驱动时行为一致。
    """
    return ", ".join("'" + stage + "'" for stage in stream.stages)


def capacity(limit: int | None, inflight: int) -> int | None:
    """这一轮还能派发几个；None 表示不限（导出线）。"""
    if limit is None:
        return None
    return max(0, int(limit) - max(0, int(inflight)))


def dispatch_stream(stream: Stream, limit: int | None, company_id: int) -> int:
    """按差额派发一条线，返回实际投递数。

    消息在事务提交前发出：若提交失败，job 行上不会留下 dispatched_at，
    下一 tick 会重发——任务侧有 advisory lock 与状态判断挡住重复执行（`_serialize_job`），
    而"少发一次"会导致任务卡在 pending 直到下次改配置，代价更大。
    """
    sent = 0
    with _engine.begin() as connection:
        stages = _stage_list(stream)
        inflight = int(
            connection.execute(
                text(_INFLIGHT_SQL.format(stages=stages)),
                {"company_id": company_id},
            ).scalar_one()
        )
        room = capacity(limit, inflight)
        if room == 0:
            return 0
        candidates = (
            connection.execute(
                text(_PENDING_SQL.format(stages=stages)),
                {"company_id": company_id, "max_rows": room},
            )
            .mappings()
            .all()
        )
        for row in candidates:
            try:
                celery_app.send_task(stream.task_name, args=[row["id"]])
            except Exception as exc:
                # broker 不可用时留待下一 tick；已发出去的消息不受影响。
                logger.warning("派发 %s 任务失败，下个 tick 重试：%s", stream.name, exc)
                break
            connection.execute(text(_MARK_DISPATCHED_SQL), {"job_id": row["id"]})
            sent += 1
    return sent


@celery_app.task(bind=True, name="tender.worker.dispatch.dispatch_pending", max_retries=0)
def dispatch_pending(self: Any) -> dict[str, int]:
    """beat 每 5 秒唤醒；实际间隔由 `dispatch.interval_seconds` 决定（只能拉长）。"""
    global _last_run_at
    company_id = settings.company_id()
    resolved = registry().resolved(company_id)
    interval = float(resolved.get("dispatch.interval_seconds") or 5)
    now = time.monotonic()
    if now - _last_run_at < interval:
        return {}
    _last_run_at = now

    dispatched: dict[str, int] = {}
    for stream in STREAMS:
        limit = None if stream.limit_key is None else int(resolved[stream.limit_key])
        count = dispatch_stream(stream, limit, company_id)
        if count:
            dispatched[stream.name] = count
    return dispatched
