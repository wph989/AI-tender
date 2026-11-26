"""模块运行状态机（``ports/repository/agent_runtime`` 的实现）。

一次模块执行的配额、租约、fencing 都靠 PostgreSQL 的 advisory lock 与 ``pg_locks``
系统目录表达，这些对象没有 ORM 映射，也不该有（见 ``knowledge.py`` 顶部同样的取舍）。
因此**本文件是唯一允许出现裸 SQL 的业务访问实现**，且裸 SQL 只用于 advisory lock、
``pg_locks`` 与跨行 ``UPDATE ... FROM`` 的原子抢槽；其余业务表读写一律走 typed declarative。
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, case, func, insert, literal, select, text, update
from sqlalchemy.dialects.postgresql import INTERVAL
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.pool import NullPool

from tender.adapters.pg.locks import (
    acquire_xact_lock_id,
    try_acquire_xact_lock,
)
from tender.adapters.pg.models import (
    AgentModuleRun,
    AgentRunEvent,
    AnalysisModule,
    AnalysisReport,
    LlmCallLog,
)
from tender.adapters.pg.models.analysis import AgentCallAttempt, AgentModelInvocation
from tender.adapters.pg.session import create_pg_engine

# 双整数 advisory lock 与旧 hashtextextended 锁处于不同空间，避免业务 ID 意外撞锁。
QUOTA_NAMESPACE = 16843009

_LEASE_WINDOW = literal("45 seconds", type_=INTERVAL)

# 报告执行锁：控制器持有整个执行周期，键与取消/补跑检查一致。
_REPORT_LOCK_KEY = "analysis_report:{}"

# 下面这几条必须与 pg_locks 联合判断「是否还有执行者持有配额锁」，故保留裸 SQL。
# 判断「无执行者」是跨进程语义，拆分成分步查询会留下先判断后被占用的竞态窗口。
# pg_locks可见整个实例；配额及所有权只认当前数据库，否则另一库的同号运行会误占或冒用锁。
_OCCUPIED_SQL = """
SELECT count(*) FROM pg_locks l
JOIN agent_module_run a ON a.id=l.objid::bigint
WHERE l.locktype='advisory' AND l.classid=:ns AND l.objsubid=2
  AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
  AND l.granted AND a.company_id=:company
"""

_REAP_SQL = """
UPDATE agent_module_run a SET status='pending',owner=NULL,lease_until=NULL
FROM analysis_module m
WHERE a.module_id=m.id AND m.report_id=:report AND a.status='running'
  AND a.lease_until IS NOT NULL AND a.lease_until<now()
  AND NOT EXISTS (SELECT 1 FROM pg_locks l WHERE l.locktype='advisory'
    AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
    AND l.classid=:ns AND l.objid=a.id AND l.objsubid=2 AND l.granted)
RETURNING a.module_id
"""

_REQUEUE_SQL = """
UPDATE agent_module_run a SET status='pending',owner=NULL,lease_until=NULL
FROM analysis_module m
WHERE a.module_id=m.id AND m.report_id=:report AND a.status='running'
  AND NOT EXISTS (SELECT 1 FROM pg_locks l WHERE l.locktype='advisory'
    AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
    AND l.classid=:ns AND l.objid=a.id AND l.objsubid=2 AND l.granted)
RETURNING a.module_id
"""

_FIRST_WAITING_SQL = """
SELECT a.id FROM agent_module_run a
JOIN analysis_module m ON m.id=a.module_id WHERE m.report_id=:report
  AND a.status IN ('pending','running') AND NOT EXISTS (
    SELECT 1 FROM pg_locks l WHERE l.locktype='advisory' AND l.classid=:ns
      AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
      AND l.objid=a.id AND l.objsubid=2 AND l.granted)
