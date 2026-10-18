"""知识库、资料来源与分析报告的数据访问端口。

方法命名按**用例语义**而不是 SQL 片段：``sources`` 是「这批知识库当前可用的资料」，
``publish_snapshot`` 是「把报告成果固化成一份正式业务数据快照」。实现怎么拼查询、
用哪些索引，是 ``adapters/pg`` 的事——换一个存储实现（内存、只读副本）不该动用例层。

返回值统一是 ``dict`` / ``list[dict]``，键名与既有调用点一致。这是刻意的：SQLAlchemy
模型带 ``Mapped[]`` 声明与关系属性，用它当返回值等于把持久化细节塞进用例层
（docs/工程/10 第 4.2 节第 1 条）。取数走 typed declarative，出口是普通字典。
"""

from __future__ import annotations

from typing import Any, Protocol

from tender.ports.configuration.registry import ActiveConfig
from tender.ports.repository.analysis.runtime import AgentRunStore


class KnowledgeSession(Protocol):
    """一个业务库事务。用例层把「要在同一事务里做的事」编排在 ``with`` 里。

    为什么需要它：发布快照与领取配额都要求多条语句原子提交（中间不能被取消或补跑插队），
    而事务边界属于实现细节，不能由用例层 ``begin()``。
    """

    def __enter__(self) -> KnowledgeSession: ...

    def __exit__(self, *exc: object) -> None: ...

    def lock_project(self, project_id: int) -> None:
        """取项目的会话锁，串行化同项目的发布与取消。"""
        ...

    def lock_report(self, report_id: int) -> dict[str, Any]:
        """锁定报告行并返回全字段；报告不存在时抛 ``LookupError``。"""
        ...

    def start_report(
        self,
        report_id: int,
        *,
        source_snapshot: list[dict[str, Any]],
        reference_snapshot: list[dict[str, Any]],
    ) -> bool:
        """把等待/排队中的报告置为执行中并固定资料快照；已被取消时返回 ``False``。"""
        ...

    def requeue_unlocked_runs(self, report_id: int) -> None:
        """把没有执行者持锁的在途运行退回等待，避免僵尸运行长期占住执行名额。"""
        ...

    def ensure_modules(self, report_id: int, modules: dict[str, str]) -> list[dict[str, Any]]:
        """确保报告的模块行存在（标题随 Skill 更新），返回各模块当前 ``id`` / ``status``。"""
        ...

    def ensure_module_run(
        self,
        module_id: int,
        *,
        company_id: int,
        thread_id: str,
        limits: dict[str, Any],
    ) -> None:
        """确保首次 attempt（=1）的运行账存在；重复投递或补跑不覆盖既有行。"""
        ...

    def report_runs(self, report_id: int) -> list[dict[str, Any]]:
        """报告下全部模块运行（含历史 attempt），按 id 升序。"""
        ...

    def report_modules(self, report_id: int) -> list[dict[str, Any]]:
        """报告下全部模块及其成果，按 id 升序。"""
        ...

    def snapshot_by_manifest(self, report_id: int, manifest_hash: str) -> dict[str, Any] | None:
        """已存在同一份成果指纹的快照时直接复用，不重复发布。"""
        ...

    def lot_id_for_code(self, project_id: int, code: str) -> int | None:
        """按标段编号取已有标段 id；重名时取 id 最小的那条（与既有口径一致）。"""
        ...

    def create_lot(self, project_id: int, *, code: str, name: str) -> int:
        """新建标段，序号接在现有最大序号之后。"""
        ...

    def set_derived_lots(self, report_id: int, lot_ids: list[int]) -> None:
        """记录本次发布自动派生出的标段，供前端区分「识别到」与「人工设定」。"""
        ...

    def next_snapshot_revision(self, report_id: int) -> int:
        """下一版快照号；同一报告的快照按 revision 递增，旧版本保留可回溯。"""
        ...

    def insert_snapshot(
        self,
        *,
        report_id: int,
        revision: int,
        schema_version: str,
        manifest_hash: str,
        inputs: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """写入快照并返回整行。"""
        ...

    def lock_collection(self, collection_id: int) -> None: ...

    def pending_index(self, source_id: int, run_id: int) -> bool: ...

    def insert_index(self, *, source_id: int, version_id: int, run_id: int) -> None: ...

    def lock_source(self, source_id: int) -> None: ...

    def inflight_source_job(self, source_id: int) -> bool: ...

    def insert_job(self, values: dict[str, Any]) -> None: ...

    def active_report(self, project_id: int) -> int | None: ...

    def other_active_report(self, project_id: int, report_id: int) -> int | None: ...

    def insert_report(self, values: dict[str, Any]) -> dict[str, Any]: ...

    def report_status(self, report_id: int, *, lock: bool = False) -> str: ...

    def update_report(self, report_id: int, values: dict[str, Any]) -> None: ...

    def mark_report_canceled(self, report_id: int) -> None: ...

    def execution_active(self, report_id: int) -> bool: ...

    def try_lock_execution(self, report_id: int) -> bool: ...

    def cancel_unlocked_runs(self, report_id: int) -> None: ...

    def modules_for_retry(
        self, report_id: int, keys: list[str], *, explicit: bool
    ) -> list[dict[str, Any]]: ...

    def report_has_modules(self, report_id: int) -> bool: ...

    def reset_modules(self, module_ids: list[int]) -> None: ...

    def mark_modules_pending(self, module_ids: list[int]) -> None: ...

    def module_attempt(self, module_id: int) -> int: ...

    def previous_run_state(self, module_id: int) -> dict[str, Any]: ...

    def insert_module_run(
        self,
        *,
        module_id: int,
        attempt: int,
        thread_id: str,
        limits: dict[str, Any],
        state: dict[str, Any],
    ) -> None: ...

    def snapshot_for_job(self, active: ActiveConfig | None) -> int | None: ...


class KnowledgeStore(Protocol):
    """业务库取数端口；由装配点注入具体实现（见 ``tender.core.di``）。"""

    company_id: int

    # —— 运行期配置 ——
    def resolved_config(self) -> dict[str, Any]:
        """本公司的运行期配置全量值（默认值已合并）；供预算上限等参数读取。"""
        ...

    # —— 知识库集合 ——
    def collection(self, collection_id: int) -> dict[str, Any]:
        """取知识库；不存在、已删除或项目已删除时抛 ``LookupError``。"""
        ...

    def collection_for_project(self, project_id: int) -> int | None:
        """项目的资料库 id；项目下没有资料库时返回 ``None``。"""
        ...

    def collections_for_project(self, project_id: int) -> list[int]:
        """项目可用的知识库：自己的资料库 + 显式关联的独立知识库。"""
        ...

    def collection_overview(self) -> list[dict[str, Any]]:
        """全部知识库及其在用文件数，项目库排在独立库之前。"""
        ...

    def update_collection(self, collection_id: int, *, name: str, purpose: str) -> None:
        """改名与改用途；只作用于本公司未删除的知识库。"""
        ...

    def soft_delete_collection(self, collection_id: int) -> None:
        """软删除知识库；资料与历史答案的溯源记录保留。"""
        ...

    # —— 资料来源 ——
    def sources(self, collection_ids: list[int]) -> list[dict[str, Any]]:
        """这批知识库里当前可用的资料及其解析/索引状态。

        每行同时带回解析批次、在途任务、最近一次失败与最新索引，调用方据此判断
        「能不能检索」而不是再查一遍库。
        """
        ...

    def source_for_processing(self, source_id: int) -> dict[str, Any] | None:
        """取资料以发起解析；跨公司、已删除或项目已删除时返回 ``None``。"""
        ...

    def mark_source_parseable(self, project_file_id: int) -> None:
        """把文件标记为可解析（用户显式要求处理原本判定为不支持的文件）。"""
        ...

    def has_parse_run(self, version_id: int) -> bool:
        """该版本是否已经解析过；决定重新处理是「首次」还是「重跑」。"""
        ...

    def blocks(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        """资料在该解析批次下的全部元素（按页、按序）。"""
        ...

    def readable_chunks(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        """资料的检索分块：在元素之上再按长度切分，并带定位信息。"""
        ...

    def resolve(self, ref: dict[str, Any], *, with_content: bool = False) -> dict[str, Any]:
        """校验一条引文的身份并补全定位；身份不符时抛 ``LookupError``。

        引文里的数字全部视作不可信输入，所以整条身份必须在**一次**带权限约束的查询里匹配。
        """
        ...

    # —— 检索与索引 ——
    def embedding_config(self) -> dict[str, Any] | None:
        """绑定到语义检索的向量模型；未配置时返回 ``None``。"""
        ...

    def rerank_config(self) -> dict[str, Any] | None:
        """绑定到重排的模型；未配置时返回 ``None``。"""
        ...

    def index_vectors(self, index_id: int) -> list[dict[str, Any]]:
        """索引批次里各分块的向量（``ordinal`` / ``embedding``），用于关键词之外的召回。"""
        ...

    # —— 数据库结构门禁 ——
    def schema_columns(self, tables: list[str]) -> set[tuple[str, str]]:
        """当前 schema 下这些表实际存在的 (表名, 列名)。"""
        ...

    def schema_tables(self, tables: list[str]) -> set[str]:
        """当前 schema 下实际存在的表名。"""
        ...

    # —— 分析报告 ——
    def report(self, report_id: int) -> dict[str, Any] | None:
        """取报告；项目已删除或跨公司时返回 ``None``。"""
        ...

    def report_for_analysis(self, report_id: int) -> dict[str, Any] | None:
        """worker 侧取报告以判断能否执行；项目已删除时返回 ``None``。"""
        ...

    def accessible_report_status(self, report_id: int) -> str | None:
        """报告状态；权限已撤销时返回 ``None``。

        与 ``report`` 分开：调用方要区分「报告不在了」和「报告还在但不能访问」，
        而这里只需要一个可执行性判断。
        """
        ...

    def analysis_settings(self, project_id: int) -> dict[str, Any] | None:
        """项目的分析类别与专题设置。"""
        ...

    def project_lots(self, project_id: int) -> list[dict[str, Any]]:
        """项目的全部标段及各自的分析设置，按序号排序。"""
        ...

    def project_lot_ids(self, project_id: int) -> list[int]:
        """项目的全部标段 id；用于校验设置里的标段归属。"""
        ...

    def analysis_reports(self, project_id: int) -> list[dict[str, Any]]:
        """项目最近 30 份分析报告的概要。"""
        ...

    def report_modules(self, report_id: int) -> list[dict[str, Any]]:
        """报告的全部模块（含成果与工具日志），按 id 升序。"""
        ...

    def report_runs(self, report_id: int) -> list[dict[str, Any]]:
        """报告的全部模块运行账（含尚未核实的暂存成果），按 attempt 升序。"""
        ...

    def report_active_modules(self, report_id: int) -> list[dict[str, Any]]:
        """各模块最新一个 attempt 中仍处于等待/运行的行。"""
        ...

    def run_belongs_to_report(self, run_id: int, report_id: int) -> bool:
        """该运行是否属于本报告与本公司；用于接口层的越权检查。"""
        ...

    def run_events(self, run_id: int, *, after: int, limit: int) -> list[dict[str, Any]]:
        """运行的审计事件增量（``id > after``），按 id 升序。"""
        ...

    def data_snapshot(
        self, report_id: int, snapshot_id: int | None = None
    ) -> dict[str, Any] | None:
        """正式业务数据快照；不指定 ``snapshot_id`` 时取最新一版。"""
        ...

    def snapshot_state(self, report_id: int) -> dict[str, Any] | None:
        """报告状态 + 运行账 + 模块成果，一次读出以判断快照是否仍然有效。"""
        ...

    def answer(self, answer_id: int) -> dict[str, Any] | None:
        """取问答记录；跨公司时返回 ``None``。"""
        ...

    def verified_relations(self, project_id: int) -> list[dict[str, Any]]:
        """最近一次完成/部分完成报告里已核实的知识关系，供图谱扩展。"""
        ...

    # —— 写回（短事务）——
    def set_report_coverage(self, report_id: int, coverage: dict[str, Any]) -> None:
        """记录本次分析覆盖了哪些资料。"""
        ...

    def defer_report(self, report_id: int, seconds: int) -> None:
        """资料未就绪时把等待中的报告推迟多久再次尝试。"""
        ...

    def renew_report_lease(
        self, report_id: int, seconds: int, *, status: str | None = None
    ) -> None:
        """续租报告；``status`` 给定时空值也必须匹配（避免续到已换状态的报告上）。"""
        ...

    def finish_report(
        self,
        report_id: int,
        *,
        status: str,
        summary: list[Any],
        error: str | None,
    ) -> None:
        """报告收口：写终态、汇总与结束时间，并清掉租约。"""
        ...

    def fail_report(self, report_id: int, error: str) -> None:
        """报告在运行中异常收尾；已取消的报告不再改写。"""
        ...

    def mark_answer_running(self, answer_id: int) -> None:
        """问答开始执行。"""
        ...

    def save_answer(
        self,
        answer_id: int,
        *,
        items: list[Any],
        relations: list[Any],
        snapshot: dict[str, Any],
    ) -> None:
        """写回问答结果与本次检索口径。"""
        ...

    def create_index(self, source: dict[str, Any]) -> None:
        """为一份资料登记一次索引任务。"""
        ...

    def collections_pending_index(self) -> list[int]:
        """资料仍可用的知识库 id；派发索引前先按它缩小范围。"""
        ...

    def index_for_build(self, index_id: int) -> dict[str, Any] | None:
        """取索引任务（含所属知识库）以执行构建；跨公司时返回 ``None``。"""
        ...

    def mark_index_running(self, index_id: int) -> None:
        """索引任务开始执行。"""
        ...

    def complete_index(
        self,
        index_id: int,
        *,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """用重建的分块与向量收口索引：整批替换旧分块，再写完成态与嵌入空间。"""
        ...

    def renew_lease(self, kind: str, record_id: int) -> None:
        """给长任务续租。``kind`` 取 ``index`` / ``report`` / ``answer``。"""
        ...

    def claim_dispatchable(self, kind: str, limit: int) -> list[int]:
        """取出本公司在期应执行的任务并顺带续租，防止同一任务被重复投递。``kind`` 同上。"""
        ...

    def finish_task(self, kind: str, record_id: int, status: str, error: str | None = None) -> None:
        """任务收口；已取消的记录不再改写。``kind`` 同上。"""
        ...

    def transaction(self) -> KnowledgeSession:
        """开启一个事务；见 :class:`KnowledgeSession`。"""
        ...

    # —— agent 运行 ——
    def agent_run_store(self, report: dict[str, Any], run: dict[str, Any]) -> AgentRunStore:
        """取报告/模块运行的状态机入口（见 ``ports.repository.agent_runtime``）。"""
        ...

    def append_run_event(self, run_id: int, kind: str, detail: dict[str, Any] | None) -> None:
        """写一条运行审计事件（独立短事务，不参与配额事务）。"""
        ...

    def create_collection(self, *, name: str, purpose: str) -> dict[str, Any]: ...

    def project_exists(self, project_id: int) -> bool: ...

    def update_analysis_settings(
        self, project_id: int, *, category: str, topics: list[str], lots: list[dict[str, Any]]
    ) -> None: ...

    def replace_links(self, project_id: int, collection_ids: list[int]) -> None: ...

    def enqueue_answer(
        self,
        *,
        project_id: int | None,
        collection_ids: list[int],
        question: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]: ...

    def execution_active(self, report_id: int) -> bool: ...
