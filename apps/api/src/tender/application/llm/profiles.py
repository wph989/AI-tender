"""受控协议清单；能力由管理员确认，参数只允许收窄，绝不由模型名推断。"""

from __future__ import annotations

import math
from decimal import Decimal
from urllib.parse import urlsplit

from tender.application.llm.registry import MAX_FAILOVER_LIMIT

ADAPTER_VERSION = "2026-11-13.1"


def number(
    label: str, minimum: float, maximum: float | None = None, *, integer: bool = False
) -> dict:
    return {
        "label": label,
        "type": "integer" if integer else "number",
        "min": minimum,
        **({"max": maximum} if maximum is not None else {}),
    }


def choice(label: str, *values: str) -> dict:
    return {"label": label, "type": "enum", "values": list(values)}


# 管理字段与协议参数一样由后端定义一次，API和页面读取同一份范围。
MODEL_FIELDS = {
    "timeout_seconds": number("响应间隔超时（秒）", 0) | {"exclusive_min": True},
    "total_timeout_seconds": number("单次请求总时限（秒，可留空）", 0)
    | {"exclusive_min": True, "nullable": True},
    "extra_retries": number("失败后额外重试次数", 0, integer=True),
}
FEATURE_FIELDS = {
    "failover_limit": number("故障转移级数", 1, MAX_FAILOVER_LIMIT, integer=True),
    "max_total_requests": number("总请求上限", 1, integer=True),
}


def field_bounds(rule: dict) -> dict:
    """把同一份数值范围用于请求模型；最大值缺省时不生成上限。"""
    return {
        name: rule[key]
        for name, key in (("gt" if rule.get("exclusive_min") else "ge", "min"), ("le", "max"))
        if key in rule
    }


# schema 同时用于服务端校验与表单渲染；不能允许任意 JSON 覆写 model/认证/请求路径。
LANGUAGE = {
    "temperature": number("温度", 0, 2),
    "max_tokens": number("最大输出 Token", 1, integer=True),
    "top_p": number("Top P", 0, 1),
    "stop": {"label": "停止词（每行一个，最多 4 个）", "type": "string_array", "max_items": 4},
}
OPENAI_LANGUAGE = LANGUAGE | {
    "seed": number("随机种子", 0, 2147483647, integer=True),
    "frequency_penalty": number("频率惩罚", -2, 2),
    "presence_penalty": number("重复惩罚", -2, 2),
    "reasoning_effort": choice("推理强度", "none", "minimal", "low", "medium", "high", "xhigh"),
    "token_limit_field": choice("输出预算字段", "max_tokens", "max_completion_tokens"),
}
IMAGE = {
    "size": choice(
        "图片尺寸",
        "auto",
        "256x256",
        "512x512",
        "1024x1024",
        "1536x1024",
        "1024x1536",
        "1792x1024",
        "1024x1792",
    ),
    "quality": choice(
        "图片质量", "auto", "low", "medium", "high", "xhigh", "max", "standard", "hd"
    ),
    "background": choice("背景", "auto", "transparent", "opaque"),
    "output_format": choice("图片格式", "png", "jpeg", "webp"),
    "output_compression": number("压缩质量", 0, 100, integer=True),
    "response_format": choice("响应格式（仅兼容此参数的模型）", "b64_json"),
    "style": choice("风格（仅兼容此参数的模型）", "vivid", "natural"),
}


def profile(
    protocol: str, kind: str, mode: str, required: list[str], optional: list[str], schema: dict
) -> dict:
    return {
        "protocol": protocol,
        "kind": kind,
        "api_mode": mode,
        "capabilities": required + optional,
        "required_capabilities": required,
        "default_capabilities": required + (["json_output"] if kind == "language" else []),
        "parameters": list(schema),
        "parameter_schema": schema,
        "adapter_version": ADAPTER_VERSION,
    }