ORDER BY a.started_at IS NULL,a.id LIMIT 1
"""

_CANCEL_RUNS_SQL = """
UPDATE agent_module_run a SET status='canceled',
error_message='用户取消任务',finished_at=now(),lease_until=NULL,owner=NULL
FROM analysis_module m WHERE a.module_id=m.id AND m.report_id=:id
AND a.status IN ('pending','running') AND NOT EXISTS (
    SELECT 1 FROM pg_locks l WHERE l.locktype='advisory' AND l.classid=:ns
    AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
    AND l.objid=a.id AND l.objsubid=2 AND l.granted
)
"""

_EXECUTION_ACTIVE_SQL = """
SELECT EXISTS (
SELECT 1 FROM pg_locks l WHERE l.locktype='advisory' AND l.granted
AND l.pid <> pg_backend_pid()
AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database()) AND (
    (l.objsubid=1
     AND l.classid=((hashtextextended(:key,0) >> 32) & 4294967295)::oid
     AND l.objid=(hashtextextended(:key,0) & 4294967295)::oid)
    OR (l.objsubid=2 AND l.classid=:ns AND l.objid IN (
        SELECT a.id FROM agent_module_run a JOIN analysis_module m ON m.id=a.module_id
        WHERE m.report_id=:id
    ))))
