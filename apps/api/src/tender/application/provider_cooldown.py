"""共享供应商限流截止时间；只保存运行状态，不改用户模型绑定或凭证。"""

from sqlalchemy import Engine, text


class ProviderCooldown:
    def __init__(self, engine: Engine):
        self.engine = engine

    def remaining(self, candidate) -> float:
        if candidate.provider_id is None:
            return 0
        with self.engine.connect() as conn:
            value = conn.execute(
                text("""SELECT GREATEST(0,EXTRACT(EPOCH FROM rate_limited_until-clock_timestamp()))
                FROM llm_provider WHERE id=:id"""),
                {"id": candidate.provider_id},
            ).scalar_one_or_none()
        return float(value or 0)

    def defer(self, candidate, seconds: float) -> None:
        if candidate.provider_id is None:
            return
        with self.engine.begin() as conn:
            # 并发429只能延后截止时间，较短的Retry-After不能覆盖另一个请求的长冷却。
            conn.execute(
                text("""UPDATE llm_provider SET rate_limited_until=GREATEST(
                rate_limited_until,clock_timestamp()+make_interval(secs=>:seconds))
                WHERE id=:id"""),
                {"id": candidate.provider_id, "seconds": seconds},
            )
