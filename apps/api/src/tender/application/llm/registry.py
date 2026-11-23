"""LLM 管理模块的纯规则：功能清单与优先级整表展开（docs/设计/12-LLM管理与模型路由.md）。

放在 application 而不是 api 里：这些规则同时约束接口写入与 worker 读取，
只有一份实现，页面提交与任务执行才不会对"合法优先级"产生两种理解。
"""

from __future__ import annotations

from collections.abc import Sequence

from tender.domain.shared.errors import PriorityLimitExceeded

MAX_BINDINGS = 10
MAX_FAILOVER_LIMIT = 10
DEFAULT_FAILOVER_LIMIT = 3

# 功能清单是代码内置枚举：新增功能必须同时有消费者，页面不能自己造。
FEATURES: tuple[tuple[str, str], ...] = (
    ("analysis", "招标专题解析"),
    ("knowledge_ask", "知识问答"),
    ("embedding", "向量索引与检索"),
    ("rerank", "检索重排"),
)

# 名称与用途跟随代码消费者更新，不能继续显示数据库种子中的旧流程说明。
FEATURE_DESCRIPTIONS = {
    "analysis": (
        "项目的13个招标专题解析、证据校验和上下文压缩共用此绑定；"
        "取消后补跑、指定专题重新解析也使用此绑定。"
    ),
    "knowledge_ask": "项目问答和知识库问答：检索授权资料、生成回答并核对引用。",
    "embedding": (
        "知识库索引构建及专题解析、问答中的向量检索；"
        "仅绑定一个向量模型，未配置时使用基础检索。"
    ),
    "rerank": "对专题解析和问答的检索候选重新排序；仅绑定一个重排模型，未配置时保留混合检索顺序。",
}


def binding_rows(model_ids: Sequence[int]) -> list[tuple[int, int]]:
    """把整表提交的有序模型 id 展开成 (model_id, priority) 行。

    优先级由数组位置推导，而不是接收客户端传来的数字：数字会带来空洞、同级、越界
    三类非法状态，而"有序数组"天然只有一种解释（见docs/设计/12-LLM管理与模型路由.md）。
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