"""


def lock_project(connection: Connection, project_id: int) -> None:
    """会话级 advisory 锁串行化同项目的发布与补跑；跨进程也需要，因此不用行锁。"""
    acquire_xact_lock_id(connection, project_id)


def try_lock_report_execution(connection: Connection, report_id: int) -> bool:
    """尝试立刻取得报告执行锁；控制器仍持有时返回 ``False``，调用方应让用户等待。"""
    return try_acquire_xact_lock(connection, _REPORT_LOCK_KEY.format(report_id))


def execution_active(connection: Connection, report_id: int) -> bool:
    """取消后仍须等待旧控制器和模块释放锁，才能让新 attempt 接管同一报告。"""
    return bool(
        connection.execute(
            text(_EXECUTION_ACTIVE_SQL),
            {
                "id": report_id,
                "ns": QUOTA_NAMESPACE,
                "key": _REPORT_LOCK_KEY.format(report_id),
            },
        ).scalar_one()
    )


def requeue_unlocked_runs(connection: Connection, report_id: int) -> None:
    """控制器恢复后显式显示等待配额，保留线程/计数/首启时限。"""
    ids = (
        connection.execute(
            text(_REQUEUE_SQL), {"report": report_id, "ns": QUOTA_NAMESPACE}
        )
        .scalars()
        .all()
    )
    if ids:
        connection.execute(
            update(AnalysisModule)
            .where(AnalysisModule.id.in_(list(ids)))
            .values(status="pending")
        )


def cancel_unlocked_runs(connection: Connection, report_id: int) -> None:
    """调用方先锁报告；无执行者的排队/遗留运行立即终止，有锁的运行由心跳退出。"""
    connection.execute(
        text(_CANCEL_RUNS_SQL), {"id": report_id, "ns": QUOTA_NAMESPACE}
    )
    connection.execute(
        update(AnalysisModule)
        .where(
            AnalysisModule.report_id == report_id,
            AnalysisModule.status.in_(("pending", "running")),
            ~select(AgentModuleRun.id)
            .where(
                AgentModuleRun.module_id == AnalysisModule.id,
                AgentModuleRun.status == "running",
            )
            .exists(),
        )
        .values(status="canceled", error_message="用户取消任务")
    )


class AgentRunStore:
    """按公司收窄的模块运行状态机；``store`` 提供引擎与公司上下文。"""

    def __init__(self, store: Any, report: dict[str, Any], run: dict[str, Any]) -> None:
        self.store = store
        self.engine: Engine = store.engine
        self.report, self.run = report, run
        self.owner = str(uuid4())
        self.lock_connection: Connection | None = None
        # 锁连接不能吃掉业务连接池，否则达到并发上限后心跳/预算查询会互相等连接。
        self.lock_engine = create_pg_engine(self.engine.url, poolclass=NullPool)

    def event(self, kind: str, detail: dict[str, Any] | None = None) -> None:
        self.store.append_run_event(self.run["id"], kind, detail)

    def claim(self) -> bool:
        resuming = self.run.get("started_at") is not None
        conn = self.lock_engine.connect()
        acquired = False
        try:
            with conn.begin():
                # 所有 worker 先串行检查总占用再取槽；降低配置后先排空旧占用才接新任务。
                conn.execute(text("SELECT pg_advisory_xact_lock(:ns, 0)"), {"ns": QUOTA_NAMESPACE})
                # 与取消串行化：取消落库后，已排队的协程不能重新领取任务。
                status = conn.execute(
                    select(AnalysisReport.status)
                    .where(AnalysisReport.id == self.report["id"])
                    .with_for_update()
                ).scalar_one_or_none()
                if status not in {"waiting", "pending", "running"}:
                    raise InterruptedError("报告已取消或不再执行")
                values = self.store.resolved_config()
                occupied = conn.execute(
                    text(_OCCUPIED_SQL),
                    {"ns": QUOTA_NAMESPACE, "company": self.store.company_id},
                ).scalar_one()
                if occupied >= values["analysis.max_inflight"]:
                    return False
                # 先收殓无执行者的僵尸运行：租约已过期且没有任何进程持有配额锁，说明原
                # 执行者已经不在（异常收尾失败、进程被杀）。不降级的话它会一直占据下面
                # 「本报告最靠前的待执行运行」这个名次，使后面的模块每次抢槽都被拒绝。
                reaped = (
                    conn.execute(
                        text(_REAP_SQL),
                        {"report": self.report["id"], "ns": QUOTA_NAMESPACE},
                    )
                    .scalars()
                    .all()
                )
                if reaped:
                    conn.execute(
                        update(AnalysisModule)
                        .where(AnalysisModule.id.in_(list(reaped)))
                        .values(status="pending")
                    )
                # 同报告优先恢复已开始的线程，再按模块顺序取槽，避免旧任务因抢锁抖动饿死。
                first = conn.execute(
                    text(_FIRST_WAITING_SQL),
                    {"report": self.report["id"], "ns": QUOTA_NAMESPACE},
                ).scalar_one_or_none()
                if first != self.run["id"]:
                    return False
                acquired = conn.execute(
                    text("SELECT pg_try_advisory_lock(:ns,:id)"),
                    {"ns": QUOTA_NAMESPACE, "id": self.run["id"]},
                ).scalar_one()
                if not acquired:
                    return False
                table = AgentModuleRun.__table__
                applied = conn.execute(
                    update(AgentModuleRun)
                    .where(
                        AgentModuleRun.id == self.run["id"],
                        AgentModuleRun.status.in_(("pending", "running")),
                    )
                    .values(
                        status="running",
                        owner=UUID(self.owner),
                        lease_until=func.now() + _LEASE_WINDOW,
                        started_at=func.coalesce(AgentModuleRun.started_at, func.now()),
                        deadline_at=func.coalesce(
                            AgentModuleRun.deadline_at,
                            func.now()
                            + func.make_interval(
                                0, 0, 0, 0, 0, 0, self.run["limits"]["timeout_seconds"]
                            ),
                        ),
                    )
                    .returning(AgentModuleRun.id)
                ).scalar_one_or_none()
                if applied is None:
                    raise InterruptedError("模块已有终态")
                # 模块键在 analysis_module 上，UPDATE 的 RETURNING 取不到，必须回读一次：
                # 用例层按 ``module_key`` 组织运行（技能、事件、恢复标记都要它）。
                row = (
                    conn.execute(
                        select(*table.c, AnalysisModule.module_key)
                        .join(AnalysisModule, AnalysisModule.id == table.c.module_id)
                        .where(table.c.id == self.run["id"])
                    )
                    .mappings()
                    .one()
                )
                self.run = dict(row)
                if resuming:
                    # 已独占旧运行后才释放悬挂预占；已保存有效返回的请求可直接补结算。
                    self._recover_calls(conn)
                conn.execute(
                    update(AnalysisModule)
                    .where(AnalysisModule.id == self.run["module_id"])
                    .values(status="running")
                )
            self.lock_connection = conn
            self._refresh_counts()
            self.event(
                "resumed" if resuming else "started",
                {"thread_id": self.run["thread_id"], "owner": self.owner},
            )
            return True
        finally:
            if self.lock_connection is None:
                if acquired:
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:ns,:id)"),
                        {"ns": QUOTA_NAMESPACE, "id": self.run["id"]},
                    )
                    conn.commit()
                conn.close()

    def _recover_calls(self, conn: Connection) -> None:
        """恢复与到期收尾共用同一结算事务，不能留下未回传请求占用成功额度。"""
        windows = conn.execute(select(AgentModelInvocation.progress).where(
            AgentModelInvocation.run_id == self.run["id"],
        )).scalars().all()
        for window in windows:
            record = window.get("success_record")
            if record:
                self._settle(conn, "model",
                             f"{record['invocation_id']}:{record['request_ordinal']}",
                             "ok", record)
        conn.execute(update(AgentCallAttempt).where(
            AgentCallAttempt.run_id == self.run["id"],
            AgentCallAttempt.status == "running",
        ).values(status="unknown", detail={"reason": "旧执行者失联，结果未知"}))
        # 调用方已独占旧模块或原子终止无执行者的排队行；未回传的请求必须显式标为未知。
        module_key = self.run.get("module_key") or conn.execute(
            select(AnalysisModule.module_key).where(AnalysisModule.id == self.run["module_id"]),
        ).scalar_one()
        purpose = (
            f"analysis:{self.report['id']}:{module_key}"
            f":{self.run['attempt']}"
        )
        unknown = (
            conn.execute(
                update(LlmCallLog)
                .where(
                    LlmCallLog.status == "running",
                    LlmCallLog.purpose == purpose,
                )
                .values(
                    status="unknown",
                    error_message="worker中断，供应商结果未知；释放成功额度预占",
                )
                .returning(LlmCallLog.id)
            )
            .scalars()
            .all()
        )
        if unknown:
            conn.execute(insert(AgentRunEvent).values(
                run_id=self.run["id"], kind="requests_unknown", detail={"call_ids": list(unknown)},
            ))

    def guard(self) -> None:
        if self._guard_execution() <= datetime.now(UTC):
            raise TimeoutError("模块总时长预算已耗尽，恢复不会重置时限")

    def guard_settlement(self) -> None:
        self._guard_execution()

    def _guard_execution(self) -> datetime:
        # 单独开短连接复核：锁连接随时可能被判定失效，不能拿它证明自己仍然合法。
        with self.engine.connect() as conn:
            deadline = conn.execute(
                text("""SELECT a.deadline_at FROM agent_module_run a
                WHERE a.id=:id AND a.owner=CAST(:owner AS UUID) AND a.status='running'
                  AND a.lease_until>now() AND EXISTS (SELECT 1 FROM pg_locks l
                    WHERE l.locktype='advisory' AND l.classid=:ns AND l.objid=a.id
                      AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
                      AND l.objsubid=2 AND l.granted)"""),
                {"id": self.run["id"], "owner": self.owner, "ns": QUOTA_NAMESPACE},
            ).scalar_one_or_none()
        if deadline is None:
            raise InterruptedError("模块租约或配额锁已失效")
        return deadline

    def heartbeat(self) -> None:
        # 原连接断开时即使连接池能重连也不延续所有权，防止旧执行者越过 fencing。
        if self.lock_connection is None or self.lock_connection.invalidated:
            raise InterruptedError("模块配额连接已断开")
        self.lock_connection.execute(text("SELECT 1"))
        self.lock_connection.commit()
        self.guard()
        with self.engine.begin() as conn:
            conn.execute(
                update(AgentModuleRun)
                .where(
                    AgentModuleRun.id == self.run["id"],
                    AgentModuleRun.owner == UUID(self.owner),
                    AgentModuleRun.status == "running",
                )
                .values(lease_until=func.now() + _LEASE_WINDOW)
            )

    def load_invocation(self, key: str) -> dict:
        with self.engine.connect() as conn:
            return conn.execute(select(AgentModelInvocation.progress).where(
                AgentModelInvocation.run_id == self.run["id"],
                AgentModelInvocation.call_key == key,
            )).scalar_one_or_none() or {}

    def save_invocation(self, key: str, value: dict) -> None:
        # 请求发送前由 reserve 复核时限。已返回的回执在到期后仍须在有效所有权内落库。
        self.guard_settlement()
        with self.engine.begin() as conn:
            self._lock_owned(conn)
            statement = pg_insert(AgentModelInvocation).values(
                run_id=self.run["id"], call_key=key, progress=value,
            )
            conn.execute(statement.on_conflict_do_update(
                index_elements=["run_id", "call_key"], set_={"progress": value},
            ))

    def other_invocation_wait(self, key: str) -> float:
        # 只取等待字段，避免每次逻辑调用重读其余窗口的对话和模型回执。
        progress = AgentModelInvocation.progress
        with self.engine.connect() as conn:
            rows = conn.execute(select(
                progress["rate_waited"],
                case((progress["rate_waited"].astext.is_(None), progress["rate_state"])),
            ).where(
                AgentModelInvocation.run_id == self.run["id"],
                AgentModelInvocation.call_key != key,
            )).all()
        return sum(float(waited) if waited is not None else sum(
            candidate.get("waited", 0.0) for candidate in (legacy or {}).values()
        ) for waited, legacy in rows)

    def _lock_owned(self, conn: Connection) -> dict:
        row = conn.execute(select(AgentModuleRun).where(
            AgentModuleRun.id == self.run["id"],
            AgentModuleRun.owner == UUID(self.owner),
            AgentModuleRun.status == "running",
            AgentModuleRun.lease_until > func.now(),
        ).with_for_update()).mappings().one_or_none()
        if row is None:
            raise InterruptedError("模块所有权已改变，不能结算旧调用")
        locked = conn.execute(text("""SELECT 1 FROM pg_locks l
            WHERE l.locktype='advisory' AND l.classid=:ns AND l.objid=:id
              AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
              AND l.objsubid=2 AND l.granted"""),
            {"ns": QUOTA_NAMESPACE, "id": self.run["id"]}).first()
        if locked is None:
            raise InterruptedError("模块配额锁已失效，不能结算旧调用")
        return dict(row)

    def _refresh_counts(self) -> None:
        # 仅在事务提交后更新内存预算；回滚不能留下虚假的成功数。
        with self.engine.connect() as conn:
            counts = conn.execute(select(
                AgentModuleRun.model_calls, AgentModuleRun.tool_calls,
                AgentModuleRun.successful_model_calls, AgentModuleRun.successful_tool_calls,
            ).where(AgentModuleRun.id == self.run["id"])).mappings().one()
        for key, value in counts.items():
            if value is not None:
                self.run[key] = max(self.run.get(key) or 0, value)

    def reserve(self, kind: str, call_key: str | None = None) -> str:
        if kind not in {"model", "tool"}:
            raise ValueError("未知预算类型")
        call_key = call_key or str(uuid4())
        column = kind + "_calls"
        field = getattr(AgentModuleRun, column)
        with self.engine.begin() as conn:
            row = self._lock_owned(conn)
            previous = conn.execute(select(AgentCallAttempt.status).where(
                AgentCallAttempt.run_id == self.run["id"], AgentCallAttempt.kind == kind,
                AgentCallAttempt.call_key == call_key,
            )).scalar_one_or_none()
            if previous == "unknown" and kind == "tool":
                # 失联工具重新执行是新的实际尝试；旧未知回执不能被改写成成功。
                call_key += ":retry:" + str(uuid4())
            elif previous is not None:
                return call_key
            pending = conn.execute(select(func.count()).select_from(AgentCallAttempt).where(
                AgentCallAttempt.run_id == self.run["id"], AgentCallAttempt.kind == kind,
                AgentCallAttempt.status == "running",
            )).scalar_one()
            successes = row["successful_" + column]
            used = row[column] if successes is None else successes + pending
            if used >= row["limits"]["max_" + column] or row["deadline_at"] <= datetime.now(UTC):
                label = "模型请求" if kind == "model" else "工具调用"
                from tender.domain.shared.errors import BudgetExhausted

                raise BudgetExhausted(f"模块{label}预算已耗尽")
            conn.execute(insert(AgentCallAttempt).values(
                run_id=self.run["id"], kind=kind, call_key=call_key, status="running", detail={},
            ))
            conn.execute(update(AgentModuleRun).where(
                AgentModuleRun.id == self.run["id"],
            ).values({field: field + 1}))
            conn.execute(
                insert(AgentRunEvent).values(
                    run_id=self.run["id"], kind=kind + "_reserved",
                    detail={"ordinal": row[column] + 1, "call_key": call_key},
                )
            )
        self._refresh_counts()
        return call_key

    def _settle(self, conn: Connection, kind: str, call_key: str, status: str,
                detail: dict) -> bool:
        changed = conn.execute(update(AgentCallAttempt).where(
            AgentCallAttempt.run_id == self.run["id"], AgentCallAttempt.kind == kind,
            AgentCallAttempt.call_key == call_key, AgentCallAttempt.status == "running",
        ).values(status=status, detail=detail).returning(AgentCallAttempt.call_key)).first()
        if changed is None:
            return False
        updates = {}
        if status == "ok":
            field = getattr(AgentModuleRun, "successful_" + kind + "_calls")
            updates[field] = field + 1
        if kind == "model":
            updates[AgentModuleRun.prompt_tokens] = (AgentModuleRun.prompt_tokens
                                                     + (detail.get("prompt_tokens") or 0))
            updates[AgentModuleRun.completion_tokens] = (AgentModuleRun.completion_tokens
                                                         + (detail.get("completion_tokens") or 0))
        if updates:
            conn.execute(update(AgentModuleRun).where(
                AgentModuleRun.id == self.run["id"],
            ).values(updates))
        return True

    def record_call(self, record: dict[str, Any]) -> None:
        # 运行行锁使预占、成功额度和用量幂等结算；失败尝试仍保留审计。
        with self.engine.begin() as conn:
            self._lock_owned(conn)
            call_key = (f"{record['invocation_id']}:{record['request_ordinal']}"
                        if record.get("invocation_id") else conn.execute(
                            select(AgentCallAttempt.call_key).where(
                                AgentCallAttempt.run_id == self.run["id"],
                                AgentCallAttempt.kind == "model",
                                AgentCallAttempt.status == "running",
                            ).order_by(AgentCallAttempt.call_key).limit(1),
                        ).scalar_one_or_none())
            if call_key is None or not self._settle(
                conn, "model", call_key, record["status"], record,
            ):
                return
            conn.execute(
                insert(AgentRunEvent).values(
                    run_id=self.run["id"], kind="model_result", detail=record
                )
            )
        self._refresh_counts()

    def save(self, state: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            previous = conn.execute(
                select(AgentModuleRun.state)
                .where(
                    AgentModuleRun.id == self.run["id"],
                    AgentModuleRun.owner == UUID(self.owner),
                    AgentModuleRun.status == "running",
                )
                .with_for_update()
            ).scalar_one_or_none()
            if previous is None:
                raise InterruptedError("模块所有权已改变，不能写入旧状态")
            self._lock_owned(conn)
            conn.execute(
                update(AgentModuleRun)
                .where(AgentModuleRun.id == self.run["id"])
                .values(state=state)
            )
            for call_id in (
                (state.get("tool_results", {}).keys() - previous.get("tool_results", {}).keys())
                | (state.get("tool_outcomes", {}).keys() - previous.get("tool_outcomes", {}).keys())
            ):
                message = state.get("tool_results", {}).get(call_id, {}).get("data", {})
                outcome = state.get("tool_outcomes", {}).get(call_id,
                    "error" if message.get("status") == "error" else "ok")
                attempt_key = state.get("tool_call_keys", {}).get(call_id, call_id)
                self._settle(conn, "tool", attempt_key, outcome, {"name": message.get("name")})
                # 公共审计只记录动作和结果状态；正文与错误草稿仍留在受控的证据账。
                conn.execute(
                    insert(AgentRunEvent).values(
                        run_id=self.run["id"],
                        kind="tool_result",
                        detail={
                            "tool_call_id": call_id,
                            "name": message.get("name"),
                            "status": "success" if outcome == "ok" else outcome,
                        },
                    )
                )
        self._refresh_counts()

    def finish(
        self,
        status: str,
        error: str | None = None,
        *,
        publish: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
    ) -> None:
        publish_error: Exception | None = None
        should_publish = publish is not None
        with self.engine.begin() as conn:
            report_status = conn.execute(
                select(AnalysisReport.status)
                .where(AnalysisReport.id == self.report["id"])
                .with_for_update()
            ).scalar_one_or_none()
            if status in {"completed", "partial"} and report_status != "running":
                # 与取消 API 串行提交；取消已落库后不能再发布刚完成或部分完成的模块结果。
                status, should_publish, error = "canceled", False, "报告已停止，未发布模块结果"
            row = conn.execute(
                select(AgentModuleRun.id)
                .where(
                    AgentModuleRun.id == self.run["id"],
                    AgentModuleRun.owner == UUID(self.owner),
                    AgentModuleRun.status == "running",
                )
                .with_for_update()
            ).first()
            if row is None:
                return
            conn.execute(update(AgentCallAttempt).where(
                AgentCallAttempt.run_id == self.run["id"], AgentCallAttempt.status == "running",
            ).values(status="unknown", detail={"reason": "运行结束，尚无确定回执"}))
            if state is not None:
                # 到期仅豁免时间，收尾事务仍复核租约和锁；与状态、展示投影一次提交。
                valid = conn.execute(text("""SELECT 1 FROM agent_module_run a
                    WHERE a.id=:id AND a.lease_until>now() AND EXISTS
                    (SELECT 1 FROM pg_locks l WHERE l.locktype='advisory'
                     AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
                     AND l.classid=:ns AND l.objid=a.id AND l.objsubid=2 AND l.granted)"""),
                    {"id": self.run["id"], "ns": QUOTA_NAMESPACE}).first()
                if valid is None:
                    raise InterruptedError("模块租约或配额锁已失效")
            if should_publish and status == "completed":
                # 成果在 savepoint 内发布：业务库缺少 business_data 等新列时只回滚成果，
                # 运行终态照常提交。否则异常会连 UPDATE agent_module_run 一起回滚，留下
                # lease 已过期却永远 status='running' 的僵尸，把该报告后面的模块全部饿死。
                try:
                    with conn.begin_nested():
                        self._publish(conn, publish or {})
                except Exception as exc:
                    publish_error = exc
                    status, error = "failed", f"模块成果发布失败：{str(exc)[:500]}"
            finished = conn.execute(
                update(AgentModuleRun)
                .where(
                    AgentModuleRun.id == self.run["id"],
                    AgentModuleRun.owner == UUID(self.owner),
                )
                .values(
                    status=status,
                    error_message=error,
                    finished_at=func.now(),
                    lease_until=None,
                    **({"state": state} if state is not None else {}),
                )
                .returning(AgentModuleRun.status, AgentModuleRun.error_message,
                           AgentModuleRun.finished_at, AgentModuleRun.state,
                           AgentModuleRun.model_calls, AgentModuleRun.tool_calls,
                           AgentModuleRun.prompt_tokens, AgentModuleRun.completion_tokens)
            ).mappings().one()
            conn.execute(
                update(AnalysisModule)
                .where(AnalysisModule.id == self.run["module_id"])
                .values(status=status, error_message=error)
            )
        # 只有事务成功且所有权仍有效才更新本地终态，供诊断归档采用实际结果和完成时间。
        self.run.update(finished)
        if publish_error is not None:
            with suppress(Exception):
                self.event(
                    "publish_failed",
                    {
                        "error_type": type(publish_error).__name__,
                        "message": str(publish_error)[:500],
                    },
                )
        self.event(status, {"error": error})

    def abandon(self, status: str, error: str | None = None) -> None:
        """异常收尾；尚未领取配额时也要形成终态，否则排队行永远显示等待配额。"""
        if self.lock_connection is not None:
            self.finish(status, error)
            return
        with self.engine.begin() as conn:
            # 到期可在claim前退出，但结算必须先排除仍在执行的旧进程；该锁天然隔离数据库。
            if not conn.execute(text("SELECT pg_try_advisory_xact_lock(:ns,:id)"),
                                {"ns": QUOTA_NAMESPACE, "id": self.run["id"]}).scalar_one():
                return
            changed = conn.execute(
                update(AgentModuleRun)
                .where(
                    AgentModuleRun.id == self.run["id"],
                    AgentModuleRun.status == "pending",
                )
                .values(status=status, error_message=error, finished_at=func.now())
                .returning(AgentModuleRun.module_id, AgentModuleRun.finished_at)
            ).mappings().one_or_none()
            if changed:
                self._recover_calls(conn)
                conn.execute(
                    update(AnalysisModule)
                    .where(AnalysisModule.id == changed["module_id"])
                    .values(status=status, error_message=error)
                )
        if changed:
            self.run.update(status=status, error_message=error, finished_at=changed["finished_at"])
            self._refresh_counts()

    def _publish(self, conn: Connection, publish: dict[str, Any]) -> None:
        """发布通过校验的业务成果；单独成方法以便在 savepoint 内失败即回滚。"""
        conn.execute(
            update(AnalysisModule)
            .where(AnalysisModule.id == self.run["module_id"])
            .values(business_data=publish["business"])
        )

    def release(self) -> None:
        conn, self.lock_connection = self.lock_connection, None
        if conn is not None:
            try:
                if not conn.invalidated:
                    conn.execute(
                        text("SELECT pg_advisory_unlock(:ns,:id)"),
                        {"ns": QUOTA_NAMESPACE, "id": self.run["id"]},
                    )
                    conn.commit()
            finally:
                # 会话锁不能随连接池回收泄漏；断连时 PostgreSQL 自动释放。
                conn.invalidate()
                conn.close()
