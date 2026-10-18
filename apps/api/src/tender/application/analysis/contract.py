"""分析运行时的稳定契约。

版本号被快照读取、业务用例和 Agent 同时使用；单独保留轻量模块，
避免只读快照也需要加载完整的 Agent 运行时。
"""

from __future__ import annotations

RUNTIME_VERSION = "deepagents-0.7.22-v5-records"