PROFILES = [
    *[
        profile(
            p,
            "language",
            "chat_completions",
            ["text_input"],
            ["json_output", "image_input"],
            OPENAI_LANGUAGE,
        )
        for p in ("openai", "openai_compatible")
    ],
    *[
        profile(
            p,
            "language",
            "responses",
            ["text_input"],
            ["json_output", "image_input"],
            {
                "temperature": LANGUAGE["temperature"],
                "max_tokens": number("最大输出 Token", 16, integer=True),
                "top_p": LANGUAGE["top_p"],
                "reasoning_effort": OPENAI_LANGUAGE["reasoning_effort"],
            },
        )
        for p in ("openai", "openai_compatible")
    ],
    profile(
        "anthropic",
        "language",
        "messages",
        ["text_input"],
        ["json_output", "image_input"],
        LANGUAGE
        | {
            "temperature": number("温度", 0, 1),
            "top_k": number("Top K", 1, integer=True),
        },
    ),
    profile(
        "gemini",
        "language",
        "generate_content",
        ["text_input"],
        ["json_output", "image_input"],
        LANGUAGE
        | {
            "top_k": number("Top K", 1, integer=True),
            "seed": OPENAI_LANGUAGE["seed"],
        },
    ),
    *[
        profile(
            p,
            "embedding",
            "embeddings",
            ["text_input", "embedding"],
            [],
            {
                "dimensions": number("输出向量维度", 1, 65536, integer=True),
            },
        )
        for p in ("openai", "openai_compatible")
    ],
    profile(
        "gemini",
        "embedding",
        "embeddings",
        ["text_input", "embedding"],
        ["image_input"],
        {
            "dimensions": number("输出向量维度", 1, 65536, integer=True),
            "task_type": choice(
                "嵌入任务类型",
                "SEMANTIC_SIMILARITY",
                "RETRIEVAL_DOCUMENT",
                "RETRIEVAL_QUERY",
                "CLASSIFICATION",
                "CLUSTERING",
                "QUESTION_ANSWERING",
                "FACT_VERIFICATION",
                "CODE_RETRIEVAL_QUERY",
            ),
        },
    ),
    profile(
        "rerank_http",
        "rerank",
        "rerank",
        ["text_input", "rerank"],
        [],
        {
            "top_n": number("最多返回候选数", 1, integer=True),
        },
    ),
    *[
        profile(
            p, "image_generation", "image_generation", ["text_input", "image_generation"], [], IMAGE
        )
        for p in ("openai", "openai_compatible")
    ],
    profile(
        "gemini",
        "image_generation",
        "image_generation",
        ["text_input", "image_generation"],
        ["image_input"],
        {
            "aspect_ratio": choice(
                "宽高比",
                "1:1",
                "1:4",
                "4:1",
                "1:8",
                "8:1",
                "2:3",
                "3:2",
                "3:4",
                "4:3",
                "4:5",
                "5:4",
                "9:16",
                "16:9",
                "21:9",
            ),
            "image_size": choice("图片分辨率", "512", "1K", "2K", "4K"),
        },
    ),
]


def get_profile(protocol: str, model: dict) -> dict:
    found = next(
        (
            p
            for p in PROFILES
            if (p["protocol"], p["kind"], p["api_mode"])
            == (protocol, model["kind"], model["api_mode"])
        ),
        None,
    )
    if not found:
        raise ValueError("当前适配器尚不支持所选协议、种类或接口模式")
    return found


def supported_parameters(protocol: str, model: dict) -> list[str]:
    return (
        model.get("supported_parameters")
        if model.get("supported_parameters") is not None
        else get_profile(protocol, model)["parameters"]
    )


def validate_model(protocol: str, model: dict) -> dict:
    for field in ("timeout_seconds", "total_timeout_seconds"):
        value = model.get(field)
        if value is None:
            continue
        if (
            type(value) not in {int, float, Decimal}
            or not math.isfinite(float(value))
            or value <= 0
        ):
            raise ValueError("时限必须为有限正数")
    if model["kind"] != "language" and model.get("total_timeout_seconds") is not None:
        raise ValueError("单次请求总时限仅用于文本模型")
    selected = get_profile(protocol, model)
    capabilities = model["capabilities"]
    if (
        len(capabilities) != len(set(capabilities))
        or not set(selected["required_capabilities"]).issubset(capabilities)
        or not set(capabilities).issubset(selected["capabilities"])
    ):
        raise ValueError("当前适配器尚不支持所选能力组合")
    supported = supported_parameters(protocol, model)
    if len(supported) != len(set(supported)) or not set(supported).issubset(selected["parameters"]):
        raise ValueError("模型参数支持范围只能收窄适配器清单")
    params = model.get("parameters") or {}
    if not isinstance(params, dict) or set(params) & {"temperature", "max_tokens"}:
        raise ValueError("温度和最大输出 Token 使用独立字段配置")
    params = params | {
        k: model[k] for k in ("temperature", "max_tokens") if model.get(k) is not None
    }
    for key, value in params.items():
        if key not in supported:
            raise ValueError(f"该模型不支持参数 {key}")
        rule = selected["parameter_schema"][key]
        kind = rule["type"]
        valid = False
        if kind in {"number", "integer"}:
            # NUMERIC 列经 psycopg 返回 Decimal，按数值统一转 float 再比较范围。
            valid = (
                type(value) in ({int} if kind == "integer" else {int, float, Decimal})
                and (kind == "integer" or math.isfinite(float(value)))
                and value >= rule["min"]
                and ("max" not in rule or value <= rule["max"])
            )
        elif kind == "enum":
            valid = isinstance(value, str) and value in rule["values"]
        elif kind == "string_array":
            valid = (
                isinstance(value, list)
                and 1 <= len(value) <= rule["max_items"]
                and all(isinstance(v, str) and 0 < len(v) <= 200 for v in value)
            )
        if not valid:
            raise ValueError(f"{key} 的类型或取值超出适配器范围")
    if "output_compression" in params and params.get("output_format") not in {"jpeg", "webp"}:
        raise ValueError("压缩质量仅适用于 jpeg/webp 输出")
    return selected


def test_capabilities(model: dict) -> list[str]:
    if model["kind"] == "language":
        return ["text"] + (["vision"] if "image_input" in model["capabilities"] else [])
    if model["kind"] == "embedding":
        return ["embedding"] + (
            ["multimodal_embedding"] if "image_input" in model["capabilities"] else []
        )
    return [model["kind"]]


def required_kind(feature: str) -> str:
    return feature if feature in {"embedding", "rerank"} else "language"


def validate_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("请填写不含账号、密码、查询参数或片段的 HTTP(S) API 根地址")
    if parsed.hostname in {"169.254.169.254", "metadata.google.internal", "100.100.100.200"}:
        raise ValueError("不能使用云主机元数据地址作为模型端点")
    return value
