"""供应商共享冷却状态；模型路由无需了解数据库的时间表达式。"""

from typing import Protocol


class ProviderIdentity(Protocol):
    @property
    def provider_id(self) -> int | None: ...


class ProviderCooldown(Protocol):
    def remaining(self, candidate: ProviderIdentity) -> float: ...

    def defer(self, candidate: ProviderIdentity, seconds: float) -> None: ...
