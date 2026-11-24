"""业务库表映射模型（SQLAlchemy 2.0 typed declarative）。

这些类只是「表 ↔ 对象」映射，不是领域模型（docs/工程/10-技术选型与工程结构.md）；
通用约定与「刻意不复制哪些东西」的理由见 base.py。与迁移 DDL 的一致性由
tests/contract/test_orm_models_match_ddl.py 守住（表名/列名/可空性/类型四样）。

按业务域拆分：documents 解析管线 / projects 项目标段 /
configs 配置审计 / jobs 任务 / llm 模型管理 / knowledge 知识库 / analysis 智能分析。
"""

from tender.adapters.pg.models.analysis import (
    AgentModuleRun,
    AgentRunEvent,
    AnalysisDataSnapshot,
    AnalysisModule,
    AnalysisReport,
)
from tender.adapters.pg.models.base import Base
from tender.adapters.pg.models.configs import (
    ConfigAck,
    ConfigAudit,
    ConfigItem,
    ConfigRelease,
    JobConfigSnapshot,
)
from tender.adapters.pg.models.documents import (
    Document,
    DocumentVersion,
    Element,
    Page,
    ParseRun,
    TableCell,
)
from tender.adapters.pg.models.jobs import Job
from tender.adapters.pg.models.knowledge import (
    KnowledgeAnswer,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeIndex,
    KnowledgeSource,
    ProjectKnowledgeCollection,
)
from tender.adapters.pg.models.llm import (
    LlmCallLog,
    LlmFeature,
    LlmFeatureModel,
    LlmModel,
    LlmProvider,
    LlmTest,
)
from tender.adapters.pg.models.projects import Lot, Project, ProjectFile

__all__ = [
    "AgentModuleRun",
    "AgentRunEvent",
    "AnalysisDataSnapshot",
    "AnalysisModule",
    "AnalysisReport",
    "Base",
    "ConfigAck",
    "ConfigAudit",
    "ConfigItem",
    "ConfigRelease",
    "Document",
    "DocumentVersion",
    "Element",
    "Job",
    "JobConfigSnapshot",
    "KnowledgeAnswer",
    "KnowledgeChunk",
    "KnowledgeCollection",
    "KnowledgeIndex",
    "KnowledgeSource",
    "LlmCallLog",
    "LlmFeature",
    "LlmFeatureModel",
    "LlmModel",
    "LlmProvider",
    "LlmTest",
    "Lot",
    "Page",
    "ParseRun",
    "Project",
    "ProjectFile",
    "ProjectKnowledgeCollection",
    "TableCell",
]
