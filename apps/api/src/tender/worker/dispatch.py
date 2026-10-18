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

from tender.core import settings
from tender.core.di import create_dispatch_repository, create_worker_config_reader
from tender.ports.configuration.registry import ConfigReader
from tender.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_repository = create_dispatch_repository()
_registry: ConfigReader | None = None
_last_run_at = 0.0


@dataclass(frozen=True, slots=True)
class Stream:
    """一条派发线：哪些 stage 归它管、受哪个上限约束、投递哪个任务。"""

    name: str
    stages: tuple[str, ...]
    limit_key: str | None
    task_name: str


# 顺序即优先级：转换完成后才能解析，专题分析由独立报告调度器管理。
STREAMS: tuple[Stream, ...] = (
    Stream(
        "convert",
        ("converting", "probing"),
        "convert.max_inflight",
        "tender.worker.tasks.process_file",
    ),
    Stream("parse", ("submitting",), "parse.max_inflight", "tender.worker.tasks.submit_parse"),
)


def registry() -> ConfigReader:
    """进程内单例：beat 每秒唤醒，不该每次都新建 Redis 连接。"""
    global _registry
    if _registry is None:
        _registry = create_worker_config_reader()
    return _registry


def capacity(limit: int | None, inflight: int) -> int | None:
    """这一轮还能派发几个；None 表示没有并发限制。"""
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
    with _repository.transaction() as transaction:
        inflight = transaction.inflight(stream.stages, company_id)
        room = capacity(limit, inflight)
        if room == 0:
            return 0
        candidates = transaction.pending(stream.stages, company_id, room)
        for job_id in candidates:
            try:
                celery_app.send_task(stream.task_name, args=[job_id])
            except Exception:
                # broker 不可用时留待下一 tick；已发出去的消息不受影响。
                logger.warning(
                    "dispatch.fail", exc_info=True, extra={"job_id": job_id, "stream": stream.name}
                )
                break
            transaction.mark_dispatched(job_id)
            sent += 1
    return sent


@celery_app.task(bind=True, name="tender.worker.dispatch.dispatch_pending", max_retries=0)
def dispatch_pending(self: Any) -> dict[str, int]:
    """beat 每秒唤醒；实际派发间隔读取当前配置，无需因调小间隔重启beat。"""
    global _last_run_at
    company_id = settings.company_id()
    resolved = registry().resolved(company_id)
    interval = float(resolved["dispatch.interval_seconds"])
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
