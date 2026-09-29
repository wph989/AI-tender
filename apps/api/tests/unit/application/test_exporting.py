"""Excel 导出列的口径。

docs/README.md 第 4.5 节的决策 20 明确定了导出列（字段 / 值 / 标段 / 页码 / 原文片段 /
置信度 / 尝试次数 / 复核状态），
少一列就是验收漏项；列顺序也是对外约定，业务方按列名读表。
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import load_workbook

from tender.application.exporting import EXPORT_COLUMNS, workbook_bytes


def test_export_columns_follow_the_frozen_list() -> None:
    assert list(EXPORT_COLUMNS) == [
        "字段名",
        "分组",
        "值",
        "适用范围",
        "来源文件",
        "页码",
        "原文片段",
        "置信度",
        "尝试次数",
        "复核状态",
        "修正说明",
    ]


def test_workbook_writes_header_and_row_in_column_order() -> None:
    rows = [
        {
            "字段名": "project_name",
            "值": "某市政道路工程",
            "置信度": 0.9,
            "尝试次数": 2,
            "复核状态": "auto",
        }
    ]

    sheet = load_workbook(BytesIO(workbook_bytes(rows)))["抽取结果"]

    assert [cell.value for cell in sheet[1]] == list(EXPORT_COLUMNS)
    # 缺列写 None（空单元格），不能错位：错位比缺列更难被发现。
    assert [cell.value for cell in sheet[2]] == [
        "project_name",
        None,
        "某市政道路工程",
        None,
        None,
        None,
        None,
        0.9,
        2,
        "auto",
        None,
    ]
    # 筛选范围跟着列数走：写死列字母时加一列就会漏掉最后一列。
    assert sheet.auto_filter.ref == "A1:K2"
