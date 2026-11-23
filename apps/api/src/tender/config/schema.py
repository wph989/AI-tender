"""运行与解析配置的定义、默认值和类型校验（docs/质量/08-动态配置中心.md）。

代码默认值补齐当前版本未覆盖的参数，`config_item` 保存页面与审计使用的元数据。
基线种子与代码清单由 `test_config_items_match_migration.py` 核对，防止默认值漂移。
参数值按登记类型校验，防止前端与执行端对同一个值作出不同解释。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

L1 = "L1"
L2 = "L2"

# 谁能写哪一层（docs/质量/08-动态配置中心.md）：viewer/reviewer 只读，operator 只写 L1，admin 全写。
WRITERS: dict[str, frozenset[str]] = {
    L1: frozenset({"operator", "admin"}),
    L2: frozenset({"admin"}),
}
READERS: frozenset[str] = frozenset({"viewer", "reviewer", "operator", "admin"})


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
    _item("analysis.max_evidence_blocks", L1, "int", 160, "每模块保留的原文证据块上限"),
    _item(
        "analysis.similarity_threshold", L1, "number", 0.6,
        "专题语义检索的最低余弦相似度（0到1）；关键词独立召回，按命中数参与融合排序",
    ),
    _item("analysis.max_search_results", L1, "int", 6, "每次专题检索通过阈值后返回的证据块上限"),
    _item(
        "analysis.rate_limit_backoff_seconds", L1, "int", 30,
        "上游429未给出恢复时间时的首次等待秒数，后续按倍数递增",
    ),
    _item(
        "analysis.rate_limit_max_wait_seconds", L1, "int", 600,
        "单个模块内为上游限流累计等待的上限秒数，超出后按可补跑失败收尾",
    ),
    _item("analysis.max_subagent_retries", L1, "int", 2, "子Agent本地执行故障的自动恢复上限"),
    _item(
        "analysis.timeout_seconds", L1, "int", 1800, "单个模块的总时限（非单次请求），恢复不重置"
    ),
    _item("analysis.context_tokens", L1, "int", 24000, "模块上下文预算，达到百分之八十时压缩"),
    _item("analysis.max_output_tokens", L1, "int", 8192, "模块单次模型输出上限"),
    # 并发与派发间隔实时读取；任务执行预算在创建时冻结。
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
    # L2 解析配置（docs/质量/08-动态配置中心.md）：改的是解析产物，必须绑定快照与门禁
    _item(
        "mineru.tier",
        L2,
        "string",
        "standard",
        "MinerU 生产固定档；advanced 建议仅由人工对单文档触发",
    ),
    _item("mineru.ocr_mode", L2, "string", "auto", "逐页自适应；扫描件占比高时可评估改 ocr"),

)

ITEMS_BY_KEY: dict[str, ConfigItem] = {entry.key: entry for entry in ITEMS}

def value_rules(key: str) -> dict[str, Any]:
    """让页面与写入校验共享约束；无 maximum 就表示没有人工最大值。"""
    entry = item(key)
    if key == "mineru.tier":
        return {"choices": ["flash", "basic", "standard", "advanced"]}
    if key == "mineru.ocr_mode":
        return {"choices": ["auto", "txt", "ocr"]}
    if key == "analysis.similarity_threshold":
        return {"minimum": 0, "maximum": 1}
    if entry.value_type == "int":
        nonnegative = {
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
    """从当前登记项补齐默认值，任务在创建时冻结执行参数。"""
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
    """逐项 diff（docs/质量/08-动态配置中心.md差异视图）：只列真正变化的 key。"""
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
    denied = [layer for layer in sorted(layers_of(keys)) if role not in WRITERS[layer]]
    if denied:
        return f"角色 {role} 无权修改 {'/'.join(denied)} 配置"
    return None


def gated_keys(keys: object) -> frozenset[str]:
    """这些 key 里需要走变更门禁的部分（L2）。"""
    return frozenset(str(key) for key in keys if item(str(key)).requires_gate)  # type: ignore[union-attr]
