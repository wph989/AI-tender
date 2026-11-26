"""模块运行状态机端口：领取配额、续租、写回状态与成果。

为什么单独一个端口：一次模块执行的生命周期横跨「数据库会话锁存活期」，锁连接、
fencing、未知请求标记这些都属于持久化细节。用例层只表达「现在想领取一个执行槽」
「把这一版状态存下来」「按这个终态收尾」，不铺开 ``UPDATE ... WHERE owner=...``。

实现见 ``adapters/pg/repositories/analysis/runtime.py``；``None`` 一律表示「调用方不需要
这次写回」，例如状态未变化时不必发布成果。
"""

from __future__ import annotations

from typing import Any, Protocol

from tender.ports.llm.chat import ModelInvocationStore


class AgentRunStore(ModelInvocationStore, Protocol):
    """一次 ``agent_module_run`` 的状态机入口；由 ``KnowledgeStore.agent_run_store`` 取得。"""

    run: dict[str, Any]
    """当前运行账。``claim`` 成功会就地替换为最新一行（含 owner、期限与计数）。"""

    def claim(self) -> bool:
        """尝试领取本次运行的配额槽；拿到锁并成为本报告最靠前的待执行运行才返回 ``True``。

        返回 ``False`` 表示此刻不该执行（配额占满、别的模块排在前面或抢锁失败），
        调用方应稍后重试，而不是当作失败。
        """
        ...

    def guard(self) -> None:
        """复核运行仍然合法：所有权、租约、配额锁与会话权限都在，且未超总时限。"""
        ...

    def heartbeat(self) -> None:
        """保活：先证锁连接仍然有效，再续租并复核运行合法性。"""
        ...

    def guard_settlement(self) -> None:
        """到期后仅允许核实成果收尾，仍须验证所有权、租约与配额锁。"""
        ...

    def reserve(self, kind: str, call_key: str | None = None) -> str:
        """预占一次模型或工具调用；预算耗尽时抛 ``ValueError``。``kind`` 取 model/tool。"""
        ...

    def record_call(self, record: dict[str, Any]) -> None:
        """累计一次模型调用的 token 用量并记一条审计事件（``record`` 已序列化为字典）。"""
        ...

    def save(self, state: dict[str, Any]) -> None:
        """把这一版Agent工作区状态写回检查点。"""
        ...

    def finish(
        self,
        status: str,
        error: str | None = None,
        *,
        publish: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
    ) -> None:
        """按终态收口本次运行；``publish`` 给出 ``completed`` 时要发布的成果。"""
        ...

    def abandon(self, status: str, error: str | None = None) -> None:
        """异常收尾：已领取则按所有权收口，尚未领取也要把排队行置为终态。"""
        ...

    def event(self, kind: str, detail: dict[str, Any] | None = None) -> None:
        """写一条运行审计事件（独立短事务）。"""
        ...

    def release(self) -> None:
        """释放配额锁与会话锁连接；无论成功失败都必须执行。"""
        ...
