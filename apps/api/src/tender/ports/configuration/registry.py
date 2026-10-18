"""用例使用的配置值与读取端口；缓存和数据库回源由 config.registry 实现。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ActiveConfig:
    release_id: int
    version_no: int
    values: Mapping[str, Any]
    resolved: Mapping[str, Any]

    def cache_payload(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id,
            "version_no": self.version_no,
            "values": dict(self.values),
        }


class ConfigReader(Protocol):
    def active(self, company_id: int | None = None) -> ActiveConfig | None: ...

    def resolved(self, company_id: int | None = None) -> Mapping[str, Any]: ...

    def refresh(self, company_id: int, active: ActiveConfig) -> None: ...
