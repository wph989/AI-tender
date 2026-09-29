"""把已经授权查询的结果行写成 Excel；查询范围由 API 或 worker 负责限定。"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

EXPORT_COLUMNS = (
    "字段名",
    "分组",
    "值",
    "适用范围",
    "来源文件",
    "页码",
    "原文片段",
    "置信度",
    # 尝试次数：机器尝试序号（人工修正填"人工"）；列清单见 docs/README.md 4.5 节（决策 20）。
    "尝试次数",
    "复核状态",
    "修正说明",
)


def workbook_bytes(rows: list[dict[str, Any]]) -> bytes:
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("抽取结果")
    sheet.freeze_panes = "A2"
    # 列数从常量推导：写死列字母时，加一列就会让筛选范围悄悄少一列。
    last_column = get_column_letter(len(EXPORT_COLUMNS))
    sheet.auto_filter.ref = f"A1:{last_column}{max(1, len(rows) + 1)}"
    sheet.append(EXPORT_COLUMNS)
    for row in rows:
        sheet.append([row.get(column) for column in EXPORT_COLUMNS])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
