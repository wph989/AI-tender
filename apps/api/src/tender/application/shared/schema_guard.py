"""分析运行前的数据库结构门禁。

代码可能先于业务库升级落地（例如刚发布了新契约但现场还没跑迁移）。缺列时错误
要等到模块发布成果才暴露，而那个失败又会挡在写回运行终态的路上，留下租约过期
却永远 ``status='running'`` 的僵尸运行。所以把分析链路强依赖的对象在任务入口
一次性核对，缺什么就直接失败并说清，不浪费模型预算。
"""

from __future__ import annotations

from tender.ports.repository.shared.schema import SchemaReader

# 分析链路强依赖的对象，缺少任何一个都会在流程中途报错，必须提前发现。
REQUIRED_COLUMNS = (
    ("analysis_module", "business_data"), ("analysis_report", "derived_lot_ids"),
    ("agent_module_run", "successful_model_calls"), ("agent_module_run", "successful_tool_calls"),
)
REQUIRED_TABLES = ("analysis_data_snapshot", "agent_call_attempt", "agent_model_invocation")


def missing_schema(db: SchemaReader) -> list[str]:
    """返回业务库缺少的分析数据对象（人类可读），全部就绪时返回空列表。"""
    tables = sorted({table for table, _ in REQUIRED_COLUMNS})
    present = db.schema_columns(tables)
    missing = [
        f"列 {table}.{column}"
        for table, column in REQUIRED_COLUMNS
        if (table, column) not in present
    ]
    found = db.schema_tables(list(REQUIRED_TABLES))
    missing.extend(f"表 {table}" for table in REQUIRED_TABLES if table not in found)
    return missing
