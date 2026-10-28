"""知识来源、运行账与正式快照的数据访问（``ports/repository/knowledge`` 的实现）。

三处刻意的取舍：

* **所有读都带公司/权限约束**。调用方拿到的是「当前还有权访问的」资料，不是一个裸查询
  结果；撤销关联、软删除、被新版本替代都在同一段条件里收窄。
* **一份资料的解析/索引状态一次查全**。``sources`` 用几个 LATERAL 把解析批次、在途任务、
  最近失败与最新索引并进一行，调用方据此判断「能不能检索」，不必再回库补查而跨过提交边界。
* **``sources`` / ``blocks`` / ``resolve`` 的身份匹配在一条语句里完成**。引文里的数字全部
  视作不可信输入，分两步校验会留下「先校验后删除」的竞态窗口。
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any

from sqlalchemy import (
    Connection,
    Engine,
    and_,
    delete,
    exists,
    func,
    insert,
    literal,
    or_,
    select,
    text,
    true,
    update,
)
from sqlalchemy.dialects.postgresql import INTERVAL
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from tender.adapters.pg.models import (
    AgentModuleRun,
    AgentRunEvent,
    AnalysisDataSnapshot,
    AnalysisModule,
    AnalysisReport,
    DocumentVersion,
    Element,
    Job,
    KnowledgeAnswer,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeIndex,
    KnowledgeRelation,
    KnowledgeSource,
    Lot,
    ParseRun,
    Project,
    ProjectFile,
    ProjectKnowledgeCollection,
)
from tender.adapters.pg.repositories.analysis.reports import ReportQueries
from tender.adapters.pg.repositories.analysis.runtime import (
    AgentRunStore,
    cancel_unlocked_runs,
    execution_active,
    lock_project,
    requeue_unlocked_runs,
    try_lock_report_execution,
)
from tender.adapters.pg.repositories.knowledge.retrieval import (
    indexed_chunks,
    read_chunk_window,
    search_candidates,
)
from tender.adapters.pg.repositories.llm.retrieval import RetrievalModelQueries
from tender.config.registry import ConfigRegistry
from tender.domain.knowledge.text import (
    CHUNK_VERSION,
    chunk_bbox,
    chunk_block_id,
    plain_text,
    split_elements,
)
from tender.ports.configuration.registry import ActiveConfig
from tender.ports.repository.knowledge.retrieval import SearchCandidates
from tender.ports.repository.knowledge.sources import ChunkWindow


def ensure_project_collection(connection: Any, project_id: int) -> int:
    """给项目建（或复用）资料库：项目资料库与项目一一对应。"""
    statement = pg_insert(KnowledgeCollection).from_select(
        ["company_id", "name", "purpose", "upload_project_id", "is_project"],
        select(
            Project.company_id,
            Project.name,
            literal("tender"),
            Project.id,
            literal(True),
        ).where(Project.id == project_id),
    )
    statement = statement.on_conflict_do_update(
        index_elements=["upload_project_id"],
        set_={"name": statement.excluded.name},
    ).returning(KnowledgeCollection.id)
    return int(connection.execute(statement).scalar_one())


def sync_sources(connection: Any, project_id: int) -> None:
    """把项目当前未删除的文件登记为该资料库的来源；重复登记不覆盖既有行。"""
    statement = pg_insert(KnowledgeSource).from_select(
        ["collection_id", "project_file_id"],
        select(KnowledgeCollection.id, ProjectFile.id)
        .join(ProjectFile, ProjectFile.project_id == KnowledgeCollection.upload_project_id)
        .where(ProjectFile.project_id == project_id, ProjectFile.deleted_at.is_(None)),
    )
    connection.execute(statement.on_conflict_do_nothing(index_elements=["project_file_id"]))


# information_schema 是 PostgreSQL 的系统目录，不是业务表，没有也更不该有 ORM 映射；
# 这里的裸 SQL 是唯一途径（SQLAlchemy 的 inspect() 内部走的也是同一组目录查询）。
_SCHEMA_COLUMNS_SQL = """
SELECT table_name, column_name FROM information_schema.columns
WHERE table_schema = current_schema() AND table_name = ANY(:tables)
"""
_SCHEMA_TABLES_SQL = """
SELECT table_name FROM information_schema.tables
WHERE table_schema = current_schema() AND table_name = ANY(:tables)
"""


# 长任务租约时长；调用方只给「续多久」，具体 SQL 由适配器拼。
_LEASE_WINDOW = literal("5 minutes", type_=INTERVAL)

# 三张长任务表共用一套派发/续租/收口写法；``kind`` 是稳定的用例语义名，不是表名。
_TASK_MODELS: dict[str, Any] = {
    "index": KnowledgeIndex,
    "report": AnalysisReport,
    "answer": KnowledgeAnswer,
}


def _scoped(model: Any, company_id: int) -> Any:
    """任务表的公司约束：只有 ``knowledge_index`` 需顺着来源回查所属公司。"""
    if model is not KnowledgeIndex:
        return model.company_id == company_id
    scoped = aliased(KnowledgeIndex)
    return model.id.in_(
        select(scoped.id)
        .join(KnowledgeSource, KnowledgeSource.id == scoped.source_id)
        .join(KnowledgeCollection, KnowledgeCollection.id == KnowledgeSource.collection_id)
        .where(
            KnowledgeCollection.company_id == company_id,
            KnowledgeCollection.deleted_at.is_(None),
        )
    )


class KnowledgeStore(ReportQueries, RetrievalModelQueries):
    """按公司收窄的知识库取数与短事务写回。"""

    def __init__(
        self, engine: Engine, company_id: int, configs: ConfigRegistry | None = None
    ) -> None:
        self.engine = engine
        self.company_id = company_id
        self.configs = configs

    # —— 运行期配置 ——
    def resolved_config(self) -> dict[str, Any]:
        """完整配置值；模型额度、超时预算等运行参数都从这里读。"""
        from tender.config.registry import ConfigRegistry

        return dict(ConfigRegistry(self.engine).resolved(self.company_id))

    # —— 知识库集合 ——
    def collection(self, collection_id: int) -> dict[str, Any]:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(KnowledgeCollection)
                    .join(Project, Project.id == KnowledgeCollection.upload_project_id)
                    .where(
                        KnowledgeCollection.id == collection_id,
                        KnowledgeCollection.company_id == self.company_id,
                        KnowledgeCollection.deleted_at.is_(None),
                        Project.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise LookupError("知识库不存在或已移除")
        return dict(row)

    def collection_for_project(self, project_id: int) -> int | None:
        """项目自己的资料库 id（``upload_project_id`` 与项目一一对应）。"""
        with self.engine.connect() as connection:
            return connection.execute(
                select(KnowledgeCollection.id)
                .join(Project, Project.id == KnowledgeCollection.upload_project_id)
                .where(
                    KnowledgeCollection.upload_project_id == project_id,
                    KnowledgeCollection.company_id == self.company_id,
                    KnowledgeCollection.deleted_at.is_(None),
                    Project.deleted_at.is_(None),
                )
                .order_by(KnowledgeCollection.id)
                .limit(1)
            ).scalar_one_or_none()

    def collections_for_project(self, project_id: int) -> list[int]:
        """项目自己的资料库 + 显式关联的独立知识库，二者都可读。"""
        own = (
            select(KnowledgeCollection.id)
            .join(Project, Project.id == KnowledgeCollection.upload_project_id)
            .where(
                Project.id == project_id,
                Project.company_id == self.company_id,
                Project.deleted_at.is_(None),
                KnowledgeCollection.company_id == self.company_id,
                KnowledgeCollection.deleted_at.is_(None),
            )
        )
        linked = (
            select(KnowledgeCollection.id)
            .join(
                ProjectKnowledgeCollection,
                ProjectKnowledgeCollection.collection_id == KnowledgeCollection.id,
            )
            .join(Project, Project.id == ProjectKnowledgeCollection.project_id)
            .where(
                ProjectKnowledgeCollection.project_id == project_id,
                Project.company_id == self.company_id,
                Project.deleted_at.is_(None),
                KnowledgeCollection.company_id == self.company_id,
                KnowledgeCollection.deleted_at.is_(None),
            )
        )
        with self.engine.connect() as connection:
            return list(connection.execute(own.union(linked).order_by("id")).scalars())

    def collection_overview(self) -> list[dict[str, Any]]:
        """全部知识库及其在用文件数，项目库排在独立库之前。"""
        statement = (
            select(KnowledgeCollection, func.count(ProjectFile.id).label("file_count"))
            .join(Project, Project.id == KnowledgeCollection.upload_project_id)
            .outerjoin(
                ProjectFile,
                and_(
                    ProjectFile.project_id == Project.id,
                    ProjectFile.deleted_at.is_(None),
                ),
            )
            .where(
                KnowledgeCollection.company_id == self.company_id,
                KnowledgeCollection.deleted_at.is_(None),
                Project.deleted_at.is_(None),
            )
            .group_by(KnowledgeCollection.id)
            .order_by(KnowledgeCollection.is_project, KnowledgeCollection.id.desc())
        )
        with self.engine.connect() as connection:
            # Connection 返回的是模型各列加计数的扁平行，不是 (实体, 计数)。
            return [dict(row) for row in connection.execute(statement).mappings()]

    def update_collection(self, collection_id: int, *, name: str, purpose: str) -> None:
        """改名与改用途；只作用于本公司未删除的知识库。"""
        with self.engine.begin() as connection:
            connection.execute(
                update(KnowledgeCollection)
                .where(
                    KnowledgeCollection.id == collection_id,
                    KnowledgeCollection.company_id == self.company_id,
                    KnowledgeCollection.deleted_at.is_(None),
                )
                .values(name=name, purpose=purpose)
            )

    def soft_delete_collection(self, collection_id: int) -> None:
        """软删除知识库；资料与历史答案的溯源记录保留。"""
        with self.engine.begin() as connection:
            connection.execute(
                update(KnowledgeCollection)
                .where(
                    KnowledgeCollection.id == collection_id,
                    KnowledgeCollection.company_id == self.company_id,
                    KnowledgeCollection.deleted_at.is_(None),
                )
                .values(deleted_at=func.now())
            )

    # —— 资料来源 ——
    def sources(self, collection_ids: Sequence[int]) -> list[dict[str, Any]]:
        """这批知识库里当前可用的资料及其解析/索引状态（见模块文档）。"""
        run = aliased(ParseRun)
        running = aliased(Job)
        failure = aliased(Job)
        index = aliased(KnowledgeIndex)
        version = aliased(DocumentVersion)
        newer = aliased(ProjectFile)

        current_run = (
            select(
                run.id.label("parse_run_id"),
                run.status.label("parse_status"),
                run.error_message.label("run_error"),
                run.page_count.label("parsed_pages"),
            )
            .where(run.version_id == ProjectFile.version_id)
            .order_by(run.created_at.desc(), run.id.desc())
            .limit(1)
            .correlate(ProjectFile)
            .lateral("current_run")
        )
        active_job = (
            select(running.id.label("active_job_id"), running.stage.label("active_stage"))
            .where(
                running.project_file_id == ProjectFile.id,
                running.stage.in_((
                    "probing", "converting", "geometry", "submitting", "parsing", "resubmitting",
                )),
                running.status.in_(("pending", "running", "submitting", "canceling", "draining")),
                running.finished_at.is_(None),
            )
            .order_by(running.created_at.desc())
            .limit(1)
            .correlate(ProjectFile)
            .lateral("active_job")
        )
        last_job = (
            select(
                failure.status.label("processing_status"),
                failure.error_message.label("job_error"),
            )
            .where(
                failure.project_file_id == ProjectFile.id,
                failure.stage.in_(("probing", "converting", "submitting", "parsing")),
            )
            .order_by(failure.created_at.desc(), failure.id.desc())
            .limit(1)
            .correlate(ProjectFile)
            .lateral("last_job")
        )
        current_index = (
            select(
                index.id.label("index_id"),
                index.status.label("index_status"),
                index.embedding_signature,
                index.embedding_model_id,
                index.dimension,
                index.error_message.label("index_error"),
            )
            .where(
                index.source_id == KnowledgeSource.id,
                index.run_id == current_run.c.parse_run_id,
            )
            .order_by(index.id.desc())
            .limit(1)
            .correlate(KnowledgeSource, current_run)
            .lateral("current_index")
        )
        statement = (
            select(
                KnowledgeSource.id.label("source_id"),
                KnowledgeCollection.id.label("collection_id"),
                KnowledgeCollection.purpose,
                Project.id.label("project_id"),
                ProjectFile.id.label("project_file_id"),
                ProjectFile.display_name.label("file_name"),
                ProjectFile.role,
                ProjectFile.is_parseable,
                ProjectFile.sha256,
                ProjectFile.version_id,
                current_run.c.parse_run_id,
                current_run.c.parse_status,
                func.coalesce(last_job.c.job_error, current_run.c.run_error).label("error_message"),
                current_run.c.parsed_pages,
                version.page_count,
                active_job.c.active_job_id,
                active_job.c.active_stage,
                last_job.c.processing_status,
                current_index.c.index_id,
                current_index.c.index_status,
                current_index.c.embedding_signature,
                current_index.c.embedding_model_id,
                current_index.c.dimension,
                current_index.c.index_error,
            )
            .select_from(KnowledgeSource)
            .join(KnowledgeCollection, KnowledgeCollection.id == KnowledgeSource.collection_id)
            .join(ProjectFile, ProjectFile.id == KnowledgeSource.project_file_id)
            .join(Project, Project.id == ProjectFile.project_id)
            .outerjoin(version, version.id == ProjectFile.version_id)
            .outerjoin(current_run, true())
            .outerjoin(active_job, true())
            .outerjoin(last_job, true())
            .outerjoin(current_index, true())
            .where(
                KnowledgeCollection.id.in_(list(collection_ids)),
                KnowledgeCollection.company_id == self.company_id,
                Project.company_id == self.company_id,
                KnowledgeCollection.deleted_at.is_(None),
                Project.deleted_at.is_(None),
                ProjectFile.deleted_at.is_(None),
                ~select(newer.id)
                .where(newer.replaces_id == ProjectFile.id, newer.deleted_at.is_(None))
                .exists(),
            )
            .order_by(ProjectFile.sort_no, ProjectFile.id)
        )
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(statement).mappings()]

    def _blocks_query(self, source: dict[str, Any]):
        """原文与索引共用身份/权限筛选，避免索引绕过资料撤销。"""
        return (
            select(
                Element.id,
                Element.anchor,
                Element.page_no,
                Element.type,
                Element.text,
                Element.html,
                Element.bbox_x0,
                Element.bbox_y0,
                Element.bbox_x1,
                Element.bbox_y1,
            )
            .join(DocumentVersion, DocumentVersion.id == Element.version_id)
            .join(
                ProjectFile,
                and_(
                    ProjectFile.id == source["project_file_id"],
                    ProjectFile.version_id == DocumentVersion.id,
                ),
            )
            .join(Project, Project.id == ProjectFile.project_id)
            .join(
                KnowledgeSource,
                and_(
                    KnowledgeSource.project_file_id == ProjectFile.id,
                    KnowledgeSource.id == source["source_id"],
                ),
            )
            .join(KnowledgeCollection, KnowledgeCollection.id == KnowledgeSource.collection_id)
            .where(
                Element.version_id == source["version_id"],
                Element.run_id == source["parse_run_id"],
                Project.company_id == self.company_id,
                KnowledgeCollection.company_id == self.company_id,
                ProjectFile.deleted_at.is_(None),
                Project.deleted_at.is_(None),
                KnowledgeCollection.deleted_at.is_(None),
            )
            .order_by(Element.page_no, Element.order_no)
        )

    def blocks(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            return [dict(row) for row in connection.execute(self._blocks_query(source)).mappings()]

    def search_candidates(
        self, sources: list[dict], query: str, vector: list[float] | None,
        signature: str | None, *, limit: int, min_similarity: float | None,
    ) -> SearchCandidates:
        return search_candidates(
            self, sources, query, vector, signature, limit=limit, min_similarity=min_similarity,
        )

    def readable_chunks(self, source: dict[str, Any]) -> list[dict[str, Any]]:
        """分块由元素派生，元素越界一次也不额外查库。"""
        if source.get("index_id") and source.get("index_status") == "completed":
            rows = indexed_chunks(self, source)
            if rows is not None:
                return rows
        elements = self.blocks(source)
        by_id = {element["id"]: element for element in elements}
        result = []
        for offset, chunk in enumerate(split_elements(elements)):
            element = by_id[chunk["element_id"]]
            result.append(
                {
                    **source,
                    **chunk,
                    "offset": offset,
                    "block_id": chunk_block_id(
                        source["source_id"], source["parse_run_id"], offset
                    ),
                    "anchor": element["anchor"],
                    "page_no": element["page_no"],
                    "bbox": chunk_bbox(element),
                }
            )
        return result

    def read_chunk_window(self, source: dict[str, Any], offset: int, limit: int) -> ChunkWindow:
        return read_chunk_window(self, source, offset, limit)

    def resolve(self, ref: dict[str, Any], *, with_content: bool = False) -> dict[str, Any]:
        """校验一条引文的身份并补全定位；整条身份在一次带权限的查询里匹配。"""
        statement = (
            select(
                Element.id,
                Element.page_no,
                Element.anchor,
                Element.text,
                Element.html,
                Element.bbox_x0,
                Element.bbox_y0,
                Element.bbox_x1,
                Element.bbox_y1,
                ProjectFile.display_name.label("file_name"),
            )
            .select_from(KnowledgeSource)
            .join(KnowledgeCollection, KnowledgeCollection.id == KnowledgeSource.collection_id)
            .join(ProjectFile, ProjectFile.id == KnowledgeSource.project_file_id)
            .join(Project, Project.id == ProjectFile.project_id)
            .join(
                Element,
                and_(
                    Element.version_id == ref["version_id"],
                    Element.run_id == ref["parse_run_id"],
                ),
            )
            .where(
                KnowledgeSource.id == ref["source_id"],
                KnowledgeSource.collection_id == ref["collection_id"],
                ProjectFile.id == ref["project_file_id"],
                Project.id == ref["project_id"],
                ProjectFile.version_id == Element.version_id,
                Element.id == ref["element_id"],
                Element.anchor == ref["anchor"],
                KnowledgeCollection.company_id == self.company_id,
                Project.company_id == self.company_id,
                KnowledgeCollection.deleted_at.is_(None),
                ProjectFile.deleted_at.is_(None),
                Project.deleted_at.is_(None),
            )
        )
        with self.engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        if row is None:
            raise LookupError("引用原文已删除、撤销访问或与解析批次不符")
        resolved = {
            **ref,
            "page_no": row["page_no"],
            "file_name": row["file_name"],
            "bbox": chunk_bbox(row),
        }
        if with_content:
            # 展示层要按元素原文回查值的位置，这里顺带返回，避免为同一权限再查一次。
            resolved["content"] = plain_text(row)
        return resolved

    def source_for_processing(self, source_id: int) -> dict[str, Any] | None:
        """取资料以发起解析；跨公司、已删除或项目已删除时返回 ``None``。"""
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(
                        ProjectFile.id,
                        ProjectFile.project_id,
                        ProjectFile.version_id,
                        ProjectFile.role,
                        ProjectFile.display_name,
                        KnowledgeSource.collection_id,
                    )
                    .select_from(KnowledgeSource)
                    .join(ProjectFile, ProjectFile.id == KnowledgeSource.project_file_id)
                    .join(Project, Project.id == ProjectFile.project_id)
                    .join(
                        KnowledgeCollection,
                        KnowledgeCollection.id == KnowledgeSource.collection_id,
                    )
                    .where(
                        KnowledgeSource.id == source_id,
                        Project.company_id == self.company_id,
                        KnowledgeCollection.company_id == self.company_id,
                        ProjectFile.deleted_at.is_(None),
                        Project.deleted_at.is_(None),
                        KnowledgeCollection.deleted_at.is_(None),
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def mark_source_parseable(self, project_file_id: int) -> None:
        """把文件标记为可解析（用户显式要求处理原本判定为不支持的文件）。"""
        with self.engine.begin() as connection:
            connection.execute(
                update(ProjectFile)
                .where(
                    ProjectFile.id == project_file_id,
                    ProjectFile.project_id.in_(
                        select(Project.id).where(Project.company_id == self.company_id)
                    ),
                )
                .values(is_parseable=True)
            )

    def has_parse_run(self, version_id: int) -> bool:
        """该版本是否已经解析过；决定重新处理是「首次」还是「重跑」。"""
        with self.engine.connect() as connection:
            return bool(
                connection.execute(
                    select(exists().where(ParseRun.version_id == version_id))
                ).scalar_one()
            )

    # —— 检索与索引 ——


    # —— 分析报告 ——

    def answer(self, answer_id: int) -> dict[str, Any] | None:
        """取问答记录；跨公司时返回 ``None``。"""
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(KnowledgeAnswer).where(
                        KnowledgeAnswer.id == answer_id,
                        KnowledgeAnswer.company_id == self.company_id,
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

    def verified_relations(self, project_id: int) -> list[dict[str, Any]]:
        """最近一次完成/部分完成报告里已核实的知识关系，供图谱扩展。"""
        latest = (
            select(func.max(AnalysisReport.id))
            .where(
                AnalysisReport.project_id == project_id,
                AnalysisReport.company_id == self.company_id,
                AnalysisReport.status.in_(("completed", "partial")),
            )
            .scalar_subquery()
        )
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(KnowledgeRelation)
                .join(AnalysisReport, AnalysisReport.id == KnowledgeRelation.report_id)
                .join(Project, Project.id == AnalysisReport.project_id)
                .where(
                    AnalysisReport.project_id == project_id,
                    AnalysisReport.company_id == self.company_id,
                    Project.deleted_at.is_(None),
                    KnowledgeRelation.verified,
                    KnowledgeRelation.report_id == latest,
                )
            ).mappings()
            return [dict(row) for row in rows]


    # —— 数据库结构门禁 ——
    def schema_columns(self, tables: Sequence[str]) -> set[tuple[str, str]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(_SCHEMA_COLUMNS_SQL), {"tables": list(tables)}
            ).mappings()
            return {(row["table_name"], row["column_name"]) for row in rows}

    def schema_tables(self, tables: Sequence[str]) -> set[str]:
        with self.engine.connect() as connection:
            rows = connection.execute(text(_SCHEMA_TABLES_SQL), {"tables": list(tables)}).scalars()
            return set(rows)

    # —— 写回（短事务）——
    def set_report_coverage(self, report_id: int, coverage: dict[str, Any]) -> None:
        """记录本次分析覆盖了哪些资料。"""
        with self.engine.begin() as connection:
            connection.execute(
                update(AnalysisReport)
                .where(AnalysisReport.id == report_id)
                .values(coverage=coverage)
            )

    def defer_report(self, report_id: int, seconds: int) -> None:
        """资料未就绪时把等待中的报告推迟多久再次尝试。"""
        window = func.make_interval(0, 0, 0, 0, 0, 0, seconds)
        with self.engine.begin() as connection:
            connection.execute(
                update(AnalysisReport)
                .where(AnalysisReport.id == report_id, AnalysisReport.status == "waiting")
                .values(lease_until=func.now() + window)
            )

    def renew_report_lease(
        self, report_id: int, seconds: int, *, status: str | None = None
    ) -> None:
        """续租报告；``status`` 给定时空值也必须匹配（避免续到已换状态的报告上）。"""
        window = func.make_interval(0, 0, 0, 0, 0, 0, seconds)
        statement = update(AnalysisReport).where(AnalysisReport.id == report_id)
        if status is not None:
            statement = statement.where(AnalysisReport.status == status)
        with self.engine.begin() as connection:
            connection.execute(statement.values(lease_until=func.now() + window))

    def finish_report(
        self,
        report_id: int,
        *,
        status: str,
        summary: list[Any],
        error: str | None,
    ) -> None:
        """报告收口：写终态、汇总与结束时间，并清掉租约。"""
        with self.engine.begin() as connection:
            connection.execute(
                update(AnalysisReport)
                .where(AnalysisReport.id == report_id, AnalysisReport.status == "running")
                .values(
                    status=status,
                    summary=summary,
                    error_message=error,
                    finished_at=func.now(),
                    lease_until=None,
                )
            )

    def mark_answer_running(self, answer_id: int) -> None:
        """问答开始执行。"""
        with self.engine.begin() as connection:
            connection.execute(
                update(KnowledgeAnswer)
                .where(KnowledgeAnswer.id == answer_id)
                .values(status="running")
            )

    def save_answer(
        self,
        answer_id: int,
        *,
        items: list[Any],
        relations: list[Any],
        snapshot: dict[str, Any],
    ) -> None:
        """写回问答结果与本次检索口径。"""
        with self.engine.begin() as connection:
            connection.execute(
                update(KnowledgeAnswer)
                .where(KnowledgeAnswer.id == answer_id)
                .values(items=items, relations=relations, snapshot=snapshot)
            )

    def create_index(self, source: dict[str, Any]) -> None:
        """为一份资料登记一次索引任务。"""
        with self.engine.begin() as connection:
            connection.execute(
                insert(KnowledgeIndex).values(
                    source_id=source["source_id"],
                    version_id=source["version_id"],
                    run_id=source["parse_run_id"],
                    # 写入端显式记录分块版本，不依赖数据库默认值；读取端共用同一常量。
                    chunk_version=CHUNK_VERSION,
                )
            )

    def collections_pending_index(self) -> list[int]:
        """资料仍可用的知识库 id；派发索引前先按它缩小范围。"""
        with self.engine.connect() as connection:
            return list(
                connection.execute(
                    select(KnowledgeCollection.id)
                    .join(Project, Project.id == KnowledgeCollection.upload_project_id)
                    .join(
                        KnowledgeSource,
                        KnowledgeSource.collection_id == KnowledgeCollection.id,
                    )
                    .where(
                        KnowledgeCollection.company_id == self.company_id,
                        KnowledgeCollection.deleted_at.is_(None),
                        Project.deleted_at.is_(None),
                    )
                    .distinct()
                ).scalars()
            )

    def index_for_build(self, index_id: int) -> dict[str, Any] | None:
        """取索引任务（含所属知识库）以执行构建；跨公司时返回 ``None``。"""
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    select(KnowledgeIndex, KnowledgeSource.collection_id)
                    .join(KnowledgeSource, KnowledgeSource.id == KnowledgeIndex.source_id)
                    .join(
                        KnowledgeCollection,
                        KnowledgeCollection.id == KnowledgeSource.collection_id,
                    )
                    .where(
                        KnowledgeIndex.id == index_id,
                        KnowledgeCollection.company_id == self.company_id,
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return {**dict(row), "collection_id": row["collection_id"]}

    def mark_index_running(self, index_id: int) -> None:
        """索引任务开始执行。"""
        with self.engine.begin() as connection:
            connection.execute(
                update(KnowledgeIndex).where(KnowledgeIndex.id == index_id).values(status="running")
            )

    def complete_index(
        self,
        index_id: int,
        *,
        chunks: list[dict[str, Any]],
        vectors: list[list[float]] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """用重建的分块与向量收口索引：整批替换旧分块，再写完成态与嵌入空间。"""
        rows = [
            {
                "index_id": index_id,
                "element_id": chunk["element_id"],
                "ordinal": chunk["ordinal"],
                "char_start": chunk["char_start"],
                "char_end": chunk["char_end"],
                "chapter": chunk["chapter"],
                "content": chunk["content"],
                "embedding": vectors[position] if vectors else None,
            }
            for position, chunk in enumerate(chunks)
        ]
        with self.engine.begin() as connection:
            connection.execute(delete(KnowledgeChunk).where(KnowledgeChunk.index_id == index_id))
            if rows:
                connection.execute(insert(KnowledgeChunk), rows)
            connection.execute(
                update(KnowledgeIndex)
                .where(KnowledgeIndex.id == index_id)
                .values(
                    status="completed",
                    embedding_model_id=config["id"] if config else None,
                    embedding_signature=config["signature"] if config else None,
                    dimension=len(vectors[0]) if vectors else None,
                    error_message=None,
                    finished_at=func.now(),
                    lease_until=None,
                )
            )

    def claim_dispatchable(self, kind: str, limit: int) -> list[int]:
        """取出本公司在期应执行的任务并顺带续租，防止同一任务被重复投递。

        小批次派发限制消息积压；长任务会定期续约，重复消息由会话锁拒绝。
        """
        model = _TASK_MODELS[kind]
        with self.engine.begin() as connection:
            ids = list(
                connection.execute(
                    select(model.id)
                    .where(
                        model.status.in_(("pending", "waiting", "running")),
                        _scoped(model, self.company_id),
                        or_(model.lease_until.is_(None), model.lease_until < func.now()),
                    )
                    .order_by(model.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                ).scalars()
            )
            if ids:
                connection.execute(
                    update(model)
                    .where(model.id.in_(ids))
                    .values(lease_until=func.now() + _LEASE_WINDOW)
                )
        return ids

    def renew_lease(self, kind: str, record_id: int) -> None:
        """给长任务续租。``kind`` 取 ``index`` / ``report`` / ``answer``。"""
        model = _TASK_MODELS[kind]
        with self.engine.begin() as connection:
            connection.execute(
                update(model)
                .where(model.id == record_id)
                .values(lease_until=func.now() + _LEASE_WINDOW)
            )
            if kind == "report":
                # 续租时顺带回显取消：报告已取消要立刻中断长任务，不必再等下一次检查。
                status = connection.execute(
                    select(AnalysisReport.status).where(AnalysisReport.id == record_id)
                ).scalar_one_or_none()
                if status is None or status == "canceled":
                    raise InterruptedError("分析已取消")

    def finish_task(self, kind: str, record_id: int, status: str, error: str | None = None) -> None:
        """任务收口；已取消的记录不再改写。``kind`` 同上。"""
        model = _TASK_MODELS[kind]
        with self.engine.begin() as connection:
            connection.execute(
                update(model)
                .where(model.id == record_id, model.status != "canceled")
                .values(
                    status=status,
                    error_message=error,
                    finished_at=func.now(),
                    lease_until=None,
                )
            )

    def append_run_event(self, run_id: int, kind: str, detail: dict[str, Any] | None) -> None:
        """写一条运行审计事件（独立短事务，不参与配额事务）。"""
        with self.engine.begin() as connection:
            connection.execute(
                insert(AgentRunEvent).values(run_id=run_id, kind=kind, detail=detail or {})
            )

    # —— agent 运行 ——
    def agent_run_store(self, report: dict[str, Any], run: dict[str, Any]) -> AgentRunStore:
        """取模块运行状态机；``run`` 需带 ``id``/``module_id``/``module_key``/``limits``。"""
        return AgentRunStore(self, report, run)

    # —— 事务 ——
    def transaction(self) -> KnowledgeSession:
        return KnowledgeSession(self.engine, self.company_id, self.configs)

    def create_collection(self, *, name: str, purpose: str) -> dict[str, Any]:
        with self.engine.begin() as connection:
            project_id = connection.execute(
                insert(Project)
                .values(company_id=self.company_id, name=name, kind="knowledge")
                .returning(Project.id)
            ).scalar_one()
            row = (
                connection.execute(
                    insert(KnowledgeCollection)
                    .values(
                        company_id=self.company_id,
                        name=name,
                        purpose=purpose,
                        upload_project_id=project_id,
                    )
                    .returning(
                        KnowledgeCollection.id,
                        KnowledgeCollection.company_id,
                        KnowledgeCollection.name,
                        KnowledgeCollection.purpose,
                        KnowledgeCollection.upload_project_id,
                        KnowledgeCollection.is_project,
                        KnowledgeCollection.created_at,
                        KnowledgeCollection.deleted_at,
                    )
                )
                .mappings()
                .one()
            )
        return dict(row)

    def project_exists(self, project_id: int) -> bool:
        with self.engine.connect() as connection:
            found = connection.execute(
                select(Project.id).where(
                    Project.id == project_id,
                    Project.company_id == self.company_id,
                    Project.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
        return found is not None

    def update_analysis_settings(
        self,
        project_id: int,
        *,
        category: str,
        topics: list[str],
        lots: list[dict[str, Any]],
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(analysis_category=category, analysis_topics=topics)
            )
            for lot in lots:
                connection.execute(
                    update(Lot)
                    .where(Lot.id == lot["id"], Lot.project_id == project_id)
                    .values(
                        analysis_category=lot.get("category"),
                        analysis_topics=lot.get("topics"),
                    )
                )

    def replace_links(self, project_id: int, collection_ids: list[int]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                delete(ProjectKnowledgeCollection).where(
                    ProjectKnowledgeCollection.project_id == project_id
                )
            )
            for collection_id in collection_ids:
                connection.execute(
                    insert(ProjectKnowledgeCollection).values(
                        project_id=project_id,
                        collection_id=collection_id,
                    )
                )

    def enqueue_answer(
        self,
        *,
        project_id: int | None,
        collection_ids: list[int],
        question: str,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    insert(KnowledgeAnswer)
                    .values(
                        company_id=self.company_id,
                        project_id=project_id,
                        collection_ids=collection_ids,
                        question=question,
                        snapshot=snapshot,
                    )
                    .returning(KnowledgeAnswer.id, KnowledgeAnswer.status)
                )
                .mappings()
                .one()
            )
        return dict(row)

    def execution_active(self, report_id: int) -> bool:
        with self.engine.connect() as connection:
            return execution_active(connection, report_id)


def _entity_columns(model: Any) -> list[Any]:
    """实体的列清单，供必须在事务里按列取行的地方使用。

    ``Session.execute(select(模型))`` 会把整行装成 ORM 实体，``.mappings()`` 的键就成了
    实体名（``{'AnalysisReport': <obj>}``）而不是列名；用例层要的是普通字典，所以显式
    列出列，让 Session 走列结果，键名与 DDL 一致（与仓储其它取数出口同一口径）。
    """
    return list(model.__table__.columns)


class KnowledgeSession:
    """一次业务库事务；发布快照要的多条语句在其中原子提交。

    ``Session`` 绑外部连接时默认以 savepoint 加入连接里已开始的事务，``commit()`` 只释放
    savepoint，连接回池时整笔事务被回滚——写入会静默丢失。所以这里把事务所有权显式分开：
    引擎给的是空闲连接就自己 ``begin()`` 并由本会话提交；引擎给的是已有事务的连接（集成
    测试共享同一连接）就只借道，绝不提交别人的事务。``rollback_only`` 让 ``Session`` 只
    负责 flush，事务边界由本会话或外层所有者掌握。
    """

    def __init__(
        self, engine: Engine, company_id: int, configs: ConfigRegistry | None = None
    ) -> None:
        self.company_id = company_id
        self.configs = configs
        self._engine = engine
        self._connection_cm: Any = None
        self._raw_connection: Any = None
        self._transaction: Any = None
        self._session: Session | None = None

    def __enter__(self) -> KnowledgeSession:
        self._connection_cm = self._engine.connect()
        self._raw_connection = self._connection_cm.__enter__()
        self._transaction = (
            None if self._raw_connection.in_transaction() else self._raw_connection.begin()
        )
        self._session = Session(bind=self._raw_connection, join_transaction_mode="rollback_only")
        return self

    def __exit__(self, *exc: object) -> None:
        """干净退出即提交、异常即回滚：调用方只划事务范围，不自己开关事务。"""
        assert self._session is not None
        try:
            if exc[0] is None:
                self._session.flush()
                if self._transaction is not None:
                    self._transaction.commit()
            elif self._transaction is not None:
                self._transaction.rollback()
            else:
                self._session.rollback()
        finally:
            try:
                self._session.close()
            finally:
                self._connection_cm.__exit__(*exc)

    def _connection(self) -> Connection:
        """本事务正在使用的连接；advisory 锁等 Core 语句与 ORM 同连接同事务。"""
        assert self._session is not None
        return self._session.connection()

    def lock_project(self, project_id: int) -> None:
        """事务级 advisory 锁串行化同项目的发布与补跑；跨进程也需要，因此不用行锁。"""
        lock_project(self._connection(), project_id)

    def lock_report(self, report_id: int) -> dict[str, Any]:
        row = (
            self._session.execute(
                select(*_entity_columns(AnalysisReport))
                .where(AnalysisReport.id == report_id)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if row is None:
            raise LookupError("报告不存在")
        return dict(row)

    def start_report(
        self,
        report_id: int,
        *,
        source_snapshot: list[dict[str, Any]],
        reference_snapshot: list[dict[str, Any]],
    ) -> bool:
        """把等待/排队中的报告置为执行中并固定资料快照；已被取消时返回 ``False``。"""
        row = self._session.execute(
            update(AnalysisReport)
            .where(
                AnalysisReport.id == report_id,
                AnalysisReport.status.in_(("waiting", "pending", "running")),
            )
            .values(
                status="running",
                source_snapshot=source_snapshot,
                reference_snapshot=reference_snapshot,
            )
            .returning(AnalysisReport.id)
        ).first()
        return row is not None

    def requeue_unlocked_runs(self, report_id: int) -> None:
        requeue_unlocked_runs(self._connection(), report_id)

    def ensure_modules(self, report_id: int, modules: dict[str, str]) -> list[dict[str, Any]]:
        """确保报告的模块行存在（标题随 Skill 更新），返回各模块当前 ``id`` / ``status``。"""
        result = []
        for key, title in modules.items():
            statement = pg_insert(AnalysisModule).values(
                report_id=report_id, module_key=key, title=title
            )
            row = (
                self._session.execute(
                    statement.on_conflict_do_update(
                        index_elements=["report_id", "module_key"],
                        set_={"title": statement.excluded.title},
                    ).returning(AnalysisModule.id, AnalysisModule.status)
                )
                .mappings()
                .one()
            )
            result.append(dict(row))
        return result

    def ensure_module_run(
        self,
        module_id: int,
        *,
        company_id: int,
        thread_id: str,
        limits: dict[str, Any],
    ) -> None:
        """确保首次 attempt（=1）的运行账存在；重复投递或补跑不覆盖既有行。"""
        self._session.execute(
            pg_insert(AgentModuleRun)
            .values(
                module_id=module_id,
                company_id=company_id,
                attempt=1,
                thread_id=thread_id,
                limits=limits,
            )
            .on_conflict_do_nothing(index_elements=["module_id", "attempt"])
        )

    def report_runs(self, report_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            select(
                AgentModuleRun.id,
                AgentModuleRun.status,
                AgentModuleRun.attempt,
                AgentModuleRun.module_id,
            )
            .join(AnalysisModule, AnalysisModule.id == AgentModuleRun.module_id)
            .where(AnalysisModule.report_id == report_id)
            .order_by(AgentModuleRun.id)
        ).mappings()
        return [dict(row) for row in rows]

    def report_modules(self, report_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            select(*_entity_columns(AnalysisModule))
            .where(AnalysisModule.report_id == report_id)
            .order_by(AnalysisModule.id)
        ).mappings()
        return [dict(row) for row in rows]

    def snapshot_by_manifest(self, report_id: int, manifest_hash: str) -> dict[str, Any] | None:
        row = (
            self._session.execute(
                select(*_entity_columns(AnalysisDataSnapshot)).where(
                    AnalysisDataSnapshot.report_id == report_id,
                    AnalysisDataSnapshot.manifest_hash == manifest_hash,
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row is not None else None

    def lot_id_for_code(self, project_id: int, code: str | None) -> int | None:
        return self._session.execute(
            select(Lot.id)
            .where(Lot.project_id == project_id, Lot.code == code)
            .order_by(Lot.id)
            .limit(1)
        ).scalar_one_or_none()

    def create_lot(self, project_id: int, *, code: str | None, name: str | None) -> int:
        """新建标段，序号接在现有最大序号之后（``ORDER BY sort_no, id`` 的口径）。"""
        next_no = self._session.execute(
            select(func.coalesce(func.max(Lot.sort_no), -1) + 1).where(Lot.project_id == project_id)
        ).scalar_one()
        return int(
            self._session.execute(
                insert(Lot)
                .values(project_id=project_id, code=code, name=name, sort_no=next_no)
                .returning(Lot.id)
            ).scalar_one()
        )

    def set_derived_lots(self, report_id: int, lot_ids: list[int]) -> None:
        self._session.execute(
            update(AnalysisReport)
            .where(AnalysisReport.id == report_id)
            .values(derived_lot_ids=sorted(lot_ids))
        )

    def next_snapshot_revision(self, report_id: int) -> int:
        return int(
            self._session.execute(
                select(func.coalesce(func.max(AnalysisDataSnapshot.revision), 0) + 1).where(
                    AnalysisDataSnapshot.report_id == report_id
                )
            ).scalar_one()
        )

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
        row = (
            self._session.execute(
                insert(AnalysisDataSnapshot)
                .values(
                    report_id=report_id,
                    revision=revision,
                    schema_version=schema_version,
                    manifest_hash=manifest_hash,
                    input_snapshot=inputs,
                    data=data,
                )
                .returning(*_entity_columns(AnalysisDataSnapshot))
            )
            .mappings()
            .one()
        )
        # 提交交给 ``with`` 边界（见 ``__exit__``）：快照与它依赖的标段派生同一批提交。
        return dict(row)

    def lock_collection(self, collection_id: int) -> None:
        lock_project(self._connection(), -collection_id)

    def pending_index(self, source_id: int, run_id: int) -> bool:
        found = (
            self._connection()
            .execute(
                select(KnowledgeIndex.id).where(
                    KnowledgeIndex.source_id == source_id,
                    KnowledgeIndex.run_id == run_id,
                    KnowledgeIndex.status.in_(("pending", "running")),
                )
            )
            .first()
        )
        return found is not None

    def insert_index(self, *, source_id: int, version_id: int, run_id: int) -> None:
        self._connection().execute(
            insert(KnowledgeIndex).values(
                source_id=source_id,
                version_id=version_id,
                run_id=run_id,
            )
        )

    def lock_source(self, source_id: int) -> None:
        self._connection().execute(
            select(ProjectFile.id).where(ProjectFile.id == source_id).with_for_update()
        )

    def inflight_source_job(self, source_id: int) -> bool:
        found = (
            self._connection()
            .execute(
                select(Job.id).where(
                    Job.project_file_id == source_id,
                    Job.status.in_(("pending", "running", "submitting", "canceling", "draining")),
                    Job.finished_at.is_(None),
                )
            )
            .first()
        )
        return found is not None

    def insert_job(self, values: dict[str, Any]) -> None:
        self._connection().execute(insert(Job).values(**values))

    def active_report(self, project_id: int) -> int | None:
        return (
            self._connection()
            .execute(
                select(AnalysisReport.id).where(
                    AnalysisReport.project_id == project_id,
                    AnalysisReport.status.in_(("waiting", "pending", "running")),
                )
            )
            .scalar_one_or_none()
        )

    def other_active_report(self, project_id: int, report_id: int) -> int | None:
        return (
            self._connection()
            .execute(
                select(AnalysisReport.id).where(
                    AnalysisReport.project_id == project_id,
                    AnalysisReport.id != report_id,
                    AnalysisReport.status.in_(("waiting", "pending", "running")),
                )
            )
            .scalar_one_or_none()
        )

    def insert_report(self, values: dict[str, Any]) -> dict[str, Any]:
        return dict(
            self._connection()
            .execute(
                insert(AnalysisReport)
                .values(**values)
                .returning(AnalysisReport.id, AnalysisReport.status)
            )
            .mappings()
            .one()
        )

    def report_status(self, report_id: int, *, lock: bool = False) -> str:
        statement = select(AnalysisReport.status).where(
            AnalysisReport.id == report_id,
            AnalysisReport.company_id == self.company_id,
        )
        if lock:
            statement = statement.with_for_update()
        return self._connection().execute(statement).scalar_one()

    def update_report(self, report_id: int, values: dict[str, Any]) -> None:
        self._connection().execute(
            update(AnalysisReport).where(AnalysisReport.id == report_id).values(**values)
        )

    def mark_report_canceled(self, report_id: int) -> None:
        self._connection().execute(
            update(AnalysisReport)
            .where(AnalysisReport.id == report_id)
            .values(
                status="canceled",
                finished_at=func.coalesce(AnalysisReport.finished_at, func.now()),
                lease_until=None,
            )
        )
        cancel_unlocked_runs(self._connection(), report_id)

    def execution_active(self, report_id: int) -> bool:
        return execution_active(self._connection(), report_id)

    def try_lock_execution(self, report_id: int) -> bool:
        return try_lock_report_execution(self._connection(), report_id)

    def cancel_unlocked_runs(self, report_id: int) -> None:
        cancel_unlocked_runs(self._connection(), report_id)

    def modules_for_retry(
        self, report_id: int, keys: list[str], *, explicit: bool
    ) -> list[dict[str, Any]]:
        statement = (
            select(AnalysisModule.id, AnalysisModule.status)
            .where(AnalysisModule.report_id == report_id, AnalysisModule.module_key.in_(keys))
            .with_for_update()
        )
        if not explicit:
            statement = statement.where(AnalysisModule.status.in_(("failed", "canceled")))
        return [dict(row) for row in self._connection().execute(statement).mappings().all()]

    def report_has_modules(self, report_id: int) -> bool:
        return bool(
            self._connection()
            .execute(select(exists().where(AnalysisModule.report_id == report_id)))
            .scalar_one()
        )

    def reset_modules(self, module_ids: list[int]) -> None:
        if module_ids:
            self._connection().execute(
                update(AnalysisModule)
                .where(AnalysisModule.id.in_(module_ids))
                .values(items=[], business_data={})
            )

    def mark_modules_pending(self, module_ids: list[int]) -> None:
        if module_ids:
            self._connection().execute(
                update(AnalysisModule)
                .where(AnalysisModule.id.in_(module_ids))
                .values(status="pending", error_message=None)
            )

    def module_attempt(self, module_id: int) -> int:
        return int(
            self._connection()
            .execute(
                select(func.coalesce(func.max(AgentModuleRun.attempt), 0) + 1).where(
                    AgentModuleRun.module_id == module_id
                )
            )
            .scalar_one()
        )

    def previous_run_state(self, module_id: int) -> dict[str, Any]:
        return (
            self._connection()
            .execute(
                select(AgentModuleRun.state)
                .where(AgentModuleRun.module_id == module_id)
                .order_by(AgentModuleRun.attempt.desc())
                .limit(1)
            )
            .scalar_one_or_none()
            or {}
        )

    def insert_module_run(
        self,
        *,
        module_id: int,
        attempt: int,
        thread_id: str,
        limits: dict[str, Any],
        state: dict[str, Any],
    ) -> None:
        self._connection().execute(
            insert(AgentModuleRun).values(
                module_id=module_id,
                company_id=self.company_id,
                attempt=attempt,
                thread_id=thread_id,
                limits=limits,
                state=state,
            )
        )

    def snapshot_for_job(self, active: ActiveConfig | None) -> int | None:
        # API 装配时注入配置实现；复用原有回源行为，并与入队共用当前事务。
        assert self.configs is not None
        return self.configs.snapshot_for_job(self._connection(), active)


@contextmanager
def project_lock(connection: Any, project_id: int):
    """给调用方在同一事务里显式加项目会话锁的便捷包装。"""
    connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": project_id})
    yield connection


__all__ = [
    "KnowledgeSession",
    "KnowledgeStore",
    "ensure_project_collection",
    "project_lock",
    "sync_sources",
]
