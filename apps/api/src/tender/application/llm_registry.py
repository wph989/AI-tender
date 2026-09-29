"""LLM 管理模块的纯规则：优先级整表展开与转移深度夹取（设计文档 12 第 3、4 节）。

放在 application 而不是 api 里：这些规则同时约束接口写入与 worker 读取，
只有一份实现，页面提交与任务执行才不会对"合法优先级"产生两种理解。
"""

from __future__ import annotations

from collections.abc import Sequence

from tender.domain.errors import PriorityLimitExceeded

MAX_BINDINGS = 10
MAX_FAILOVER_LIMIT = 10
DEFAULT_FAILOVER_LIMIT = 3

# 功能清单是代码内置枚举：新增功能必须同时有消费者，页面不能自己造。
FEATURES: tuple[tuple[str, str], ...] = (
    ("extract", "字段抽取"),
    ("retry", "重跑与带提示重跑"),
)


def binding_rows(model_ids: Sequence[int]) -> list[tuple[int, int]]:
    """把整表提交的有序模型 id 展开成 (model_id, priority) 行。

    优先级由数组位置推导，而不是接收客户端传来的数字：数字会带来空洞、同级、越界
    三类非法状态，而"有序数组"天然只有一种解释（见设计文档 12 第 3 节）。
    """
    if len(model_ids) > MAX_BINDINGS:
        raise PriorityLimitExceeded(f"一个功能最多绑定 {MAX_BINDINGS} 个模型")
    if len(set(model_ids)) != len(model_ids):
        raise ValueError("同一个模型不能重复绑定到同一功能")
    if any(
        not isinstance(model_id, int) or isinstance(model_id, bool) or model_id <= 0
        for model_id in model_ids
    ):
        raise ValueError("model_ids 必须是正整数")
    return [(model_id, index + 1) for index, model_id in enumerate(model_ids)]


def effective_limit(configured: int | None, bound_count: int) -> int:
    """实际参与转移的候选数：夹到绑定数量以内，没配置时用默认 3。"""
    if bound_count <= 0:
        return 0
    limit = configured if configured is not None else DEFAULT_FAILOVER_LIMIT
    return max(1, min(limit, bound_count, MAX_FAILOVER_LIMIT))
