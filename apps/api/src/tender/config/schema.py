"""三层配置项定义与值解析（设计文档 08 第 2 节）。

默认值在代码里必须存在一份：读不到某个 key 时（迁移未跑、release 为空）业务要有确定答案。
`config_item` 表里的同名列是给页面与审计看的副本，两侧一致性由
`tests/contract/test_config_items_match_migration.py` 盯着——手工同步两份清单迟早漂移。

`value_type` 里的 `number` 是 DDL 注释中 `int|bool|string|json|secret` 的补充：
参数值按登记类型校验，防止前端与执行端对同一个值作出不同解释。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

L1 = "L1"
L2 = "L2"
LAYERS: tuple[str, ...] = (L1, L2)

# 谁能写哪一层（08 第 9 节）：viewer/reviewer 只读，operator 只写 L1，admin 全写。
WRITERS: dict[str, frozenset[str]] = {
    L1: frozenset({"operator", "admin"}),
    L2: frozenset({"admin"}),
}
READERS: frozenset[str] = frozenset({"viewer", "reviewer", "operator", "admin"})

_VALUE_TYPES = frozenset({"int", "number", "bool", "string", "json", "secret"})


@dataclass(frozen=True, slots=True)
class ConfigItem:
    key: str
    layer: str
    value_type: str
    default: Any
    description: str
    requires_gate: bool = False


def _item(
    key: str,
    layer: str,
    value_type: str,
    default: Any,
    description: str,
) -> ConfigItem:
    # L2 改的是"结果"而不是"速度"，全部走快照与门禁；L1 立即生效，不进回归。
    return ConfigItem(key, layer, value_type, default, description, requires_gate=layer != L1)


ITEMS: tuple[ConfigItem, ...] = (
    _item("analysis.max_inflight", L1, "int", 2, "同公司所有报告共享的 DeepAgents 子代理并发上限"),
    _item(
        "analysis.max_model_calls", L1, "int", 40,
        "每模块每次运行的成功模型请求上限，含摘要，协议失败不扣次数"
    ),
    _item("analysis.max_tool_calls", L1, "int", 48, "每模块每次运行的成功工具执行上限"),
    _item("analysis.max_review_repairs", L1, "int", 1,
          "完整审查后的自动修复及定向复核上限，0表示不自动修复"),
    _item("analysis.review_max_input_tokens", L1, "int", 12000,
          "审查单包完整输入的估算token上限，包含规则、正文、引文及依赖"),
    _item("analysis.max_evidence_blocks", L1, "int", 160, "每模块保留的原文证据块上限"),
    _item(
        "analysis.similarity_threshold", L1, "number", 0.6,
        "专题检索最低相关度（0到1），有向量时用余弦相似度，否则用检索词命中比例",
    ),
    _item("analysis.max_search_results", L1, "int", 6, "每次专题检索通过阈值后返回的证据块上限"),
    _item("analysis.max_tool_failures", L1, "int", 3, "工具连续失败上限，按工具及全局分别计数"),
    _item(
        "analysis.max_no_progress_rounds", L1, "int", 3, "无新增证据或有效成果的轮数，达到后收尾"
    ),
    _item(
        "analysis.max_finish_corrections", L1, "int", 2,
        "进入收尾后允许的连续无进展纠正轮数，耗尽时保留已核实成果并终止",
    ),
    _item(
        "analysis.rate_limit_backoff_seconds", L1, "int", 30,
        "上游429未给出恢复时间时的首次等待秒数，后续按倍数递增",
    ),
    _item(
        "analysis.rate_limit_max_wait_seconds", L1, "int", 600,
        "单个模块内为上游限流累计等待的上限秒数，超出后按可补跑失败收尾",
    ),
    _item("analysis.max_identical_tool_calls", L1, "int", 3, "同一工具与参数的累计调用上限"),
    _item("analysis.max_validation_failures", L1, "int", 3, "同一事实校验失败上限，含首次失败"),
    _item("analysis.max_subagent_retries", L1, "int", 2, "子Agent本地执行故障的自动恢复上限"),
    _item(
        "analysis.timeout_seconds", L1, "int", 1800, "单个模块的总时限（非单次请求），恢复不重置"
    ),
    _item("analysis.context_tokens", L1, "int", 24000, "模块上下文预算，达到百分之八十时压缩"),
    _item("analysis.max_output_tokens", L1, "int", 8192, "模块单次模型输出上限"),
    # L1 运行参数（08 第 2.1 节）：改了不影响结果，可以随便改、立即生效
    _item("convert.max_inflight", L1, "int", 4, "同时在途的 Gotenberg 转换请求数"),
    _item(
        "parse.max_inflight",
        L1,
        "int",
        2,
        "MinerU 侧同时处于 queued+running 的 job 数上限，建议不超过 GPU 数 x2",
    ),
    _item(
        "dispatch.interval_seconds",
        L1,
        "int",
        5,
        "调度器派发间隔；这就是配置改完多久生效的上限",
    ),
    _item("job.poll.initial_interval_ms", L1, "int", 2000, "MinerU 轮询初始间隔（毫秒）"),
    _item("job.poll.max_interval_ms", L1, "int", 30000, "MinerU 轮询最大间隔（毫秒）"),
    _item("job.poll.max_attempts", L1, "int", 180, "轮询次数上限，超出视为超时"),
    _item("job.timeout.convert_minutes", L1, "int", 10, "转换超时（分钟）"),
    _item("job.timeout.parse_minutes", L1, "int", 60, "解析超时（分钟）"),
    _item("job.retry.convert_500", L1, "int", 3, "Gotenberg 5xx 重试次数（400 不重试）"),
    _item("queue.priority.batch", L1, "string", "low", "批量任务的队列优先级"),
    # L2 解析配置（08 第 2.2 节）：改的是解析产物，必须绑定快照与门禁
    _item(
        "mineru.tier",
        L2,
        "string",
        "standard",
        "MinerU 生产固定档；advanced 建议仅由人工对单文档触发",
    ),
    _item("mineru.ocr_mode", L2, "string", "auto", "逐页自适应；扫描件占比高时可评估改 ocr"),
    _item(
        "mineru.output_formats",
        L2,
        "json",
        ["middle_json", "zip"],
        "需要的输出格式；ZIP 默认不下载，按需获取",
    ),
    _item(
        "mineru.page_range",
        L2,
        "string",
        "all",
        "解析页码范围，必须为 all，否则 title_leveling 失效",
    ),
    _item("render.crop_dpi", L2, "int", 300, "页面裁剪图 DPI"),
    _item("llm_aided.title_leveling", L2, "bool", True, "章节树构建依赖的标题分级"),
    _item("llm_aided.cross_page_table_cell_merge", L2, "bool", True, "跨页表格单元格合并"),
    _item("preprocess.deskew", L2, "bool", True, "扫描件纠偏"),
    _item("preprocess.denoise", L2, "bool", True, "扫描件去噪"),
    _item("preprocess.min_dpi", L2, "int", 300, "低于此值的扫描件先升采样"),

)

ITEMS_BY_KEY: dict[str, ConfigItem] = {entry.key: entry for entry in ITEMS}

# 未接入的能力不能伪装成生效开关；保留登记项以便查看历史版本和后续接入。
READONLY_REASONS: dict[str, str] = {
    "queue.priority.batch": "当前队列未接入动态批次优先级",
    "mineru.output_formats": "当前解析协议固定使用 middle_json 和 zip",
    "mineru.page_range": "当前章节与坐标契约要求解析全部页码 all",
    **dict.fromkeys(
        ("render.crop_dpi", "llm_aided.title_leveling", "llm_aided.cross_page_table_cell_merge",
         "preprocess.deskew", "preprocess.denoise", "preprocess.min_dpi"),
        "当前执行流程尚未接入该配置",
    ),
}


def value_rules(key: str) -> dict[str, Any]:
    """让页面与写入校验共享约束；无 maximum 就表示没有人工最大值。"""
    entry = item(key)
    if key in READONLY_REASONS:
        return {}
    if key == "mineru.tier":
        return {"choices": ["flash", "basic", "standard", "advanced"]}
    if key == "mineru.ocr_mode":
        return {"choices": ["auto", "txt", "ocr"]}
    if key == "analysis.similarity_threshold":
        return {"minimum": 0, "maximum": 1}
    if entry.value_type == "int":
        nonnegative = {
            "analysis.max_review_repairs",
            "analysis.max_subagent_retries", "convert.max_inflight", "parse.max_inflight",
            "job.retry.convert_500",
        }
        return {"minimum": 0 if key in nonnegative else 1}
    return {}


def field_bounds(key: str) -> dict[str, Any]:
    """补跑入口复用配置中心范围，避免同一个预算再出现另一套上下限。"""
    rules = value_rules(key)
    return {name: rules[source] for name, source in (
        ("ge", "minimum"), ("le", "maximum")
    ) if source in rules}


class UnknownConfigKey(ValueError):
    """写入未登记 key：配置中心只认登记过的项，防止页面/脚本塞进无审计的值。"""


def item(key: str) -> ConfigItem:
    entry = ITEMS_BY_KEY.get(key)
    if entry is None:
        raise UnknownConfigKey(f"未登记的配置项：{key}")
    return entry


def default_values() -> dict[str, Any]:
    return {entry.key: entry.default for entry in ITEMS}


def resolve_values(overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    """只解析仍登记的参数；历史快照原样留存，已下线参数不再进入执行配置。"""
    resolved = default_values()
    resolved.update({k: v for k, v in (overrides or {}).items() if k in ITEMS_BY_KEY})
    return resolved


def document_execution_snapshot(values: Mapping[str, Any] | None) -> dict[str, Any]:
    """冻结任务执行预算；派发并发和间隔仍由调度器读取实时配置。"""
    resolved = resolve_values(values)
    return {
        key: resolved[key]
        for key in (
            "job.poll.initial_interval_ms",
            "job.poll.max_interval_ms",
            "job.poll.max_attempts",
            "job.timeout.convert_minutes",
            "job.timeout.parse_minutes",
            "job.retry.convert_500",
        )
    }


def validate_value(key: str, value: Any) -> str | None:
    """返回错误说明；None 表示合法。页面与 API 共用同一份类型口径。"""
    entry = item(key)
    if entry.value_type == "bool":
        ok = isinstance(value, bool)
    elif entry.value_type == "int":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif entry.value_type == "number":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif entry.value_type in {"string", "secret"}:
        ok = isinstance(value, str)
    else:
        ok = True  # json 接受任意可序列化值，序列化失败由写入侧兜底
    if not ok:
        return f"{key} 期望 {entry.value_type}，收到 {type(value).__name__}"
    if entry.value_type == "number" and not isfinite(value):
        return f"{key} 必须是有限数值"
    rules = value_rules(key)
    if "minimum" in rules and value < rules["minimum"]:
        return f"{key} 不能小于 {rules['minimum']}"
    if "maximum" in rules and value > rules["maximum"]:
        return f"{key} 不能大于 {rules['maximum']}"
    if "choices" in rules and value not in rules["choices"]:
        return f"{key} 仅支持 {' / '.join(rules['choices'])}"
    return None


def validate_values(values: Mapping[str, Any]) -> str | None:
    """在合并完整草稿后检查字段关系，单字段补丁也不能绕过轮询间隔的顺序。"""
    if values["job.poll.max_interval_ms"] < values["job.poll.initial_interval_ms"]:
        return "轮询最大间隔不能小于初始间隔"
    return None


def parse_options(
    values: Mapping[str, Any], tier: str | None = None, ocr_mode: str | None = None
) -> dict[str, str]:
    """仅显式传入的任务选项覆盖配置中心，默认选择不再被界面的固定值遮住。"""
    resolved = resolve_values(values)
    options = {
        "tier": tier if tier is not None else resolved["mineru.tier"],
        "ocr_mode": ocr_mode if ocr_mode is not None else resolved["mineru.ocr_mode"],
    }
    for key, value in options.items():
        message = validate_value("mineru." + key, value)
        if message is not None:
            raise ValueError(message)
    return options


def diff_values(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """逐项 diff（08 第 6 节差异视图）：只列真正变化的 key。"""
    changed: dict[str, dict[str, Any]] = {}
    for key in sorted(set(old) | set(new)):
        before = old.get(key)
        after = new.get(key)
        if before != after:
            changed[key] = {"old": before, "new": after}
    return changed


def layers_of(keys: object) -> frozenset[str]:
    return frozenset(item(str(key)).layer for key in keys)  # type: ignore[union-attr]


def write_denial(role: str, keys: object) -> str | None:
    """角色能否写这些 key：返回拒绝说明；None 表示允许。"""
    if role not in READERS:
        return f"未知角色：{role}"
    readonly = [str(key) for key in keys if str(key) in READONLY_REASONS]
    if readonly:
        return f"配置项暂为只读：{'、'.join(readonly)}"
    denied = [layer for layer in sorted(layers_of(keys)) if role not in WRITERS[layer]]
    if denied:
        return f"角色 {role} 无权修改 {'/'.join(denied)} 配置"
    return None


def gated_keys(keys: object) -> frozenset[str]:
    """这些 key 里需要走变更门禁的部分（L2）。"""
    return frozenset(str(key) for key in keys if item(str(key)).requires_gate)  # type: ignore[union-attr]
