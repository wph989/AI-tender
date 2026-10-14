"""确定性指纹：同一组结构化输入永远给出同一个短标识。

放 ``domain`` 而不是 ``application``：用例层与 ``adapters/pg`` 都要算嵌入空间签名、
快照清单指纹等，而这两层必须互不引用（``pyproject.toml`` 的 import-linter 契约）。
它只依赖标准库，是纯函数，正好落在纯领域层。
"""

from __future__ import annotations

import hashlib
import json


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
