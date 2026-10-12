"""持久运行账、动态权限和跨进程硬配额；数据库会话锁存活时绝不抢占。"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.pool import NullPool

from tender.application.analysis_data import display_items, module_data
from tender.application.analysis_research import AgentLimits
from tender.application.knowledge_store import KnowledgeStore, encode
from tender.config.registry import ConfigRegistry

# 双整数 advisory lock 与旧 hashtextextended 锁处于不同空间，避免业务 ID 意外撞锁。
QUOTA_NAMESPACE = 16843009


def limits_snapshot(db: KnowledgeStore) -> dict:
    values = ConfigRegistry(db.engine).resolved(db.company_id)
    return asdict(
        AgentLimits(
            **{
                key: values["analysis." + key]
                for key in asdict(AgentLimits())
                if "analysis." + key in values
            }
        )
    )


def check_report_access(db: KnowledgeStore, report: dict, sources: list[dict]) -> None:
    rows = db.rows(
        """SELECT r.status FROM analysis_report r JOIN project p ON p.id=r.project_id
        WHERE r.id=:id AND r.company_id=:company_id AND p.deleted_at IS NULL""",
        {"id": report["id"]},
    )
    if not rows or rows[0]["status"] not in {"waiting", "pending", "running"}:
        raise InterruptedError("报告已取消或不再执行")
    allowed = db.collections_for_project(report["project_id"])
    if any(s["collection_id"] not in allowed for s in sources):
        raise PermissionError("知识库关联已撤销，停止使用原会话中的资料")
    current = {s["source_id"]: s for s in db.sources(allowed)}
    for source in sources:
        live = current.get(source["source_id"])
        if live is None or any(
            live[k] != source[k]
            for k in (
                "project_id",
                "collection_id",
                "project_file_id",
                "version_id",
                "parse_run_id",
            )
        ):
            raise PermissionError("资料已删除、替换或重新解析，请基于最新版本重新分析")


def requeue_unlocked_runs(conn: Connection, report_id: int) -> None:
    """控制器恢复后显式显示等待配额，保留线程/计数/首启时限。"""
    ids = (
        conn.execute(
            text("""UPDATE agent_module_run a SET status='pending',
        owner=NULL,lease_until=NULL FROM analysis_module m
        WHERE a.module_id=m.id AND m.report_id=:report AND a.status='running'
          AND NOT EXISTS (SELECT 1 FROM pg_locks l WHERE l.locktype='advisory'
            AND l.classid=:ns AND l.objid=a.id AND l.objsubid=2 AND l.granted)
        RETURNING a.module_id"""),
            {"report": report_id, "ns": QUOTA_NAMESPACE},
        )
        .scalars()
        .all()
    )
    if ids:
        conn.execute(
            text("UPDATE analysis_module SET status='pending' WHERE id=ANY(:ids)"), {"ids": ids}
        )


def execution_active(conn: Connection, report_id: int) -> bool:
    """取消后仍须等待旧控制器和模块释放锁，才能让新 attempt 接管同一报告。"""
    return bool(conn.execute(text("""SELECT EXISTS (
        SELECT 1 FROM pg_locks l WHERE l.locktype='advisory' AND l.granted
        AND l.pid <> pg_backend_pid()
        AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database()) AND (
            (l.objsubid=1
             AND l.classid=((hashtextextended(:key,0) >> 32) & 4294967295)::oid
             AND l.objid=(hashtextextended(:key,0) & 4294967295)::oid)
            OR (l.objsubid=2 AND l.classid=:ns AND l.objid IN (
                SELECT a.id FROM agent_module_run a JOIN analysis_module m ON m.id=a.module_id
                WHERE m.report_id=:id
            ))))"""), {
        "id": report_id, "ns": QUOTA_NAMESPACE, "key": f"analysis_report:{report_id}",
    }).scalar_one())


def cancel_unlocked_runs(conn: Connection, report_id: int) -> None:
    """调用方先锁报告；无执行者的排队/遗留运行立即终止，有锁的运行由心跳退出。"""
    conn.execute(text("""UPDATE agent_module_run a SET status='canceled',
        error_message='用户取消任务',finished_at=now(),lease_until=NULL,owner=NULL
        FROM analysis_module m WHERE a.module_id=m.id AND m.report_id=:id
        AND a.status IN ('pending','running') AND NOT EXISTS (
            SELECT 1 FROM pg_locks l WHERE l.locktype='advisory' AND l.classid=:ns
            AND l.objid=a.id AND l.objsubid=2 AND l.granted
        )"""), {"id": report_id, "ns": QUOTA_NAMESPACE})
    conn.execute(text("""UPDATE analysis_module m SET status='canceled',
        error_message='用户取消任务' WHERE report_id=:id AND status IN ('pending','running')
        AND NOT EXISTS (SELECT 1 FROM agent_module_run a
            WHERE a.module_id=m.id AND a.status='running')"""), {"id": report_id})


class AgentRuntime:
    def __init__(self, db: KnowledgeStore, report: dict, run: dict, sources: list[dict]):
        self.db, self.report, self.run, self.sources = db, report, run, sources
        self.owner = str(uuid4())
        self.lock_connection: Connection | None = None
        # 锁连接不能吃掉业务连接池，否则达到并发上限后心跳/预算查询会互相等连接。
        self.lock_engine = create_engine(db.engine.url, poolclass=NullPool)

    def event(self, kind: str, detail: dict | None = None) -> None:
        self.db.execute(
            """INSERT INTO agent_run_event (run_id,kind,detail)
            VALUES (:id,:kind,CAST(:detail AS JSONB))""",
            {"id": self.run["id"], "kind": kind, "detail": encode(detail or {})},
        )

    def claim(self) -> bool:
        check_report_access(self.db, self.report, self.sources)
        resuming = self.run.get("started_at") is not None
        conn = self.lock_engine.connect()
        acquired = False
        try:
            with conn.begin():
                # 所有 worker 先串行检查总占用再取槽；降低配置后先排空旧占用才接新任务。
                conn.execute(text("SELECT pg_advisory_xact_lock(:ns, 0)"), {"ns": QUOTA_NAMESPACE})
                # 与取消串行化：取消落库后，已排队的协程不能重新领取任务。
                status = conn.execute(text(
                    "SELECT status FROM analysis_report WHERE id=:id FOR UPDATE"
                ), {"id": self.report["id"]}).scalar_one()
                if status not in {"waiting", "pending", "running"}:
                    raise InterruptedError("报告已取消或不再执行")
                values = ConfigRegistry(self.db.engine).resolved(self.db.company_id)
                occupied = conn.execute(
                    text("""SELECT count(*) FROM pg_locks l
                    JOIN agent_module_run a ON a.id=l.objid::bigint
                    WHERE l.locktype='advisory' AND l.classid=:ns AND l.objsubid=2
                      AND l.granted AND a.company_id=:company"""),
                    {"ns": QUOTA_NAMESPACE, "company": self.db.company_id},
                ).scalar_one()
                if occupied >= values["analysis.max_inflight"]:
                    return False
                # 同报告优先恢复已开始的线程，再按模块顺序取槽，避免旧任务因抢锁抖动饿死。
                first = conn.execute(
                    text("""SELECT a.id FROM agent_module_run a
                    JOIN analysis_module m ON m.id=a.module_id WHERE m.report_id=:report
                      AND a.status IN ('pending','running') AND NOT EXISTS (
                        SELECT 1 FROM pg_locks l WHERE l.locktype='advisory' AND l.classid=:ns
                          AND l.objid=a.id AND l.objsubid=2 AND l.granted)
                    ORDER BY a.started_at IS NULL,a.id LIMIT 1"""),
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
                row = (
                    conn.execute(
                        text("""UPDATE agent_module_run SET status='running',
                    owner=CAST(:owner AS UUID),lease_until=now()+interval '45 seconds',
                    started_at=COALESCE(started_at,now()),
                    deadline_at=COALESCE(deadline_at,now()+make_interval(secs=>:timeout))
                    WHERE id=:id AND status IN ('pending','running') RETURNING *"""),
                        {
                            "owner": self.owner,
                            "id": self.run["id"],
                            "timeout": self.run["limits"]["timeout_seconds"],
                        },
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    raise InterruptedError("模块已有终态")
                self.run = dict(row)
                if resuming:
                    # 已取得旧模块的独占锁，原执行者不再存活；未回传的请求必须显式标为未知。
                    unknown = (
                        conn.execute(
                            text("""UPDATE llm_call_log l SET status='unknown',
                        error_message='worker中断，供应商结果未知；恢复保留已预占预算'
                        FROM analysis_module m WHERE m.id=:module AND l.status='running'
                          AND l.purpose='analysis:' || m.report_id || ':' || m.module_key
                              || ':' || CAST(:attempt AS TEXT) RETURNING l.id"""),
                            {"module": self.run["module_id"], "attempt": self.run["attempt"]},
                        )
                        .scalars()
                        .all()
                    )
                    if unknown:
                        conn.execute(
                            text("""INSERT INTO agent_run_event(run_id,kind,detail)
                            VALUES (:id,'requests_unknown',CAST(:detail AS JSONB))"""),
                            {"id": self.run["id"], "detail": encode({"call_ids": unknown})},
                        )
                conn.execute(
                    text("UPDATE analysis_module SET status='running' WHERE id=:id"),
                    {"id": self.run["module_id"]},
                )
            self.lock_connection = conn
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

    def guard(self) -> None:
        check_report_access(self.db, self.report, self.sources)
        rows = self.db.rows(
            """SELECT a.deadline_at FROM agent_module_run a
            WHERE a.id=:id AND a.owner=CAST(:owner AS UUID) AND a.status='running'
              AND a.lease_until>now() AND EXISTS (SELECT 1 FROM pg_locks l
                WHERE l.locktype='advisory' AND l.classid=:ns AND l.objid=a.id
                  AND l.objsubid=2 AND l.granted)""",
            {"id": self.run["id"], "owner": self.owner, "ns": QUOTA_NAMESPACE},
        )
        if not rows:
            raise InterruptedError("模块租约或配额锁已失效")
        if rows[0]["deadline_at"] <= datetime.now(UTC):
            raise TimeoutError("模块总时长预算已耗尽，恢复不会重置时限")

    def heartbeat(self) -> None:
        # 原连接断开时即使连接池能重连也不延续所有权，防止旧执行者越过 fencing。
        if self.lock_connection is None or self.lock_connection.invalidated:
            raise InterruptedError("模块配额连接已断开")
        self.lock_connection.execute(text("SELECT 1"))
        self.lock_connection.commit()
        self.guard()
        self.db.execute(
            """UPDATE agent_module_run SET lease_until=now()+interval '45 seconds'
            WHERE id=:id AND owner=CAST(:owner AS UUID) AND status='running'""",
            {"id": self.run["id"], "owner": self.owner},
        )

    def reserve(self, kind: str) -> None:
        self.guard()
        if kind not in {"model", "tool"}:
            raise ValueError("未知预算类型")
        column = kind + "_calls"
        with self.db.engine.begin() as conn:
            row = conn.execute(
                text(f"""UPDATE agent_module_run SET {column}={column}+1
                WHERE id=:id AND owner=CAST(:owner AS UUID) AND status='running'
                  AND {column}<:maximum AND deadline_at>now()
                RETURNING {column}"""),
                {
                    "id": self.run["id"],
                    "owner": self.owner,
                    "maximum": self.run["limits"]["max_" + column],
                },
            ).first()
            if row is None:
                label = "模型请求" if kind == "model" else "工具调用"
                raise ValueError(f"模块{label}预算已耗尽")
            self.run[column] = row[0]
            conn.execute(
                text("""INSERT INTO agent_run_event(run_id,kind,detail)
                VALUES (:id,:kind,CAST(:detail AS JSONB))"""),
                {
                    "id": self.run["id"],
                    "kind": kind + "_reserved",
                    "detail": encode({"ordinal": row[0]}),
                },
            )

    def record_call(self, record) -> None:
        # unknown 请求也保留已预占次数，不能靠中断把不确定的供应商请求当作免费。
        with self.db.engine.begin() as conn:
            conn.execute(
                text("""UPDATE agent_module_run
                SET prompt_tokens=prompt_tokens+:input,completion_tokens=completion_tokens+:output
                WHERE id=:id"""),
                {
                    "id": self.run["id"],
                    "input": record.prompt_tokens or 0,
                    "output": record.completion_tokens or 0,
                },
            )
            conn.execute(
                text("""INSERT INTO agent_run_event(run_id,kind,detail)
                VALUES (:id,'model_result',CAST(:detail AS JSONB))"""),
                {"id": self.run["id"], "detail": encode(asdict(record))},
            )

    def save(self, state: dict) -> None:
        self.guard()
        params = {"id": self.run["id"], "owner": self.owner}
        with self.db.engine.begin() as conn:
            previous = conn.execute(
                text("""SELECT state FROM agent_module_run
                WHERE id=:id AND owner=CAST(:owner AS UUID) AND status='running' FOR UPDATE"""),
                params,
            ).scalar_one_or_none()
            if previous is None:
                raise InterruptedError("模块所有权已改变，不能写入旧状态")
            conn.execute(
                text("UPDATE agent_module_run SET state=CAST(:state AS JSONB) WHERE id=:id"),
                params | {"state": encode(state)},
            )
            if state.get("loaded_skill") and not previous.get("loaded_skill"):
                conn.execute(
                    text("""INSERT INTO agent_run_event(run_id,kind,detail)
                    VALUES (:id,'skill_loaded',CAST(:detail AS JSONB))"""),
                    {"id": self.run["id"], "detail": encode(state["loaded_skill"])},
                )
            if state.get("staged_items_verified"):
                # 运行状态与成果分开：未完成/失败仍可展示已核实字段，且与检查点同事务保存。
                conn.execute(
                    text("""UPDATE analysis_module SET items=CAST(:items AS JSONB),
                        business_data=CAST(:business AS JSONB) WHERE id=:id"""),
                    {
                        "id": self.run["module_id"],
                        "business": encode(module_data(state)),
                        "items": encode(display_items([
                            item for item in state.get("staged_items", [])
                            if item.get("verification") == "supported"
                        ])),
                    },
                )
            for call_id in (
                state.get("tool_results", {}).keys() - previous.get("tool_results", {}).keys()
            ):
                message = state["tool_results"][call_id]["data"]
                # 公共审计只记录动作和结果状态；正文与错误草稿仍留在受控的证据账。
                conn.execute(
                    text("""INSERT INTO agent_run_event(run_id,kind,detail)
                    VALUES (:id,'tool_result',CAST(:detail AS JSONB))"""),
                    {
                        "id": self.run["id"],
                        "detail": encode(
                            {
                                "tool_call_id": call_id,
                                "name": message.get("name"),
                                "status": message.get("status", "success"),
                            }
                        ),
                    },
                )

    def finish(self, status: str, error: str | None = None, draft: dict | None = None) -> None:
        if status == "completed":
            self.guard()
        with self.db.engine.begin() as conn:
            report_status = conn.execute(
                text("SELECT status FROM analysis_report WHERE id=:id FOR UPDATE"),
                {"id": self.report["id"]},
            ).scalar_one()
            if status == "completed" and report_status != "running":
                # 与取消 API 串行提交；取消已落库后不能再发布刚完成的模块结果。
                status, draft, error = "canceled", None, "报告已停止，未发布模块结果"
            row = conn.execute(
                text("""UPDATE agent_module_run SET status=:status,
                error_message=:error,finished_at=now(),lease_until=NULL
                WHERE id=:id AND owner=CAST(:owner AS UUID) AND status='running' RETURNING id"""),
                {"id": self.run["id"], "owner": self.owner, "status": status, "error": error},
            ).first()
            if row is None:
                return
            conn.execute(
                text("""UPDATE analysis_module SET status=:status,error_message=:error,
                items=CASE WHEN :status='completed' THEN CAST(:items AS JSONB) ELSE items END,
                business_data=CASE WHEN :status='completed' THEN CAST(:business AS JSONB)
                                  ELSE business_data END
                WHERE id=:id"""),
                {
                    "id": self.run["module_id"],
                    "status": status,
                    "error": error,
                    "items": encode(display_items((draft or {}).get("fields", []))),
                    "business": encode((draft or {}).get("business_data", {})),
                },
            )
            if draft is not None:
                conn.execute(
                    text("DELETE FROM knowledge_relation WHERE module_id=:id"),
                    {"id": self.run["module_id"]},
                )
                for rel in draft["relations"]:
                    conn.execute(
                        text("""INSERT INTO knowledge_relation
                        (report_id,module_id,subject,predicate,object,scope,condition,citations,verified)
                        VALUES (:report,:module,:subject,:predicate,:object,:scope,:condition,
                                CAST(:citations AS JSONB),true)"""),
                        {
                            **rel,
                            "report": self.report["id"],
                            "module": self.run["module_id"],
                            "citations": encode(rel["citations"]),
                        },
                    )
        self.event(status, {"error": error})

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
