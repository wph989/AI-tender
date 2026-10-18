"""模型运行时的数据访问契约；候选转换与凭证解释由调用方完成。"""

from collections.abc import Mapping
from typing import Any, Protocol


class ModelRuntimeRepository(Protocol):
    def candidates(self, feature_key: str) -> list[Mapping[str, Any]]: ...

    def policy(self, feature_key: str) -> Mapping[str, Any] | None: ...

    def record_call(self, values: Mapping[str, Any]) -> None: ...

    def maintain_tests(self) -> None: ...
