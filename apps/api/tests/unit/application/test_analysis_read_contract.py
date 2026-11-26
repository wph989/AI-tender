"""底层补读拒绝超范围和负数参数，工具层不能放宽证据窗口边界。"""

import asyncio

import pytest
from test_analysis_research import block, session

from tender.application.shared.research import ToolArgumentError


def rows(count=15):
    return [
        block()
        | {"block_id": f"s1r1c{i}", "element_id": i + 1, "offset": i, "content": f"第{i}项条款"}
        for i in range(count)
    ]
def test_lower_level_read_evidence_still_rejects_oversized_window():
    async def run():
        research = session(rows())
        await research.search("条款", "project")
        with pytest.raises(ToolArgumentError):
            await research.read_evidence("s1r1c0", 11, 11)
        # 单侧越界仍由底层拒绝，工具层的截断不能放宽证据窗口底线。
        with pytest.raises(ToolArgumentError):
            await research.read_evidence("s1r1c0", -1, 0)

    asyncio.run(run())
