"""只观察完整请求的供应商用量，业务计费继续沿用现有调用账。"""

import structlog

logger = structlog.get_logger(__name__)


def log_usage(model: str, mode: str, usage: dict, *, agent: bool = False) -> None:
    def tokens(value):
        return value if type(value) is int and value >= 0 else None

    if not isinstance(usage, dict):
        usage = {}
    details = (usage.get("completion_tokens_details") or usage.get("output_tokens_details")
               or usage.get("output_token_details") or {})
    reasoning = details.get("reasoning_tokens", details.get("reasoning")) if isinstance(
        details, dict,
    ) else None
    # 分项缺失保持未知，不能用零掩盖供应商未报告；不读取任何正文或推理文本。
    logger.debug(
        "model.usage", model=model, api_mode=mode, agent=agent,
        prompt_tokens=tokens(usage.get("prompt_tokens", usage.get("input_tokens",
                            usage.get("promptTokenCount")))),
        completion_tokens=tokens(usage.get("completion_tokens", usage.get("output_tokens",
                                usage.get("candidatesTokenCount")))),
        reasoning_tokens=tokens(usage.get("thoughtsTokenCount", reasoning)),
    )
