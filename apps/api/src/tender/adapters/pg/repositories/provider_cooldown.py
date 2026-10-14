"""共享供应商限流截止时间；只保存运行状态，不改用户模型绑定或凭证。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, select, update

from tender.adapters.pg.models import LlmProvider


class ProviderCooldown:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def remaining(self, candidate: Any) -> float:
        if candidate.provider_id is None:
            return 0
        with self.engine.connect() as conn:
            value = conn.execute(
                select(
                    func.greatest(
                        0,
                        func.extract(
                            "epoch",
                            LlmProvider.rate_limited_until - func.clock_timestamp(),
                        ),
                    )
                ).where(LlmProvider.id == candidate.provider_id)
            ).scalar_one_or_none()
        return float(value or 0)

    def defer(self, candidate: Any, seconds: float) -> None:
        if candidate.provider_id is None:
            return
        with self.engine.begin() as conn:
            # 并发429只能延后截止时间，较短的Retry-After不能覆盖另一个请求的长冷却。
            # make_interval 只按位置传参：秒数是第 7 个，SQLAlchemy 的 func 不支持 `secs=>`。
            window = func.make_interval(0, 0, 0, 0, 0, 0, seconds)
            conn.execute(
                update(LlmProvider)
                .where(LlmProvider.id == candidate.provider_id)
                .values(
                    rate_limited_until=func.greatest(
                        LlmProvider.rate_limited_until,
                        func.clock_timestamp() + window,
                    )
                )
            )
